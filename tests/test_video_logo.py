import base64
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core.product_manager import ProductManager
from core.video_logo import VideoLogoRenderer
from ui.main_window import MainWindow


class DummyVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class VideoLogoTests(unittest.TestCase):
    def test_imports_transparent_logo_into_persistent_library_without_duplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stream = BytesIO()
            Image.new("RGBA", (96, 64), (50, 100, 200, 120)).save(stream, format="PNG")
            payload = {
                "filename": "My Brand.png",
                "data_url": "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii"),
            }
            window = object.__new__(MainWindow)
            window.logo_file = DummyVar("")
            window.logo_status = DummyVar("")
            with patch("ui.main_window.ROOT", root):
                first = window._save_desktop_logo(payload)
                second = window._save_desktop_logo(payload)
                stored = Path(window.logo_file.get())
                self.assertTrue(stored.is_file())
                self.assertEqual(stored.parent, root / "assets" / "logos" / "user")
                self.assertEqual(first["asset_id"], second["asset_id"])
                self.assertEqual(len(list(stored.parent.glob("*.png"))), 1)
                with Image.open(stored) as logo:
                    self.assertEqual(logo.mode, "RGBA")

    def test_saving_logo_updates_live_config_as_well_as_disk(self):
        with tempfile.TemporaryDirectory() as temp:
            logo = Path(temp) / "brand.png"
            Image.new("RGBA", (64, 64), "red").save(logo)
            window = object.__new__(MainWindow)
            window.logo_file = DummyVar(str(logo))
            window.logo_opacity = DummyVar(75)
            window.logo_size = DummyVar(16)
            window.logo_position = DummyVar("บนขวา")
            window.logo_margin = DummyVar(24)
            window.logo_status = DummyVar("")
            window.cfg = {}
            with patch("ui.main_window.save_logo_settings") as save:
                settings = window._save_logo_preferences()
            save.assert_called_once_with(settings)
            self.assertEqual(window.cfg["logo_file"], str(logo.resolve()))
            self.assertEqual(window.cfg["logo_position"], "top_right")
            self.assertEqual(window.cfg["logo_opacity"], 0.75)

    def test_composes_logo_with_opacity_size_and_position(self):
        with tempfile.TemporaryDirectory() as temp:
            logo_path = Path(temp) / "logo.png"
            Image.new("RGBA", (100, 50), (255, 0, 0, 255)).save(logo_path)
            frame = Image.new("RGB", (1000, 500), "white")
            renderer = object.__new__(VideoLogoRenderer)

            preview = renderer.compose_preview(
                frame, logo_path, opacity=0.5, size_percent=20,
                position="bottom_right", margin=10,
            )

            self.assertEqual(preview.size, (1000, 500))
            red, green, blue = preview.getpixel((800, 400))
            self.assertGreaterEqual(red, 250)
            self.assertTrue(120 <= green <= 135)
            self.assertTrue(120 <= blue <= 135)
            self.assertEqual(preview.getpixel((100, 100)), (255, 255, 255))

    def test_calculates_all_nine_positions(self):
        self.assertEqual(VideoLogoRenderer._position(720, 1280, 144, 72, "top_left", 20), (20, 20))
        self.assertEqual(VideoLogoRenderer._position(720, 1280, 144, 72, "top_center", 20), (288, 20))
        self.assertEqual(VideoLogoRenderer._position(720, 1280, 144, 72, "top_right", 20), (556, 20))
        self.assertEqual(VideoLogoRenderer._position(720, 1280, 144, 72, "center", 20), (288, 604))
        self.assertEqual(VideoLogoRenderer._position(720, 1280, 144, 72, "bottom_left", 20), (20, 1188))
        self.assertEqual(VideoLogoRenderer._position(720, 1280, 144, 72, "bottom_center", 20), (288, 1188))
        self.assertEqual(VideoLogoRenderer._position(720, 1280, 144, 72, "bottom_right", 20), (556, 1188))

    def test_saves_logo_result_without_overwriting_source_video(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = ProductManager(root)
            job, _ = manager.import_product({"product_name": "สินค้า", "product_url": "https://shopee.co.th/product/1/2"})
            folder = manager.root / job["id"]
            source = folder / "videos" / "final.mp4"
            output = folder / "videos" / "final_with_logo.mp4"
            logo = root / "logo.png"
            source.write_bytes(b"source-video")
            output.write_bytes(b"logo-video")
            Image.new("RGBA", (64, 64), "red").save(logo)

            saved = manager.save_logo_video(job["id"], output, source, logo, {
                "opacity": 0.75,
                "size_percent": 16,
                "position": "top_right",
                "margin": 24,
            })

            self.assertEqual(source.read_bytes(), b"source-video")
            self.assertEqual(saved["video_path"], "videos\\final_with_logo.mp4")
            self.assertEqual(saved["video_without_logo_path"], "videos\\final.mp4")
            self.assertEqual(saved["logo_position"], "top_right")
            self.assertEqual(saved["logo_opacity"], 0.75)
            self.assertTrue((folder / saved["logo_file"]).is_file())


if __name__ == "__main__":
    unittest.main()
