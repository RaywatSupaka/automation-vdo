import base64
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from core.drama_series import DramaSeriesManager
from core.story_manager import StoryManager


class StoryDramaManagerIntegrityTests(unittest.TestCase):
    @staticmethod
    def _encoded_scene(color="#345678"):
        buffer = BytesIO()
        Image.new("RGB", (180, 320), color).save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    @staticmethod
    def _seed_generated_scene(manager, job_id, color="#345678"):
        folder = manager.root / job_id
        target = folder / "generated" / "scene_01.png"
        Image.new("RGB", (180, 320), color).save(target)
        manifest = manager.get(job_id)
        manifest["generated_images"] = [str(target.relative_to(folder))]
        manifest["video_title"] = "เรื่องทดสอบ"
        manager._save(manifest)
        return folder

    def test_manifests_use_atomic_unique_temporary_files_and_recover_empty_primary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stories = StoryManager(root)
            story = stories.create("เรื่องทดสอบ", scene_count=6)
            story_path = stories.root / story["id"] / "job.json"
            self.assertGreater(stories.get(story["id"])["revision"], 0)
            self.assertFalse(list(story_path.parent.glob(".job.json-*.tmp")))
            story_path.write_text("", encoding="utf-8")
            recovered_story = stories.get(story["id"])
            self.assertEqual(recovered_story["id"], story["id"])
            self.assertTrue(story_path.read_text(encoding="utf-8").strip())

            drama = DramaSeriesManager(root)
            series = drama.create("ละครทดสอบ", characters=[{"name": "มิน"}])
            series_path = drama.root / series["id"] / "series.json"
            self.assertGreater(drama.get(series["id"])["revision"], 0)
            self.assertFalse(list(series_path.parent.glob(".series.json-*.tmp")))
            series_path.write_text("", encoding="utf-8")
            recovered_series = drama.get(series["id"])
            self.assertEqual(recovered_series["id"], series["id"])
            self.assertTrue(series_path.read_text(encoding="utf-8").strip())

    def test_drama_dialogue_speakers_are_normalised_without_discarding_completed_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = StoryManager(Path(temporary))
            context = {
                "series_id": "SERIES-TEST",
                "characters": [{"name": "มิน", "description": "หญิงผมดำ"}],
            }
            job = manager.create("ละครทดสอบ", scene_count=6, job_type="drama_episode", series_context=context)
            base_result = {
                "job_id": job["id"],
                "narration_script": "คืนฝนตก",
                "visual_bible": {"tone": "blue"},
                "story_entities": [{"id": "min", "name": "มิน", "aliases": [], "visual_identity": "หญิงผมดำ"}],
                "scene_entities": [["min"] for _ in range(6)],
                "scene_prompts": [f"มินอยู่ในฉาก {index}" for index in range(6)],
                "scene_narrations": [f"ฉาก {index}" for index in range(6)],
                "scene_durations": [4] * 6,
                "generated_images": [self._encoded_scene()] * 6,
            }
            invalid = dict(base_result)
            invalid["dialogue_turns"] = [{"speaker": "ตัวละครลึกลับ", "text": "ฉันมาแล้ว"}]
            recovered = manager.apply_ai_result(invalid)
            self.assertEqual(recovered["dialogue_turns"][0]["speaker"], "ผู้บรรยาย")
            self.assertEqual(recovered["speaker_corrections"][0]["from"], "ตัวละครลึกลับ")
            self.assertEqual(recovered["speaker_corrections"][0]["reason"], "supporting_speaker_not_in_bible")
            self.assertEqual(len(recovered["generated_images"]), 6)

            valid = dict(base_result)
            valid["dialogue_turns"] = [
                {"speaker": "Narrator:", "text": "ฝนตก"},
                {"speaker": "มิน：", "text": "ฉันมาแล้ว"},
            ]
            saved = manager.apply_ai_result(valid)
            self.assertEqual([turn["speaker"] for turn in saved["dialogue_turns"][:2]], ["ผู้บรรยาย", "มิน"])

    def test_drama_request_declares_exact_allowed_speakers(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = StoryManager(Path(temporary))
            job = manager.create(
                "ละครทดสอบ", scene_count=6, job_type="drama_episode",
                series_context={
                    "series_id": "SERIES-TEST",
                    "characters": [{"name": "มิน"}, {"name": "ต้น"}],
                },
            )
            folder = manager.root / job["id"]
            request = __import__("json").loads((folder / "ai_request.json").read_text(encoding="utf-8"))
            prompt = (folder / "prompts" / "chatgpt_request.txt").read_text(encoding="utf-8")
            self.assertEqual(request["allowed_speakers"], ["มิน", "ต้น", "ผู้บรรยาย"])
            self.assertIn('ALLOWED SPEAKERS', prompt)
            self.assertIn('["มิน", "ต้น", "ผู้บรรยาย"]', prompt)
            self.assertIn("แบบตัวอักษรต่ออักษร", prompt)

    def test_video_is_not_complete_until_story_cover_is_ready(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = StoryManager(Path(temporary))
            job = manager.create("เรื่องไม่มีปก", scene_count=6)
            folder = manager.root / job["id"]
            video = folder / "videos" / "story_short_complete.mp4"
            video.write_bytes(b"rendered-video")
            with self.assertRaisesRegex(ValueError, "ยังไม่มีภาพฉากจริง"):
                manager.save_video(job["id"], video, {"source_type": "story_image_sequence"})
            pending = manager.get(job["id"])
            self.assertEqual(pending["video_status"], "waiting_cover")
            self.assertEqual(pending["pipeline_stage"], "cover")

            self._seed_generated_scene(manager, job["id"])
            saved = manager.save_video(job["id"], video, {"source_type": "story_image_sequence"})
            self.assertEqual(saved["video_status"], "ready")
            self.assertEqual(saved["pipeline_stage"], "complete")
            self.assertEqual(saved["cover_status"], "ready")
            self.assertTrue((folder / saved["cover_path"]).is_file())
            self.assertEqual(saved["cover_size"], [1080, 1920])

    def test_drama_video_completion_creates_episode_cover(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = StoryManager(Path(temporary))
            job = manager.create(
                "ละครทดสอบ", scene_count=6, job_type="drama_episode",
                series_context={
                    "series_id": "SERIES-TEST",
                    "series_title": "ละครทดสอบ",
                    "episode_no": 1,
                    "characters": [{"name": "มิน"}],
                    "cover_theme": "thriller",
                },
            )
            folder = self._seed_generated_scene(manager, job["id"], "#552233")
            video = folder / "videos" / "story_short_complete.mp4"
            video.write_bytes(b"rendered-drama-video")
            saved = manager.save_video(job["id"], video, {"source_type": "story_image_sequence"})
            self.assertEqual(saved["status"], "ready")
            self.assertRegex(saved["cover_path"].replace("\\", "/"), r"^covers/cover_[a-f0-9]{32}\.jpg$")
            self.assertTrue((folder / saved["cover_path"]).is_file())
            self.assertEqual(saved["cover_size"], [1080, 1920])


if __name__ == "__main__":
    unittest.main()
