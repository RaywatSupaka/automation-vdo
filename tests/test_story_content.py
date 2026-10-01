"""Story identity tests use temporary jobs; never inspect or regenerate user media."""
import base64
import copy
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from core.story_content import (
    StoryContentError, contains_story_name, requested_story_names,
    story_content_review, validate_story_content,
)
from core.story_manager import StoryManager
from core.story_styles import story_style_instruction


class StoryContentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.manager = StoryManager(temporary.name)

    def job(self, style="anime", topic="จักรวาล: Marvel", story="ตัวละคร: Doctor Doom\nDoctor Doom เปิดประตูมิติแล้วกลับบ้าน"):
        return self.manager.create(topic, story, scene_count=6, visual_style=style)

    @staticmethod
    def analysis(job):
        return {
            "job_id": job["id"], "video_title": "ด็อกเตอร์ดูมกลับบ้าน",
            "video_description": "เรื่องเล่าตามหัวข้อ", "narration_script": "ด็อกเตอร์ดูมเปิดประตูมิติแล้วกลับบ้าน",
            "pronunciation_notes": {"Doctor Doom": "ด็อกเตอร์ ดูม"},
            "visual_bible": {"universe": "Marvel", "setting": "Latveria"},
            "scene_prompts": [f"Doctor Doom in the Marvel universe, green hood and metal mask, opens portal scene {i}" for i in range(6)],
            "scene_narrations": ["ด็อกเตอร์ดูมเปิดประตูมิติ" for _ in range(6)],
            "scene_durations": [4] * 6,
            "story_entities": [
                {"id": "doom", "name": "Doctor Doom", "aliases": ["ด็อกเตอร์ ดูม"],
                 "visual_identity": {"costume": "green hood and metal mask", "role": "ruler of Latveria"}},
                {"id": "marvel", "name": "Marvel", "aliases": ["มาร์เวล"],
                 "visual_identity": "the requested Marvel fictional universe"},
            ],
            "scene_entities": [["doom"] for _ in range(6)],
        }

    @staticmethod
    def with_images(result):
        stream = BytesIO()
        Image.new("RGB", (64, 64), "navy").save(stream, "PNG")
        return {**copy.deepcopy(result), "generated_images": [base64.b64encode(stream.getvalue()).decode()] * 6}

    def test_six_visual_media_preserve_same_named_story_and_scene_content(self):
        for style in ("realistic", "cinematic", "anime", "3d", "watercolor", "comic"):
            with self.subTest(style=style):
                job = self.job(style)
                result = self.analysis(job)
                package = self.manager.plugin_request(job["id"])
                self.assertEqual(package["request"]["story_content_contract"], {"version": 1})
                self.assertEqual(package["request"]["required_named_entities"], ["Marvel", "Doctor Doom"])
                self.assertIn("story_entities", package["request"]["required_fields"])
                self.assertIn("scene_entities", package["request"]["required_fields"])
                self.assertNotIn("เก็บชื่อจริงไว้ได้เฉพาะ", package["prompt"])
                self.assertNotIn("scene_prompts ต้องออกแบบตัวละครต้นฉบับ", package["prompt"])
                self.assertIn("Actor likeness is not implied", package["request"]["visual_style_instruction"])
                self.assertNotIn("Original ", story_style_instruction(style))
                saved = self.manager.save_analysis_checkpoint(job["id"], result)
                self.assertEqual(saved["story_entities"], result["story_entities"])
                self.assertEqual(saved["scene_entities"], result["scene_entities"])
                self.assertEqual(saved["scene_prompts"], result["scene_prompts"])
                self.assertEqual(saved["scene_narrations"], result["scene_narrations"])
                self.assertEqual(story_content_review(saved)["status"], "ready")

    def test_original_scenery_story_allows_empty_registry_and_scene_ids(self):
        job = self.job(topic="ทะเลหลังฝน", story="แสงแดดปรากฏเหนือทะเลหลังฝน")
        result = self.analysis(job)
        result.update(story_entities=[], scene_entities=[[] for _ in range(6)],
                      scene_prompts=["A calm sea after rain"] * 6, scene_narrations=["ทะเลกลับมาสงบ"] * 6)
        saved = self.manager.save_analysis_checkpoint(job["id"], result)
        self.assertEqual(story_content_review(saved)["status"], "ready")

    def test_actor_discussion_does_not_erase_fictional_cast_or_require_actor_portraits(self):
        job = self.job(story="ตัวละคร: Doctor Doom\nบทวิเคราะห์ Marvel และ Doctor Doom กล่าวถึง Hugh Jackman, Tobey Maguire และ Reddit โดยไม่ได้ขอภาพนักแสดง")
        package = self.manager.plugin_request(job["id"])
        self.assertEqual(package["request"]["required_named_entities"], ["Marvel", "Doctor Doom"])
        self.assertIn("แยกชื่อนักแสดงจากตัวละครสมมติ", package["prompt"])
        self.assertIn("ไม่ทำให้ต้องลบตัวละครสมมติออกจากภาพ", package["prompt"])
        result = self.analysis(job)
        saved = self.manager.save_analysis_checkpoint(job["id"], result)
        self.assertEqual(saved["story_entities"][0]["name"], "Doctor Doom")
        self.assertTrue(all("Doctor Doom" in prompt for prompt in saved["scene_prompts"]))
        self.assertNotIn("Hugh Jackman", json.dumps(saved["story_entities"]))

    def test_source_declared_alias_is_valid_for_anchored_character(self):
        job = self.job()
        job["character_bible"] = [{"name": "Doctor Doom", "aliases": ["Victor von Doom"], "description": "green hood"}]
        result = self.analysis(job)
        result["scene_prompts"] = ["Victor von Doom opens a portal in the Marvel universe"] * 6
        self.assertEqual(validate_story_content(job, result)["scene_entities"], [["doom"] for _ in range(6)])

    def test_thai_aliases_connect_narration_and_images_without_replacing_canonical_name(self):
        job = self.job()
        result = self.analysis(job)
        result["scene_prompts"] = ["ด็อกเตอร์ดูมเปิดประตูมิติ" for _ in range(6)]
        saved = self.manager.save_analysis_checkpoint(job["id"], result)
        self.assertEqual(saved["story_entities"][0]["name"], "Doctor Doom")
        self.assertEqual(saved["pronunciation_notes"], result["pronunciation_notes"])
        self.assertTrue(contains_story_name("ด็อกเตอร์ดูม", "ด็อกเตอร์ ดูม"))
        self.assertFalse(contains_story_name("An author", "Thor"))
        self.assertTrue(contains_story_name("Thor raises a hammer", "Thor"))

    def test_unknown_id_and_wrong_scene_count_fail_before_checkpoint_writes(self):
        for change in (lambda result: result["scene_entities"][2].append("stranger"),
                       lambda result: result["scene_entities"].pop()):
            job = self.job()
            result = self.analysis(job)
            change(result)
            folder = self.manager.root / job["id"]
            before = (folder / "job.json").read_bytes()
            with self.assertRaisesRegex(StoryContentError, "STORY_CONTENT_MISMATCH"):
                self.manager.save_analysis_checkpoint(job["id"], result)
            self.assertEqual((folder / "job.json").read_bytes(), before)
            self.assertFalse((folder / "prompts/ai_analysis_checkpoint.json").exists())
            self.assertEqual(list((folder / "generated").iterdir()), [])

    def test_missing_entity_in_prompt_is_rejected_and_offscreen_narration_is_allowed(self):
        job = self.job()
        for field, change in (
            ("scene_prompts", lambda rows: rows.__setitem__(2, "An anonymous green cloaked man")),
        ):
            with self.subTest(field=field):
                result = self.analysis(job)
                change(result[field])
                with self.assertRaises(StoryContentError) as error:
                    validate_story_content(job, result)
                self.assertEqual(error.exception.issues[0]["scene"], 3)
        result = self.analysis(job)
        result["scene_entities"][2] = []
        result["scene_prompts"][2] = "An empty mountain with no people"
        self.assertEqual(validate_story_content(job, result)["scene_entities"][2], [])

    def test_requested_names_cannot_be_replaced_by_generic_registry(self):
        job = self.job()
        result = self.analysis(job)
        result.update(story_entities=[{"id": "hero", "name": "Anonymous hero", "aliases": [], "visual_identity": "green coat"}],
                      scene_entities=[["hero"] for _ in range(6)],
                      scene_prompts=["Anonymous hero saves a generic world"] * 6,
                      scene_narrations=["ชายผู้กล้าช่วยโลกไว้"] * 6, visual_bible={})
        with self.assertRaises(StoryContentError) as error:
            validate_story_content(job, result)
        self.assertTrue(any(issue["code"] == "REQUESTED_NAME_MISSING" for issue in error.exception.issues))

    def test_registry_alone_is_not_evidence_named_content_reached_image_plan(self):
        job = self.job()
        result = self.analysis(job)
        result.update(scene_entities=[[] for _ in range(6)], scene_prompts=["An anonymous green coat hero"] * 6,
                      scene_narrations=["ชายผู้กล้าช่วยโลกไว้"] * 6, visual_bible={})
        with self.assertRaises(StoryContentError) as error:
            validate_story_content(job, result)
        self.assertTrue(any(issue["code"] == "REQUESTED_NAME_GENERICIZED" for issue in error.exception.issues))

    def test_generated_alias_cannot_hide_generic_rename_or_generic_image(self):
        job = self.job()
        for rename in (True, False):
            result = self.analysis(job)
            entity = result["story_entities"][0]
            entity["name"] = "a generic cosmic hero" if rename else "Doctor Doom"
            entity["aliases"] = ["Doctor Doom"] if rename else ["a generic cosmic hero"]
            entity["visual_identity"] = "new armor and face"
            result["scene_prompts"] = ["a generic cosmic hero walks in the city"] * 6
            with self.subTest(rename=rename), self.assertRaises(StoryContentError):
                validate_story_content(job, result)

    def test_apply_result_rejects_identity_drift_before_media_or_caption_writes(self):
        job = self.job()
        valid = self.analysis(job)
        self.manager.save_analysis_checkpoint(job["id"], valid)
        folder = self.manager.root / job["id"]
        before_job = (folder / "job.json").read_bytes()
        before_analysis = (folder / "prompts/ai_analysis_checkpoint.json").read_bytes()
        result = self.with_images(valid)
        result["scene_prompts"][0] = "An anonymous person"
        with self.assertRaises(StoryContentError):
            self.manager.apply_ai_result(result)
        self.assertEqual((folder / "job.json").read_bytes(), before_job)
        self.assertEqual((folder / "prompts/ai_analysis_checkpoint.json").read_bytes(), before_analysis)
        self.assertEqual(list((folder / "generated").iterdir()), [])
        self.assertEqual(list((folder / "captions").iterdir()), [])

    def test_completed_result_and_refreshed_checkpoint_preserve_identity_metadata(self):
        job = self.job()
        result = self.analysis(job)
        self.manager.save_analysis_checkpoint(job["id"], result)
        saved = self.manager.apply_ai_result(self.with_images(result))
        package = self.manager.plugin_request(job["id"])
        self.assertEqual(saved["story_entities"], result["story_entities"])
        self.assertEqual(package["analysis_checkpoint"]["scene_entities"], result["scene_entities"])
        self.assertEqual(package["analysis_checkpoint"]["story_entities"][0]["name"], "Doctor Doom")

    def test_new_contract_rejects_missing_fields_but_unmarked_legacy_jobs_remain_compatible(self):
        job = self.job()
        result = self.analysis(job)
        result.pop("story_entities")
        result.pop("scene_entities")
        with self.assertRaises(StoryContentError):
            self.manager.save_analysis_checkpoint(job["id"], result)
        job.pop("story_content_contract")
        self.manager._save(job)
        saved = self.manager.save_analysis_checkpoint(job["id"], result)
        self.assertNotIn("story_entities", saved)
        package = self.manager.plugin_request(job["id"])
        self.assertNotIn("story_content_contract", package["request"])
        self.assertNotIn("story_entities", package["request"]["required_fields"])
        self.manager.apply_ai_result(self.with_images(result))

    def test_legacy_review_is_read_only_and_only_flags_relevant_substitution(self):
        job = self.job()
        job.pop("story_content_contract")
        job.update(scene_prompts=["ตัวละครต้นฉบับ ไม่มีหน้ากาก"] * 6,
                   generated_images=["generated/scene_01.png"], voice_job_id="paid-job", voice_path="audio/voice.wav")
        before = copy.deepcopy(job)
        review = story_content_review(job)
        self.assertEqual(review["status"], "needs_review")
        self.assertEqual(review["verification"], "structural_only")
        self.assertEqual(job, before)
        job.update(topic="หมาน้อยหลงป่า", story_input="สุนัขตัวเล็กหาทางกลับบ้าน")
        self.assertEqual(story_content_review(job)["status"], "legacy")
        self.assertEqual(story_content_review(job)["issues"], [])

    def test_invalid_identity_types_and_oversize_names_are_not_silently_trimmed(self):
        job = self.job()
        for field, value in (("id", "x" * 81), ("name", "x" * 201),
                             ("aliases", ["x"] * 17), ("aliases", "Doctor Doom"),
                             ("visual_identity", ""), ("visual_identity", "x" * 4001)):
            with self.subTest(field=field):
                result = self.analysis(job)
                result["story_entities"][0][field] = value
                with self.assertRaises(StoryContentError):
                    validate_story_content(job, result)

    def test_pending_review_and_character_bible_names_do_not_guess_thai_prose(self):
        job = self.job()
        self.assertEqual(story_content_review(job)["status"], "pending")
        self.assertEqual(requested_story_names({"topic": "The fox finds a home"}), [])
        self.assertEqual(requested_story_names({"topic": "A Dragon Returns Home"}), [])
        self.assertEqual(requested_story_names({"topic": "Doctor Doom VS Avengers Prime", "story_input": "Doctor Doom meets Loki. Later they save New York."}), [])
        self.assertEqual(requested_story_names({"topic": "จักรวาล: มาร์เวล", "character_bible": [{"name": "โลกิ"}]}), ["โลกิ", "มาร์เวล"])

    def test_refusal_detection_is_not_done_by_structural_content_layer(self):
        job = self.job(topic="คำปฏิเสธ", story="เรื่องสอนให้ปฏิเสธอย่างสุภาพ")
        result = self.analysis(job)
        result.update(story_entities=[], scene_entities=[[] for _ in range(6)],
                      scene_prompts=["A letter reading I cannot help with that request"] * 6,
                      scene_narrations=["เธอตัดสินใจปฏิเสธอย่างสุภาพ"] * 6)
        self.assertEqual(validate_story_content(job, result)["story_entities"], [])


if __name__ == "__main__":
    unittest.main()
