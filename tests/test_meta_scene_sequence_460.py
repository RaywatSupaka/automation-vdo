import base64
import io
import json
import logging
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from core.atomic_json import AtomicJsonFile
from core.local_bridge import LocalBridge
from core.meta_scene_sequence import (adopt, assert_all_ready, enabled, gate,
    needs_scene_work, scene_input, store_for)
from core.meta_video import MetaVideoManager
from core.story_manager import StoryManager

ROOT = Path(__file__).resolve().parents[1]


class MetaSceneSequenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stories = StoryManager(self.temp.name)
        job = self.stories.create(topic='A garden', scene_count=6,
            video_generation_mode='meta_ai', meta_scene_sequence=True)
        self.job_id = job['id']
        job.update(scene_count=2, audio_choices={'mode': 'none'}, status='failed')
        self.analysis = {'job_id': self.job_id, 'scene_prompts': ['A red garden', 'A blue garden'],
            'scene_narrations': ['A person enters', 'A person leaves'],
            'flow_shot_prompts': ['Wind moves leaves', 'Water flows'],
            'narration_script': 'A person enters. A person leaves.', 'scene_durations': [10, 10]}
        job.update(self.analysis)
        self.stories._save(job)
        self.folder = self.stories.root / self.job_id
        AtomicJsonFile(self.folder / 'prompts/ai_analysis_checkpoint.json').write(self.analysis)
        self.bridge = self.new_bridge()

    def new_bridge(self):
        from core.product_manager import ProductManager
        bridge = LocalBridge('127.0.0.1', 0, ProductManager(self.temp.name), logging.getLogger('sequence-test'), stories=self.stories)
        bridge.meta_video.validator = lambda _: {'width': 720, 'height': 1280, 'duration': 10}
        bridge._extension_runs[('ai', self.job_id, 0)] = {'run_id': 'RUN-AI'}
        return bridge

    def image(self, index):
        output = io.BytesIO()
        Image.new('RGB', (144, 256), ('red' if index == 1 else 'blue')).save(output, format='PNG')
        self.stories.save_partial_image(self.job_id, index, base64.b64encode(output.getvalue()).decode())

    def call(self, index=1, action='ready', run='RUN-AI'):
        with self.bridge._extension_lock:
            return gate(self.bridge, {'job_id': self.job_id, 'index': index,
                                     'action': action, 'run_id': run})

    def video(self, index):
        manager = self.bridge.meta_video
        row = manager.begin(self.job_id, index)
        body = {key: row[key] for key in ('job_id', 'index', 'request_id', 'context_id')}
        for stage in manager.STAGES[1:]:
            if stage == 'stored':
                break
            if stage == 'submitted': body['conversation_url'] = f'https://www.meta.ai/prompt/test-{index}'
            if stage == 'downloading': body['download_id'] = index
            manager.event({**body, 'stage': stage})
        path = Path(self.temp.name) / f'result-{index}.mp4'
        path.write_bytes(bytes([index]) * 2048)
        return manager.event({**body, 'stage': 'stored', 'filename': str(path)})

    def test_full_serial_save_barrier_and_final(self):
        self.image(1)
        self.assertNotIn('generated_images', self.stories.get(self.job_id))
        self.assertEqual(self.call()['phase'], 'video_pending')
        self.assertEqual(len(self.bridge._extension_commands), 1)
        for _ in range(3): self.assertEqual(self.call(action='status')['phase'], 'video_pending')
        self.assertEqual(len(self.bridge._extension_commands), 1)
        self.image(2)  # Existing local media alone must not bypass the barrier.
        with self.assertRaisesRegex(ValueError, 'ก่อนหน้า'): self.call(2)
        with self.assertRaises(ValueError): assert_all_ready(self.stories, self.stories.get(self.job_id))
        self.video(1)
        self.assertEqual(self.call(action='status')['phase'], 'scene_ready')
        self.call(2); self.video(2)
        self.assertEqual(self.call(2, 'status')['phase'], 'scene_ready')
        assert_all_ready(self.stories, self.stories.get(self.job_id))
        self.assertFalse(needs_scene_work(self.stories, self.stories.get(self.job_id)))
        self.call(1); self.call(2)
        self.assertEqual(len(self.bridge._extension_commands), 2)

    def test_lost_dispatch_ack_reuses_same_id(self):
        self.image(1)
        real = self.bridge.queue_extension_command
        def lost(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError('lost acknowledgement')
        with patch.object(self.bridge, 'queue_extension_command', side_effect=lost):
            with self.assertRaises(OSError): self.call()
        original = dict(self.bridge._extension_commands[0])
        self.call()
        self.assertEqual(self.bridge._extension_commands, [original])
        self.bridge = self.new_bridge()  # Process memory gone, durable intent retained.
        self.call()
        self.assertEqual(self.bridge._extension_commands[0]['id'], original['id'])
        self.assertEqual(self.bridge._extension_commands[0]['run_id'], original['run_id'])

    def test_status_never_dispatches_or_initializes(self):
        self.image(1)
        with self.assertRaises(ValueError): self.bridge.meta_video.begin(self.job_id, 1)
        with self.assertRaises(ValueError): self.call(action='status')
        self.assertFalse(self.bridge._extension_commands)
        self.assertFalse(self.bridge.meta_video.get(self.job_id, 1))

    def test_stale_run_and_reconnect(self):
        self.image(1); self.call()
        self.bridge._extension_runs[('ai', self.job_id, 0)] = {'run_id': 'RUN-NEW'}
        with self.assertRaises(ValueError): self.call(action='status')
        self.call(run='RUN-NEW')
        self.assertEqual(len(self.bridge._extension_commands), 1)
        self.assertEqual(self.call(action='status', run='RUN-NEW')['phase'], 'video_pending')

    def test_stored_receipt_before_gate_ack_recovers_without_dispatch(self):
        self.image(1); self.call(); self.video(1)
        self.bridge = self.new_bridge()
        self.assertEqual(self.call()['phase'], 'scene_ready')
        self.assertFalse(self.bridge._extension_commands)

    def test_script_settings_and_image_change_rejected(self):
        self.image(1); self.call()
        job = self.stories.get(self.job_id)
        job['audio_choices'] = {'mode': 'flow_original'}
        self.stories._save(job)
        with self.assertRaises(ValueError): self.call(action='status')
        job['audio_choices'] = {'mode': 'none'}; self.stories._save(job)
        image = self.folder / 'generated/scene_01.png'; image.write_bytes(b'changed')
        with self.assertRaises(ValueError): self.call(action='status')

    def test_changed_saved_video_blocks_final_and_advance(self):
        self.image(1); self.call(); row = self.video(1); self.call(action='status')
        (self.folder / row['path']).write_bytes(b'wrong clip')
        self.image(2)
        with self.assertRaises(ValueError): self.call(2)
        with self.assertRaises(ValueError): assert_all_ready(self.stories, self.stories.get(self.job_id))

    def test_missing_middle_image_not_renumbered(self):
        self.image(2)
        with self.assertRaises(ValueError): scene_input(self.stories, self.stories.get(self.job_id), 1)
        self.assertTrue(scene_input(self.stories, self.stories.get(self.job_id), 2)[1].endswith('scene_02.png'))

    def test_attention_does_not_implicitly_restart_request(self):
        self.image(1); self.call()
        manager = self.bridge.meta_video
        row = manager.get(self.job_id, 1)
        manager.event({**row, 'stage': 'needs_attention', 'message': 'login required'})
        count = len(self.bridge._extension_commands)
        self.assertEqual(self.call()['phase'], 'error')
        self.assertEqual(manager.get(self.job_id, 1)['request_id'], row['request_id'])
        self.assertEqual(len(self.bridge._extension_commands), count)

    def test_cancel_is_not_resume_authority(self):
        self.image(1); self.call()
        job = self.stories.get(self.job_id); job['cancel_requested'] = True; self.stories._save(job)
        with self.assertRaises(ValueError): self.call(action='status')

    def test_redesigned_image_successor_is_accepted_without_changing_next_reference(self):
        self.image(1); self.call()
        manager = self.bridge.meta_video
        original_image = (self.folder / 'generated/scene_01.png').read_bytes()
        row = manager.begin(self.job_id, 1)
        body = {key: row[key] for key in ('job_id', 'index', 'request_id', 'context_id')}
        for stage in manager.STAGES[1:]:
            if stage == 'submitted': body['conversation_url'] = 'https://www.meta.ai/prompt/repair-test'
            manager.event({**body, 'stage': stage})
            if stage == 'generating': break
        repaired = manager.event({**body, 'stage': 'redesign_prepare', 'retry_evidence': {
            'matched_request': True, 'answer_complete': True, 'answer_truncated': False,
            'stop': False, 'busy': False, 'video_count': 0, 'samples': 2, 'stable_ms': 6000,
            'answer_text': 'ขออภัย ดูเหมือนว่าทางฝั่งของฉันจะเกิดปัญหาบางอย่าง โปรดลองอีกครั้ง'}})
        body['redesign_id'] = repaired['redesign']['id']
        manager.redesign_event({**body, 'action': 'claim'})
        out = io.BytesIO(); Image.new('RGB', (360, 640), 'green').save(out, format='PNG')
        manager.redesign_event({**body, 'action': 'save_image', 'image': 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()})
        successor = manager.redesign_event({**body, 'action': 'save_prompt',
            'proposal': {'needs_review': False, 'video_prompt': 'Wind gently moves the new leaves, slow camera pan.'}})
        self.assertNotEqual(successor['request_id'], row['request_id'])
        self.video(1)
        self.assertEqual(self.call(action='status')['phase'], 'scene_ready')
        self.assertEqual((self.folder / 'generated/scene_01.png').read_bytes(), original_image)
        self.image(2); self.call(2)

    def test_long_landscape_uses_same_partial_scene_contract(self):
        job = self.stories.get(self.job_id)
        job['long_video'] = {'version': 2, 'scene_count': 2, 'duration_seconds': 20}
        self.stories._save(job)
        out = io.BytesIO(); Image.new('RGB', (256, 144), 'red').save(out, format='PNG')
        self.stories.save_partial_image(self.job_id, 1, base64.b64encode(out.getvalue()).decode())
        self.call()
        package = self.bridge.meta_video.package(self.job_id, 1)
        self.assertEqual(package['aspect_ratio'], '16:9')
        self.assertNotIn('generated_images', self.stories.get(self.job_id))
        self.bridge.meta_video.validator = lambda _: {'width': 1280, 'height': 720, 'duration': 10}
        self.video(1)
        self.assertEqual(self.call(action='status')['phase'], 'scene_ready')

    def test_explicit_adoption_only_and_pending_guard(self):
        self.image(1)
        job = self.stories.get(self.job_id); job.pop('meta_scene_sequence_version'); self.stories._save(job)
        self.assertFalse(enabled(self.stories.get(self.job_id)))
        with patch('core.ai_web_resume.ai_web_resume_target', return_value={'index': 2}):
            with self.assertRaises(ValueError): adopt(self.stories, self.job_id)
        self.assertFalse(enabled(self.stories.get(self.job_id)))
        with patch('core.ai_web_resume.ai_web_resume_target', return_value=None):
            self.assertTrue(enabled(adopt(self.stories, self.job_id)))
        self.assertFalse(self.bridge._extension_commands)

    def test_other_routes_not_opted_in(self):
        for provider, mode in [('gemini', 'meta_ai'), ('chatgpt', 'google_flow'), ('chatgpt', 'image_motion')]:
            job = self.stories.create(topic='control', image_ai_provider=provider,
                video_generation_mode=mode, meta_scene_sequence=True)
            self.assertFalse(enabled(job))
        job = self.stories.create(topic='legacy', video_generation_mode='meta_ai')
        self.assertFalse(enabled(job))

    def test_http_gate_owner_auth_and_nested_broker_lock(self):
        from tests.extension_identity_fixture import pair_fixture
        self.image(1)
        self.bridge.start(); self.addCleanup(self.bridge.stop)
        headers = {'Origin': pair_fixture(self.bridge), 'X-SmartFlow-Token': self.bridge._extension_token,
                   'Content-Type': 'application/json'}
        url = f'http://127.0.0.1:{self.bridge.server.server_address[1]}/api/stories/scene-gate'
        body = {'job_id': self.job_id, 'index': 1, 'run_id': 'RUN-AI', 'action': 'ready'}
        with urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers), timeout=5) as response:
            self.assertEqual(json.load(response)['phase'], 'video_pending')
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(urllib.request.Request(url, data=json.dumps({**body, 'run_id': 'RUN-STALE'}).encode(), headers=headers), timeout=5)

    def test_actual_extension_functions(self):
        for name in ('story_binding_transport_460.cjs', 'meta_scene_sequence_460.cjs', 'meta_scene_sequence_ui_460.cjs'):
            result = subprocess.run(['node', str(ROOT / 'tests' / name)], capture_output=True,
                                    text=True, encoding='utf-8', timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
