"""A late Story heartbeat must not submit the same analysis in another tab."""

import logging
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.story_manager import StoryManager
from core.story_pipeline import story_existing_draft_notice, story_recovery_action
from ui.main_window import MainWindow


class StoryDuplicateDispatchTests(unittest.TestCase):
    def test_foreign_chatgpt_draft_requires_review_without_another_dispatch(self):
        job_id = "STORY-DRAFT"
        failure = "ผิดพลาด: เครื่องมือสร้างรูปภาพยังไม่พร้อม • ยังไม่กดส่งคำขอ"
        trace = [{"job_id": job_id, "action": "error", "message": failure,
                  "detail": {"tool_reason": "draft_changed", "dispatch_completed": False}}]
        notice = story_existing_draft_notice(job_id, failure, trace)
        self.assertIn("AI_WEB_WAIT_REVIEW", notice)
        self.assertEqual(story_recovery_action({"scene_count": 10}, notice), "")
        self.assertEqual(story_existing_draft_notice("STORY-OTHER", failure, trace), "")
        self.assertEqual(story_existing_draft_notice(job_id, failure, [{**trace[0],
            "detail": {"tool_reason": "draft_changed", "dispatch_completed": True}}]), "")

    def test_existing_chrome_does_not_open_another_tab_during_extension_heartbeat_gap(self):
        window = Mock()
        window._chrome_window_available.return_value = True
        window._compatible_extension.return_value = ({"connected": False}, None)
        with patch("ui.main_window.threading.Thread") as worker:
            result = MainWindow._activate_or_launch_chrome(window, "https://chatgpt.com/")
        self.assertEqual(result, "focused")
        window._open_url.assert_not_called()
        window.bridge.queue_extension_command.assert_not_called()
        worker.assert_called_once_with(target=window._focus_chrome_after_launch, daemon=True)

    def test_resume_launch_uses_saved_conversation_and_does_not_queue_twice(self):
        job_id = "STORY-RESUME"
        conversation = "https://chatgpt.com/c/6abea014-ed90-83ec-bc08-38f5d5ff8055"
        window = Mock()
        window._story_pipeline_job_id = job_id
        window._story_browser_launches = {}
        window.stories.root = Path("C:/fixture/stories")
        window.stories.get.return_value = {"id": job_id, "image_ai_provider": "chatgpt",
                                           "partial_generated_images": ["images/scene_01.png"]}
        window._story_browser_target_url = lambda *args: conversation
        with patch("ui.main_window.time.monotonic", return_value=100.0):
            self.assertTrue(MainWindow._launch_story_browser(
                window, job_id, "chatgpt", command_queued=True))
        window._activate_or_launch_chrome.assert_called_once_with(conversation)
        self.assertTrue(window._story_browser_launches[job_id]["resume_sent"])
        window.bridge.queue_extension_command.assert_not_called()

    def test_browser_target_prefers_exact_saved_conversation_only_for_resume(self):
        window = Mock()
        window.stories.root = Path("C:/fixture/stories")
        window.stories.get.return_value = {"id": "STORY-RESUME"}
        window._ai_web_url.return_value = "https://chatgpt.com/"
        target = {"required": True, "provider": "chatgpt",
                  "conversation_url": "https://chatgpt.com/c/saved-story"}
        with patch("core.ai_web_resume.ai_web_resume_target", return_value=target):
            self.assertEqual(MainWindow._story_browser_target_url(
                window, "STORY-RESUME", "chatgpt", "resume_chatgpt"), target["conversation_url"])
            self.assertEqual(MainWindow._story_browser_target_url(
                window, "STORY-RESUME", "chatgpt", "open_story_chatgpt"), "https://chatgpt.com/")
        with patch("core.ai_web_resume.ai_web_resume_target", return_value={**target, "conversation_url": ""}):
            with self.assertRaisesRegex(ValueError, "AI_WEB_RESUME_REVIEW"):
                MainWindow._story_browser_target_url(window, "STORY-RESUME", "chatgpt", "resume_chatgpt")

    def test_missing_saved_chat_reports_story_error_without_opening_root(self):
        window = Mock()
        window._story_pipeline_job_id = "STORY-RESUME"
        window._story_browser_launches = {}
        window.stories.get.return_value = {"id": "STORY-RESUME", "image_ai_provider": "chatgpt"}
        window._story_browser_target_url.side_effect = ValueError("AI_WEB_RESUME_REVIEW • missing URL")
        self.assertFalse(MainWindow._launch_story_browser(
            window, "STORY-RESUME", "chatgpt", action="resume_chatgpt", command_queued=True))
        window._activate_or_launch_chrome.assert_not_called()
        event = window.events.put.call_args.args[0]
        self.assertEqual(event[0], "story_error")
        self.assertIn("AI_WEB_RESUME_REVIEW", event[1]["value"])

    def test_protected_stale_reference_does_not_auto_recover(self):
        job = {"scene_count": 10, "partial_generated_images": ["images/scene_01.png"]}
        self.assertEqual(story_recovery_action(job, "AI_IMAGE_REFERENCE_UNCONFIRMED"), "")
        self.assertEqual(story_recovery_action(job, "AI_WEB_RESUME_REVIEW"), "")

    def test_open_command_is_single_per_story_run_even_after_ack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stories = StoryManager(root)
            products = ProductManager(root)
            job = stories.create("แอปเปิ้ล", scene_count=2)
            bridge = LocalBridge("127.0.0.1", 0, products, logging.getLogger("story-dispatch"), stories=stories)

            first = bridge.queue_extension_command("open_story_chatgpt", job["id"])
            self.assertEqual(bridge.queue_extension_command("open_story_chatgpt", job["id"])["id"], first["id"])
            self.assertEqual(len(bridge._extension_commands), 1)

            bridge._extension_commands[0]["status"] = "completed"
            self.assertEqual(bridge.queue_extension_command("open_story_chatgpt", job["id"])["id"], first["id"])
            self.assertEqual(len(bridge._extension_commands), 1)

            resumed = bridge.queue_extension_command("resume_chatgpt", job["id"])
            self.assertNotEqual(resumed["id"], first["id"])
            new_run = bridge.queue_extension_command("open_story_chatgpt", job["id"], run_id="RUN-NEW")
            self.assertNotEqual(new_run["id"], first["id"])

            trace = stories.root / job["id"] / "logs" / "extension_trace.jsonl"
            trace.parent.mkdir(parents=True, exist_ok=True)
            trace.write_text(json.dumps({"job_id": job["id"], "service": "chatgpt",
                                         "action": "ai_send_accepted", "run_id": "RUN-NEW"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "AI_WEB_WAIT_REVIEW"):
                bridge.queue_extension_command("open_story_chatgpt", job["id"], run_id="RUN-AFTER-RESTART")
            self.assertEqual(story_recovery_action(job, "AI_WEB_WAIT_REVIEW • คำขอเดิมยังไม่บันทึก"), "")


if __name__ == "__main__":
    unittest.main()
