"""Real desktop FIFO/event handlers + durable cover state; no provider calls."""
import base64
import io
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from core.ai_cover import AICovers
from core.atomic_json import AtomicJsonFile
from core.creation_queue import CreationQueue
from ui.main_window import MainWindow
from ui.ai_cover import finish_ai_cover


class CoverQueueGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.app = MainWindow.__new__(MainWindow)
        self.app.stories = SimpleNamespace(root=self.root / 'stories')
        self.app.products = SimpleNamespace(root=self.root / 'products')
        self.app.stories.get = lambda job: AtomicJsonFile(self.app.stories.root / job / 'job.json').read()
        self.app.products.get_job = lambda job: AtomicJsonFile(self.app.products.root / job / 'job.json').read()
        self.service = AICovers(self.app.products, self.app.stories)
        self.app.bridge = SimpleNamespace(
            ai_covers=self.service, REQUIRED_EXTENSION_VERSION='0.15.515',
            extension_status=Mock(return_value={
                'connected': True, 'clients': [{'version': '0.15.515'}]}))
        self.app.story_queue = CreationQueue(self.root)
        self.app.events = queue.Queue()
        for name in ('status', 'root', 'story_run_button', 'product_run_button', 'drama_series'):
            setattr(self.app, name, Mock())
        for name in ('_schedule_next_story_queue_item', '_desktop_set_notice', '_write_console',
                     '_close_automation_browser', '_start_auto_cleanup_completed_job',
                     '_finish_story_popup', '_finish_product_popup', '_poll_desktop_requests',
                     '_creation_preflight', '_retry_story_job', '_creation_start_product'):
            setattr(self.app, name, Mock())
        self.app._creation_workers_alive = Mock(return_value=False)
        self.app._story_queue_browser_recycled = Mock(return_value=True)
        self.app._story_pipeline_job_id = self.app._product_pipeline_job_id = ''
        self.app._creation_dispatch_item = None

    def job(self, mode='story', enabled=True):
        job = 'JOB-COVER-TEST' if mode == 'product' else 'STORY-COVER-TEST'
        manager = self.app.products if mode == 'product' else self.app.stories
        folder = manager.root / job
        folder.mkdir(parents=True)
        (folder / 'final.mp4').write_bytes(b'keep existing video; offline fixture')
        Image.new('RGB', (576, 1024), 'blue').save(folder / 'scene.jpg')
        manifest = dict(id=job, job_type='drama_episode' if mode == 'drama' else 'story_short',
            status='ready', automation_status='completed', video_status='ready', video_path='final.mp4',
            cover_status='pending_ai', generated_images=['scene.jpg'], video_title='เรื่องเดิม',
            ai_cover_options={'enabled': enabled}, image_ai_provider='chatgpt')
        if mode == 'drama':
            manifest.update(series_id='SERIES-KEEP', episode_no=1)
        self.manifest = AtomicJsonFile(folder / 'job.json')
        self.manifest.write(manifest)
        rows = self.app.story_queue.enqueue('product' if mode == 'product' else 'story',
            ['https://s.shopee.co.th/test'] if mode == 'product' else ['เรื่องเดิม'])['items']
        self.app.story_queue.resume()
        row = self.app.story_queue.claim_next()
        self.app.story_queue._update(row['queue_id'], job_id=job, mode=mode)
        self.app.story_queue.enqueue('story', ['หัวข้อถัดไป'])
        self.app.story_queue.resume()
        self.row_id = rows[0]['queue_id']
        return job, folder

    def cover(self, job, phase):
        row = self.service.request(job)
        if phase != 'queued':
            self.service.event(row['request_id'], {'phase': 'claimed'})
        if phase == 'ready':
            data = io.BytesIO()
            Image.new('RGB', (576, 1024), 'red').save(data, 'PNG')
            self.service.event(row['request_id'], {'phase':'ready',
                'image':'data:image/png;base64,' + base64.b64encode(data.getvalue()).decode()})
        elif phase not in {'queued', 'claimed'}:
            self.service.event(row['request_id'], {'phase':phase, 'message':'observed cover state'})
        return row['request_id']

    def test_legacy_disabled_does_not_require_ai_cover(self):
        job, _ = self.job(enabled=False)
        self.manifest.update(lambda m: {k:v for k,v in m.items() if k != 'ai_cover_options'})
        self.assertTrue(self.service.completion(job)['ready'])
        self.assertTrue(self.app._creation_restore_final(self.app.story_queue.get_item(self.row_id)))
        self.assertEqual(self.app.story_queue.get_item(self.row_id)['status'], 'completed')

    def test_active_cover_wait_keeps_fifo_owner_and_does_not_pause_or_send(self):
        job, _ = self.job()
        rid = self.cover(job, 'running')
        for _ in range(3):
            self.app._start_next_story_queue_item()
        self.assertEqual(self.app.story_queue.get_item(self.row_id)['status'], 'running')
        self.assertFalse(self.app.story_queue.snapshot()['paused'])
        self.assertIsNone(self.app.story_queue.claim_next())
        self.assertEqual(len(self.service.store.read()), 1)
        self.assertEqual(self.service.get(rid)['phase'], 'running')
        self.app._retry_story_job.assert_not_called()
        self.app._close_automation_browser.assert_not_called()

    def test_queued_cover_with_old_extension_pauses_visibly_without_replay(self):
        job, folder = self.job()
        rid = self.cover(job, 'queued')
        original = (folder / 'final.mp4').read_bytes()
        self.app.bridge.extension_status.return_value = {
            'connected': True, 'clients': [{'version': '0.15.513'}]}

        self.app._start_next_story_queue_item()

        item = self.app.story_queue.get_item(self.row_id)
        self.assertEqual(item['status'], 'queued')
        self.assertEqual(item['job_id'], job)
        self.assertIn('0.15.515', item['error'])
        self.assertEqual(self.app.story_queue.snapshot()['pause_reason'], 'ai_cover_needs_attention')
        self.assertEqual(self.service.get(rid)['phase'], 'queued')
        self.assertEqual(len(self.service.store.read()), 1)
        self.assertEqual((folder / 'final.mp4').read_bytes(), original)
        self.app._retry_story_job.assert_not_called()
        self.app._desktop_set_notice.assert_called_once()

        for _ in range(2):
            self.app.story_queue.resume()
            self.app._start_next_story_queue_item()
            self.assertTrue(self.app.story_queue.snapshot()['paused'])
            self.assertEqual(self.service.get(rid)['phase'], 'queued')
            self.assertEqual(len(self.service.store.read()), 1)

        # After the original Extension identity reports the required version,
        # Resume keeps the same cover request and lets the collector claim it.
        self.app.bridge.extension_status.return_value = {
            'connected': True, 'clients': [{'version': '0.15.515'}]}
        self.app.story_queue.resume()
        self.app._start_next_story_queue_item()
        self.assertEqual(self.app.story_queue.get_item(self.row_id)['status'], 'running')
        self.assertFalse(self.app.story_queue.snapshot()['paused'])
        self.assertEqual(self.service.get(rid)['phase'], 'queued')
        self.assertEqual(len(self.service.store.read()), 1)
        self.app._retry_story_job.assert_not_called()

    def test_review_pauses_then_cover_only_recovery_reuses_final(self):
        job, folder = self.job()
        rid = self.cover(job, 'needs_review')
        original = (folder / 'final.mp4').read_bytes()
        self.app._start_next_story_queue_item()
        row = self.app.story_queue.get_item(self.row_id)
        self.assertEqual(row['status'], 'queued')
        self.assertEqual(row['job_id'], job)
        self.assertEqual(self.app.story_queue.snapshot()['pause_reason'], 'ai_cover_needs_attention')
        self.assertIsNone(self.app.story_queue.claim_next())
        message = self.service.completion(job)['message']
        self.assertIn('จัดการปก AI', message)
        self.assertIn('เมื่อบันทึกปกสำเร็จแล้ว', message)
        # Run Queue alone cannot recover the reviewed cover or redo the video.
        for _ in range(2):
            self.app.story_queue.resume()
            self.app._start_next_story_queue_item()
        self.assertEqual(len(self.service.store.read()), 1)
        self.assertEqual(self.service.get(rid)['phase'], 'needs_review')
        self.assertEqual((folder / 'final.mp4').read_bytes(), original)
        # Explicit cover-only action creates a new request; gate never does.
        new = self.service.request(job, force=True)
        self.assertNotEqual(new['request_id'], rid)
        self.cover(job, 'ready')
        self.app.story_queue.resume()
        self.app._start_next_story_queue_item()
        self.assertEqual(self.app.story_queue.get_item(self.row_id)['status'], 'completed')
        self.assertEqual(self.app.story_queue.claim_next()['topic'], 'หัวข้อถัดไป')
        self.assertEqual((folder / 'final.mp4').read_bytes(), original)
        self.assertEqual(self.service.get(rid)['phase'], 'needs_review')
        self.app._retry_story_job.assert_not_called()

    def test_ready_requires_exact_saved_file_not_old_cover_or_state_only(self):
        job, folder = self.job()
        rid = self.cover(job, 'ready')
        self.assertTrue(self.service.completion(job)['ready'])
        (folder / self.manifest.read()['cover_path']).unlink()
        self.assertFalse(self.service.completion(job)['ready'])
        self.manifest.update(lambda m: {**m, 'cover_path':'scene.jpg', 'cover_revision':'old'})
        self.assertFalse(self.service.completion(job)['ready'])
        self.assertEqual(self.service.completion(job)['request_id'], rid)

    def test_manual_cover_is_not_overwritten_and_saved_ai_history_can_complete(self):
        job, _ = self.job()
        self.cover(job, 'ready')
        self.manifest.update(lambda m: {**m, 'cover_path':'scene.jpg', 'cover_revision':'manual'})
        self.assertTrue(self.service.completion(job)['ready'])
        self.assertEqual(self.manifest.read()['cover_revision'], 'manual')

    def test_completion_reads_manifest_under_the_cover_event_lock(self):
        job, _ = self.job()
        self.cover(job, 'ready')
        original = AtomicJsonFile.read
        observed = []
        def read(store, *args, **kwargs):
            if store.path.samefile(self.manifest.path):
                observed.append(self.service.store._thread_lock._is_owned())
            return original(store, *args, **kwargs)
        with patch.object(AtomicJsonFile, 'read', read):
            self.assertTrue(self.service.completion(job)['ready'])
        self.assertEqual(observed, [True])

    def test_missing_or_cancelled_cover_does_not_complete_enabled_job(self):
        job, _ = self.job()
        self.assertFalse(self.service.completion(job)['ready'])
        self.cover(job, 'cancelled')
        self.assertFalse(self.app._creation_cover_gate(job))
        self.assertTrue(self.app.story_queue.snapshot()['paused'])

    def test_library_cover_blocks_next_topic_without_claiming_or_resending(self):
        job, _ = self.job()
        rid = self.cover(job, 'running')
        self.app.story_queue.mark_completed_by_job(job, 'final.mp4')
        self.app._start_next_story_queue_item()
        self.assertIsNone(self.app.story_queue.running_item())
        self.assertEqual(self.service.get(rid)['phase'], 'running')
        self.app._creation_preflight.assert_not_called()
        self.app._creation_start_product.assert_not_called()
        self.app._retry_story_job.assert_not_called()

    def test_product_ready_handler_preserves_browser_and_does_not_report_success(self):
        job, folder = self.job('product')
        self.cover(job, 'needs_review')
        self.app._handle_product_pipeline_ready((job, folder / 'final.mp4', {}))
        self.assertNotEqual(self.app.story_queue.get_item(self.row_id)['status'], 'completed')
        self.app._close_automation_browser.assert_not_called()
        self.app._start_auto_cleanup_completed_job.assert_not_called()
        self.assertEqual(self.app._finish_product_popup.call_args.args[0], 'warning')

    def test_product_terminal_defence_keeps_missing_cover_out_of_completed(self):
        job, folder = self.job('product')
        self.cover(job, 'needs_review')
        self.assertTrue(self.app._creation_product_terminal(job, 'completed', output=folder/'final.mp4'))
        self.assertEqual(self.app.story_queue.get_item(self.row_id)['status'], 'queued')

    def test_current_story_ready_event_does_not_close_or_cleanup_or_advance(self):
        job, folder = self.job()
        self.cover(job, 'needs_review')
        event = threading.Event()
        self.app._story_pipeline_job_id, self.app._story_cancel_event = job, event
        finish_ai_cover(self.app, job, event, Mock())
        self.app.events.put(('story_ready', {'job_id':job, 'cancel_event':event,
            'value':(self.manifest.read(), folder/'final.mp4', {})}))
        self.app._poll_once()
        self.assertEqual(self.app.story_queue.get_item(self.row_id)['status'], 'queued')
        self.app._close_automation_browser.assert_not_called()
        self.app._start_auto_cleanup_completed_job.assert_not_called()
        self.assertEqual(self.app._finish_story_popup.call_args.args[0], 'warning')
        self.assertEqual(self.app._story_pipeline_job_id, '')

    def test_drama_resume_waits_then_marks_same_episode_ready(self):
        job, folder = self.job('drama')
        self.cover(job, 'needs_review')
        self.app._start_next_story_queue_item()
        self.app.drama_series.mark_episode_ready.assert_not_called()
        self.service.request(job, force=True)
        self.cover(job, 'ready')
        self.app.story_queue.resume()
        self.app._start_next_story_queue_item()
        self.app.drama_series.mark_episode_ready.assert_called_once()
        self.assertEqual(self.app.story_queue.get_item(self.row_id)['status'], 'completed')
        self.app._retry_story_job.assert_not_called()


if __name__ == '__main__':
    unittest.main()
