import json
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.video_library import VideoLibrary
from core.job_file_guard import app_guard, guard_for, guarded_thread
from ui.main_window import MainWindow


class FakeThread:
    pending = []
    def __init__(self, target, args=(), **kwargs):
        self.target, self.args, self.alive = target, args, False
    def start(self):
        self.alive = True
        self.pending.append(self)
    def is_alive(self):
        return self.alive
    def run(self):
        try:
            return self.target(*self.args)
        finally:
            self.alive = False


class DeleteGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'workspace/products/JOB-OLD'
        self.folder.mkdir(parents=True)
        (self.folder / 'videos').mkdir()
        (self.folder / 'videos/final.mp4').write_bytes(b'old final')
        self.manifest = dict(id='JOB-OLD', status='ready', video_status='ready', video_path='videos/final.mp4')
        self.save()
        self.recycler = Mock(side_effect=OSError('fixture recycler never deletes'))
        self.library = VideoLibrary(self.root, recycler=self.recycler)
        self.app = MainWindow.__new__(MainWindow)
        self.app.video_library = self.library
        self.app.products = SimpleNamespace(root=self.root / 'workspace/products', get_job=lambda ident: dict(self.manifest))
        self.app.stories = SimpleNamespace(root=self.root / 'workspace/stories')
        self.app._product_pipeline_job_id = ''
        self.app._story_pipeline_job_id = ''
        self.app.story_queue = SimpleNamespace(snapshot=lambda: {'items': []})
        self.app.bridge = SimpleNamespace(ai_covers=SimpleNamespace(active=lambda: []),
            extension_status=lambda: {'connected': False, 'clients': []}, pending_job_commands=lambda ids: [])
        self.app._desktop_select_product = lambda ident: True
        self.app.events = queue.Queue()
        self.app.cfg = {}
        app_guard(self.app)
        FakeThread.pending = []
        self.addCleanup(lambda: [claim.release() for claim in list(self.library.file_guard.claims)])

    def save(self):
        (self.folder / 'job.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def test_active_product_never_reaches_recycler(self):
        self.manifest.update(automation_status='running')
        self.save()
        try:
            result = self.library.delete_project('product:JOB-OLD')
        except ValueError:
            pass
        self.recycler.assert_not_called()

    def test_active_story_never_reaches_recycler(self):
        story = self.root / 'workspace/stories/STORY-ACTIVE'
        story.mkdir(parents=True)
        (story / 'job.json').write_text(json.dumps(dict(id='STORY-ACTIVE', status='running')), encoding='utf-8')
        try:
            self.library.delete_project('story:STORY-ACTIVE')
        except ValueError:
            pass
        self.recycler.assert_not_called()

    def test_product_and_individual_library_routes_reject_active_before_thread(self):
        for action, payload in [('product_tool', {'job_id': 'JOB-OLD', 'tool': 'delete_project'}),
                ('delete_library_project', {'item_id': 'product:JOB-OLD'}),
                ('delete_library_video', {'item_id': 'product:JOB-OLD'})]:
            with self.subTest(action=action), patch('threading.Thread', FakeThread):
                self.app._product_pipeline_job_id = 'JOB-OLD'
                with self.assertRaises(ValueError):
                    self.app._desktop_execute_action(action, payload)
        self.assertEqual(FakeThread.pending, [])
        self.recycler.assert_not_called()

    def test_confirmation_open_then_job_starts_is_rechecked(self):
        self.library.project_summary('product:JOB-OLD')  # The old confirmation data.
        self.app._story_pipeline_job_id = 'STORY-WORK'
        other = self.root / 'workspace/stories/STORY-WORK'
        other.mkdir(parents=True)
        (other / 'job.json').write_text(json.dumps({'id':'STORY-WORK',
            'source_footage':[str(self.folder / 'videos/final.mp4')]}), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.app._reserve_file_deletion('project', 'product:JOB-OLD')
        self.recycler.assert_not_called()

    def test_duplicate_confirmation_reserves_only_one_worker(self):
        with patch('threading.Thread', FakeThread):
            self.app._start_desktop_delete('project', 'product:JOB-OLD')
            with self.assertRaises(ValueError):
                self.app._start_desktop_delete('project', 'product:JOB-OLD')
        self.assertEqual(len(FakeThread.pending), 1)
        self.recycler.assert_not_called()

    def test_queue_active_cover_and_scene_worker_block_exact_target(self):
        cases = [
            ('queue', lambda: setattr(self.app.story_queue, 'snapshot', lambda: {'items':[{'status':'queued', 'job_id':'JOB-OLD'}]})),
            ('cover', lambda: setattr(self.app.bridge.ai_covers, 'active', lambda: [{'job_id':'JOB-OLD', 'phase':'waiting_result'}])),
            ('scene', lambda: setattr(self.app, '_story_scene_threads', {('JOB-OLD', 1, 'r'):SimpleNamespace(is_alive=lambda:True)})),
            ('remote', lambda: setattr(self.app.bridge, 'extension_status', lambda: {'connected':False,
                'clients':[{'ai_job_id':'JOB-OLD','ai_step':'generating'}]})),
            ('pending', lambda: setattr(self.app.bridge, 'pending_job_commands', lambda ids: ids)),
        ]
        for name, prepare in cases:
            with self.subTest(name=name):
                self.app.story_queue.snapshot = lambda: {'items':[]}
                self.app.bridge.ai_covers.active = lambda: []
                self.app.bridge.extension_status = lambda: {'clients':[]}
                self.app.bridge.pending_job_commands = lambda ids: []
                self.app._story_scene_threads = {}
                prepare()
                with self.assertRaises(ValueError):
                    self.app._reserve_file_deletion('project', 'product:JOB-OLD')
        self.recycler.assert_not_called()

    def test_unrelated_active_job_does_not_block_idle_target(self):
        self.app._story_pipeline_job_id = 'STORY-OTHER'
        with self.app._reserve_file_deletion('project', 'product:JOB-OLD'):
            pass

    def test_reference_worker_claim_exists_before_thread_runs_and_releases_on_error(self):
        def fail():
            raise RuntimeError('fixture failure')
        with patch('threading.Thread', FakeThread):
            worker = guarded_thread(self.app, 'STORY-WORK', fail,
                references=str(self.folder / 'videos/final.mp4'), daemon=True)
        with self.assertRaises(ValueError):
            self.app._reserve_file_deletion('project', 'product:JOB-OLD')
        with self.assertRaises(RuntimeError):
            worker.run()
        with self.app._reserve_file_deletion('project', 'product:JOB-OLD'):
            pass

    def test_delete_claim_blocks_actual_manual_and_scheduler_start_before_body(self):
        self.app.voice_job_id = SimpleNamespace(get=lambda:'JOB-OLD')
        self.app.voice_reference_file = SimpleNamespace(get=lambda:'')
        self.app.story_queue.running_item = lambda: {'job_id':'JOB-OLD'}
        self.app._selected_product_job = lambda: 'JOB-OLD'
        with self.app._reserve_file_deletion('project', 'product:JOB-OLD'):
            for start in (self.app._create_voice, self.app._start_next_story_queue_item,
                          lambda: self.app._create_product_and_run('JOB-OLD'),
                          lambda: self.app._retry_story_job('JOB-OLD')):
                with self.assertRaisesRegex(ValueError, 'กำลังลบ'):
                    start()

    def test_recheck_before_recycler_and_finally_release(self):
        with patch('threading.Thread', FakeThread):
            self.app._start_desktop_delete('project', 'product:JOB-OLD')
        self.app.bridge.ai_covers.active = lambda: [{'job_id':'JOB-OLD'}]
        FakeThread.pending[0].run()
        self.recycler.assert_not_called()
        self.assertFalse(self.library.file_guard.claims)
        event, value = self.app.events.get_nowait()
        self.assertEqual(event, 'desktop_operation')
        self.assertEqual(value[0], 'warning')

    def test_bulk_truthfully_skips_busy_job_and_reports_failed_idle_recycler(self):
        busy = self.root / 'workspace/stories/STORY-WORK'
        busy.mkdir(parents=True)
        (busy / 'job.json').write_text(json.dumps({'id':'STORY-WORK','status':'running'}), encoding='utf-8')
        result = self.library.delete_all_projects()
        self.assertEqual(result['skipped_projects'], ['STORY-WORK'])
        self.assertEqual(result['failed_projects'], ['JOB-OLD'])
        self.assertEqual(result['deleted_count'], 0)
        self.recycler.assert_called_once_with(self.folder)
        self.assertEqual((self.folder / 'videos/final.mp4').read_bytes(), b'old final')

    def test_atomic_race_winner_owns_target_until_release(self):
        for _ in range(20):
            barrier, finished = threading.Barrier(2), threading.Barrier(2)
            winners, errors = [], []
            def attempt(deleting):
                claim = None
                try:
                    barrier.wait()
                    claim = self.library.file_guard.reserve_delete(['JOB-OLD']) if deleting else self.library.file_guard.start('JOB-OLD')
                    winners.append('delete' if deleting else 'start')
                except ValueError:
                    errors.append('blocked')
                finally:
                    finished.wait()
                    if claim:
                        claim.release()
            threads = [threading.Thread(target=attempt, args=(value,)) for value in (True, False)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=3)
            self.assertEqual(len(winners), 1)
            self.assertEqual(errors, ['blocked'])
            self.assertFalse(self.library.file_guard.claims)

    def test_thread_launch_failure_releases_start_and_delete_claims(self):
        with patch('threading.Thread', side_effect=RuntimeError('cannot launch')):
            with self.assertRaises(RuntimeError):
                self.app._start_desktop_delete('project', 'product:JOB-OLD')
            self.assertFalse(self.library.file_guard.claims)
            with self.assertRaises(RuntimeError):
                guarded_thread(self.app, 'JOB-OLD', lambda: None)
            self.assertFalse(self.library.file_guard.claims)

    def test_relative_reference_cannot_bypass_claim(self):
        other = self.root / 'workspace/stories/STORY-WORK'
        other.mkdir(parents=True)
        (other / 'job.json').write_text(json.dumps({'id':'STORY-WORK',
            'source_footage':['../../products/JOB-OLD/videos/final.mp4']}), encoding='utf-8')
        with self.library.file_guard.start('STORY-WORK'):
            with self.assertRaises(ValueError):
                self.app._reserve_file_deletion('project', 'product:JOB-OLD')

    def test_actual_cover_request_and_recovery_use_delete_guard_without_writes(self):
        from core.ai_cover import AICovers
        from PIL import Image
        Image.new('RGB', (64, 64), 'blue').save(self.folder / 'scene.png')
        self.manifest.update(generated_images=['scene.png'], ai_cover_options={'enabled':True})
        self.save()
        service = AICovers(self.app.products)
        self.app.bridge.ai_covers = service
        original = (self.folder / 'job.json').read_bytes()
        with self.app._reserve_file_deletion('project', 'product:JOB-OLD'):
            with self.assertRaisesRegex(ValueError, 'กำลังลบ'):
                service.request('JOB-OLD')
        self.assertEqual((self.folder / 'job.json').read_bytes(), original)
        row = service.request('JOB-OLD')
        with self.assertRaises(ValueError):
            self.app._reserve_file_deletion('project', 'product:JOB-OLD')
        service.event(row['request_id'], {'phase':'needs_review', 'message':'fixture interrupted'})
        with self.app._reserve_file_deletion('project', 'product:JOB-OLD'):
            for action in (lambda: service.recover_result(row['request_id'], 'JOB-OLD'),
                           lambda: service.event(row['request_id'], {'phase':'running'})):
                with self.assertRaisesRegex(ValueError, 'กำลังลบ'):
                    action()
        self.recycler.assert_not_called()

    def test_bulk_reservation_does_not_expand_to_newly_added_jobs(self):
        claim = self.app._reserve_file_deletion('all_products')
        newcomer = self.root / 'workspace/products/JOB-NEW'
        newcomer.mkdir(parents=True)
        (newcomer / 'job.json').write_text(json.dumps({'id':'JOB-NEW', 'status':'ready'}), encoding='utf-8')
        result = claim.guard.run_delete(claim, self.library.delete_all_projects, 'product')
        self.assertEqual(result['skipped_projects'], ['JOB-NEW'])
        self.recycler.assert_called_once_with(self.folder)
        self.assertTrue(newcomer.is_dir())

    def test_cover_cancel_keeps_guard_before_store_while_other_job_is_probed(self):
        from core.ai_cover import AICovers
        from ui.ai_cover import _cancel_linked_cover
        from PIL import Image
        Image.new('RGB', (64, 64), 'blue').save(self.folder / 'scene.png')
        self.manifest.update(generated_images=['scene.png'], ai_cover_options={'enabled':True})
        self.save()
        service = AICovers(self.app.products)
        self.app.bridge.ai_covers = service
        row = service.request('JOB-OLD')
        other = self.root / 'workspace/stories/STORY-OTHER'
        other.mkdir(parents=True)
        (other / 'job.json').write_text(json.dumps({'id':'STORY-OTHER','status':'ready'}), encoding='utf-8')
        guard = self.library.file_guard
        entered, release, probe_entered = threading.Event(), threading.Event(), threading.Event()
        errors = []
        original_event, original_probe = service.event, guard.probe
        def nested_event(*args, **kwargs):
            # Fail cleanly on the old store -> guard order, before creating a
            # deliberately blocked second thread that could never be released.
            self.assertTrue(guard.lock._is_owned())
            entered.set()
            self.assertTrue(release.wait(2))
            return original_event(*args, **kwargs)
        def probe(job_id):
            probe_entered.set()
            return original_probe(job_id)  # Includes covers.active/store read.
        def cancel():
            try:
                _cancel_linked_cover(service, row['request_id'])
            except BaseException as exc:
                errors.append(exc)
        def delete_other():
            try:
                with guard.reserve_delete(['STORY-OTHER']):
                    pass
            except BaseException as exc:
                errors.append(exc)
        guard.probe = probe
        with patch.object(service, 'event', side_effect=nested_event):
            first = threading.Thread(target=cancel, daemon=True)
            second = threading.Thread(target=delete_other, daemon=True)
            try:
                first.start()
                self.assertTrue(entered.wait(1), errors)
                second.start()
                self.assertFalse(probe_entered.wait(.05))
            finally:
                release.set()
                first.join(timeout=2)
                if second.ident is not None:
                    second.join(timeout=2)
                guard.probe = original_probe
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(probe_entered.is_set())
        self.assertEqual(service.get(row['request_id'])['phase'], 'cancelled')
        self.recycler.assert_not_called()


if __name__ == '__main__':
    unittest.main()
