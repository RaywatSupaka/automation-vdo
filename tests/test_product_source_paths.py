"""Shopee image paths stay inside their own job for new and older imports."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core.product_image_review import product_image_asset, product_image_review
from core.product_image_recovery import ProductImageRecovery
from core.product_manager import ProductManager
from core.product_source_images import canonical_source_image_paths, select_source_images
from core.product_story import ProductCast


class ProductSourcePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="smartflow-product-paths-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.products = ProductManager(self.root)
        self.cast = ProductCast(self.root)

    @staticmethod
    def download(_url, folder, index):
        target = Path(folder) / f"product_{index:02d}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (300, 300), "blue").save(target, format="JPEG")
        return target

    def make_job(self):
        product = {
            "product_name": "Fixture item", "product_url": "https://shopee.co.th/item",
            "images": ["https://img.example/product.jpg"],
        }
        with patch.object(self.products, "_download_image", side_effect=self.download):
            job, created = self.products.import_product(product, force_new=True)
        self.assertTrue(created)
        return job

    def test_new_import_can_snapshot_and_send_real_file_to_ai(self):
        job = self.make_job()
        folder = self.products.root / job["id"]
        self.assertEqual(job["source_images"], ["original/product_01.jpg"])
        self.assertTrue((folder / job["source_images"][0]).is_file())

        context = self.cast.snapshot(self.products, job)
        snapshot = self.cast.root / "snapshots" / context["snapshot_id"]
        self.assertTrue((snapshot / "reference_0.jpg").is_file())

        package = self.products.plugin_request(job["id"])
        self.assertEqual(package["request"]["image_files"], ["original/product_01.jpg"])
        self.assertEqual(package["job"]["ai_reference_images"], ["original/product_01.jpg"])
        self.assertTrue((folder / package["request"]["image_files"][0]).is_file())

    def test_previous_root_relative_job_recovers_without_reimporting_images(self):
        job = self.make_job()
        folder = self.products.root / job["id"]
        manifest_path = folder / "job.json"
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        legacy = f"{job['id']}\\original\\product_01.jpg"
        raw["source_images"] = [legacy]
        manifest_path.write_text(json.dumps(raw), encoding="utf-8")

        # Reading a saved job does not rewrite or discard the legacy manifest.
        self.assertEqual(self.products.get_job(job["id"])["source_images"], ["original/product_01.jpg"])
        self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8"))["source_images"], [legacy])
        self.assertTrue((self.cast.root / "snapshots" / self.cast.snapshot(self.products, raw)["snapshot_id"] / "reference_0.jpg").is_file())

        package = self.products.plugin_request(job["id"])
        self.assertEqual(package["request"]["image_files"], ["original/product_01.jpg"])
        self.assertEqual(package["job"]["source_images"], ["original/product_01.jpg"])
        self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8"))["source_images"], ["original/product_01.jpg"])
        self.assertEqual(self.products.flow_package(job["id"], 1)["image_files"], ["original/product_01.jpg"])
        review = product_image_review(self.products, job["id"])
        self.assertEqual(review["images"][0]["decision"], "accept")
        self.assertEqual(Path(product_image_asset(self.products, job["id"], 0)), folder / "original/product_01.jpg")
        recovery = ProductImageRecovery(self.products, job["id"]).start({"image_prompts": ["scene"] * 3})
        self.assertEqual(recovery["sources"][0][0], "original/product_01.jpg")

    def test_wrong_job_or_missing_legacy_file_is_never_adopted(self):
        job = self.make_job()
        folder = self.products.root / job["id"]
        paths = ["JOB-OTHER/original/product_01.jpg", f"{job['id']}/original/missing.jpg"]
        self.assertEqual(canonical_source_image_paths(folder, paths), paths)
        selected, decisions = select_source_images(folder, paths)
        self.assertEqual(selected, [])
        self.assertTrue(all(item["reason"] == "invalid_or_missing_image" for item in decisions))


if __name__ == "__main__":
    unittest.main()
