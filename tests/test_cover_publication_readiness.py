"""Real cover-file publication across overlapping Story completion tokens."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core.story_manager import StoryManager


class CoverPublicationReadinessTests(unittest.TestCase):
    def test_old_renderer_cannot_overwrite_newer_completed_cover_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = StoryManager(tmp)
            job = manager.create("Concurrent first cover", scene_count=6)
            folder = manager.root / job["id"]
            source = folder / "generated" / "source.png"
            source.parent.mkdir(exist_ok=True)
            Image.new("RGB", (40, 80), "white").save(source)
            video = folder / "videos" / "final.mp4"
            video.write_bytes(b"preserved fixture video")
            job["generated_images"] = ["generated/source.png"]
            manager._save(job)
            real_save = Image.Image.save
            evidence = {}
            render_count = 0

            def render(*args):
                nonlocal render_count
                render_count += 1
                return Image.new("RGB", (40, 80), "red" if render_count == 1 else "blue")

            def save(image, target, *args, **kwargs):
                if Path(target).parent.name == "covers" and not evidence.get("nested"):
                    evidence["nested"] = True
                    newest = manager.save_video(job["id"], video, {"source_type": "story_image_sequence"})
                    evidence["new_path"] = newest["cover_path"]
                    evidence["new_bytes"] = (folder / newest["cover_path"]).read_bytes()
                return real_save(image, target, *args, **kwargs)

            with patch("core.clip_cover.ClipCoverRenderer.render", side_effect=render), patch.object(Image.Image, "save", save):
                with self.assertRaises(ValueError):
                    manager.save_video(job["id"], video, {"source_type": "story_image_sequence"})
            current = manager.get(job["id"])
            self.assertEqual(current["status"], "ready")
            self.assertEqual(current["cover_path"], evidence["new_path"])
            self.assertEqual((folder / current["cover_path"]).read_bytes(), evidence["new_bytes"])
            with Image.open(folder / current["cover_path"]) as image:
                red, _, blue = image.getpixel((20, 40))
                self.assertGreater(blue, 240)
                self.assertLess(red, 10)
            self.assertEqual(video.read_bytes(), b"preserved fixture video")


if __name__ == "__main__":
    unittest.main()
