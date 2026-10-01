"""Local Shopee image-capture diagnostics; no live site or provider access."""
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image

from core.atomic_json import AtomicJsonFile
from core.product_manager import ProductManager
from core.product_story import prepare_link


class ProductCaptureDiagnostics420Tests(unittest.TestCase):
    def test_capture_failure_records_http_reason_without_signed_url(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            product = {
                "product_name": "Fixture product",
                "product_url": "https://shopee.co.th/item",
                "images": [],
            }
            job, created = manager.import_product(product, force_new=True)
            self.assertTrue(created)
            signed = "https://down-th.img.susercontent.com/item.jpg?token=PRIVATE"
            failure = urllib.error.HTTPError(signed, 403, "Forbidden", {}, None)
            with patch.object(manager, "_download_image", side_effect=failure):
                manager.import_product({**product, "images": [signed]}, target_job_id=job["id"])

            saved = manager.get_job(job["id"])
            self.assertEqual(saved["source_image_capture"]["attempted"], 1)
            self.assertEqual(saved["source_image_capture"]["saved"], 0)
            self.assertEqual(saved["source_image_capture"]["failures"], [
                {"host": "down-th.img.susercontent.com", "reason": "HTTP 403"}
            ])
            self.assertNotIn("PRIVATE", json.dumps(saved["source_image_capture"]))

    def test_partial_image_success_is_saved_and_failure_count_is_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            product = {
                "product_name": "Fixture product",
                "product_url": "https://shopee.co.th/item",
                "images": [],
            }
            job, _ = manager.import_product(product, force_new=True)
            failed_url = "https://img.example/blocked.jpg"
            failed = urllib.error.HTTPError(failed_url, 503, "Unavailable", {}, None)

            def download(url, folder, index):
                if url == failed_url:
                    raise failed
                target = Path(folder) / f"product_{index:02d}.jpg"
                target.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (160, 200), "teal").save(target, format="JPEG")
                return target

            with patch.object(manager, "_download_image", side_effect=download):
                manager.import_product(
                    {**product, "images": [failed_url, "https://img.example/ok.jpg"]},
                    target_job_id=job["id"],
                )

            saved = manager.get_job(job["id"])
            self.assertEqual(len(saved["source_images"]), 1)
            self.assertEqual(saved["source_images"], ["original/product_02.jpg"])
            self.assertTrue((manager.root / job["id"] / saved["source_images"][0]).is_file())
            self.assertEqual(saved["source_image_capture"]["attempted"], 2)
            self.assertEqual(saved["source_image_capture"]["saved"], 1)
            self.assertEqual(saved["source_image_capture"]["failures"][0]["reason"], "HTTP 503")

    def test_failed_extension_capture_surfaces_saved_download_reason(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = AtomicJsonFile(root / "JOB-X" / "job.json")
            store.write({
                "id": "JOB-X",
                "product_name": "Fixture product",
                "source_images": [],
                "story_source_only": True,
                "source_image_capture": {
                    "attempted": 2,
                    "saved": 0,
                    "failures": [{"host": "img.example", "reason": "HTTP 403"}],
                },
            })
            command = {"id": "CMD-X", "status": "failed", "error": "ภาพสินค้าไม่พร้อม"}
            products = SimpleNamespace(
                root=root,
                project_root=root,
                _manifest_store=lambda _path: store,
                import_link=lambda *_args, **_kwargs: (store.read({}), True),
                get_job=lambda _job_id: store.read({}),
            )
            bridge = Mock()
            bridge.queue_extension_command.return_value = {"id": "CMD-X"}
            bridge.extension_command_status.return_value = command
            cast = Mock()

            with self.assertRaises(ValueError) as caught:
                prepare_link(products, cast, bridge, {"link": "https://shopee.co.th/item"})

            self.assertIn("img.example: HTTP 403", str(caught.exception))
            self.assertIn("ยังไม่ได้ส่งงานไป AI", str(caught.exception))
            cast.snapshot.assert_not_called()


if __name__ == "__main__":
    unittest.main()
