"""Story checkpoints cannot cross a resumed browser run. No server is started."""
import base64
import io
import json
import logging
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.story_manager import StoryManager


class StoryCheckpointOwnershipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.stories = StoryManager(root)
        self.job = self.stories.create("แม่น้ำยามเช้า", scene_count=6)
        self.bridge = LocalBridge("127.0.0.1", 0, ProductManager(root),
                                  logging.getLogger("story-checkpoint-owner-test"), stories=self.stories)
        self.folder = self.stories.root / self.job["id"]
        image = io.BytesIO()
        Image.new("RGB", (128, 128), "navy").save(image, format="PNG")
        self.image_bytes = image.getvalue()
        self.image = base64.b64encode(self.image_bytes).decode("ascii")
        self.analysis = {
            "job_id": self.job["id"], "video_title": "แม่น้ำยามเช้า", "video_description": "เรื่องเดิม",
            "narration_script": "แม่น้ำไหลผ่านหมู่บ้าน", "visual_bible": {"lighting": "dawn"},
            "scene_prompts": [f"A river at dawn, camera angle {index}" for index in range(6)],
            "scene_narrations": ["แม่น้ำไหลผ่านหมู่บ้าน"] * 6, "scene_durations": [4] * 6,
            "story_entities": [], "scene_entities": [[] for _ in range(6)],
        }

    def payload(self, run_id="RUN-CURRENT"):
        return {"job_id": self.job["id"], "run_id": run_id, "index": 2,
                "image": self.image, "result": self.analysis}

    def own(self, run="RUN-CURRENT"):
        self.bridge._extension_runs[("ai", self.job["id"], 0)] = {"run_id": run}

    def snapshot(self):
        return {str(path.relative_to(self.folder)): path.read_bytes()
                for path in self.folder.rglob("*") if path.is_file()}

    def test_current_run_saves_the_exact_image_scene_and_analysis(self):
        self.own()
        self.bridge._accept_story_checkpoint(self.payload())
        self.assertEqual((self.folder / "generated/scene_02.png").read_bytes(), self.image_bytes)
        self.assertFalse((self.folder / "generated/scene_01.png").exists())
        self.assertEqual(self.stories.get(self.job["id"])["partial_generated_images"], [str(Path("generated") / "scene_02.png")])
        self.bridge._accept_story_checkpoint(self.payload(), analysis=True)
        saved = json.loads((self.folder / "prompts/ai_analysis_checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["scene_prompts"], self.analysis["scene_prompts"])
        self.assertEqual(saved["job_id"], self.job["id"])

    def test_stale_missing_or_wrong_job_run_does_not_write_any_checkpoint(self):
        self.own()
        self.stories.save_partial_image(self.job["id"], 2, self.image)
        before = self.snapshot()
        for run in ("RUN-OLD", "", None):
            for analysis in (False, True):
                with self.subTest(run=run, analysis=analysis):
                    with self.assertRaises(ValueError):
                        self.bridge._accept_story_checkpoint(self.payload(run), analysis=analysis)
                    self.assertEqual(self.snapshot(), before)
        other = self.stories.create("เรื่องอื่น", scene_count=6)
        other_payload = {**self.payload(), "job_id": other["id"]}
        with self.assertRaises(ValueError):
            self.bridge._accept_story_checkpoint(other_payload)
        self.assertFalse((self.stories.root / other["id"] / "generated/scene_02.png").exists())

    def test_supplied_run_without_current_owner_is_rejected(self):
        before = self.snapshot()
        for analysis in (False, True):
            with self.subTest(analysis=analysis), self.assertRaises(ValueError):
                self.bridge._accept_story_checkpoint(self.payload(), analysis=analysis)
        self.assertEqual(self.snapshot(), before)

    def test_same_run_late_different_image_cannot_overwrite_saved_scene(self):
        self.own()
        self.bridge._accept_story_checkpoint(self.payload())
        self.bridge._accept_story_checkpoint(self.payload())  # lost-ACK retry is idempotent
        before = self.snapshot()
        replacement = io.BytesIO()
        Image.new("RGB", (128, 128), "green").save(replacement, format="PNG")
        changed = {**self.payload(), "image": base64.b64encode(replacement.getvalue()).decode("ascii")}
        with self.assertRaisesRegex(ValueError, "Checkpoint"):
            self.bridge._accept_story_checkpoint(changed)
        self.assertEqual(self.snapshot(), before)
        self.stories.discard_partial_image(self.job["id"], 2, "explicit scene replacement")
        self.bridge._accept_story_checkpoint(changed)
        self.assertEqual((self.folder / "generated/scene_02.png").read_bytes(), replacement.getvalue())

    def test_internal_legacy_no_run_path_remains_available_without_active_owner(self):
        payload = self.payload("")
        payload.pop("run_id")
        self.bridge._accept_story_checkpoint(payload)
        self.bridge._accept_story_checkpoint(payload, analysis=True)
        self.assertEqual((self.folder / "generated/scene_02.png").read_bytes(), self.image_bytes)
        self.assertTrue((self.folder / "prompts/ai_analysis_checkpoint.json").is_file())

    def test_cancelled_job_cannot_accept_even_current_run(self):
        self.own()
        self.stories.mark_cancelled(self.job["id"])
        before = self.snapshot()
        for analysis in (False, True):
            with self.subTest(analysis=analysis), self.assertRaises(ValueError):
                self.bridge._accept_story_checkpoint(self.payload(), analysis=analysis)
        self.assertEqual(self.snapshot(), before)

    def test_owner_lock_is_held_until_the_manager_saves(self):
        self.own()
        save = self.stories.save_partial_image

        def checked_save(*args):
            # The callback must own the reentrant fence until persistence ends.
            self.assertTrue(self.bridge._extension_lock._is_owned())
            return save(*args)

        with patch.object(self.stories, "save_partial_image", side_effect=checked_save):
            self.bridge._accept_story_checkpoint(self.payload())
        self.assertFalse(self.bridge._extension_lock._is_owned())

    def test_background_actual_handlers_validate_owner_before_http(self):
        harness = Path(__file__).with_name("story_checkpoint_ownership_harness.js")
        result = subprocess.run(["node", str(harness)], capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        outcome = json.loads(result.stdout)
        self.assertTrue(outcome["ok"])
        self.assertGreaterEqual(outcome["cases"], 16)


if __name__ == "__main__":
    unittest.main()
