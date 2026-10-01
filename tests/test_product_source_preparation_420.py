"""Offline regression tests for resumable Shopee Product Story preparation."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core.product_manager import ProductManager
from core.product_source_images import verified_source_image_paths


class ProductSourcePreparation420Tests(unittest.TestCase):
    def make_image(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (24, 24), "navy").save(path, format="JPEG")
        return path

    def test_request_id_reuses_same_source_and_rejects_rebinding(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            calls = []

            def import_link(url, force_new=False):
                calls.append((url, force_new))
                return manager.import_product({
                    "product_name": "Fixture product",
                    "product_url": url,
                    "images": [],
                }, force_new=True)

            with patch.object(manager, "import_link", side_effect=import_link):
                first, created = manager.create_story_source(
                    "https://shopee.co.th/item/1", "PSP-stable-request-1",
                    {"provider": "gemini", "scene_count": 6, "handoff_mode": "queue"},
                )
                second, created_again = manager.create_story_source(
                    "https://shopee.co.th/item/1", "PSP-stable-request-1", {},
                )
                self.assertEqual(first["id"], second["id"])
                self.assertTrue(created)
                self.assertFalse(created_again)
                self.assertEqual(len(calls), 1)
                self.assertEqual(second["story_prepare_options"]["provider"], "gemini")
                self.assertEqual(second["story_prepare_options"]["scene_count"], 6)
                self.assertEqual(second["story_prepare_options"]["handoff_mode"], "queue")
                with self.assertRaisesRegex(ValueError, "ผูกกับลิงก์สินค้าอื่น"):
                    manager.create_story_source(
                        "https://shopee.co.th/item/2", "PSP-stable-request-1", {},
                    )

    def test_capture_command_must_match_and_image_must_exist(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            url = "https://shopee.co.th/item/1"
            job, _ = manager.import_product({
                "product_name": "Fixture product", "product_url": url, "images": [],
            }, force_new=True)
            manager._manifest_store(manager.root / job["id"] / "job.json").update(
                lambda row: {**row, "story_source_only": True,
                             "story_capture_command_id": "CMD-current"}
            )
            captured = {
                "product_name": "Fixture product", "product_url": url,
                "product_id": job.get("product_id") or "", "images": ["https://img.example/p.jpg"],
            }
            with self.assertRaisesRegex(ValueError, "ไม่ตรงคำสั่งจับภาพ"):
                manager.import_product(captured, target_job_id=job["id"], target_capture_command_id="CMD-old")
            with self.assertRaisesRegex(ValueError, "ไม่ตรงคำสั่งจับภาพ"):
                manager.import_product(captured, target_job_id=job["id"])

            def download(_url, folder, index):
                return self.make_image(Path(folder) / f"product_{index:02d}.jpg")

            with patch.object(manager, "_download_image", side_effect=download):
                saved, _ = manager.import_product(
                    captured, target_job_id=job["id"], target_capture_command_id="CMD-current",
                )
            self.assertEqual(saved["source_images"], ["original/product_01.jpg"])
            self.assertEqual(verified_source_image_paths(manager.root / job["id"], saved["source_images"]),
                             ["original/product_01.jpg"])

    def test_legacy_root_prefixed_path_is_canonicalized_only_if_real(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "JOB-20260923-ABC123"
            path = self.make_image(folder / "original" / "product_01.jpg")
            accepted = verified_source_image_paths(folder, [
                f"{folder.name}/original/product_01.jpg",
                f"{folder.name}/original/missing.jpg",
                "../../outside.jpg",
            ])
            self.assertEqual(accepted, ["original/product_01.jpg"])
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
