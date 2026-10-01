"""Source-less Story/Drama requests and reference-required terminal safety."""
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PIL import Image

from core.story_content import STORY_VISUAL_DEPICTION_INSTRUCTION
from core.story_manager import StoryManager
from core.story_pipeline import story_provider_failover_action, story_recovery_action
from core.story_styles import story_style_instruction
from ui.main_window import MainWindow


class StoryReferenceContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manager = StoryManager(self.root)
        self.reference = self.root / "reference.png"
        Image.new("RGB", (16, 16), "green").save(self.reference)

    def create_job(self, *, drama=False, references=False, provider="chatgpt", description=True):
        return self.manager.create(
            "ตัวละคร: Doctor Doom", "ด็อกเตอร์ดูมรอที่ประตูมิติ เรื่องและอายุของตัวละครต้องคงเดิม",
            scene_count=6, image_ai_provider=provider, visual_style="anime",
            job_type="drama_episode" if drama else "story_short",
            source_images=[str(self.reference)] if references else None,
            series_context={"series_title": "ประตูมิติ", "episode_no": 1, "episode_count": 2,
                            "characters": [{"name": "Doctor Doom", "role": "ตัวละครหลัก",
                                            "description": "เสื้อคลุมสีเขียวและหน้ากากโลหะ" if description else ""}]}
            if drama else None,
        )

    def assert_request_contract_preserved(self, job, package):
        request = package["request"]
        self.assertEqual(request["mode"], "story")
        self.assertEqual(request["job_id"], job["id"])
        self.assertEqual(request["image_count"], 6)
        self.assertEqual(request["prompt_field"], "scene_prompts")
        self.assertEqual(request["image_files"], job["source_images"])
        self.assertEqual(request["story_content_contract"], {"version": 1})
        self.assertEqual(request["visual_style_instruction"], story_style_instruction("anime"))
        self.assertEqual(request["visual_depiction_instruction"], STORY_VISUAL_DEPICTION_INSTRUCTION)
        self.assertNotIn("image_urls", request)
        self.assertNotIn("image_urls", package)
        self.assertEqual(package["checkpoint_images"], [])
        self.assertIsNone(package["analysis_checkpoint"])
        for field in ("narration_script", "visual_bible", "scene_narrations", "scene_prompts",
                      "scene_durations", "story_entities", "scene_entities"):
            self.assertIn(field, request["required_fields"])
        for phrase in ("self-contained", "รูปลักษณ์คงที่ สถานที่ และการกระทำที่มองเห็น",
                       "ฉากแรกสร้างภาพจำตาม text bible",
                       "Doctor Doom", job["story_input"]):
            self.assertIn(phrase, package["prompt"])
        if job["source_images"]:
            self.assertIn("ไม่กำหนดให้ต้องอัปโหลดภาพฉากก่อนหน้า", package["prompt"])
        else:
            self.assertIn("กำหนดภาพแต่ละฉากจากคำบรรยายข้อความที่ครบถ้วน", package["prompt"])
            self.assertNotIn("อัปโหลดภาพฉากก่อนหน้า", package["prompt"])
        if job["job_type"] == "drama_episode":
            self.assertEqual(request["story_mode"], "drama_episode")
            self.assertEqual(request["allowed_speakers"], ["Doctor Doom", "ผู้บรรยาย"])
            for field in ("episode_title", "episode_summary", "dialogue_turns", "continuity_state"):
                self.assertIn(field, request["required_fields"])

    def test_story_and_drama_without_sources_are_self_contained_for_both_providers(self):
        for drama in (False, True):
            for provider in ("chatgpt", "gemini"):
                with self.subTest(drama=drama, provider=provider):
                    job = self.create_job(drama=drama, provider=provider)
                    manifest = self.manager._folder(job["id"]) / "job.json"
                    before = manifest.read_bytes()
                    package = self.manager.plugin_request(job["id"])
                    self.assert_request_contract_preserved(job, package)
                    self.assertEqual(package["request"]["image_files"], [])
                    self.assertIn("สร้างภาพใหม่จากข้อความ", package["prompt"])
                    self.assertNotIn("ไม่ต้องมีภาพก่อนหน้าจึงจะสร้างได้", package["prompt"])
                    self.assertNotIn("รูปที่แนบเป็น Character Reference", package["prompt"])
                    self.assertEqual(manifest.read_bytes(), before)
                    self.assertEqual(self.manager.get(job["id"])["image_ai_provider"], provider)

    def test_optional_real_sources_are_kept_without_inventing_previous_images(self):
        for drama in (False, True):
            with self.subTest(drama=drama):
                job = self.create_job(drama=drama, references=True)
                source = self.manager._folder(job["id"]) / job["source_images"][0]
                before = source.read_bytes()
                package = self.manager.plugin_request(job["id"])
                self.assert_request_contract_preserved(job, package)
                self.assertEqual(len(package["request"]["image_files"]), 1)
                self.assertIn("มีไฟล์รูปอ้างอิงที่ผู้ใช้ให้ไว้", package["prompt"])
                self.assertIn("เฉพาะรูปที่แนบสำเร็จจริง", package["prompt"])
                self.assertIn("ไม่สมมติว่ามีภาพฉากก่อนหน้า", package["prompt"])
                self.assertNotIn("ไม่มีรูปอ้างอิงแนบมา", package["prompt"])
                self.assertEqual(source.read_bytes(), before)
                self.assertEqual(self.manager.get(job["id"])["source_images"], job["source_images"])

    def test_drama_missing_description_uses_text_bible_when_no_reference_exists(self):
        job = self.create_job(drama=True, description=False)
        package = self.manager.plugin_request(job["id"])
        self.assertIn("อธิบายจากข้อมูลตัวละครเดิมเป็น text bible", package["prompt"])
        self.assertNotIn("ยึดตามรูปอ้างอิง", package["prompt"])
        self.assertEqual(self.manager.get(job["id"])["character_bible"], job["character_bible"])

    def test_legacy_request_keeps_optional_metadata_and_source_less_support(self):
        for drama in (False, True):
            with self.subTest(drama=drama):
                job = self.create_job(drama=drama)
                job.pop("story_content_contract")
                self.manager._save(job)
                before = (self.manager._folder(job["id"]) / "job.json").read_bytes()
                package = self.manager.plugin_request(job["id"])
                self.assertNotIn("story_content_contract", package["request"])
                self.assertNotIn("story_entities", package["request"]["required_fields"])
                self.assertEqual(package["request"]["image_files"], [])
                self.assertIn("self-contained", package["prompt"])
                self.assertIn("สร้างภาพใหม่จากข้อความ", package["prompt"])
                self.assertEqual((self.manager._folder(job["id"]) / "job.json").read_bytes(), before)

    def test_refreshing_request_does_not_rewrite_saved_story_or_analysis(self):
        job = self.create_job()
        analysis = {
            "video_title": "ประตูมิติ", "video_description": "เรื่องเดิม", "narration_script": "ด็อกเตอร์ดูมรอที่ประตูมิติ",
            "pronunciation_notes": {"Doctor Doom": "ด็อกเตอร์ดูม"}, "visual_bible": {"place": "ประตูมิติ"},
            "scene_prompts": ["Doctor Doom in a green cloak waits at the portal"] * 6,
            "scene_narrations": ["ด็อกเตอร์ดูมรอที่ประตูมิติ"] * 6, "scene_durations": [4] * 6,
            "story_entities": [{"id": "doom", "name": "Doctor Doom", "aliases": ["ด็อกเตอร์ดูม"],
                                "visual_identity": "green cloak and metal mask"}],
            "scene_entities": [["doom"] for _ in range(6)],
        }
        saved = self.manager.save_analysis_checkpoint(job["id"], analysis)
        folder = self.manager._folder(job["id"])
        checkpoint_before = (folder / "prompts/ai_analysis_checkpoint.json").read_bytes()
        manifest_before = (folder / "job.json").read_bytes()
        package = self.manager.plugin_request(job["id"])
        self.assertEqual(package["analysis_checkpoint"]["scene_prompts"], analysis["scene_prompts"])
        self.assertEqual(package["analysis_checkpoint"]["narration_script"], analysis["narration_script"])
        self.assertEqual((folder / "prompts/ai_analysis_checkpoint.json").read_bytes(), checkpoint_before)
        self.assertEqual((folder / "job.json").read_bytes(), manifest_before)
        self.assertEqual(self.manager.get(job["id"]), saved)

    def test_reference_request_terminal_never_schedules_recovery_or_provider_failover(self):
        job = self.create_job()
        job = self.manager.mark_failed(job["id"], "chatgpt", "STORY_REFERENCE_REQUIRED: upload a reference image")
        before = copy.deepcopy(job)
        path = self.manager._folder(job["id"]) / "job.json"
        before_bytes = path.read_bytes()
        window = SimpleNamespace(stories=self.manager, root=Mock(), bridge=Mock(), _write_console=Mock())
        for message in ("STORY_REFERENCE_REQUIRED: upload a reference image",
                        "story_reference_required: please provide the previous scene image"):
            with self.subTest(message=message):
                self.assertEqual(story_recovery_action(job, message), "")
                self.assertEqual(story_provider_failover_action(job, message), "")
                self.assertFalse(MainWindow._schedule_story_recovery(window, job["id"], message))
        self.assertEqual(window.root.mock_calls, [])
        self.assertEqual(window.bridge.mock_calls, [])
        window._write_console.assert_not_called()
        self.assertEqual(path.read_bytes(), before_bytes)
        self.assertEqual(self.manager.get(job["id"]), before)

    def test_existing_terminals_and_unrelated_transient_recovery_remain_unchanged(self):
        job = self.create_job()
        for code in ("STORY_IMAGE_REFUSED", "STORY_CONTENT_MISMATCH", "STORY_SCENE_PROMPT_STALE",
                     "STORY_IMAGE_AUDIT_UNCONFIRMED", "STORY_IMAGE_CONTEXT_CONFLICT"):
            self.assertEqual(story_recovery_action(job, f"{code}: review scene"), "")
            self.assertEqual(story_provider_failover_action(job, f"{code}: review scene"), "")
        self.assertEqual(story_recovery_action(job, "temporary connection lost"), "resume_chatgpt")
        self.assertEqual(story_recovery_action(job, "unrelated reference cache network timeout"), "resume_chatgpt")

    def test_completed_unknown_image_response_requires_review_without_commands_or_recovery(self):
        job = self.create_job()
        message = "STORY_IMAGE_RESPONSE_REVIEW: completed response contains text but no new image"
        job = self.manager.mark_failed(job["id"], "chatgpt", message)
        path = self.manager._folder(job["id"]) / "job.json"
        before = path.read_bytes()
        window = SimpleNamespace(stories=self.manager, root=Mock(), bridge=Mock(), _write_console=Mock())
        for terminal in (message, message.lower()):
            with self.subTest(terminal=terminal):
                self.assertEqual(story_recovery_action(job, terminal), "")
                self.assertEqual(story_provider_failover_action(job, terminal), "")
                self.assertFalse(MainWindow._schedule_story_recovery(window, job["id"], terminal))
        self.assertEqual(window.root.mock_calls, [])
        self.assertEqual(window.bridge.mock_calls, [])
        window._write_console.assert_not_called()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.manager.get(job["id"])["last_error"], message)
        self.assertEqual(self.manager.get(job["id"])["image_ai_provider"], "chatgpt")
        self.assertEqual(story_recovery_action(job, "temporary connection lost"), "resume_chatgpt")


if __name__ == "__main__":
    unittest.main()
