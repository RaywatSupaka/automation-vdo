import json
import tempfile
import unittest
from pathlib import Path

from core.product_manager import ProductManager


class ProductSpecificCgiPromptTests(unittest.TestCase):
    def test_flow_package_puts_product_relevance_ahead_of_generic_hud(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job_id = "JOB-CGI-TEST"
            folder = manager.root / job_id
            (folder / "generated").mkdir(parents=True)
            (folder / "prompts").mkdir(parents=True)
            (folder / "captions").mkdir(parents=True)
            manifest = {
                "id": job_id,
                "product_name": "กรงสุนัขเหล็กพร้อมประตูและฝาปิดด้านบน",
                "description": "ตะแกรงเหล็กสีดำ ใช้แบ่งพื้นที่สัตว์เลี้ยง มีประตูด้านหน้า",
                "generated_images": ["generated/selling_image_01.png"],
                "flow_shot_prompts": ["Add generic technology HUD, radial dashboard and floating data cards."],
            }
            (folder / "job.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            package = manager.flow_package(job_id, 1)
            prompt = package["video_prompt"]

            self.assertEqual(package["cgi_prompt_policy"], "product_specific_v1")
            self.assertTrue(prompt.startswith("HIGHEST-PRIORITY PRODUCT-SPECIFIC CGI DIRECTION"))
            self.assertIn("กรงสุนัขเหล็กพร้อมประตูและฝาปิดด้านบน", prompt)
            self.assertIn("real visible feature, material, structure", prompt)
            self.assertIn("Do not use generic technology HUDs", prompt)
            self.assertLess(prompt.index("Do not use generic technology HUDs"), prompt.index("Add generic technology HUD"))

    def test_apparel_prompt_does_not_invent_controls_hose_or_mechanisms(self):
        manifest = {
            "product_name": "เสื้อคาร์ดิแกนแขนยาวติดกระดุม",
            "description": "เสื้อสีพื้น คอปก ผ้าริบแนวตั้ง",
        }
        prompt = ProductManager._product_specific_cgi_prompt("cinematic macro fashion shot", manifest, 2)
        self.assertIn("collar, button, seam, ribbing", prompt)
        self.assertNotIn("controls, hose", prompt)
        self.assertNotIn("mechanism", prompt)

    def test_terminal_policy_uses_same_image_local_motion_and_hybrid_final(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = ProductManager(Path(temp))
            job_id = "JOB-POLICY-HYBRID"
            folder = manager.root / job_id
            (folder / "generated").mkdir(parents=True)
            (folder / "videos" / ".working").mkdir(parents=True)
            manifest = {
                "id": job_id,
                "product_name": "สินค้าทดสอบ",
                "generated_images": [
                    "generated/selling_image_01.png",
                    "generated/selling_image_02.png",
                    "generated/selling_image_03.png",
                ],
                "flow_shot_prompts": ["shot one", "shot two", "shot three"],
                "flow_clips": {},
                "video_ai_provider": "flow",
                "flow_target_clip_count": 3,
                "flow_source_image_map": {"1": 1, "2": 3, "3": 3},
                "flow_source_variant_map": {"1": 1, "2": 1, "3": 2},
                "flow_prompt_retry_modes": {"2": "policy_safe_v1"},
            }
            (folder / "job.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            first = folder / "shot1.mp4"
            local_second = folder / "local2.mp4"
            third = folder / "shot3.mp4"
            first.write_bytes(b"first-real-video")
            local_second.write_bytes(b"local-motion-from-image-two")
            third.write_bytes(b"third-real-video")

            stale_package = manager.flow_package(job_id, 2)
            self.assertEqual(stale_package["source_image_index"], 2)
            self.assertEqual(stale_package["source_variant_index"], 1)
            self.assertEqual(stale_package["cgi_prompt_policy"], "product_specific_v1")
            self.assertIn("shot two", stale_package["video_prompt"])
            self.assertNotIn("ALTERNATE TAKE", stale_package["video_prompt"])
            normalized = manager.ensure_product_flow_source_identity(job_id)
            self.assertEqual(normalized["flow_source_image_map"], {"1": 1, "2": 2, "3": 3})
            self.assertEqual(normalized["flow_source_variant_map"], {"1": 1, "2": 1, "3": 1})
            self.assertNotIn("2", normalized["flow_prompt_retry_modes"])
            package_two = manager.flow_package(job_id, 2)
            package_three = manager.flow_package(job_id, 3)
            manager.attach_flow_clip(job_id, 1, first)
            pending = manager.mark_flow_policy_fallback(
                job_id, 2, 2, "policy denied", category="face_or_public_figure",
                fingerprint="policy-card-2", flow_run_id="flow-run-2",
            )
            # Simulate a process crash after the terminal decision was saved
            # but before FFmpeg could attach its local segment.
            resumed_manager = ProductManager(Path(temp))
            repeated = resumed_manager.mark_flow_policy_fallback(
                job_id, 2, 2, "same heartbeat", category="face_or_public_figure",
                fingerprint="policy-card-2", flow_run_id="flow-run-2",
            )
            self.assertEqual(pending["flow_policy_fallbacks"]["2"]["status"], "render_pending")
            self.assertEqual(len(repeated["flow_policy_fallback_history"]), 1)
            local_ready = resumed_manager.attach_flow_local_motion_clip(
                job_id, 2, local_second,
                {"source_type": "product_local_motion_policy_fallback"},
            )
            manager.attach_flow_clip(job_id, 3, third)
            final = folder / "videos" / ".working" / "joined.mp4"
            final.write_bytes(b"joined-three-clips")
            completed = manager.promote_video(job_id, str(final.relative_to(folder)), flow_source_path=str(final.relative_to(folder)))

            self.assertEqual(package_two["source_image_index"], 2)
            self.assertEqual(package_two["source_variant_index"], 1)
            self.assertEqual(package_three["source_image_index"], 3)
            self.assertEqual(package_three["source_variant_index"], 1)
            self.assertNotIn("ALTERNATE TAKE", package_three["video_prompt"])
            self.assertEqual(local_ready["flow_remote_clip_count"], 1)
            self.assertEqual(local_ready["flow_local_motion_clip_count"], 1)
            self.assertEqual(completed["flow_clip_count"], 2)
            self.assertEqual(completed["flow_remote_clip_count"], 2)
            self.assertEqual(completed["flow_local_motion_clip_count"], 1)
            self.assertEqual(completed["flow_segment_count"], 3)
            self.assertEqual(completed["video_source_type"], "google_flow_hybrid_composite")
            self.assertEqual(completed["flow_segment_provenance"]["2"]["flow_run_id"], "flow-run-2")
            with self.assertRaisesRegex(ValueError, "ห้ามส่งเข้า Google Flow ซ้ำ"):
                manager.flow_package(job_id, 2)
            with self.assertRaisesRegex(ValueError, "ห้ามส่งซ้ำ"):
                manager.attach_flow_clip(job_id, 2, first)


if __name__ == "__main__":
    unittest.main()
