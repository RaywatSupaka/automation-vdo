import hashlib
import json
import logging
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.scene_pipeline import ScenePipeline


class SceneResumeGateTests(unittest.TestCase):
    def test_resume_ack_precedes_worker_and_real_extension_keeps_waiting(self):
        # Real isolated HTTP route, with UI dispatch deliberately not executing yet.
        # This is the race that made ChatGPT error while the Flow worker continued.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            job_id = 'STORY-FIXTURE'
            folder = root / job_id
            folder.mkdir()
            (folder / 'image.png').write_bytes(b'saved image')
            job = {'id': job_id, 'scene_count': 1, 'generated_images': ['image.png'],
                   'scene_narrations': ['scene'], 'audio_choices': {'mode': 'none'}}
            stories = SimpleNamespace(root=root, get=lambda _: job,
                                      prepare_scene_pipeline=lambda *_: job)
            pipeline = ScenePipeline(folder)
            identity = {'image_sha256': hashlib.sha256(b'saved image').hexdigest(),
                        'narration': 'scene', 'audio_choices': job['audio_choices']}
            old = pipeline.request(1, 1, identity)
            pipeline.update(1, old['revision'], phase='error', error='FLOW_SEND_REVIEW old')
            bridge = LocalBridge('127.0.0.1', 0, ProductManager(root / 'products'),
                                 logging.getLogger('scene-resume'), stories=stories).start()
            dispatched = []
            bridge.on_story_scene_ready = dispatched.append
            bridge._extension_runs[('ai', job_id, 0)] = {'run_id': 'RUN-NEW'}
            port = bridge.server.server_address[1]

            def call(action, run='RUN-NEW'):
                req = urllib.request.Request(f'http://127.0.0.1:{port}/api/stories/scene-gate',
                    data=json.dumps({'job_id': job_id, 'index': 1, 'action': action,
                                     'run_id': run}).encode(),
                    headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req) as response:
                    return json.load(response)

            try:
                ready = call('ready')
                self.assertEqual(ready['phase'], 'requested')
                self.assertNotIn('error', ready)
                self.assertEqual(pipeline.get(1)['phase'], 'requested')
                self.assertEqual(len(dispatched), 1)
                self.assertEqual(ready['error_history'][-1]['error'], 'FLOW_SEND_REVIEW old')
                pipeline.update(1, old['revision'], phase='video')
                video = call('status')
                pipeline.update(1, old['revision'], phase='error', error='new failure')
                calls_before = len(dispatched)
                self.assertEqual(call('status')['phase'], 'error')
                self.assertEqual(len(dispatched), calls_before)
                # Explicit resume normally retains the same AI run ID.
                self.assertEqual(call('ready')['phase'], 'requested')
                pipeline.update(1, old['revision'], phase='voice')
                voice = call('status')
                (folder / 'scene.mp4').write_bytes(b'fixture' * 1024)
                pipeline.update(1, old['revision'], phase='complete', segment='scene.mp4')
                complete = call('status')
                calls_before = len(dispatched)
                self.assertEqual(call('ready')['phase'], 'complete')
                self.assertEqual(len(dispatched), calls_before)
                result = subprocess.run(['node', 'tests/scene_resume_gate.js'],
                    cwd=Path(__file__).resolve().parents[1],
                    input=json.dumps([ready, video, voice, complete]),
                    capture_output=True, text=True, encoding='utf-8', timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                with self.assertRaises(urllib.error.HTTPError):
                    call('ready', 'RUN-OLD')
            finally:
                bridge.stop()

    def test_passive_error_is_retained_but_explicit_same_run_resume_works(self):
        with tempfile.TemporaryDirectory() as temp:
            p = ScenePipeline(temp)
            row = p.request(1, 1, {'image': 'saved'}, run_id='RUN-ONE')
            p.update(1, row['revision'], phase='error', error='real new failure')
            self.assertEqual(p.get(1)['phase'], 'error')
            with self.assertRaises(ValueError):
                p.request(1, 1, {'image': 'different'}, run_id='RUN-TWO')
            resumed = p.request(1, 1, {'image': 'saved'}, run_id='RUN-ONE')
            self.assertEqual(resumed['phase'], 'requested')
            self.assertEqual(len(resumed['error_history']), 1)
            self.assertEqual(resumed['revision'], row['revision'])

    def test_active_and_complete_phases_do_not_carry_old_current_error(self):
        with tempfile.TemporaryDirectory() as temp:
            p = ScenePipeline(temp)
            row = p.request(1, 1, {'image': 'saved'})
            p.update(1, row['revision'], phase='error', error='old')
            row = p.update(1, row['revision'], phase='video')
            self.assertNotIn('error', row)
            self.assertEqual(row['error_history'][-1]['error'], 'old')
            (Path(temp) / 'scene.mp4').write_bytes(b'x' * 2048)
            p.update(1, row['revision'], phase='complete', segment='scene.mp4')
            self.assertNotIn('error', p.get(1))
            self.assertEqual(len(p.segments(1)), 1)
