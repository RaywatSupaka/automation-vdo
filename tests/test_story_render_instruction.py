"""Render-only image direction must not rewrite analysis or source contracts."""
import base64
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from core.story_manager import StoryManager
from core.story_styles import (
    STORY_VISUAL_STYLES, story_render_instruction, story_style_instruction,
)


class StoryRenderInstructionTests(unittest.TestCase):
    def test_fixed_styles_use_the_canonical_rendering_text_only(self):
        for item in STORY_VISUAL_STYLES:
            if item["value"] in {"auto", "custom"}:
                continue
            with self.subTest(style=item["value"]):
                actual = story_render_instruction(item["value"])
                self.assertEqual(actual, item["prompt"])
                for excluded in ("Actor likeness", "Preserve the story", "VISUAL STYLE", "NON-GRAPHIC"):
                    self.assertNotIn(excluded, actual)

    def test_auto_does_not_ask_the_image_generator_to_choose_the_medium_again(self):
        self.assertEqual(story_render_instruction(), "")
        self.assertEqual(story_render_instruction(None), "")
        self.assertEqual(story_render_instruction("auto", "แสงอุ่น\nพื้นผิวกระดาษ"), "แสงอุ่น\nพื้นผิวกระดาษ")

    def test_custom_and_additional_direction_keep_exact_normalized_user_content(self):
        custom = "แสงสีม่วง #8844ff\nลายเส้นหมึก 'บาง' และวัสดุด้าน"
        for value in ("custom", "anime", "cinematic"):
            with self.subTest(style=value):
                item = next(item for item in STORY_VISUAL_STYLES if item["value"] == value)
                self.assertEqual(story_render_instruction(value, "  " + custom + "  "), item["prompt"] + "\n" + custom)

    def test_render_only_direction_uses_existing_style_validation(self):
        for value, custom in (("unknown", ""), ("custom", ""), ("auto", "x" * 401)):
            with self.subTest(style=value, length=len(custom)):
                with self.assertRaises(ValueError):
                    story_render_instruction(value, custom)

    def test_analysis_style_instruction_remains_exactly_the_existing_contract(self):
        suffix = (
            "\nThe visual medium changes only the rendering. Preserve the story's named characters, entities, universe, events, relationships and established visual identities."
            " Do not replace them with generic or newly invented characters. Actor likeness is not implied; use it only when explicitly requested by the user."
        )
        for item in STORY_VISUAL_STYLES:
            for custom in ("แสงสีทอง\nเส้นหมึกคม", ""):
                if item["value"] == "custom" and not custom:
                    continue
                with self.subTest(style=item["value"], custom=bool(custom)):
                    expected = f"VISUAL STYLE — {item['label']}: {item['prompt']}" + suffix
                    if custom:
                        expected += "\nAdditional visual direction: " + custom
                    self.assertEqual(story_style_instruction(item["value"], custom), expected)

    def test_story_and_drama_requests_expose_separate_fields_for_both_providers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manager = StoryManager(root)
            reference = root / "reference.png"
            Image.new("RGB", (16, 16), "green").save(reference)
            for drama in (False, True):
                for provider in ("chatgpt", "gemini"):
                    for sources in (False, True):
                        for style, custom in (("auto", ""), ("anime", ""), ("custom", "แสงทอง\nเส้นหมึกคม")):
                            with self.subTest(drama=drama, provider=provider, sources=sources, style=style):
                                job = manager.create(
                                    "ตัวละคร: Doctor Doom", "ด็อกเตอร์ดูมรอที่ประตูมิติ",
                                    scene_count=6, image_ai_provider=provider,
                                    visual_style=style, visual_style_custom=custom,
                                    source_images=[str(reference)] if sources else None,
                                    job_type="drama_episode" if drama else "story_short",
                                    series_context={"series_title": "ประตูมิติ", "episode_no": 1, "episode_count": 2,
                                                    "characters": [{"name": "Doctor Doom", "role": "ตัวละครหลัก",
                                                                    "description": "หน้ากากโลหะและเสื้อคลุมเขียว"}]}
                                    if drama else None,
                                )
                                folder = manager._folder(job["id"])
                                manifest_before = (folder / "job.json").read_bytes()
                                master_before = (folder / "prompts/chatgpt_request.txt").read_bytes()
                                package = manager.plugin_request(job["id"])
                                request = package["request"]
                                self.assertEqual(request["visual_render_instruction"], story_render_instruction(style, custom))
                                self.assertEqual(request["visual_style_instruction"], story_style_instruction(style, custom))
                                self.assertIn(request["visual_style_instruction"], package["prompt"])
                                self.assertEqual(request["image_files"], job["source_images"])
                                self.assertEqual((folder / "job.json").read_bytes(), manifest_before)
                                self.assertEqual((folder / "prompts/chatgpt_request.txt").read_bytes(), master_before)

    def test_resume_refreshes_254_request_without_changing_analysis_or_image_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = StoryManager(Path(directory))
            for drama in (False, True):
                for style in ("auto", "anime"):
                    with self.subTest(drama=drama, style=style):
                        job = manager.create(
                            "ประตูมิติ", "ด็อกเตอร์ดูมรอที่ประตูมิติ", scene_count=6,
                            visual_style=style, job_type="drama_episode" if drama else "story_short",
                            series_context={"series_title": "ประตูมิติ", "episode_no": 1, "episode_count": 2,
                                            "characters": [{"name": "Doctor Doom", "description": "หน้ากากโลหะ"}]}
                            if drama else None,
                        )
                        analysis = {
                            "video_title": "ประตูมิติ", "video_description": "เรื่องเดิม",
                            "narration_script": "ด็อกเตอร์ดูมรอที่ประตูมิติ",
                            "pronunciation_notes": {"Doctor Doom": "ด็อกเตอร์ดูม"},
                            "visual_bible": {"world": "ประตูมิติ", "lighting": "blue"},
                            "scene_prompts": ["Doctor Doom in a green cloak waits at the portal"] * 6,
                            "scene_narrations": ["ด็อกเตอร์ดูมรอที่ประตูมิติ"] * 6,
                            "scene_durations": [4] * 6,
                            "story_entities": [{"id": "doom", "name": "Doctor Doom", "aliases": ["ด็อกเตอร์ดูม"],
                                                "visual_identity": "green cloak and metal mask"}],
                            "scene_entities": [["doom"] for _ in range(6)],
                        }
                        manager.save_analysis_checkpoint(job["id"], analysis)
                        with BytesIO() as encoded:
                            Image.new("RGB", (128, 128), "orange").save(encoded, format="PNG")
                            manager.save_partial_image(job["id"], 1, base64.b64encode(encoded.getvalue()).decode())
                        folder = manager._folder(job["id"])
                        request_file = folder / "ai_request.json"
                        old_request = json.loads(request_file.read_text(encoding="utf-8"))
                        old_request.pop("visual_render_instruction")
                        request_file.write_text(json.dumps(old_request, ensure_ascii=False), encoding="utf-8")
                        protected_paths = (
                            folder / "job.json", folder / "prompts/ai_analysis_checkpoint.json",
                            folder / "prompts/chatgpt_request.txt", folder / "generated/scene_01.png",
                        )
                        protected_before = {path: path.read_bytes() for path in protected_paths}
                        package = manager.plugin_request(job["id"])
                        refreshed = json.loads(request_file.read_text(encoding="utf-8"))
                        self.assertEqual(refreshed.pop("visual_render_instruction"), story_render_instruction(style))
                        self.assertEqual(refreshed, old_request)
                        self.assertEqual(package["request"]["visual_render_instruction"], story_render_instruction(style))
                        self.assertEqual(package["analysis_checkpoint"]["narration_script"], analysis["narration_script"])
                        self.assertEqual(package["analysis_checkpoint"]["scene_prompts"], analysis["scene_prompts"])
                        self.assertEqual(package["checkpoint_images"], [str(Path("generated") / "scene_01.png")])
                        self.assertEqual(package["job"]["partial_image_count"], 1)
                        for path, before in protected_before.items():
                            self.assertEqual(path.read_bytes(), before, str(path))


if __name__ == "__main__":
    unittest.main()
