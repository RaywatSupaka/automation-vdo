import ast
import copy
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.cancellable_process import OperationCancelled, hidden_process_kwargs, run_cancellable
from core.story_pipeline import browser_progress, story_provider_failover_action, story_recovery_action


class StoryPipelineTests(unittest.TestCase):
    def test_accepted_analysis_timeout_never_resubmits_and_preserves_checkpoints(self):
        for partial in ([], ["generated/scene_01.png"]):
            job = {"scene_count": 6, "ai_status": "request_ready", "status": "running",
                   "partial_generated_images": partial, "auto_recovery_attempts": 0}
            original = copy.deepcopy(job)
            for message in (
                "ผิดพลาด: AI_ANALYSIS_TIMEOUT • ChatGPT Web • answer_length=900",
                "ผิดพลาด: ChatGPT Web ใช้เวลาตอบนานเกิน 6 นาที • ระบบไม่ส่ง Prompt ซ้ำ",
                "ผิดพลาด: Gemini Web ใช้เวลาตอบนานเกิน 6 นาที • ระบบไม่ส่ง Prompt ซ้ำ",
            ):
                with self.subTest(message=message, partial=partial):
                    self.assertEqual(story_recovery_action(job, message), "")
                    self.assertEqual(job, original)

    def test_gemini_image_failure_fails_over_to_chatgpt_checkpoint(self):
        job = {"image_ai_provider": "gemini", "analysis_status": "ready"}
        self.assertEqual(
            story_provider_failover_action(job, "Gemini Web ตอบกลับแล้วแต่ไม่ได้สร้างไฟล์ภาพใหม่"),
            "",
        )
        self.assertEqual(story_provider_failover_action({"image_ai_provider": "chatgpt"}, "ไม่ส่งรูป"), "")

    def test_gemini_invalid_json_fails_over_with_fresh_analysis(self):
        job = {"image_ai_provider": "gemini", "analysis_status": ""}
        self.assertEqual(
            story_provider_failover_action(job, "Gemini Web ไม่ได้ตอบข้อมูล JSON ตามรูปแบบที่โปรแกรมต้องใช้"),
            "",
        )

    def test_browser_percent_uses_completed_image_count(self):
        result = browser_progress(
            {"ai_job_id": "STORY-ONE", "ai_step": "generating_images", "ai_image_count": 5, "ai_message": "กำลังสร้าง"},
            "STORY-ONE", 10,
        )
        self.assertEqual(result["percent"], 35)
        self.assertEqual(result["detail"], "ภาพเสร็จจริง 5/10")
        self.assertIsNone(browser_progress({"ai_job_id": "STORY-OTHER"}, "STORY-ONE", 10))

    def test_image_attempt_diagnostic_preserves_progress_without_counting_a_reply_as_image(self):
        result = browser_progress(
            {"ai_job_id": "STORY-ONE", "ai_step": "image_attempt_result",
             "ai_image_count": 2, "ai_message": "CHATGPT_NO_IMAGE • completed_no_image_response"},
            "STORY-ONE", 10,
        )
        self.assertEqual(result["percent"], 23)
        self.assertEqual(result["detail"], "ตรวจคำตอบภาพก่อนตัดสินใจ • ภาพเสร็จจริง 2/10")
        self.assertEqual(result["step"], "image_attempt_result")
        self.assertIn("completed_no_image_response", result["message"])

    def test_image_recovery_keeps_saved_progress_and_is_not_terminal(self):
        for step in ("recovering_result", "recovering_response", "image_refresh_check", "image_restart_pending",
                     "image_restart_started", "image_result_verified"):
            with self.subTest(step=step):
                result = browser_progress({"ai_job_id": "STORY-ONE", "ai_step": step,
                                           "ai_image_count": 3}, "STORY-ONE", 15)
                self.assertEqual(result["percent"], 23)
                self.assertEqual(result["step"], step)
                self.assertIn("ภาพเสร็จจริง 3/15", result["detail"])
                if step == "image_result_verified":
                    self.assertIn("กำลังบันทึก", result["detail"])
                    self.assertNotIn("กู้ฉาก", result["detail"])

    def test_reports_json_repair_as_real_pre_image_progress(self):
        result = browser_progress(
            {"ai_job_id": "STORY-ONE", "ai_step": "repairing_analysis", "ai_image_count": 0, "ai_message": "กำลังจัดรูปแบบใหม่"},
            "STORY-ONE", 10,
        )
        self.assertEqual(result["percent"], 12)
        self.assertIn("ซ่อมรูปแบบ", result["detail"])

    def test_image_retry_keeps_completed_image_count(self):
        result = browser_progress(
            {"ai_job_id": "STORY-ONE", "ai_step": "retrying_image", "ai_image_count": 9, "ai_message": "กำลังลองภาพสุดท้ายใหม่"},
            "STORY-ONE", 10,
        )
        self.assertEqual(result["percent"], 51)
        self.assertEqual(result["detail"], "ภาพเสร็จจริง 9/10")

    def test_cancel_event_stops_running_child_process(self):
        event = threading.Event()
        threading.Timer(0.2, event.set).start()
        started = time.monotonic()
        with self.assertRaises(OperationCancelled):
            run_cancellable([sys.executable, "-c", "import time; time.sleep(10)"], cancel_event=event, timeout=15)
        self.assertLess(time.monotonic() - started, 3)

    def test_partial_chatgpt_job_resumes_but_uncertain_voice_does_not_repeat(self):
        partial = {
            "scene_count": 10, "ai_status": "request_ready", "status": "running",
            "partial_generated_images": [f"generated/scene_{i:02d}.png" for i in range(1, 9)],
        }
        self.assertEqual(story_recovery_action(partial, "หน้าเว็บขาดการเชื่อมต่อ"), "resume_chatgpt")
        voice_pending = {"scene_count": 10, "ai_status": "ready", "generated_images": [str(i) for i in range(10)], "pipeline_stage": "voice"}
        self.assertEqual(story_recovery_action(voice_pending, "network timeout"), "")
        voice_checkpointed = dict(voice_pending, voice_status="queued", voice_job_id="TTS-SAVED-1")
        self.assertEqual(story_recovery_action(voice_checkpointed, "network timeout"), "voice")
        voice_saved = dict(voice_pending, voice_status="ready", voice_path="audio/narration.mp3")
        self.assertEqual(story_recovery_action(voice_saved, "ffmpeg stopped"), "render")

    def test_auth_and_credit_errors_require_user_action(self):
        job = {"scene_count": 10, "ai_status": "request_ready", "status": "running"}
        self.assertEqual(story_recovery_action(job, "กรุณาเข้าสู่ระบบ ChatGPT"), "")
        self.assertEqual(story_recovery_action(job, "เครดิตไม่พอ"), "")

    def test_story_identity_and_refusal_stop_auto_recovery_without_changing_checkpoints(self):
        job = {
            "scene_count": 6, "ai_status": "request_ready", "status": "running",
            "analysis_status": "ready", "image_ai_provider": "gemini",
            "partial_generated_images": ["generated/scene_01.png", "generated/scene_02.png"],
            "scene_prompts": ["Doctor Doom in Latveria"] * 6,
            "narration_script": "ด็อกเตอร์ ดูม อยู่ในแลตเวอเรีย",
            "voice_job_id": "paid-existing-queue",
            "auto_recovery_attempts": 0,
        }
        original = copy.deepcopy(job)
        for code in ("STORY_CONTENT_MISMATCH", "STORY_IMAGE_REFUSED", "STORY_SCENE_PROMPT_STALE",
                     "GEMINI_TEXT_SEND_REVIEW", "AI_ANALYSIS_TIMEOUT", "ChatGPT Web ใช้เวลาตอบนานเกิน 6 นาที"):
            for message in (f"{code} • ต้องตรวจเนื้อเรื่อง", f"ผิดพลาด: {code.lower()} • ต้องตรวจภาพ"):
                with self.subTest(message=message):
                    self.assertEqual(story_recovery_action(job, message), "")
                    self.assertEqual(story_provider_failover_action(job, message), "")
                    self.assertEqual(job, original)
        # The narrow terminal check must not disable an unrelated recoverable
        # disconnection or silently consume the existing recovery budget.
        self.assertEqual(story_recovery_action(job, "หน้าเว็บขาดการเชื่อมต่อ"), "resume_chatgpt")
        self.assertEqual(job, original)

    def test_desktop_scheduler_does_not_reopen_identity_or_refusal_terminal(self):
        source = Path(__file__).resolve().parents[1] / "ui" / "main_window.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        method = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef) and node.name == "_schedule_story_recovery")
        namespace = {
            "story_provider_failover_action": story_provider_failover_action,
            "story_recovery_action": story_recovery_action,
        }
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
        job = {"scene_count": 6, "ai_status": "request_ready", "auto_recovery_attempts": 0}
        # Only reading the job is available. Reaching mark_recovering, a timer,
        # or any browser/restart action would fail instead of hiding a retry.
        engine = SimpleNamespace(stories=SimpleNamespace(get=lambda job_id: job))
        for code in ("STORY_CONTENT_MISMATCH", "STORY_IMAGE_REFUSED", "STORY_SCENE_PROMPT_STALE"):
            with self.subTest(code=code):
                self.assertFalse(namespace["_schedule_story_recovery"](engine, "STORY-TEST", f"ผิดพลาด: {code}"))

    def test_provider_redirect_can_fall_back_without_discarding_job(self):
        job = {"scene_count": 10, "ai_status": "request_ready", "status": "running"}
        self.assertEqual(story_recovery_action(job, "Gemini Web ถูกเปลี่ยนเส้นทางไปหน้าตรวจสอบของ Google"), "resume_chatgpt")

    def test_browser_progress_reports_human_verification_without_failing_job(self):
        result = browser_progress(
            {"ai_job_id": "STORY-ONE", "ai_step": "user_action_required", "ai_image_count": 4,
             "ai_message": "กรุณาติ๊ก ฉันไม่ใช่โปรแกรมอัตโนมัติ"},
            "STORY-ONE", 10,
        )
        self.assertEqual(result["step"], "user_action_required")
        self.assertGreater(result["percent"], 5)
        self.assertIn("Chrome", result["detail"])

    def test_browser_progress_distinguishes_login_from_captcha(self):
        result = browser_progress(
            {"ai_job_id": "STORY-ONE", "ai_step": "user_action_required", "ai_image_count": 2,
             "ai_message": "กรุณาเข้าสู่ระบบ Gemini Web", "ai_action_kind": "login_required",
             "ai_service": "gemini"},
            "STORY-ONE", 10,
        )
        self.assertEqual(result["action_kind"], "login_required")
        self.assertEqual(result["service"], "gemini")
        self.assertIn("Login", result["detail"])

    def test_background_children_are_hidden_on_windows(self):
        kwargs = hidden_process_kwargs()
        if sys.platform == "win32":
            self.assertTrue(kwargs.get("creationflags"))
            self.assertIsNotNone(kwargs.get("startupinfo"))


if __name__ == "__main__":
    unittest.main()
