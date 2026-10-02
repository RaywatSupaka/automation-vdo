"""Focused guards for Story image prompting and refusal diagnostics."""

import tempfile
import unittest
import json
from pathlib import Path

from core.story_failure_timeline import story_failure_timeline
from core.story_manager import StoryManager
from core.story_pipeline import story_image_refusal_notice, story_recovery_action


class StoryPromptSafetyTests(unittest.TestCase):
    def test_topic_only_story_does_not_request_an_invented_child_age(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = StoryManager(Path(directory))
            job = manager.create("แอปเปิ้ล", scene_count=2)
            prompt = (manager.root / job["id"] / "prompts/chatgpt_request.txt").read_text(encoding="utf-8")
            self.assertIn("อายุเฉพาะเมื่อผู้ใช้ระบุไว้", prompt)
            self.assertIn("ไม่แต่งตัวเลขอายุเด็ก", prompt)
            self.assertIn("เพิ่มเด็กมนุษย์เองเพื่อแทนผลไม้", prompt)
            self.assertIn("fully clothed, non-sexual scenes", prompt)

    def test_explicit_user_age_remains_in_the_story_request(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = StoryManager(Path(directory))
            job = manager.create("แอปเปิ้ลการ์ตูน", "ตัวละครแอปเปิ้ลอายุ 9 ปี", scene_count=2)
            prompt = (manager.root / job["id"] / "prompts/chatgpt_request.txt").read_text(encoding="utf-8")
            self.assertIn("ตัวละครแอปเปิ้ลอายุ 9 ปี", prompt)
            self.assertIn("อายุเฉพาะเมื่อผู้ใช้ระบุไว้", prompt)

    def test_helper_failure_reports_the_owned_policy_refusal(self):
        rows = [
            {"sequence": 1, "job_id": "STORY-OTHER", "run_id": "RUN-ONE", "action": "image_attempt_result",
             "message": "ภาพ 8 • policy_refusal"},
            {"sequence": 2, "job_id": "STORY-APPLE", "run_id": "RUN-ONE", "action": "image_attempt_result",
             "message": "ภาพ 1 • ครั้ง 1 • CHATGPT_NO_IMAGE • policy_refusal • provider refusal"},
            {"sequence": 3, "job_id": "STORY-APPLE", "run_id": "RUN-ONE", "action": "error",
             "message": "ผิดพลาด: แท็บช่วยงานมีรูปค้างอยู่ ไม่แทนที่หรือใช้รูปที่ยังยืนยันไม่ได้"},
        ]
        failure = rows[-1]["message"]
        notice = story_image_refusal_notice("STORY-APPLE", failure, rows)
        self.assertIn("STORY_IMAGE_REFUSED", notice)
        self.assertIn("ภาพฉาก 1", notice)
        self.assertIn("ไม่ได้บอกข้อห้ามที่เจาะจง", notice)
        self.assertEqual(story_recovery_action({"scene_count": 2}, notice), "")
        self.assertEqual(story_image_refusal_notice("STORY-OTHER", failure, rows), "")
        self.assertEqual(story_image_refusal_notice("STORY-APPLE", "network timeout", rows), "")

    def test_different_run_cannot_supply_refusal_reason(self):
        rows = [
            {"sequence": 1, "job_id": "STORY-APPLE", "run_id": "RUN-OLD", "action": "image_attempt_result",
             "message": "ภาพ 1 • policy_refusal"},
            {"sequence": 2, "job_id": "STORY-APPLE", "run_id": "RUN-NEW", "action": "error",
             "message": "ผิดพลาด: แท็บช่วยงานมีรูปค้างอยู่"},
        ]
        self.assertEqual(story_image_refusal_notice("STORY-APPLE", rows[-1]["message"], rows), "")

    def test_local_failure_report_shows_prompt_refusal_and_recovery_in_order(self):
        with tempfile.TemporaryDirectory() as directory:
            job_id = "STORY-APPLE"
            job_dir = Path(directory) / job_id
            (job_dir / "logs").mkdir(parents=True)
            (job_dir / "prompts").mkdir()
            (job_dir / "job.json").write_text("{}", encoding="utf-8")
            (job_dir / "prompts/chatgpt_request.txt").write_text("ขอเรื่องแอปเปิ้ล", encoding="utf-8")
            rows = [
                {"job_id": job_id, "run_id": "RUN-A", "at": "10:00", "action": "image_prompt_ready",
                 "message": "ภาพ 1 พร้อมส่ง", "detail": {"scene_index": 1, "prompt": "ภาพแอปเปิ้ลการ์ตูน"}},
                {"job_id": "STORY-OTHER", "run_id": "RUN-A", "at": "10:01", "action": "error",
                 "message": "SECRET_OTHER_JOB"},
                {"job_id": job_id, "run_id": "RUN-A", "at": "10:02", "action": "ai_send_accepted",
                 "message": "เว็บรับแล้ว"},
                {"job_id": job_id, "run_id": "RUN-A", "at": "10:03", "action": "image_attempt_result",
                 "message": "policy_refusal • คำตอบจากเว็บ"},
                {"job_id": job_id, "run_id": "RUN-A", "at": "10:04", "action": "recovering_images",
                 "message": "ช่วยปรับพรอมต์"},
                {"job_id": job_id, "run_id": "RUN-A", "at": "10:05", "action": "error",
                 "message": "แท็บช่วยงานมีรูปค้างอยู่"},
            ]
            trace_file = job_dir / "logs/extension_trace.jsonl"
            trace_file.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
            report = story_failure_timeline(directory, job_id)
            self.assertIn("พรอมต์ภาพฉาก 1 (ยืนยันว่าเว็บรับแล้ว):\nภาพแอปเปิ้ลการ์ตูน", report)
            self.assertLess(report.index("policy_refusal"), report.index("ช่วยปรับพรอมต์"))
            self.assertLess(report.index("ช่วยปรับพรอมต์"), report.index("แท็บช่วยงานมีรูปค้างอยู่"))
            self.assertIn("ขอเรื่องแอปเปิ้ล", report)
            self.assertNotIn("SECRET_OTHER_JOB", report)
            self.assertIn("ระบุสาเหตุเฉพาะไม่ได้", report)
            self.assertEqual(story_failure_timeline(directory, "../STORY-OTHER"), "")


if __name__ == "__main__":
    unittest.main()
