import tempfile
import unittest
from pathlib import Path

from core.product_manager import ProductManager
from core.video_effects import ProductEffectsRenderer


class VideoEffectsTests(unittest.TestCase):
    def test_builds_animated_ring_arrow_cards_and_cta(self):
        renderer = ProductEffectsRenderer.__new__(ProductEffectsRenderer)
        script = renderer._ass_script(
            720, 1280, 48, "neon_focus", "#2AD8F2", 50, 56, 2,
            ["ภาพรวมสินค้า", "ดูรายละเอียด", "ตรวจสภาพก่อนสั่ง"],
        )
        self.assertIn("↙", script)
        self.assertIn("\\p1", script)
        self.assertIn("\\move", script)
        self.assertIn("ภาพรวมสินค้า", script)
        self.assertIn("ตรวจรายละเอียดก่อนสั่งซื้อ", script)
        self.assertGreaterEqual(script.count("Dialogue:"), 20)

    def test_validates_effect_safe_area(self):
        values = ProductEffectsRenderer.validate_options("neon_focus", "#2AD8F2", 50, 56, 2)
        self.assertEqual(values, ("neon_focus", "#2AD8F2", 50.0, 56.0, 2))
        with self.assertRaises(ValueError):
            ProductEffectsRenderer.validate_options("neon_focus", "cyan", 50, 56, 2)
        with self.assertRaises(ValueError):
            ProductEffectsRenderer.validate_options("neon_focus", "#2AD8F2", 3, 56, 2)

    def test_saves_effect_result_without_leaving_job_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = ProductManager(root)
            job, _ = manager.import_product({"product_name": "สินค้า", "product_url": "https://shopee.co.th/product/1/2"})
            folder = manager.root / job["id"]
            source = folder / "videos" / "joined.mp4"
            output = folder / "videos" / "effects.mp4"
            source.write_bytes(b"source")
            output.write_bytes(b"effects")
            saved = manager.save_effect_video(job["id"], output, source, {
                "preset": "neon_focus", "accent_color": "#2AD8F2",
                "target_x_percent": 50, "target_y_percent": 56, "intensity": 2,
            })
            self.assertEqual(saved["effect_status"], "ready")
            self.assertEqual(saved["video_path"], "videos\\effects.mp4")
            self.assertEqual(saved["video_before_effects_path"], "videos\\joined.mp4")


if __name__ == "__main__":
    unittest.main()
