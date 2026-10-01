import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core.config import load_config
from core.drama_media import DramaContinuityValidator, DramaCoverRenderer, DramaFootageMixer, StoryCoverRenderer


class DramaMediaTests(unittest.TestCase):
    def test_cover_is_vertical_shorts_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "scene.png"
            target = root / "cover.jpg"
            Image.new("RGB", (640, 960), "#345678").save(source)
            rendered = DramaCoverRenderer(Path(__file__).resolve().parents[1]).render(
                source, target, "ร้านกาแฟแห่งคำสัญญา", 2
            )
            with Image.open(rendered) as cover:
                self.assertEqual(cover.size, (1080, 1920))
                self.assertEqual(cover.mode, "RGB")

    def test_story_cover_is_vertical_shorts_size(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "scene.jpg"
            target = root / "story_cover.jpg"
            Image.new("RGB", (720, 1280), "navy").save(source)
            rendered = StoryCoverRenderer(Path(__file__).resolve().parents[1]).render(
                source, target, "หมาตัวเล็กหัวใจใหญ่"
            )
            with Image.open(rendered) as cover:
                self.assertEqual(cover.size, (1080, 1920))
                self.assertEqual(cover.mode, "RGB")

    def test_series_cover_themes_render_distinct_real_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "scene.png"
            Image.new("RGB", (640, 960), "#345678").save(source)
            renderer = DramaCoverRenderer(Path(__file__).resolve().parents[1])
            outputs = []
            for theme in renderer.THEMES:
                target = root / f"cover_{theme}.jpg"
                renderer.render(source, target, "ร้านกาแฟแห่งคำสัญญา", 1, theme)
                outputs.append(target.read_bytes())
            self.assertEqual(len(set(outputs)), len(renderer.THEMES))

    def test_continuity_validator_checks_real_portrait_and_character_prompts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            images = []
            for number in range(2):
                path = root / f"scene_{number}.png"
                Image.new("RGB", (180, 320), "#445566").save(path)
                images.append(path)
            result = DramaContinuityValidator().validate(
                images,
                ["นที ชายผมดำ เสื้อเชิ้ตครีม", "นที ยืนในร้านกาแฟเดิม"],
                [{"name": "นที"}],
                {"wardrobe": "เสื้อเชิ้ตครีม", "location": "ร้านกาแฟ"},
                {"wardrobe": "เสื้อเชิ้ตครีม"},
            )
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["prompt_character_coverage"], 1.0)
            self.assertEqual(result["image_count"], 2)

    def test_continuity_validator_rejects_landscape_scene(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "landscape.png"
            Image.new("RGB", (320, 180), "#445566").save(source)
            with self.assertRaisesRegex(ValueError, "แนวตั้ง"):
                DramaContinuityValidator().validate([source], ["นที"], [{"name": "นที"}], {"wardrobe": "เดิม"})

    def test_real_footage_is_inserted_without_losing_audio(self):
        configured = Path(str(load_config().get("ffmpeg_path") or ""))
        ffmpeg = str(configured) if configured.is_file() else shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("FFmpeg unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "base.mp4"
            footage = root / "footage.mp4"
            output = root / "mixed.mp4"
            subprocess.run([
                ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=360x640:d=4",
                "-f", "lavfi", "-i", "sine=frequency=500:duration=4", "-shortest",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(base),
            ], check=True, capture_output=True)
            subprocess.run([
                ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=640x360:d=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(footage),
            ], check=True, capture_output=True)
            rendered, plan = DramaFootageMixer(ffmpeg).mix(
                base, [footage], output, duration=4, width=360, height=640, fps=24, crf=24
            )
            self.assertTrue(rendered.is_file())
            self.assertGreater(rendered.stat().st_size, 1024)
            self.assertEqual(plan["footage_count"], 1)
            self.assertEqual(len(plan["footage_segments"]), 1)


if __name__ == "__main__":
    unittest.main()
