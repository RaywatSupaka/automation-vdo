import copy
import json
import logging
import subprocess
import tempfile
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch

from core.creation_queue import CreationQueue
from core.local_bridge import LocalBridge
from core.meta_video import MetaVideoManager
from core.story_manager import StoryManager

ROOT = Path(__file__).resolve().parents[1]


class MetaVideoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stories = StoryManager(self.temp.name)
        # Saved pre-v5 fixture: its narration-as-action bytes remain receipt-owned.
        # New role-separated packages have their own tests in test_meta_roles_455.
        job = self.stories.create(topic='cup steam', scene_count=6, image_ai_provider='gemini', video_generation_mode='meta_ai', meta_prompt_version=4)
        self.job_id = job['id']
        folder = self.stories._folder(self.job_id)
        image = folder / 'generated' / 'scene_01.png'
        image.write_bytes(b'image-fixture')
        job.update(scene_count=1, generated_images=[str(image.relative_to(folder))],
                   scene_prompts=['A ceramic mug on the table'], scene_narrations=['Steam rises'],
                   audio_choices={'mode': 'none'})
        self.stories._save(job)
        self.manager = MetaVideoManager(self.stories, lambda _: {'width': 720, 'height': 1280, 'duration': 10})

    def advance(self, end='downloading'):
        receipt = self.manager.begin(self.job_id, 1)
        body = dict(job_id=self.job_id, index=1, request_id=receipt['request_id'], context_id=receipt['context_id'])
        for stage in self.manager.STAGES[1:]:
            if stage == 'stored': break
            if stage == 'submitted': body['conversation_url'] = 'https://www.meta.ai/prompt/test-123'
            if stage == 'downloading': body['download_id'] = 17
            self.manager.event({**body, 'stage': stage})
            if stage == end: break
        return body

    def test_mode_preserves_selected_image_provider(self):
        job = self.stories.get(self.job_id)
        self.assertEqual(job['image_ai_provider'], 'gemini')
        self.assertEqual(job['video_source_type'], 'meta_ai_pending')
        self.assertEqual(job['scene_pipeline_version'], 0)
        with self.assertRaises(ValueError): self.stories.flow_package(self.job_id, 1)

    def test_prepared_wait_message_preserves_request_and_allows_next_stage(self):
        original = self.manager.begin(self.job_id, 1)
        body = dict(job_id=self.job_id, index=1, request_id=original['request_id'], context_id=original['context_id'])
        receipt = self.manager.event({**body, 'stage':'prepared', 'message':'รอช่องข้อความ Meta ที่ระบุได้ช่องเดียว'})
        self.assertEqual(receipt['request_id'], original['request_id'])
        self.assertEqual(receipt['stage'], 'prepared')
        self.assertIn('รอช่องข้อความ', receipt['message'])
        with self.assertRaises(ValueError):
            self.manager.event({**body, 'request_id':'wrong', 'stage':'prepared', 'message':'wrong wait'})
        self.assertEqual(self.manager.get(self.job_id, 1), receipt)
        receipt = self.manager.event({**body, 'stage':'uploading', 'message':'แนบภาพฉากเดิมให้ Meta'})
        self.assertEqual(receipt['stage'], 'uploading')
        self.assertEqual(receipt['request_id'], original['request_id'])

    def test_repeat_begin_is_same_request(self):
        first = self.manager.begin(self.job_id, 1)
        self.assertEqual(first, self.manager.begin(self.job_id, 1))
        self.assertIn('vertical 9:16', first['prompt'])
        self.assertIn('Steam rises', first['prompt'])

    def test_context_change_does_not_send_again(self):
        self.manager.begin(self.job_id, 1)
        job = self.stories.get(self.job_id)
        job['scene_narrations'] = ['Different action']
        self.stories._save(job)
        with self.assertRaises(ValueError): self.manager.begin(self.job_id, 1)

    def test_wrong_receipt_and_skip_transition_rejected(self):
        receipt = self.manager.begin(self.job_id, 1)
        for changes in ({'request_id': 'wrong'}, {'context_id': 'wrong'}, {'stage': 'stored'}):
            with self.assertRaises(ValueError):
                self.manager.event({**receipt, 'stage': 'uploading', **changes})

    def test_signed_or_other_conversation_rejected(self):
        body = self.advance('submitted')
        for url in ('https://example.com/prompt/test', 'https://www.meta.ai/prompt/other', 'https://www.meta.ai/prompt/test-123?secret=x'):
            with self.assertRaises(ValueError):
                self.manager.event({**body, 'stage': 'generating', 'conversation_url': url})

    def test_cancel_blocks_result_and_new_request(self):
        body = self.advance()
        job = self.stories.get(self.job_id); job['cancel_requested'] = True; self.stories._save(job)
        with self.assertRaises(ValueError): self.manager.begin(self.job_id, 1)
        with self.assertRaises(ValueError): self.manager.event({**body, 'stage': 'stored'})

    def test_ack_after_valid_file_then_idempotent_replay(self):
        body = self.advance()
        source = Path(self.temp.name) / 'result.mp4'; source.write_bytes(b'video-data' * 200)
        event = {**body, 'stage': 'stored', 'filename': str(source)}
        with self.assertRaises(ValueError): self.manager.event({**event, 'download_id': 18})
        result = self.manager.event(event)
        self.assertEqual(result['stage'], 'stored')
        self.assertEqual(result, self.manager.event(event))
        self.assertEqual(self.manager.clips(self.job_id)[0].read_bytes(), source.read_bytes())
        self.assertEqual(self.stories.get(self.job_id)['flow_clips'], {})
        self.assertEqual(self.stories.get(self.job_id)['meta_clip_count'], 1)
        self.manager.clips(self.job_id)[0].write_bytes(b'corrupt')
        with self.assertRaises(ValueError): self.manager.clips(self.job_id)

    def test_partial_and_wrong_ratio_never_mark_complete(self):
        body = self.advance()
        source = Path(self.temp.name) / 'result.partial'; source.write_bytes(b'video' * 400)
        with self.assertRaises(ValueError): self.manager.event({**body, 'stage': 'stored', 'filename': str(source)})
        source = source.rename(source.with_suffix('.mp4'))
        self.manager.validator = lambda _: {'width': 1920, 'height': 1080, 'duration': 10}
        with self.assertRaises(ValueError): self.manager.event({**body, 'stage': 'stored', 'filename': str(source)})
        self.assertEqual(self.manager.get(self.job_id, 1)['stage'], 'downloading')

    def test_resume_does_not_reset_send_intent(self):
        body = self.advance('send_intent')
        self.manager.event({**body, 'stage': 'needs_attention', 'message': 'Inspect old request'})
        self.assertEqual(self.manager.begin(self.job_id, 1)['stage'], 'needs_attention')
        self.assertEqual(self.manager.begin(self.job_id, 1, resume=True)['stage'], 'send_intent')

    def test_bridge_meta_command_is_not_flow_and_old_meta_remains_retired(self):
        bridge = LocalBridge('127.0.0.1', 0, object(), logging.getLogger('meta-test'), stories=self.stories)
        command = bridge.queue_extension_command('open_meta_video', self.job_id, 1)
        self.assertEqual(command['action'], 'open_meta_video')
        self.assertEqual(command['provider'], 'meta_ai')
        self.assertEqual(command['shot_index'], 1)
        self.assertEqual(bridge._extension_run_key(command['action'], self.job_id, 1)[0], 'meta_ai')
        with self.assertRaises(ValueError): bridge.queue_extension_command('open_meta', self.job_id, 1)

    def test_queue_freezes_meta_provider_and_native_audio(self):
        queue = CreationQueue(self.temp.name)
        data = queue.enqueue('story', ['A cup'], scene_count=6, video_generation_mode='meta_ai',
                             provider='gemini', settings={'audio_choices': {'mode': 'none'}})
        self.assertEqual(data['items'][0]['video_generation_mode'], 'meta_ai')
        self.assertEqual(data['items'][0]['provider'], 'gemini')
        queue.enqueue('story', ['A cup'], video_generation_mode='meta_ai',
                      settings={'audio_choices': {'mode': 'flow_original', 'video_audio_volume': 73}})
        saved = CreationQueue(self.temp.name).snapshot()['items'][-1]
        self.assertEqual(saved['video_generation_mode'], 'meta_ai')
        self.assertEqual(saved['settings']['audio_choices']['mode'], 'flow_original')
        self.assertEqual(saved['settings']['audio_choices']['video_audio_volume'], 73)

    def test_native_prompt_keeps_thai_dialogue_and_legacy_silent_context(self):
        old = self.manager.package(self.job_id, 1)
        job = self.stories.get(self.job_id)
        job['audio_choices'] = {'mode': 'api'}
        self.stories._save(job)
        self.assertEqual(old['context_id'], self.manager.package(self.job_id, 1)['context_id'])
        job.update(audio_choices={'mode': 'flow_original'}, product_presentation_version=1,
                   scene_narrations=['ลองนั่งเก้าอี้ตัวนี้กันค่ะ'])
        self.stories._save(job)
        new = self.manager.package(self.job_id, 1)
        self.assertNotEqual(old['context_id'], new['context_id'])
        self.assertIn('All spoken dialogue must be in Thai only', new['prompt'])
        self.assertIn('ลองนั่งเก้าอี้ตัวนี้กันค่ะ', new['prompt'])
        self.assertIn('on-camera dialogue', new['prompt'])
        self.assertNotIn('No music, speech or ambient audio', new['prompt'])
        first = self.manager.begin(self.job_id, 1)
        self.assertEqual(first, self.manager.begin(self.job_id, 1))

    def test_meta_native_real_audio_receipt_and_composition(self):
        from core.video_composer import MultiFlowComposer
        from core.flow_native_audio import inspect_clips
        source = Path('C:/Users/keera/Downloads/morning_steam_mug.mp4')
        if not source.is_file(): self.skipTest('existing Meta audio fixture unavailable')
        job = self.stories.get(self.job_id)
        job['audio_choices'] = {'mode': 'flow_original', 'subtitle': False}
        self.stories._save(job)
        body = self.advance()
        real = MetaVideoManager(self.stories)
        real.event({**body, 'stage': 'stored', 'filename': str(source)})
        clips = real.clips(self.job_id)
        output = Path(self.temp.name) / 'native-final.mp4'
        MultiFlowComposer().compose(clips, output, width=240, height=426,
                                    audio_choices=job['audio_choices'])
        info = inspect_clips([output])[0]
        self.assertTrue(info['has_audio'])
        self.assertAlmostEqual(info['duration'], 10, delta=.25)

    def test_meta_native_saved_silent_clip_requires_explicit_consent(self):
        from core.video_composer import MultiFlowComposer
        source = Path('C:/Users/keera/Downloads/morning_coffee_steam_silent.mp4')
        if not source.is_file(): self.skipTest('existing Meta silent fixture unavailable')
        job = self.stories.get(self.job_id)
        job['audio_choices'] = {'mode': 'flow_original', 'subtitle': False}
        self.stories._save(job)
        body = self.advance()
        real = MetaVideoManager(self.stories)
        saved = real.event({**body, 'stage': 'stored', 'filename': str(source)})
        with self.assertRaisesRegex(ValueError, 'ไม่มีแทร็กเสียง'):
            MultiFlowComposer().compose(real.clips(self.job_id), Path(self.temp.name) / 'final.mp4',
                                        audio_choices=job['audio_choices'])
        self.assertEqual(real.begin(self.job_id, 1)['request_id'], saved['request_id'])
        self.assertEqual(real.begin(self.job_id, 1)['stage'], 'stored')

    def test_desktop_product_queue_does_not_force_meta_back_to_flow(self):
        from ui.creation_queue import CreationQueueMixin
        from types import SimpleNamespace
        queue = CreationQueue(self.temp.name)
        window = SimpleNamespace(story_queue=queue,
            _resolve_desktop_reference_image=lambda value: '',
            _creation_capture_settings=lambda payload: dict(provider='gemini', ai_web_model='',
                audio_choices={'mode': 'none'}, creative_context=payload['creative_context']),
            _write_console=lambda *args: None, _schedule_next_story_queue_item=lambda *args: None)
        CreationQueueMixin._creation_queue_action(window, 'creation_enqueue', dict(
            values=['A product'], scene_count=3, video_generation_mode='meta_ai',
            creative_context={'kind': 'product_story', 'product_short': True}))
        item = queue.snapshot()['items'][0]
        self.assertEqual(item['video_generation_mode'], 'meta_ai')
        self.assertEqual(item['scene_count'], 3)
        self.assertEqual(item['provider'], 'gemini')

    def test_http_meta_routes_require_extension_origin_token(self):
        from core.product_manager import ProductManager
        bridge = LocalBridge('127.0.0.1', 0, ProductManager(self.temp.name), logging.getLogger('meta-http'), stories=self.stories).start()
        try:
            url = f'http://127.0.0.1:{bridge.server.server_address[1]}/api/meta-video/package?job_id={self.job_id}&index=1'
            for origin in ('https://www.meta.ai', 'chrome-extension://test'):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(urllib.request.Request(url, headers={'Origin': origin}), timeout=5)
                self.assertEqual(caught.exception.code, 403)
            from tests.extension_identity_fixture import pair_fixture
            headers = {'Origin': pair_fixture(bridge), 'X-SmartFlow-Token': bridge._extension_token}
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=5) as response:
                package = json.load(response)['package']
            event = {**package, 'stage': 'uploading', 'version': LocalBridge.REQUIRED_EXTENSION_VERSION}
            request = urllib.request.Request(url.split('/api/')[0] + '/api/meta-video/event',
                data=json.dumps(event).encode(), headers={**headers, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual(json.load(response)['receipt']['stage'], 'uploading')
        finally:
            bridge.stop()

    def test_real_meta_download_probe_when_available(self):
        source = Path('C:/Users/keera/Downloads/morning_coffee_steam_silent.mp4')
        if not source.is_file(): self.skipTest('manual Meta media fixture unavailable')
        body = self.advance()
        real = MetaVideoManager(self.stories)
        result = real.event({**body, 'stage': 'stored', 'filename': str(source)})
        self.assertEqual(result['duration'], 10)
        self.assertEqual(real.clips(self.job_id)[0].stat().st_size, source.stat().st_size)

    def test_extension_dom_and_state_machine(self):
        result = subprocess.run(['node', str(ROOT / 'tests' / 'meta_video_harness.cjs')],
                                capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_package_through_unchanged_extension_controller(self):
        job = self.stories.get(self.job_id)
        job.update(audio_choices={'mode': 'flow_original'}, scene_narrations=['สวัสดีค่ะ ลองนั่งกัน'])
        self.stories._save(job)
        result = subprocess.run(['node', str(ROOT / 'tests' / 'meta_video_harness.cjs'), '--package'],
                                input=json.dumps(self.manager.package(self.job_id, 1), ensure_ascii=False),
                                capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_saved_meta_clips_compose_without_connected_extension(self):
        body = self.advance()
        source = Path(self.temp.name) / 'result.mp4'; source.write_bytes(b'video-data' * 200)
        self.manager.event({**body, 'stage': 'stored', 'filename': str(source)})
        from ui.main_window import MainWindow
        from types import SimpleNamespace
        window = SimpleNamespace(stories=self.stories)
        paths = MainWindow._collect_story_meta_clips(window, self.job_id, None)
        self.assertEqual(len(paths), 1)


if __name__ == '__main__': unittest.main()
