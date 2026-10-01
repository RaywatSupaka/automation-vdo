import unittest

from ui.main_window import MainWindow


class _Value:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class _Queue:
    def __init__(self):
        self.reason = ""
        self.running = None
        self.cancelled_series = ""
        self.failed_job = None

    def pause(self, reason="user"):
        self.reason = reason

    def running_item(self):
        return self.running

    def mark_failed_by_job(self, job_id, error):
        self.failed_job = (job_id, error)
        if self.running and self.running.get("job_id") == job_id:
            self.running = {**self.running, "status": "failed", "error": error}
            return self.running
        return None

    def cancel_drama_series(self, series_id):
        self.cancelled_series = series_id
        return {"cancelled": 2}

    def snapshot(self):
        return {"active_count": 0, "items": []}


class _Series:
    def __init__(self):
        self.failed = None
        self.cancelled_series = ""

    def mark_episode_failed(self, series_id, episode_no, error, job_id=""):
        self.failed = (series_id, episode_no, error)
        self.failed_job_id = job_id

    def get(self, series_id):
        return {
            "id": series_id,
            "title": "เรื่องเก่า",
            "status": "running",
            "episodes": [{"episode_no": 2, "status": "running", "story_job_id": "STORY-OLD"}],
        }

    def cancel_series(self, series_id):
        self.cancelled_series = series_id
        return {"cancelled": 2}

    def snapshot(self):
        return {"active_count": 0, "items": []}


class _Log:
    def warning(self, *args, **kwargs):
        return None


class DramaQueueGuardTests(unittest.TestCase):
    def test_old_checkpoint_callback_cannot_park_replacement_episode(self):
        from unittest.mock import Mock
        window = self._window()
        window.drama_series.get = lambda sid: {
            'id': sid, 'status': 'running',
            'episodes': [{'episode_no': 2, 'status': 'running', 'story_job_id': 'STORY-NEW'}]}
        window.story_queue.mark_failed_by_job = Mock()
        self.assertIsNone(window._park_drama_checkpoint_for_recovery('STORY-OLD', 'late callback'))
        window.story_queue.mark_failed_by_job.assert_not_called()

    def test_stale_episode_failure_does_not_pause_new_job_or_change_notice(self):
        import tempfile
        from core.drama_series import DramaSeriesManager
        with tempfile.TemporaryDirectory() as folder:
            window = self._window()
            window.drama_series = DramaSeriesManager(folder)
            series = window.drama_series.create('Callback fixture', '', 2, 6, 'chatgpt', [{'name': 'A'}])
            window.drama_series.attach_story_job(series['id'], 1, 'STORY-NEW')
            item = dict(mode='drama', series_id=series['id'], episode_no=1, job_id='STORY-OLD')
            self.assertFalse(window._pause_failed_drama_episode(item, 'late failure'))
            self.assertEqual(window.story_queue.reason, '')
            self.assertEqual(window.status.value, '')
            episode = window.drama_series.get(series['id'])['episodes'][0]
            self.assertEqual(episode['story_job_id'], 'STORY-NEW')
            self.assertEqual(episode['status'], 'running')

    def test_completed_episode_failure_does_not_pause_remaining_queue(self):
        import tempfile
        from core.drama_series import DramaSeriesManager
        with tempfile.TemporaryDirectory() as folder:
            window = self._window()
            window.drama_series = DramaSeriesManager(folder)
            series = window.drama_series.create('Callback fixture', '', 2, 6, 'chatgpt', [{'name': 'A'}])
            story = dict(id='STORY-ONE', series_id=series['id'], episode_no=1)
            window.drama_series.attach_story_job(series['id'], 1, story['id'])
            window.drama_series.mark_episode_ready(story, 'saved.mp4')
            item = dict(mode='drama', series_id=series['id'], episode_no=1, job_id=story['id'])
            self.assertFalse(window._pause_failed_drama_episode(item, 'late failure'))
            self.assertEqual(window.story_queue.reason, '')

    def _window(self):
        window = MainWindow.__new__(MainWindow)
        window.story_queue = _Queue()
        window.drama_series = _Series()
        window.status = _Value()
        window.log = _Log()
        window._story_pipeline_job_id = ""
        window.stories = type("Stories", (), {"get": lambda _self, _job_id: {
            "id": "STORY-OLD", "status": "cancelled", "series_id": "SERIES-OLD", "episode_no": 2,
        }})()
        window._desktop_set_notice = lambda *args: None
        window._write_console = lambda *args: None
        return window

    def test_failed_drama_episode_pauses_later_episodes(self):
        window = self._window()
        item = {"mode": "drama", "series_id": "SERIES-TEST", "episode_no": 2, "topic": "เรื่อง • EP 2"}
        self.assertTrue(window._pause_failed_drama_episode(item, "ภาพไม่ครบ"))
        self.assertEqual(window.story_queue.reason, "drama_failure:SERIES-TEST:2")
        self.assertEqual(window.drama_series.failed, ("SERIES-TEST", 2, "ภาพไม่ครบ"))
        self.assertIn("EP 2", window.status.value)

    def test_normal_story_failure_does_not_pause_batch_queue(self):
        window = self._window()
        self.assertFalse(window._pause_failed_drama_episode({"mode": "story"}, "ทดสอบ"))
        self.assertEqual(window.story_queue.reason, "")

    def test_cancel_drama_series_action_stops_running_job_and_releases_queue(self):
        window = self._window()
        window._story_pipeline_job_id = "STORY-OLD"
        window.story_queue.running = {
            "mode": "drama", "series_id": "SERIES-OLD", "job_id": "STORY-OLD",
        }
        cancelled = []
        window._cancel_story_pipeline = lambda: cancelled.append("STORY-OLD")
        result = window._desktop_execute_action("cancel_drama_series", {"series_id": "SERIES-OLD"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["cancelled"], 2)
        self.assertEqual(cancelled, ["STORY-OLD"])
        self.assertEqual(window.story_queue.cancelled_series, "SERIES-OLD")
        self.assertEqual(window.drama_series.cancelled_series, "SERIES-OLD")
        self.assertIn("พร้อมสร้างเรื่องใหม่", window.status.value)

    def test_orphaned_cancelled_drama_job_becomes_recoverable(self):
        window = self._window()
        window.story_queue.running = {
            "mode": "drama", "series_id": "SERIES-OLD", "episode_no": 2,
            "job_id": "STORY-OLD", "status": "running", "topic": "เรื่องเก่า • EP 2",
        }

        repaired = window._repair_orphaned_drama_checkpoint()

        self.assertEqual(repaired["status"], "failed")
        self.assertEqual(window.story_queue.failed_job[0], "STORY-OLD")
        self.assertEqual(window.drama_series.failed[:2], ("SERIES-OLD", 2))
        self.assertIn("กู้คืนไฟล์", window.drama_series.failed[2])
        self.assertEqual(window.story_queue.reason, "drama_failure:SERIES-OLD:2")


if __name__ == "__main__":
    unittest.main()
