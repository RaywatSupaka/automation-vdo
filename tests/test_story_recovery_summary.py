import json
import tempfile
import unittest
from pathlib import Path

from core.story_recovery_summary import story_recovery_summary
from core.story_failure_timeline import story_failure_timeline


class StoryRecoverySummaryTests(unittest.TestCase):
    def test_saved_scenes_and_unsent_failure_are_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / "generated").mkdir()
            for index in (1, 2):
                (folder / "generated" / f"scene_{index:02}.png").write_bytes(b"saved")
            job = {
                "scene_count": 10, "analysis_status": "ready",
                "partial_generated_images": ["generated/scene_01.png", "generated/scene_02.png"],
                "last_error": "STORY_IMAGE_RECEIPT_REVIEW • ภาพฉาก 3 • "
                              "CHATGPT_IMAGE_RESULT_SEND_NOT_STARTED",
            }
            self.assertEqual(story_recovery_summary(job, folder), {
                "analysis_ready": True, "saved_image_scenes": [1, 2],
                "failed_image_scene": 3, "send_not_started": True,
            })

    def test_missing_and_outside_files_are_not_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "job"
            folder.mkdir()
            job = {"scene_count": 4, "partial_generated_images": [
                "generated/scene_01.png", "../scene_02.png", "generated/scene_09.png"],
                "last_error": "AI_WEB_WAIT_REVIEW • ก่อนสร้างภาพ"}
            self.assertEqual(story_recovery_summary(job, folder)["saved_image_scenes"], [])
            self.assertEqual(story_recovery_summary(job, folder)["failed_image_scene"], 0)

    def test_reference_error_keeps_scene_from_latest_trace_without_claiming_send(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "STORY-TEST123"
            (folder / "logs").mkdir(parents=True)
            (folder / "generated").mkdir()
            (folder / "generated" / "scene_02.png").write_bytes(b"saved")
            rows = [
                {"job_id": folder.name, "action": "image_checkpoint_saved", "message": "ภาพ 2"},
                {"job_id": folder.name, "action": "image_attempt_result",
                 "message": "ภาพ 3 • ครั้ง 1 • AI_IMAGE_REFERENCE_UNCONFIRMED"},
            ]
            (folder / "logs" / "extension_trace.jsonl").write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
            job = {"id": folder.name, "scene_count": 4, "analysis_status": "ready",
                   "partial_generated_images": ["generated/scene_02.png"],
                   "last_error": "AI_IMAGE_REFERENCE_UNCONFIRMED • มีรูปเก่าค้าง"}
            self.assertEqual(story_recovery_summary(job, folder), {
                "analysis_ready": True, "saved_image_scenes": [2],
                "failed_image_scene": 3, "send_not_started": False,
            })

    def test_error_log_separates_saved_images_from_unsent_scene(self):
        with tempfile.TemporaryDirectory() as temporary:
            job_id = "STORY-TEST123"
            folder = Path(temporary) / job_id
            (folder / "generated").mkdir(parents=True)
            (folder / "logs").mkdir()
            (folder / "generated" / "scene_01.png").write_bytes(b"saved")
            (folder / "job.json").write_text(json.dumps({
                "scene_count": 4, "analysis_status": "ready",
                "partial_generated_images": ["generated/scene_01.png"],
                "last_error": "ภาพฉาก 2 • CHATGPT_IMAGE_RESULT_SEND_NOT_STARTED",
            }), encoding="utf-8")
            (folder / "logs" / "extension_trace.jsonl").write_text(json.dumps({
                "job_id": job_id, "action": "image_prompt_ready", "run_id": "run-1",
                "detail": {"scene_index": 2, "composer_matches": True},
            }) + "\n", encoding="utf-8")
            report = story_failure_timeline(temporary, job_id)
            self.assertIn("ภาพที่บันทึกในเครื่องแล้ว: 1", report)
            self.assertIn("จุดที่หยุด: ภาพฉาก 2 • ยังไม่ส่งคำขอ", report)
            self.assertIn("ช่องพิมพ์ตรงกับคำสั่งที่เตรียมไว้", report)
            self.assertIn("ยังระบุสาเหตุที่ข้อความเปลี่ยนไม่ได้", report)


if __name__ == "__main__":
    unittest.main()
