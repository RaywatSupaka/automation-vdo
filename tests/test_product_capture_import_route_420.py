"""Bridge contract for Product Story capture: command identity plus real files."""
import io
import json
import logging
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager


class ProductCaptureImportRoute420Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.products = ProductManager(Path(self.temp.name))
        self.job, _ = self.products.import_product({
            "product_name": "Fixture product",
            "product_url": "https://shopee.co.th/item/1",
            "images": [],
        }, force_new=True)
        self.products._manifest_store(self.products.root / self.job["id"] / "job.json").update(
            lambda row: {**row, "story_source_only": True,
                         "story_capture_command_id": "CMD-current"}
        )
        self.bridge = LocalBridge("127.0.0.1", 0, self.products,
                                  logging.getLogger("product-capture-420")).start()
        self.addCleanup(self.bridge.stop)
        self.url = f"http://127.0.0.1:{self.bridge.server.server_address[1]}/api/products/import"

    @staticmethod
    def download(_url, folder, index):
        target = Path(folder) / f"product_{index:02d}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (40, 60), "teal").save(target, format="JPEG")
        return target

    def post(self, capture_command_id):
        body = {
            "product_name": "Fixture product",
            "product_url": "https://shopee.co.th/item/1",
            "posting_product_url": "https://shopee.co.th/item/1",
            "product_id": "123",
            "images": ["https://img.example/product.jpg"],
            "target_job_id": self.job["id"],
            "target_capture_command_id": capture_command_id,
        }
        request = urllib.request.Request(self.url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        return json.load(urllib.request.urlopen(request, timeout=5))

    def test_true_readiness_requires_current_command_and_readable_image_file(self):
        with patch.object(self.products, "_download_image", side_effect=self.download):
            payload = self.post("CMD-current")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["capture_ready"])
        self.assertEqual(payload["capture_command_id"], "CMD-current")
        self.assertEqual(payload["verified_source_image_count"], 1)
        self.assertTrue((self.products.root / self.job["id"] / "original/product_01.jpg").is_file())

    def test_stale_command_is_rejected_before_importing_files(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post("CMD-old")
        self.assertEqual(caught.exception.code, 400)
        saved = self.products.get_job(self.job["id"])
        self.assertEqual(saved.get("source_images"), [])


if __name__ == "__main__":
    unittest.main()
