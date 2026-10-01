import base64
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core.product_manager import ProductManager


class ProductFlowIntegrityTests(unittest.TestCase):
    def test_new_chatgpt_images_invalidate_old_flow_clips(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = ProductManager(root)
            job, _ = manager.import_product({"product_name": "สินค้าทดสอบ", "product_url": "https://affiliate.shopee.co.th/test", "images": []})
            folder = manager.root / job["id"]
            joined = folder / "videos" / "joined.mp4"
            joined.write_bytes(b"video")
            with self.assertRaisesRegex(ValueError, "Google Flow"):
                manager.promote_video(job["id"], "videos/joined.mp4", "videos/joined.mp4")
            for index in (1, 2, 3):
                clip = root / f"clip-{index}.mp4"
                clip.write_bytes(f"flow-video-{index}".encode())
                manager.attach_flow_clip(job["id"], index, clip)
            promoted = manager.promote_video(job["id"], "videos/joined.mp4", "videos/joined.mp4")
            self.assertEqual(promoted["video_source_type"], "google_flow_composite")
            self.assertEqual(promoted["video_without_subtitle_path"], "")
            self.assertEqual(promoted["subtitle_video_path"], "")
            self.assertEqual(promoted["audio_mix_path"], "")
            image = root / "image.png"
            Image.new("RGB", (32, 48), "orange").save(image)
            encoded = base64.b64encode(image.read_bytes()).decode()
            refreshed = manager.apply_ai_result({
                "job_id": job["id"], "caption_short": "แคปชั่น", "spoken_script": "บทพูดภาษาไทย",
                "image_prompts": ["หนึ่ง", "สอง", "สาม"], "flow_shot_prompts": ["หนึ่ง", "สอง", "สาม"],
                "generated_images": [encoded, encoded, encoded],
            })
            self.assertEqual(refreshed["flow_clip_count"], 0)
            self.assertEqual(refreshed["flow_clips"], {})
            self.assertEqual(refreshed["video_status"], "waiting_flow")
            self.assertEqual(refreshed["video_source_type"], "google_flow_pending")
            self.assertEqual(len(refreshed["stale_flow_clips"]), 3)

    def test_duplicate_flow_clip_is_rejected_before_manifest_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = ProductManager(root)
            job, _ = manager.import_product({"product_name": "สินค้าทดสอบ", "product_url": "https://affiliate.shopee.co.th/test", "images": []})
            first = root / "first.mp4"
            duplicate = root / "duplicate.mp4"
            first.write_bytes(b"identical-flow-result")
            duplicate.write_bytes(b"identical-flow-result")
            manager.attach_flow_clip(job["id"], 1, first)
            with self.assertRaisesRegex(ValueError, "ซ้ำกับช็อต 1"):
                manager.attach_flow_clip(job["id"], 2, duplicate)
            current = manager.get_job(job["id"])
            self.assertEqual(current["flow_clip_count"], 1)
            self.assertNotIn("2", current["flow_clips"])


if __name__ == "__main__":
    unittest.main()
