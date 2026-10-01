"""Current278: no paid calls; actual wait/recovery/audit regression coverage."""
import json
import tempfile
import unittest
from pathlib import Path
from core.flow_review import FlowVideoReviewError
from core.product_pipeline import product_ai_recovery_action, product_runtime_recovery_action
from core.story_prompt_recovery import record_recovery
from ui.main_window import MainWindow
import test_flow_attachment_fallback_worker as attachment_fixture


class FlowVideoOnlyTests(unittest.TestCase):
    def test_repair_terminal_exits_wait_without_commands(self):
        fixture = attachment_fixture.FlowAttachmentFallbackWorkerTests()
        with self.assertRaises(FlowVideoReviewError) as caught:
            fixture.wait([{"flow_step": "error", "flow_failure_code": "FLOW_REPAIR_REVIEW",
                           "flow_message": "ครบสองรอบ"}])
        self.assertTrue(caught.exception.flow_retry_forbidden)
        self.assertIn("ไม่ใช้ภาพนิ่ง", str(caught.exception))

    def test_repair_progress_is_not_job_failure(self):
        fixture = attachment_fixture.FlowAttachmentFallbackWorkerTests()
        result = fixture.wait([
            {"flow_step": "generation_in_progress", "flow_message": "กำลังซ่อมพรอมต์ รอบ 1/2"},
            {"flow_step": "generation_in_progress", "flow_message": "คิวหนาแน่น กำลังสร้าง"},
            {"flow_step": "generation_complete"},
        ])
        self.assertEqual(result["flow_step"], "generation_complete")

    def test_review_never_enters_product_automatic_recovery(self):
        job = {"ai_status": "ready", "automation_status": "error", "partial_generated_images": ["saved"]}
        for action in (product_ai_recovery_action, product_runtime_recovery_action):
            self.assertEqual(action(job, "Google Flow FLOW_REPAIR_REVIEW timeout"), "")
            self.assertEqual(action(job, "Google Flow FLOW_ATTACHMENT_UNCONFIRMED"), "")

    def test_review_never_enters_story_automatic_recovery(self):
        window = MainWindow.__new__(MainWindow)
        for code in ("FLOW_REPAIR_REVIEW", "FLOW_SEND_REVIEW", "FLOW_POLICY_BLOCKED",
                     "FLOW_FACE_POLICY_BLOCKED", "FLOW_ATTACHMENT_UNCONFIRMED"):
            self.assertFalse(window._schedule_story_recovery("STORY-X", code + " timeout"))

    def test_review_diagnostics_are_bounded_durable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            job = {"id": "STORY-X", "scene_count": 6}
            body = {"index": 2, "run_id": "RUN-X", "event": {
                "phase": "needs_review", "round": 2, "request_id": "R2",
                "reason": "provider reason", "error": "helper parse error",
                "pause_reason": "review reference", "change_summary": "x" * 2000}}
            record_recovery(folder, job, body, flow=True)
            record_recovery(folder, job, body, flow=True)
            rows = json.loads((folder / "prompts/flow_recovery.json").read_text())["scenes"]["2"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["reason"], "provider reason")
            self.assertEqual(rows[0]["error"], "helper parse error")
            self.assertEqual(rows[0]["pause_reason"], "review reference")
            self.assertEqual(len(rows[0]["change_summary"]), 1500)
            self.assertFalse((folder / "job.json").exists())
            self.assertEqual(rows[0]["round"], 2)
