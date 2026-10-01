import tempfile
import subprocess
import unittest
from pathlib import Path

from core.story_manager import StoryManager
from core.story_queue import StoryBatchQueue
from core.drama_series import DramaSeriesManager
from core.story_styles import normalize_story_style
from core.story_finisher import _subtitle_script
from core.thai_tts import prepare_thai_tts_script


class StoryStyleAndCtaTests(unittest.TestCase):
    def test_extension_uses_style_on_initial_image_and_retry(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(["node", "tests/story_style_extension_harness.js"], cwd=root, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_viewer_question_does_not_inject_english_title(self):
        narration = "เรื่องจบแล้ว กดหัวใจไว้ แล้วคุณคิดว่าใครจะเปลี่ยนใจใครก่อน?"
        actual, scenes, added = StoryManager._ensure_engagement_cta(narration, [narration], "HUNTER X HUNTER")
        self.assertEqual(actual, narration)
        self.assertEqual(scenes, [narration])
        self.assertFalse(added)

    def test_missing_cta_never_injects_unknown_english(self):
        narration, _, added = StoryManager._ensure_engagement_cta("จบเรื่อง", ["จบเรื่อง"], "UnknownHero Returns")
        self.assertTrue(added)
        self.assertNotIn("UnknownHero", narration)
        self.assertEqual(prepare_thai_tts_script(narration)[1], [])

    def test_hunter_and_notes_match_voice_and_subtitles(self):
        job = {"narration_script": "HUNTER X HUNTER พบ UnknownHero", "pronunciation_notes": {"UnknownHero": "ฮีโร่ลึกลับ"}}
        speech, issues = prepare_thai_tts_script(job["narration_script"], job["pronunciation_notes"])
        self.assertEqual(issues, [])
        self.assertEqual(_subtitle_script(job)[0], speech)
        self.assertEqual(speech, "ฮันเตอร์ ฮันเตอร์ พบ ฮีโร่ลึกลับ")

    def test_repair_exact_old_cta_once_and_preserve_paid_voice(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            job = manager.create("HUNTER X HUNTER", scene_count=6)
            source = "จบเรื่อง กดหัวใจ แล้วคุณคิดว่าใครชนะ?"
            old = "ถ้าเรื่องนี้ทำให้คุณรู้สึกอะไรบางอย่าง กดหัวใจไว้ แล้วคอมเมนต์บอกหน่อยว่า คุณคิดอย่างไรกับ HUNTER X HUNTER"
            job.update(narration_script=f"{source} {old}", scene_narrations=[source] * 5 + [f"{source} {old}"], engagement_cta_added_by_program=True, generated_images=["generated/scene_01.png"])
            manager._save(job)
            repaired = manager.repair_program_cta(job["id"])
            self.assertEqual(repaired["narration_script"], source)
            self.assertEqual(repaired["generated_images"], job["generated_images"])
            self.assertEqual(manager.repair_program_cta(job["id"]), repaired)
            job["voice_job_id"] = "paid-queue"
            manager._save(job)
            self.assertEqual(manager.repair_program_cta(job["id"])["narration_script"], job["narration_script"])

    def test_style_persists_in_job_batch_and_refreshed_package(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            job = manager.create("ท่องป่า", visual_style="anime", visual_style_custom="แสงเย็น")
            package = manager.plugin_request(job["id"])
            self.assertIn("2D anime", package["prompt"])
            self.assertIn("2D anime", package["request"]["visual_style_instruction"])
            self.assertEqual(package["job"]["visual_style"], "anime")
            queue = StoryBatchQueue(temp)
            queue.enqueue_batch(["ตอนหนึ่ง", "ตอนสอง"], visual_style="anime", visual_style_custom="แสงเย็น")
            self.assertTrue(all(row["visual_style"] == "anime" for row in queue.snapshot()["items"]))
            self.assertTrue(queue.snapshot()["paused"])

    def test_pronunciation_notes_survive_analysis_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            job = manager.create("ทดสอบ", scene_count=6)
            result = {"video_title":"เรื่องหนึ่ง", "narration_script":"UnknownHero มาแล้ว", "pronunciation_notes":{"UnknownHero":"ฮีโร่ลึกลับ"}, "scene_prompts":["scene"] * 6,"scene_narrations":["ฉาก"] * 6,
                      "story_entities": [], "scene_entities": [[] for _ in range(6)]}
            saved = manager.save_analysis_checkpoint(job["id"], result)
            self.assertEqual(saved["pronunciation_notes"], result["pronunciation_notes"])
            self.assertEqual(manager.plugin_request(job["id"])["analysis_checkpoint"]["pronunciation_notes"], result["pronunciation_notes"])

    def test_invalid_style_fails_before_job_created(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            with self.assertRaises(ValueError): manager.create("เรื่อง", visual_style="unknown")
            with self.assertRaises(ValueError): normalize_story_style("custom", "")
            self.assertEqual(manager.list_jobs(), [])

    def test_drama_episode_inherits_series_style(self):
        with tempfile.TemporaryDirectory() as temp:
            series_manager = DramaSeriesManager(temp)
            series = series_manager.create("เรื่องนิทาน", characters=[{"name":"มิน", "description":"หญิงไทยผมสั้น"}], visual_style="watercolor", visual_style_custom="กระดาษอุ่น")
            context = series_manager.episode_context(series["id"], 1)
            self.assertEqual(context["visual_style"], "watercolor")
            manager = StoryManager(temp)
            job = manager.create("ตอนแรก", job_type="drama_episode", series_context=context, visual_style=context["visual_style"], visual_style_custom=context["visual_style_custom"])
            package = manager.plugin_request(job["id"])
            self.assertIn("watercolor", package["prompt"])
            self.assertIn("กระดาษอุ่น", package["request"]["visual_style_instruction"])


if __name__ == "__main__":
    unittest.main()
