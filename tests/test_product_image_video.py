import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core.product_image_video import ProductImageVideoComposer


class ProductImageVideoComposerTests(unittest.TestCase):
    def test_policy_fallback_renders_one_truthful_silent_motion_segment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ffmpeg = root / "ffmpeg.exe"
            ffprobe = root / "ffprobe.exe"
            ffmpeg.write_bytes(b"exe")
            ffprobe.write_bytes(b"exe")
            image = root / "product.png"
            Image.new("RGB", (360, 640), "purple").save(image)
            output = root / "local-motion.mp4"
            calls = []

            def run(command, **_kwargs):
                calls.append(command)
                if Path(command[0]).name == "ffprobe.exe":
                    return subprocess.CompletedProcess(command, 0, json.dumps({"format": {"duration": "8.0"}}), "")
                Path(command[-1]).write_bytes(b"local-motion-video")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("core.product_image_video.locate_ffmpeg", return_value=ffmpeg.resolve()), patch(
                "core.product_image_video.run_cancellable", side_effect=run,
            ):
                result = ProductImageVideoComposer().render_motion_segment(image, output)

            render = next(command for command in calls if Path(command[0]).name == "ffmpeg.exe")
            self.assertTrue(output.is_file())
            self.assertEqual(result["source_type"], "product_local_motion_policy_fallback")
            self.assertEqual(result["motion"], "deterministic_center_zoom_v1")
            self.assertIn("zoompan", render[render.index("-vf") + 1])
            self.assertIn("-an", render)
            self.assertNotIn("-filter_complex", render)

    def test_exact_three_images_render_with_identity_safe_motion_and_mobile_codec(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ffmpeg = root / "ffmpeg.exe"
            ffprobe = root / "ffprobe.exe"
            ffmpeg.write_bytes(b"exe")
            ffprobe.write_bytes(b"exe")
            images = []
            for index, color in enumerate(("red", "green", "blue"), 1):
                image = root / f"image-{index}.png"
                Image.new("RGB", (360, 640), color).save(image)
                images.append(image)
            voice = root / "voice.mp3"
            voice.write_bytes(b"voice")
            output = root / "fallback.mp4"
            calls = []

            def run(command, **_kwargs):
                calls.append(command)
                if Path(command[0]).name == "ffprobe.exe":
                    return subprocess.CompletedProcess(command, 0, json.dumps({"format": {"duration": "30.0"}}), "")
                Path(command[-1]).write_bytes(b"rendered-video")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch("core.product_image_video.locate_ffmpeg", return_value=ffmpeg.resolve()), patch(
                "core.product_image_video.run_cancellable", side_effect=run,
            ):
                result = ProductImageVideoComposer().compose(images, output, voice)

            render = next(command for command in calls if Path(command[0]).name == "ffmpeg.exe")
            filter_graph = render[render.index("-filter_complex") + 1]
            self.assertTrue(output.is_file())
            self.assertEqual(result["image_count"], 3)
            self.assertEqual(result["source_type"], "product_image_sequence_fallback")
            self.assertEqual(result["motion"], "deterministic_center_zoom_v1")
            self.assertIn("force_original_aspect_ratio=increase", filter_graph)
            self.assertIn("zoompan", filter_graph)
            self.assertNotIn("perspective", filter_graph)
            self.assertNotIn("lenscorrection", filter_graph)
            self.assertIn("libx264", render)
            self.assertIn("yuv420p", render)
            self.assertIn("high", render)
            self.assertIn("aac", render)

    def test_composer_rejects_any_count_other_than_three(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ffmpeg = root / "ffmpeg.exe"
            ffprobe = root / "ffprobe.exe"
            ffmpeg.write_bytes(b"exe")
            ffprobe.write_bytes(b"exe")
            image = root / "image.png"
            Image.new("RGB", (360, 640), "red").save(image)
            voice = root / "voice.mp3"
            voice.write_bytes(b"voice")
            with patch("core.product_image_video.locate_ffmpeg", return_value=ffmpeg.resolve()):
                composer = ProductImageVideoComposer()
                with self.assertRaisesRegex(ValueError, "ครบ 3 รูป"):
                    composer.compose([image, image], root / "output.mp4", voice)


if __name__ == "__main__":
    unittest.main()
