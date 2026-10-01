import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.story_manager import StoryManager
from core.creation_queue import CreationQueue
from ui.story_recovery import clear_story_recovery, pending_short


class StoryRecoveryClearTests(unittest.TestCase):
    def test_scope(self):
        for status in ('error', 'failed', 'pending', 'processing'):
            self.assertTrue(pending_short({'status': status}))
        for extra in ({'product_story': True}, {'cast_creation': True}, {'series_id': 'x'},
                      {'long_video': True}, {'story_source_only': True}, {'job_type': 'drama'},
                      {'status': 'cancelled'}, {'status': 'deleted'}, {'video_status': 'deleted'},
                      {'status': 'success', 'video_status': 'ready'}):
            self.assertFalse(pending_short(extra), extra)

    def test_all_jobs_queue_and_files_preserved_and_repeat_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            stories = StoryManager(Path(temp))
            queue = CreationQueue(Path(temp))
            app = SimpleNamespace(stories=stories, story_queue=queue,
                _creation_idle_reason=lambda: '', bridge=SimpleNamespace(
                    pending_job_commands=lambda ids: [], extension_status=lambda: {'clients': []}))
            jobs = [stories.create(topic=f'เรื่อง {i}') for i in range(11)]
            special = stories.create(topic='สินค้า')
            special['product_story'] = True
            stories._save(special)
            image = stories.root / jobs[0]['id'] / 'generated' / 'scene_01.png'
            image.parent.mkdir(exist_ok=True)
            image.write_bytes(b'original image')
            row = queue.enqueue_batch(['เรื่อง'])['items'][0]
            queue.attach_job(row['queue_id'], jobs[0]['id'])
            duplicate = queue.enqueue_batch(['ลองทำต่อ'])['items'][-1]
            queue.attach_job(duplicate['queue_id'], jobs[0]['id'])
            queue._update(duplicate['queue_id'], status='failed')
            result = clear_story_recovery(app, {'confirmed': True})
            self.assertEqual(result['cleared'], 11)
            self.assertEqual(image.read_bytes(), b'original image')
            self.assertTrue(all(stories.get(j['id'])['status'] == 'cancelled' for j in jobs))
            self.assertNotEqual(stories.get(special['id'])['status'], 'cancelled')
            self.assertEqual(queue.snapshot()['items'][0]['status'], 'cancelled')
            self.assertTrue(all(item['status'] == 'cancelled' for item in queue.snapshot()['items']))
            self.assertEqual(clear_story_recovery(app, {'confirmed': True})['cleared'], 0)

    def test_confirmation_busy_pending_and_remote_block_before_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            stories, queue = StoryManager(Path(temp)), CreationQueue(Path(temp))
            job = stories.create(topic='งานเดิม')
            app = SimpleNamespace(stories=stories, story_queue=queue,
                _creation_idle_reason=lambda: '', bridge=SimpleNamespace(
                    pending_job_commands=lambda ids: [], extension_status=lambda: {'clients': []}))
            with self.assertRaises(ValueError): clear_story_recovery(app, {})
            app._creation_idle_reason = lambda: 'กำลังทำงาน'
            with self.assertRaises(ValueError): clear_story_recovery(app, {'confirmed': True})
            app._creation_idle_reason = lambda: ''
            app.bridge.pending_job_commands = lambda ids: ['command']
            with self.assertRaises(ValueError): clear_story_recovery(app, {'confirmed': True})
            app.bridge.pending_job_commands = lambda ids: []
            app.bridge.extension_status = lambda: {'connected': False, 'clients': [
                {'ai_job_id': job['id'], 'ai_step': 'generating'}]}
            with self.assertRaises(ValueError): clear_story_recovery(app, {'confirmed': True})
            self.assertNotEqual(stories.get(job['id'])['status'], 'cancelled')

    def test_desktop_action_routes_to_clear(self):
        from ui.main_window import MainWindow
        with tempfile.TemporaryDirectory() as temp:
            app = MainWindow.__new__(MainWindow)
            app.stories, app.story_queue = StoryManager(Path(temp)), CreationQueue(Path(temp))
            app._manual_multi_flow_job_id = ''
            app._creation_idle_reason = lambda: ''
            app.bridge = SimpleNamespace(pending_job_commands=lambda ids: [], extension_status=lambda: {'clients': []})
            app.stories.create(topic='งานทดสอบ')
            self.assertEqual(MainWindow._desktop_execute_action(app, 'clear_story_recovery', {'confirmed': True})['cleared'], 1)

    def test_real_ui_functions(self):
        result = subprocess.run(['node', 'tests/story_recovery_clear_ui.js'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, encoding='utf-8', timeout=40)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
