"""Actual-manager regressions for delayed queue/Drama completion callbacks."""
import tempfile
import threading
import unittest
from unittest.mock import patch

from core.atomic_json import AtomicJsonFile
from core.creation_queue import CreationQueue
from core.drama_series import DramaSeriesManager
from core.story_manager import StoryManager


class DesktopLifecycleReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.queue = CreationQueue(self.temporary.name)
        self.manager = DramaSeriesManager(self.temporary.name)
        self.series = self.manager.create('Lifecycle fixture', '', 2, 6, 'chatgpt', [{'name': 'A'}])
        self.sid = self.series['id']

    def queue_running_episode(self):
        self.queue.enqueue_drama_series(self.sid, 'Lifecycle fixture', 2)
        self.queue.resume()
        row = self.queue.claim_next()
        self.queue.attach_job(row['queue_id'], 'STORY-CURRENT')
        return row

    def story(self, job_id='STORY-CURRENT', **fields):
        return dict(id=job_id, series_id=self.sid, episode_no=1, **fields)

    def series_bytes(self):
        return (self.manager.root / self.sid / 'series.json').read_bytes()

    def test_cancelled_drama_queue_cannot_be_completed_by_late_result(self):
        row = self.queue_running_episode()
        self.queue.cancel_drama_series(self.sid)
        before = self.queue.path.read_bytes()
        self.assertIsNone(self.queue.mark_completed_by_job('STORY-CURRENT', 'late.mp4'))
        self.assertEqual(self.queue.path.read_bytes(), before)
        self.assertEqual(self.queue.get_item(row['queue_id'])['status'], 'cancelled')

    def test_completed_drama_queue_cannot_be_downgraded_by_late_failure(self):
        self.queue_running_episode()
        self.queue.mark_completed_by_job('STORY-CURRENT', 'saved.mp4')
        before = self.queue.path.read_bytes()
        self.assertIsNone(self.queue.mark_failed_by_job('STORY-CURRENT', 'late error'))
        self.assertIsNone(self.queue.mark_completed_by_job('STORY-CURRENT', 'wrong-late.mp4'))
        self.assertEqual(self.queue.path.read_bytes(), before)

    def test_failed_drama_queue_can_still_complete_after_manual_recovery(self):
        self.queue_running_episode()
        self.queue.mark_failed_by_job('STORY-CURRENT', 'interrupted')
        result = self.queue.mark_completed_by_job('STORY-CURRENT', 'recovered.mp4')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['output_path'], 'recovered.mp4')

    def test_replaced_job_cannot_change_episode_or_global_continuity(self):
        self.manager.attach_story_job(self.sid, 1, 'STORY-CURRENT')
        before = self.series_bytes()
        old = self.story('STORY-OLD', episode_summary='wrong summary',
                         continuity_state={'wrong': True}, image_ai_provider='gemini')
        self.manager.update_from_story(old)
        self.manager.mark_episode_ready(old, 'wrong.mp4')
        self.assertEqual(self.series_bytes(), before)

    def test_cancelled_series_rejects_metadata_before_copying_reference_or_cover(self):
        self.manager.attach_story_job(self.sid, 1, 'STORY-CURRENT')
        self.manager.cancel_series(self.sid)
        before = self.series_bytes()
        with patch.object(self.manager, '_save_continuity_references') as refs, \
                patch.object(self.manager, '_save_episode_cover') as cover:
            self.manager.mark_episode_ready(self.story(episode_summary='late'), 'late.mp4')
            self.manager.update_from_story(self.story(continuity_state={'late': True}))
        refs.assert_not_called()
        cover.assert_not_called()
        self.assertEqual(self.series_bytes(), before)

    def test_retry_unbound_window_does_not_accept_old_job(self):
        self.manager.attach_story_job(self.sid, 1, 'STORY-OLD')
        self.manager.mark_episode_failed(self.sid, 1, 'failed')
        self.manager.reset_episode_for_retry(self.sid, 1)
        before = self.series_bytes()
        self.manager.mark_episode_ready(self.story('STORY-OLD', episode_summary='late'), 'old.mp4')
        self.assertEqual(self.series_bytes(), before)
        self.manager.attach_story_job(self.sid, 1, 'STORY-CURRENT')
        result = self.manager.mark_episode_ready(self.story(episode_summary='current'), 'new.mp4')
        self.assertEqual(result['episodes'][0]['status'], 'completed')
        self.assertEqual(result['episodes'][0]['summary'], 'current')

    def test_completed_episode_ignores_duplicate_ready_progress_and_late_failure(self):
        self.manager.attach_story_job(self.sid, 1, 'STORY-CURRENT')
        self.manager.mark_episode_ready(self.story(episode_summary='saved'), 'saved.mp4')
        before = self.series_bytes()
        self.manager.mark_episode_ready(self.story(episode_summary='duplicate'), 'late.mp4')
        self.manager.update_from_story(self.story(continuity_state={'stale': True}))
        self.manager.mark_episode_failed(self.sid, 1, 'late error')
        self.assertEqual(self.series_bytes(), before)

    def test_legacy_unbound_first_attempt_remains_compatible(self):
        result = self.manager.mark_episode_ready(self.story(episode_summary='legacy'), 'saved.mp4')
        self.assertEqual(result['episodes'][0]['status'], 'completed')
        self.assertEqual(result['episodes'][0]['summary'], 'legacy')

    def test_failure_from_old_bound_job_is_ignored_but_current_failure_is_saved(self):
        self.manager.attach_story_job(self.sid, 1, 'STORY-CURRENT')
        before = self.series_bytes()
        self.manager.mark_episode_failed(self.sid, 1, 'old failure', job_id='STORY-OLD')
        self.assertEqual(self.series_bytes(), before)
        result = self.manager.mark_episode_failed(self.sid, 1, 'current failure', job_id='STORY-CURRENT')
        self.assertEqual(result['episodes'][0]['status'], 'failed')
        self.assertEqual(result['episodes'][0]['error'], 'current failure')

    def test_bound_result_without_identity_cannot_take_ownership(self):
        self.manager.attach_story_job(self.sid, 1, 'STORY-CURRENT')
        before = self.series_bytes()
        self.manager.mark_episode_ready({'series_id': self.sid, 'episode_no': 1}, 'unowned.mp4')
        self.assertEqual(self.series_bytes(), before)


class StoryCoverFinalizationReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.manager = StoryManager(self.temporary.name)
        self.job = self.manager.create('Cover finalization fixture', scene_count=6)
        self.folder = self.manager.root / self.job['id']
        self.video = self.folder / 'videos' / 'final.mp4'
        self.video.write_bytes(b'unchanged rendered fixture video')

    def finish(self):
        return self.manager.save_video(self.job['id'], self.video, {'source_type': 'story_image_sequence'})

    def test_cancel_during_local_cover_cannot_be_overwritten_by_ready(self):
        def render(*args):
            self.manager.mark_cancelled(self.job['id'], 'cover', 'explicit user cancel')
            return {'cover_status': 'ready', 'cover_path': 'covers/stale.jpg'}
        with patch('core.story_manager.ensure_cover', side_effect=render):
            with self.assertRaisesRegex(ValueError, 'ยกเลิก'):
                self.finish()
        saved = self.manager.get(self.job['id'])
        self.assertTrue(saved['cancel_requested'])
        self.assertEqual(saved['status'], 'cancelled')
        self.assertEqual(saved['cancel_reason'], 'explicit user cancel')
        self.assertNotEqual(saved.get('cover_path'), 'covers/stale.jpg')
        self.assertEqual(self.video.read_bytes(), b'unchanged rendered fixture video')

    def test_resume_during_old_cover_cannot_be_finished_by_old_worker(self):
        def render(*args):
            self.manager.mark_cancelled(self.job['id'], 'cover')
            self.manager.mark_running(self.job['id'], 'voice')
            return {'cover_status': 'ready', 'cover_path': 'covers/stale.jpg'}
        with patch('core.story_manager.ensure_cover', side_effect=render):
            with self.assertRaises(ValueError):
                self.finish()
        saved = self.manager.get(self.job['id'])
        self.assertEqual(saved['status'], 'running')
        self.assertEqual(saved['pipeline_stage'], 'voice')
        self.assertNotEqual(saved.get('cover_path'), 'covers/stale.jpg')

    def test_manual_cover_and_new_metadata_during_render_are_preserved(self):
        def render(*args):
            AtomicJsonFile(self.folder / 'job.json').update(lambda manifest: {
                **manifest, 'cover_path': 'covers/manual.jpg', 'cover_revision': 'manual-choice',
                'cover_status': 'ready', 'pronunciation_notes': 'new user value'})
            return {'cover_path': 'covers/stale.jpg', 'cover_revision': 'local-old', 'cover_status': 'ready'}
        with patch('core.story_manager.ensure_cover', side_effect=render):
            result = self.finish()
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['cover_path'], 'covers/manual.jpg')
        self.assertEqual(result['cover_revision'], 'manual-choice')
        self.assertEqual(result['pronunciation_notes'], 'new user value')

    def test_newer_finalization_claim_wins_even_with_same_video_and_plan(self):
        def render(*args):
            with patch('core.story_manager.ensure_cover', return_value={'cover_status': 'ready'}):
                self.finish()
            return {'cover_path': 'covers/stale.jpg', 'cover_status': 'ready'}
        with patch('core.story_manager.ensure_cover', side_effect=render):
            with self.assertRaises(ValueError):
                self.finish()
        saved = self.manager.get(self.job['id'])
        self.assertEqual(saved['status'], 'ready')
        self.assertNotEqual(saved.get('cover_path'), 'covers/stale.jpg')

    def test_cover_renderer_does_not_block_other_thread_cancellation(self):
        threads, observed = [], []
        def render(*args):
            thread = threading.Thread(target=lambda: self.manager.mark_cancelled(self.job['id'], 'cover'))
            threads.append(thread)
            thread.start()
            thread.join(2)
            observed.append(not thread.is_alive())
            return {}
        try:
            with patch('core.story_manager.ensure_cover', side_effect=render):
                with self.assertRaisesRegex(ValueError, 'ยกเลิก'):
                    self.finish()
        finally:
            for thread in threads:
                thread.join(2)
        self.assertEqual(observed, [True])
        self.assertTrue(all(not thread.is_alive() for thread in threads))


if __name__ == '__main__':
    unittest.main()
