"""Exercise Story terminal handling without opening the desktop or browser."""
import queue
import threading
import unittest
from unittest.mock import Mock

from core.local_bridge import LocalBridge
from ui.main_window import MainWindow


class StoryAISendDraftTests(unittest.TestCase):
    def test_missing_gemini_text_owner_keeps_scene_and_draft_without_restart(self):
        message = 'FLOW_PLAN_REVIEW • GEMINI_TEXT_REQUEST_REVIEW • ยังยืนยันคำถามของฉากนี้ไม่ได้'
        window = self.window(ai_message=message, detail={"request_owner_found": False,
                             "draft_still_present": True, "request_recovery_wait_ms": 30000})
        self.error(window, message=message)
        window._schedule_story_recovery.assert_not_called()
        window._close_automation_browser.assert_not_called()
        window.bridge.queue_extension_command.assert_not_called()

    def test_current_image_wait_review_preserves_tab_and_never_restarts_whole_story(self):
        message='STORY_IMAGE_RECEIPT_REVIEW • ภาพฉาก 11 • CHATGPT_IMAGE_RESULT_GENERATING'
        window=self.window(ai_message=message,detail={})
        self.error(window,message=message)
        window._schedule_story_recovery.assert_not_called()
        window._close_automation_browser.assert_not_called()
        window.bridge.queue_extension_command.assert_not_called()

    message = "ส่งคำสั่งคลิกปุ่มส่ง ChatGPT Web หนึ่งครั้งแล้ว แต่หน้าเว็บยังไม่ยืนยันภายใน 60 วินาที"

    def window(self, *, detail=None, **client_fields):
        window = MainWindow.__new__(MainWindow)
        window.events = queue.Queue()
        window._story_pipeline_job_id = "STORY-SEND"
        window._story_cancel_event = threading.Event()
        for name in (
            "_poll_desktop_requests", "_schedule_story_recovery", "_capture_automation_error_log",
            "_write_console", "_creation_story_failure", "_pause_failed_drama_episode",
            "_finish_story_popup", "_close_automation_browser", "_schedule_next_story_queue_item",
        ):
            setattr(window, name, Mock())
        for name in ("bridge", "stories", "story_queue", "story_status", "status", "log"):
            setattr(window, name, Mock())
        window._schedule_story_recovery.return_value = False
        window.stories.get.return_value = {"pipeline_stage": "chatgpt", "video_generation_mode": "image_motion"}
        window.story_queue.mark_failed_by_job.return_value = None
        client = {
            "ai_job_id": "STORY-SEND", "version": LocalBridge.REQUIRED_EXTENSION_VERSION,
            "ai_tab_id": 42, "ai_step": "error", "ai_message": self.message,
            "ai_send_diagnostics": detail if detail is not None else {
                "send_method": "single_trusted_ai_send_unconfirmed", "dispatch_completed": True,
                "trusted_click_seen": False, "draft_still_present": True,
                "click_events": [{"type": "pointerdown", "trusted": True},
                                 {"type": "mousedown", "trusted": True}],
            },
            **client_fields,
        }
        window.bridge.extension_status.return_value = {"clients": [client], "client": client}
        return window

    def error(self, window, *, message=None, cancel_event=None):
        window.events.put(("story_error", {
            "job_id": "STORY-SEND", "cancel_event": cancel_event or window._story_cancel_event,
            "value": message or self.message,
        }))
        window._poll_once()

    def test_unconfirmed_owned_send_keeps_draft_without_recovery_and_still_fails_job(self):
        window = self.window()
        window._schedule_story_recovery.return_value = True
        self.error(window)
        window._schedule_story_recovery.assert_not_called()
        window._close_automation_browser.assert_not_called()
        window.bridge.queue_extension_command.assert_not_called()
        window.stories.mark_failed.assert_called_once_with("STORY-SEND", "chatgpt", self.message)
        window.story_queue.mark_failed_by_job.assert_called_once_with("STORY-SEND", self.message)
        window._creation_story_failure.assert_called_once_with(None, self.message)
        window._finish_story_popup.assert_called_once_with("error", "สร้าง Story Shorts ไม่สำเร็จ", self.message)
        self.assertEqual(window._story_pipeline_job_id, "")
        self.assertIsNone(window._story_cancel_event)

    def test_captured_click_and_uncertain_release_also_keep_unacknowledged_draft(self):
        for detail in (
            {"send_method": "single_trusted_ai_send", "dispatch_completed": True,
             "trusted_click_seen": True, "draft_still_present": True},
            {"send_method": "single_trusted_ai_send_unconfirmed", "gesture_phase": "release_uncertain",
             "dispatch_completed": False, "draft_still_present": True},
        ):
            with self.subTest(detail=detail):
                window = self.window(detail=detail)
                self.error(window)
                window._schedule_story_recovery.assert_not_called()
                window._close_automation_browser.assert_not_called()

    def test_missing_or_invalid_evidence_preserves_normal_error_cleanup(self):
        for detail in (
            {}, {"dispatch_completed": True},
            {"send_method": "single_trusted_ai_send_unconfirmed", "dispatch_completed": "true", "draft_still_present": True},
            {"send_method": "single_trusted_ai_send_unconfirmed", "dispatch_completed": True, "draft_still_present": "true"},
            {"send_method": "single_trusted_ai_send_unconfirmed", "dispatch_completed": True, "draft_still_present": False},
            {"send_method": "single_trusted_ai_send_unconfirmed", "dispatch_completed": True,
             "draft_still_present": True, "submission_proof": "new_user_turn"},
            {"send_method": "single_trusted_ai_send_unconfirmed", "gesture_phase": "not_started", "draft_still_present": True},
        ):
            with self.subTest(detail=detail):
                window = self.window(detail=detail)
                self.error(window)
                window._schedule_story_recovery.assert_called_once_with("STORY-SEND", self.message)
                window._close_automation_browser.assert_called_once_with("STORY-SEND", "Story Shorts หยุดที่ Checkpoint")

    def test_other_job_version_step_message_or_unowned_tab_cannot_keep_browser(self):
        for fields in (
            {"ai_job_id": "STORY-OLD", "flow_job_id": "STORY-SEND"},
            {"version": "0.0.1"}, {"version": ""}, {"ai_step": "complete"},
            {"ai_message": "old send error"}, {"ai_tab_id": 0}, {"ai_tab_id": True},
        ):
            with self.subTest(fields=fields):
                window = self.window(**fields)
                self.error(window)
                window._close_automation_browser.assert_called_once()
        window = self.window()
        self.error(window, message="Voice download failed")
        window._close_automation_browser.assert_called_once()

    def test_cancelled_or_stale_story_event_cannot_invoke_preservation(self):
        window = self.window()
        self.error(window, cancel_event=threading.Event())
        window.stories.mark_failed.assert_not_called()
        window.bridge.extension_status.assert_not_called()
        window._story_cancel_event.set()
        self.assertFalse(window._should_keep_story_ai_draft("STORY-SEND", self.message))
        window.bridge.extension_status.assert_not_called()

    def test_existing_flow_checkpoint_keeps_browser_without_ai_evidence(self):
        window = self.window(detail={})
        window.stories.get.return_value = {"pipeline_stage": "google_flow", "video_generation_mode": "google_flow"}
        self.error(window)
        window._schedule_story_recovery.assert_called_once()
        window._close_automation_browser.assert_not_called()

    def test_saved_answer_review_keeps_owned_tab_even_when_composer_empty(self):
        for code in ("STORY_IMAGE_RECEIPT_REVIEW", "STORY_IMAGE_DOWNLOAD_PENDING",
                     "STORY_IMAGE_CHECKPOINT_UNREADABLE", "STORY_ANALYSIS_CHECKPOINT_REVIEW",
                     "GEMINI_IMAGE_SEND_REVIEW", "GEMINI_TEXT_SEND_REVIEW"):
            with self.subTest(code=code):
                message = f"ผิดพลาด: {code} • ตรวจข้อมูลเดิม"
                window = self.window(detail={"draft_still_present": False}, ai_message=message)
                self.error(window, message=message)
                window._close_automation_browser.assert_not_called()
                window._schedule_story_recovery.assert_not_called()
                window.stories.mark_failed.assert_called_once()
                window._creation_story_failure.assert_called_once()
                window.bridge.queue_extension_command.assert_not_called()

    def test_analysis_timeout_keeps_owned_answer_and_never_opens_another_chat(self):
        for message in (
            "ผิดพลาด: AI_ANALYSIS_TIMEOUT • ChatGPT Web • answer_length=900",
            "ผิดพลาด: ChatGPT Web ใช้เวลาตอบนานเกิน 6 นาที • ระบบไม่ส่ง Prompt ซ้ำ",
            "ผิดพลาด: Gemini Web ใช้เวลาตอบนานเกิน 6 นาที • ระบบไม่ส่ง Prompt ซ้ำ",
        ):
            with self.subTest(message=message):
                window = self.window(detail={"draft_still_present": False}, ai_message=message)
                window._schedule_story_recovery.return_value = True
                self.error(window, message=message)
                window._schedule_story_recovery.assert_not_called()
                window._close_automation_browser.assert_not_called()
                window.bridge.queue_extension_command.assert_not_called()
                window.stories.mark_failed.assert_called_once_with("STORY-SEND", "chatgpt", message)
                window._creation_story_failure.assert_called_once()

    def test_analysis_timeout_cannot_preserve_an_unowned_or_stale_tab(self):
        message = "ผิดพลาด: AI_ANALYSIS_TIMEOUT • ChatGPT Web"
        for fields in ({"ai_job_id": "STORY-OTHER"}, {"version": "0.0.1"},
                       {"ai_tab_id": 0}, {"ai_message": "old error"}, {"ai_step": "complete"}):
            with self.subTest(fields=fields):
                window = self.window(detail={}, **({"ai_message": message} | fields))
                self.assertFalse(window._should_keep_story_ai_draft("STORY-SEND", message))

    def test_receipt_error_from_unowned_client_does_not_change_cleanup(self):
        message = "ผิดพลาด: STORY_IMAGE_RECEIPT_REVIEW"
        for fields in ({"ai_job_id": "STORY-OTHER"}, {"version": "0.15.259"},
                       {"ai_tab_id": 0}, {"ai_message": "old error"}):
            with self.subTest(fields=fields):
                window = self.window(detail={}, **({"ai_message": message} | fields))
                self.error(window, message=message)
                window._close_automation_browser.assert_called_once()


if __name__ == "__main__":
    unittest.main()
