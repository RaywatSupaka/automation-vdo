import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.story_manager import StoryManager
from core.studio_review import story_review, scene_asset, voice_review, validate_user_notes
from core.story_finisher import _subtitle_script
from ui.main_window import MainWindow


class StudioReviewTests(unittest.TestCase):
    def test_receipt_result_explanation_does_not_mutate_saved_story(self):
        before = (self.folder/'job.json').read_bytes()
        job = dict(self.job, last_error='STORY_IMAGE_RECEIPT_REVIEW • ภาพฉาก 6 • CHATGPT_IMAGE_RESULT_NO_IMAGE')
        result = story_review(self.folder, job)
        self.assertEqual(result['image_result_review']['reason'], 'no_image')
        self.assertIn('ไม่ใช่หลักฐานว่าส่งไม่สำเร็จ', result['image_result_review']['message'])
        self.assertEqual((self.folder/'job.json').read_bytes(), before)
        self.assertEqual(result['last_error'], job['last_error'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = StoryManager(self.temp.name)
        self.job = self.manager.create("ทดสอบเรื่อง", scene_count=6)
        self.job.update(narration_script="Zorblax มาถึงแล้ว", scene_narrations=["Zorblax"] * 6,
                        scene_prompts=["same scene"] * 6, pronunciation_notes={"Zorblax": "ซอร์บ"})
        self.manager._save(self.job)
        self.folder = self.manager._folder(self.job["id"])

    def test_user_notes_override_ai_and_match_subtitle(self):
        saved = self.manager.save_pronunciation_notes(self.job["id"], {"Zorblax": "ซอร์แบล็กซ์"}, self.job["revision"])
        result = voice_review(saved)
        self.assertTrue(result["ready"])
        self.assertEqual(result["script"], "ซอร์แบล็กซ์ มาถึงแล้ว")
        self.assertEqual(_subtitle_script(saved)[0], result["script"])
        self.assertEqual(saved["narration_script"], self.job["narration_script"])
        self.assertEqual(saved["scene_prompts"], self.job["scene_prompts"])
        self.assertNotIn("voice_job_id", saved)

    def test_stale_revision_refuses_overwrite(self):
        self.manager.save_pronunciation_notes(self.job["id"], {}, self.job["revision"])
        with self.assertRaisesRegex(ValueError, "งานเปลี่ยน"):
            self.manager.save_pronunciation_notes(self.job["id"], {}, self.job["revision"])

    def test_paid_audio_and_running_jobs_are_locked(self):
        for fields in ({"voice_job_id":"paid-id"}, {"voice_path":"voice/old.mp3"},
                       {"dialogue_voice_checkpoints":{"1":{"status":"queued"}}}, {"status":"running"}):
            job = dict(self.job, **fields)
            self.manager._save(job)
            with self.assertRaises(ValueError):
                self.manager.save_pronunciation_notes(job["id"], {}, job["revision"])

    def test_invalid_notes_never_persist(self):
        for notes in ([], {"A":"english"}, {"A":"[pause:1] ไทย"}, {"":"ไทย"}, {"A":42}, {"A\n":"ไทย"}):
            if notes == {"A\n":"ไทย"}:  # trimmed single-line keys are allowed
                self.assertEqual(validate_user_notes(notes), {"A":"ไทย"})
                continue
            with self.assertRaises(ValueError):validate_user_notes(notes)

    def test_partial_scene_indices_never_shift(self):
        target = self.folder / "generated/scene_03.png"
        target.write_bytes(b"image")
        self.job["partial_generated_images"] = ["generated/scene_03.png"]
        self.assertIsNone(scene_asset(self.folder, self.job, 1))
        self.assertEqual(scene_asset(self.folder, self.job, 3), target.resolve())

    def test_path_traversal_is_not_served(self):
        outside = Path(self.temp.name) / "secret.mp4"
        outside.write_bytes(b"secret")
        self.job["flow_clips"] = {"1":str(outside)}
        self.assertIsNone(scene_asset(self.folder, self.job, 1, "flow"))
        with self.assertRaises(ValueError):scene_asset(self.folder, self.job, 0)
        with self.assertRaises(ValueError):scene_asset(self.folder, self.job, 1, "arbitrary")

    def test_review_does_not_claim_final_from_images_complete(self):
        for i in range(1,7):(self.folder / f"generated/scene_{i:02d}.png").write_bytes(b"image")
        self.job.update(video_status="images_ready", status="complete")
        result = story_review(self.folder, self.job)
        self.assertTrue(result["stages"][1]["ready"])
        self.assertFalse(result["stages"][-1]["ready"])
        self.assertEqual(len(result["scenes"]),6)
        self.assertNotIn(str(self.folder), json.dumps(result))

    def test_review_marks_real_flow_local_and_missing_separately(self):
        (self.folder / "videos/one.mp4").write_bytes(b"flow")
        (self.folder / "videos/two.mp4").write_bytes(b"local")
        self.job.update(flow_clips={"1":"videos/one.mp4"}, flow_fallback_clips={"2":"videos/two.mp4"}, video_generation_mode="google_flow")
        result = story_review(self.folder, self.job)
        self.assertEqual([x["source"] for x in result["scenes"][:3]], ["flow","local","pending"])
        self.assertIn("Flow 1", result["stages"][3]["detail"])

    def test_on_demand_adapter_and_media_route(self):
        (self.folder / "generated/scene_01.png").write_bytes(b"image")
        fake=SimpleNamespace(stories=self.manager, _story_pipeline_job_id="")
        result=MainWindow._desktop_execute_action(fake,"story_review",{"job_id":self.job["id"]})
        self.assertTrue(result["ok"])
        target=MainWindow._desktop_media_path(fake,{"item_id":f"story-scene:{self.job['id']}:1:image"})
        self.assertTrue(Path(target).is_file())
        with self.assertRaises(ValueError):MainWindow._desktop_media_path(fake,{"item_id":"story-scene:../../bad:1:image"})

    def test_active_adapter_rejects_notes_even_if_manifest_not_running(self):
        fake=SimpleNamespace(stories=self.manager, _story_pipeline_job_id=self.job["id"])
        with self.assertRaisesRegex(ValueError,"กำลังทำ"):
            MainWindow._desktop_execute_action(fake,"story_save_pronunciation",{"job_id":self.job["id"],"revision":self.job["revision"],"notes":{}})

    def test_voice_preflight_is_saved_before_images(self):
        result={"video_title":"เรื่อง", "narration_script":"Zorblax มา", "scene_prompts":["Zorblax in the same scene"]*6,"scene_narrations":["Zorblax มา"]*6,
                "story_entities":[{"id":"hero","name":"Zorblax","aliases":[],"visual_identity":"ผู้เดินทางสวมเสื้อสีฟ้า"}],"scene_entities":[["hero"] for _ in range(6)]}
        job=self.manager.save_analysis_checkpoint(self.job["id"],result)
        self.assertEqual(job["voice_review_issues"], [])
        self.assertIn("Zorblax", job['narration_script'])
        self.assertFalse(job.get("generated_images"))

    def test_content_review_is_read_only_for_legacy_paid_story(self):
        self.job.pop("story_content_contract", None)
        self.job.update(topic="ตัวละคร: Doctor Doom", story_input="Doctor Doom ชนะแล้ว", voice_job_id="paid-id",
                        scene_prompts=["ตัวละครต้นฉบับ ห้ามใช้ชื่อแฟรนไชส์"] * 6)
        self.manager._save(self.job)
        before = (self.folder / "job.json").read_bytes()
        result = story_review(self.folder, self.job)
        self.assertEqual(result["content_review"]["status"], "needs_review")
        self.assertTrue(result["content_review"]["issues"])
        self.assertEqual((self.folder / "job.json").read_bytes(), before)
        self.assertEqual(self.manager.get(self.job["id"])["voice_job_id"], "paid-id")

    def test_logs_snapshot_never_scans_library(self):
        fake=SimpleNamespace(_desktop_compact_state_payload=lambda:{"partial":True},_desktop_log_lines=lambda:["latest"])
        self.assertEqual(MainWindow._desktop_state_payload(fake,"logs"),{"partial":True,"logs":["latest"]})


if __name__ == "__main__": unittest.main()
