"""Explicit scene revisions are exercised only on temporary, unpaid Story jobs."""
import base64
import copy
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL import Image

from core.story_content import STORY_VISUAL_DEPICTION_INSTRUCTION, StoryContentError
from core.story_manager import StoryManager


class StoryScenePromptEditTests(unittest.TestCase):
    revised_prompt = "Doctor Doom stands beneath a green cloak before a distant confrontation; no strikes, blood or injury"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.manager = StoryManager(temporary.name)

    def job(self, legacy=False):
        job = self.manager.create("ตัวละคร: Doctor Doom", scene_count=6, visual_style="anime")
        if legacy:
            job.pop("story_content_contract")
            self.manager._save(job)
        analysis = {
            "job_id": job["id"], "video_title": "ประตูมิติก่อนพายุ", "video_description": "เรื่องตามหัวข้อ",
            "narration_script": "ด็อกเตอร์ดูมเปิดประตูมิติก่อนพายุ", "pronunciation_notes": {"Doctor Doom": "ด็อกเตอร์ดูม"},
            "visual_bible": {"character": "Doctor Doom in green cloak and metal mask"},
            "scene_prompts": [f"Doctor Doom at the portal, scene {index}" for index in range(1, 7)],
            "scene_narrations": ["ด็อกเตอร์ดูมเปิดประตูมิติ"] * 6, "scene_durations": [4] * 6,
        }
        if not legacy:
            analysis.update(story_entities=[{"id": "doom", "name": "Doctor Doom", "aliases": ["ด็อกเตอร์ดูม"],
                                             "visual_identity": "green cloak and metal mask"}],
                            scene_entities=[["doom"] for _ in range(6)])
        self.manager.save_analysis_checkpoint(job["id"], analysis)
        job = self.manager.mark_failed(job["id"], "chatgpt", "STORY_IMAGE_REFUSED: review scene 1")
        return job, analysis

    def edit(self, job, **kwargs):
        return self.manager.save_scene_prompt(job["id"], kwargs.get("index", 1),
                                              kwargs.get("prompt", self.revised_prompt),
                                              kwargs.get("revision", job["revision"]))

    @staticmethod
    def image_payload():
        stream = BytesIO()
        Image.new("RGB", (64, 64), "navy").save(stream, "PNG")
        return base64.b64encode(stream.getvalue()).decode()

    def test_edit_records_exact_audit_without_resetting_failure_or_touching_analysis_and_other_scene(self):
        job, analysis = self.job()
        folder = self.manager.root / job["id"]
        original = (folder / "prompts/ai_analysis_checkpoint.json").read_bytes()
        other = folder / "generated/scene_02.png"
        other.write_bytes(b"existing scene two")
        job["partial_generated_images"] = ["generated/scene_02.png"]
        self.manager._save(job)
        before = copy.deepcopy(job)
        saved = self.edit(job)
        self.assertEqual(saved["scene_prompt_overrides"], {"1": self.revised_prompt})
        self.assertEqual(saved["revision"], before["revision"] + 1)
        self.assertEqual(saved["scene_prompt_override_revision"], saved["revision"])
        self.assertEqual(saved["scene_prompt_edit_history"][0]["old_prompt"], analysis["scene_prompts"][0])
        self.assertEqual(saved["scene_prompt_edit_history"][0]["new_prompt"], self.revised_prompt)
        for key in ("status", "last_error", "pipeline_stage", "narration_script", "pronunciation_notes", "visual_bible",
                    "scene_narrations", "scene_durations", "story_entities", "scene_entities", "visual_style"):
            self.assertEqual(saved.get(key), before.get(key), key)
        self.assertEqual(saved["scene_prompts"][1:], before["scene_prompts"][1:])
        self.assertEqual((folder / "prompts/ai_analysis_checkpoint.json").read_bytes(), original)
        self.assertEqual(other.read_bytes(), b"existing scene two")
        self.assertFalse((folder / "generated/scene_01.png").exists())

    def test_strict_index_prompt_and_revision_validation_has_no_manifest_write(self):
        job, _ = self.job()
        path = self.manager.root / job["id"] / "job.json"
        before = path.read_bytes()
        cases = [{"index": value} for value in (0, 7, True, "1", 1.0)]
        cases += [{"prompt": value} for value in (None, "", "  ", [], "x" * 12001)]
        cases += [{"revision": value} for value in (True, "1", -1, job["revision"] - 1)]
        for kwargs in cases:
            with self.subTest(kwargs=repr(kwargs)[:100]), self.assertRaises(ValueError):
                self.edit(job, **kwargs)
            self.assertEqual(path.read_bytes(), before)

    def test_active_cancelled_and_deleted_jobs_cannot_be_edited(self):
        for status in ("active", "running", "recovering", "cancelled", "canceled", "deleted"):
            with self.subTest(status=status):
                job, _ = self.job()
                job["status"] = status
                self.manager._save(job)
                with self.assertRaises(ValueError):
                    self.edit(job)

    def test_paid_voice_or_final_metadata_and_files_block_edit(self):
        for fields in ({"voice_job_id": "paid"}, {"voice_path": "audio/missing.wav"},
                       {"dialogue_voice_checkpoints": {"1": {"job_id": "paid"}}},
                       {"video_path": "videos/missing-final.mp4"}, {"video_status": "ready"}):
            with self.subTest(fields=fields):
                job, _ = self.job()
                job.update(fields)
                self.manager._save(job)
                with self.assertRaises(ValueError):
                    self.edit(job)
        for relative in ("audio/narration.mp3", "audio/.tts_chunks/narration/batch.json", "videos/story_short_complete.mp4"):
            with self.subTest(relative=relative):
                job, _ = self.job()
                path = self.manager.root / job["id"] / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"retained existing artifact")
                with self.assertRaises(ValueError):
                    self.edit(job)
                self.assertEqual(path.read_bytes(), b"retained existing artifact")

    def test_target_scene_image_flow_or_local_map_and_files_block_edit(self):
        for fields in ({"generated_images": ["generated/scene_01.png"]},
                       {"partial_generated_images": ["generated/scene_01.png"]},
                       {"flow_clips": {"1": "videos/flow_scene_01.mp4"}},
                       {"flow_fallback_clips": {"1": "videos/local_motion_scene_01.mp4"}}):
            with self.subTest(fields=fields):
                job, _ = self.job()
                job.update(fields)
                self.manager._save(job)
                with self.assertRaises(ValueError):
                    self.edit(job)
        for relative in ("generated/scene_01.png", "generated/scene_01.png.partial",
                         "videos/flow_scene_01.mp4", "videos/.working/local_motion_scene_01.mp4"):
            with self.subTest(relative=relative):
                job, _ = self.job()
                path = self.manager.root / job["id"] / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"existing scene one")
                with self.assertRaises(ValueError):
                    self.edit(job)

    def test_content_identity_cannot_be_removed_by_prompt_edit(self):
        job, _ = self.job()
        before = self.manager.get(job["id"])
        with self.assertRaises(StoryContentError):
            self.edit(job, prompt="An anonymous new hero standing by the portal")
        self.assertEqual(self.manager.get(job["id"]), before)

    def test_package_overrides_only_returned_checkpoint_and_uses_current_style_and_depiction(self):
        job, analysis = self.job()
        saved = self.edit(job)
        folder = self.manager.root / job["id"]
        original = (folder / "prompts/ai_analysis_checkpoint.json").read_bytes()
        package = self.manager.plugin_request(job["id"])
        self.assertTrue(package["reuse_analysis"])
        self.assertEqual(package["scene_prompt_overrides"], {"1": self.revised_prompt})
        self.assertEqual(package["scene_prompt_override_revision"], saved["revision"])
        self.assertEqual(package["analysis_checkpoint"]["scene_prompts"], saved["scene_prompts"])
        self.assertEqual(package["analysis_checkpoint"]["narration_script"], analysis["narration_script"])
        self.assertIn("2D anime", package["request"]["visual_style_instruction"])
        self.assertEqual(package["request"]["story_content_contract"], {"version": 1})
        self.assertEqual(package["request"]["visual_depiction_instruction"], STORY_VISUAL_DEPICTION_INSTRUCTION)
        self.assertEqual((folder / "prompts/ai_analysis_checkpoint.json").read_bytes(), original)

    def test_stale_incoming_analysis_and_result_cannot_overwrite_edit_or_write_images(self):
        job, analysis = self.job()
        saved = self.edit(job)
        folder = self.manager.root / job["id"]
        before_job = (folder / "job.json").read_bytes()
        before_analysis = (folder / "prompts/ai_analysis_checkpoint.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "STORY_SCENE_PROMPT_STALE"):
            self.manager.save_analysis_checkpoint(job["id"], analysis)
        with self.assertRaisesRegex(ValueError, "STORY_SCENE_PROMPT_STALE"):
            self.manager.apply_ai_result({**analysis, "generated_images": [self.image_payload()] * 6})
        self.assertEqual((folder / "job.json").read_bytes(), before_job)
        self.assertEqual((folder / "prompts/ai_analysis_checkpoint.json").read_bytes(), before_analysis)
        self.assertEqual(list((folder / "generated").iterdir()), [])
        self.assertEqual(self.manager.get(saved["id"])["scene_prompts"][0], self.revised_prompt)

    def test_matching_incoming_override_keeps_original_analysis_file_and_audit(self):
        job, analysis = self.job()
        saved = self.edit(job)
        path = self.manager.root / job["id"] / "prompts/ai_analysis_checkpoint.json"
        original = path.read_bytes()
        analysis["scene_prompts"] = saved["scene_prompts"]
        accepted = self.manager.save_analysis_checkpoint(job["id"], analysis)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(accepted["scene_prompt_edit_history"], saved["scene_prompt_edit_history"])
        final = self.manager.apply_ai_result({**analysis, "generated_images": [self.image_payload()] * 6})
        self.assertEqual(final["scene_prompt_overrides"], saved["scene_prompt_overrides"])

    def test_legacy_manifest_only_plan_can_be_reviewed_without_creating_ai_checkpoint(self):
        job, _ = self.job(legacy=True)
        path = self.manager.root / job["id"] / "prompts/ai_analysis_checkpoint.json"
        path.unlink()
        saved = self.edit(job)
        package = self.manager.plugin_request(job["id"])
        self.assertTrue(package["reuse_analysis"])
        self.assertNotIn("story_content_contract", package["request"])
        self.assertEqual(package["analysis_checkpoint"]["scene_prompts"], saved["scene_prompts"])
        self.assertFalse(path.exists())
        self.assertIn(STORY_VISUAL_DEPICTION_INSTRUCTION, package["prompt"])

    def test_history_is_bounded_and_identical_save_does_not_create_revision(self):
        job, _ = self.job()
        for index in range(24):
            job = self.edit(job, prompt=f"Doctor Doom before a quiet doorway, composition {index}")
        self.assertEqual(len(job["scene_prompt_edit_history"]), 20)
        unchanged = self.edit(job, prompt=job["scene_prompts"][0])
        self.assertEqual(unchanged, job)

    def test_concurrent_user_edits_allow_one_revision_without_lost_update(self):
        job, _ = self.job()
        barrier = threading.Barrier(2)
        def edit(index):
            barrier.wait(timeout=5)
            try:
                return self.edit(job, prompt=f"Doctor Doom before a quiet doorway, composition {index}")
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(edit, (1, 2)))
        self.assertEqual(sum(result is not None for result in results), 1)
        saved = self.manager.get(job["id"])
        self.assertEqual(saved["revision"], job["revision"] + 1)
        self.assertEqual(len(saved["scene_prompt_edit_history"]), 1)

    def test_drama_request_has_same_depiction_rule_without_rewriting_character(self):
        job = self.manager.create("ฉากก่อนพายุ", scene_count=6, job_type="drama_episode", visual_style="comic",
                                  series_context={"characters": [{"name": "มิน", "description": "หญิงผมสั้นวัยสามสิบ"}]})
        package = self.manager.plugin_request(job["id"])
        self.assertEqual(package["request"]["visual_depiction_instruction"], STORY_VISUAL_DEPICTION_INSTRUCTION)
        self.assertIn("หญิงผมสั้นวัยสามสิบ", package["prompt"])
        self.assertIn("names, ages, identities", package["prompt"])
        self.assertIn("not a guarantee", package["prompt"])


if __name__ == "__main__":
    unittest.main()
