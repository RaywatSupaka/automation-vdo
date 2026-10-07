"""Run ownership regressions using real methods without a GUI or paid jobs."""
import queue
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ui.main_window import MainWindow


class PipelineEventOwnershipTests(unittest.TestCase):
    def window(self):
        window = MainWindow.__new__(MainWindow)
        window.events = queue.Queue()
        window._product_pipeline_job_id = "JOB-SAME"
        window._product_cancel_event = threading.Event()
        window._story_pipeline_job_id = "STORY-SAME"
        window._story_cancel_event = threading.Event()
        for name in (
            "_poll_desktop_requests", "_write_console", "_refresh", "_finish_product_popup",
            "_close_automation_browser", "_creation_product_terminal", "_schedule_story_recovery",
            "_handle_product_pipeline_ready", "_capture_automation_error_log", "_desktop_set_notice",
            "_schedule_product_runtime_recovery", "_product_error_service", "_update_story_progress",
            "_render_story", "_activate_or_launch_chrome", "_launch_story_browser", "_ai_web_url",
        ):
            setattr(window, name, Mock())
        for name in (
            "root", "status", "story_status", "story_job_id", "product_run_button", "bridge",
            "stories", "products", "story_queue", "log", "_story_progress_message", "_story_progress_detail",
        ):
            setattr(window, name, Mock())
        window._creation_product_terminal.return_value = True
        window._schedule_story_recovery.return_value = True
        window._compatible_extension = Mock(return_value=({}, True))
        window._chrome_window_available = Mock(return_value=True)
        window.stories.get.return_value = {"scene_count": 6, "image_ai_provider": "gemini"}
        window.stories.root = Path(__file__).parent / 'fixtures' / 'no-story-trace'
        return window

    @staticmethod
    def event(job_id, cancel_event, value):
        return {"job_id": job_id, "cancel_event": cancel_event, "value": value}

    def test_old_product_cancel_ack_cannot_cancel_same_job_resumed_before_event_poll(self):
        window = self.window()
        original = window._product_cancel_event
        original.set()
        window._product_pipeline_job_id = ""
        window._product_cancel_event = None
        resumed = threading.Event()
        def resume_before_worker_events():
            window._product_pipeline_job_id = "JOB-SAME"
            window._product_cancel_event = resumed
        window._poll_desktop_requests.side_effect = resume_before_worker_events
        window.events.put(("product_pipeline_cancelled", self.event("JOB-SAME", original, "JOB-SAME")))
        window._poll_once()
        self.assertEqual(window._product_pipeline_job_id, "JOB-SAME")
        self.assertIs(window._product_cancel_event, resumed)
        window._close_automation_browser.assert_not_called()
        window._creation_product_terminal.assert_not_called()

    def test_current_product_cancel_ack_still_reconciles_queue_once(self):
        window = self.window()
        current = window._product_cancel_event
        current.set()
        payload = self.event("JOB-SAME", current, "JOB-SAME")
        window.events.put(("product_pipeline_cancelled", payload))
        window.events.put(("product_pipeline_cancelled", payload))
        window._poll_once()
        self.assertEqual(window._product_pipeline_job_id, "")
        self.assertIsNone(window._product_cancel_event)
        window._creation_product_terminal.assert_called_once()

    def test_import_failure_and_cancel_before_first_progress_keep_current_event_owner(self):
        for kind in ("product_pipeline_cancelled", "product_pipeline_error"):
            with self.subTest(kind=kind):
                window = self.window()
                window._product_pipeline_job_id = "กำลังสร้าง Job"
                value = "" if kind.endswith("cancelled") else ("", "invalid link")
                window.events.put((kind, self.event("", window._product_cancel_event, value)))
                window._poll_once()
                self.assertEqual(window._product_pipeline_job_id, "")
                window._creation_product_terminal.assert_called_once()

    def test_old_product_ready_and_error_never_clear_new_run(self):
        for kind, value in (
            ("product_pipeline_ready", ("JOB-SAME", "old-final.mp4", {})),
            ("product_pipeline_error", ("JOB-SAME", "old error")),
        ):
            with self.subTest(kind=kind):
                window = self.window()
                current = window._product_cancel_event
                window.events.put((kind, self.event("JOB-SAME", threading.Event(), value)))
                window._poll_once()
                self.assertIs(window._product_cancel_event, current)
                self.assertEqual(window._product_pipeline_job_id, "JOB-SAME")
                window._handle_product_pipeline_ready.assert_not_called()
                window._creation_product_terminal.assert_not_called()

    def test_current_product_ready_preserves_existing_result_handler_payload(self):
        window = self.window()
        value = ("JOB-SAME", "final.mp4", {"clip_count": 3})
        window.events.put(("product_pipeline_ready", self.event("JOB-SAME", window._product_cancel_event, value)))
        window._poll_once()
        window._handle_product_pipeline_ready.assert_called_once_with(value)

    def test_old_or_unowned_story_error_cannot_fail_new_story(self):
        for payload in (
            "legacy unowned error",
            self.event("STORY-OLD", threading.Event(), "old error"),
            self.event("STORY-SAME", threading.Event(), "same job previous attempt"),
        ):
            with self.subTest(payload=payload):
                window = self.window()
                current = window._story_cancel_event
                window.events.put(("story_error", payload))
                window._poll_once()
                self.assertIs(window._story_cancel_event, current)
                self.assertEqual(window._story_pipeline_job_id, "STORY-SAME")
                window.stories.mark_failed.assert_not_called()
                window._schedule_story_recovery.assert_not_called()

    def test_current_story_error_still_uses_existing_recovery(self):
        window = self.window()
        window.events.put(("story_error", self.event("STORY-SAME", window._story_cancel_event, "temporary error")))
        window._poll_once()
        window._schedule_story_recovery.assert_called_once_with("STORY-SAME", "temporary error")

    def test_old_story_ready_never_finishes_or_closes_new_story(self):
        window = self.window()
        window.events.put(("story_ready", self.event("STORY-SAME", threading.Event(), ({"id": "STORY-SAME"}, "old.mp4", {}))))
        window._poll_once()
        window.story_queue.mark_completed_by_job.assert_not_called()
        window._close_automation_browser.assert_not_called()
        self.assertEqual(window._story_pipeline_job_id, "STORY-SAME")

    def test_cleared_state_drops_previously_current_terminals(self):
        window = self.window()
        event = window._product_cancel_event
        window._product_cancel_event = None
        window._product_pipeline_job_id = ""
        window.events.put(("product_pipeline_error", self.event("JOB-SAME", event, ("JOB-SAME", "old error"))))
        window._poll_once()
        window._creation_product_terminal.assert_not_called()
        window._schedule_product_runtime_recovery.assert_not_called()

    def test_story_worker_error_keeps_original_event_even_when_run_changes(self):
        window = self.window()
        original = threading.Event()
        window._story_worker("STORY-OLD", Mock(side_effect=RuntimeError("old socket error")), original)
        kind, payload = window.events.get_nowait()
        self.assertEqual(kind, "story_error")
        self.assertEqual(payload["job_id"], "STORY-OLD")
        self.assertIs(payload["cancel_event"], original)
        self.assertEqual(payload["value"], "old socket error")

    def test_story_recovery_timer_cannot_restart_same_job_after_cancel_and_resume(self):
        window = self.window()
        original = window._story_cancel_event
        job = {"id": "STORY-SAME", "auto_recovery_attempts": 1, "scene_count": 6, "analysis_status": "ready", "image_ai_provider": "gemini"}
        window.stories.get.return_value = job
        window.stories.mark_recovering.return_value = job
        with patch("ui.main_window.story_provider_failover_action", return_value=None), patch("ui.main_window.story_recovery_action", return_value="resume_chatgpt"):
            self.assertTrue(MainWindow._schedule_story_recovery(window, "STORY-SAME", "temporary error"))
        callback = window.root.after.call_args.args[1]
        original.set()
        window._story_cancel_event = threading.Event()
        callback()
        window.bridge.clear_ai_progress.assert_not_called()
        window.bridge.queue_extension_command.assert_not_called()
        window._render_story.assert_not_called()

    def test_current_story_recovery_still_reuses_provider_and_checkpoint(self):
        window = self.window()
        current = window._story_cancel_event
        window._resume_story_automatically("STORY-SAME", "resume_chatgpt", "gemini", cancel_event=current)
        window.bridge.clear_ai_progress.assert_called_once_with("STORY-SAME")
        window.bridge.queue_extension_command.assert_called_once_with("resume_chatgpt", "STORY-SAME", provider_hint="gemini")


if __name__ == "__main__":
    unittest.main()
