import base64
import io
import json
import logging
import tempfile
import time
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager


class ProductResultHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.products = ProductManager(Path(self.temp.name))
        self.job, _created = self.products.import_product({
            "product_name": "สินค้าทดสอบ", "product_url": "https://shopee.co.th/test", "images": [],
        })
        image = io.BytesIO()
        Image.new("RGB", (32, 32), "blue").save(image, format="PNG")
        encoded = base64.b64encode(image.getvalue()).decode("ascii")
        self.payload = {
            "job_id": self.job["id"], "caption_short": "แคปชั่นเดิม", "hashtags": [],
            "video_prompt": "วิดีโอสินค้า", "flow_shot_prompts": ["ช็อตหนึ่ง", "ช็อตสอง", "ช็อตสาม"],
            "spoken_script": "ลองดูสินค้าชิ้นนี้", "generated_images": [encoded] * 3,
        }
        self.on_import = Mock()
        self.bridge = LocalBridge(
            "127.0.0.1", 0, self.products, logging.getLogger("product-result-handoff"),
            on_import=self.on_import,
        ).start()
        self.addCleanup(self.bridge.stop)
        self.url = f"http://127.0.0.1:{self.bridge.server.server_address[1]}/api/ai/result"

    def post(self, payload=None):
        request = urllib.request.Request(
            self.url, data=json.dumps(payload or self.payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    def checkpoint_final(self):
        folder = self.products.root / self.job["id"]
        clip = folder / "videos" / "flow-shot-01.mp4"
        clip.write_bytes(b"existing Flow checkpoint")
        manifest = self.products.get_job(self.job["id"])
        manifest.update({"flow_clips": {"1": "videos/flow-shot-01.mp4"}, "video_path": "videos/final.mp4"})
        self.products._save_manifest_file(folder / "job.json", manifest)
        return folder

    def test_late_cancelled_result_preserves_existing_files_and_never_hands_off(self):
        self.products.apply_ai_result(self.payload)
        folder = self.checkpoint_final()
        self.products.set_automation_state(self.job["id"], "cancelled", "cancelled")
        paths = [folder / "job.json", folder / "ai_result.json", folder / "generated/selling_image_01.png"]
        before = [path.read_bytes() for path in paths]

        response = self.post(dict(self.payload, caption_short="late cancelled response"))

        self.assertTrue(response["ignored"])
        self.assertEqual(response["reason"], "job_cancelled")
        self.assertIsNone(response["flow_command"])
        self.assertEqual([path.read_bytes() for path in paths], before)
        self.assertEqual(self.bridge._extension_commands, [])
        self.on_import.assert_not_called()

    def test_exact_result_retry_preserves_later_flow_checkpoint_and_hands_off_once(self):
        first = self.post()
        self.assertEqual(first["flow_command"]["action"], "open_flow")
        folder = self.checkpoint_final()
        before = (folder / "job.json").read_bytes()

        second = self.post(dict(reversed(list(self.payload.items()))))

        self.assertTrue(second["duplicate"])
        self.assertIsNone(second["flow_command"])
        self.assertEqual(second["job"]["flow_clips"], {"1": "videos/flow-shot-01.mp4"})
        self.assertEqual((folder / "job.json").read_bytes(), before)
        self.assertEqual(len(self.bridge._extension_commands), 1)
        self.on_import.assert_called_once()

    def test_concurrent_result_retries_commit_and_handoff_once(self):
        with patch.object(self.products, "apply_ai_result", wraps=self.products.apply_ai_result) as apply:
            with ThreadPoolExecutor(max_workers=2) as executor:
                responses = list(executor.map(lambda _index: self.post(), range(2)))
        self.assertEqual(sum(bool(row.get("duplicate")) for row in responses), 1)
        self.assertEqual(apply.call_count, 1)
        self.assertEqual(len(self.bridge._extension_commands), 1)
        self.on_import.assert_called_once()

    def test_failed_apply_does_not_record_a_success_receipt(self):
        with patch.object(self.products, "apply_ai_result", side_effect=ValueError("incomplete result")):
            with self.assertRaisesRegex(ValueError, "incomplete result"):
                self.bridge._accept_product_ai_result(self.payload)
        self.assertEqual(self.bridge._ai_result_receipts, {})
        self.assertEqual(self.post()["flow_command"]["action"], "open_flow")

    def test_changed_result_is_accepted_after_successful_result(self):
        self.post()
        response = self.post(dict(self.payload, caption_short="แคปชั่นใหม่"))
        self.assertFalse(response.get("duplicate", False))
        self.assertEqual(response["job"]["caption"], "แคปชั่นใหม่")
        self.assertEqual(len(self.bridge._extension_commands), 2)

    def test_retry_finishes_failed_handoff_without_reapplying_result(self):
        with patch.object(self.products, "apply_ai_result", wraps=self.products.apply_ai_result) as apply:
            with patch.object(self.bridge, "queue_extension_command", side_effect=ValueError("queue unavailable")):
                with self.assertRaisesRegex(ValueError, "queue unavailable"):
                    self.bridge._accept_product_ai_result(self.payload)
            folder = self.checkpoint_final()
            before = (folder / "job.json").read_bytes()
            response = self.post()
        self.assertTrue(response["duplicate"])
        self.assertEqual(response["flow_command"]["action"], "open_flow")
        self.assertEqual(apply.call_count, 1)
        self.assertEqual((folder / "job.json").read_bytes(), before)
        self.on_import.assert_called_once()

    def test_same_result_can_repair_an_invalidated_image_checkpoint(self):
        self.post()
        manifest = self.products.get_job(self.job["id"])
        manifest.update({"ai_status": "waiting", "generated_images": []})
        self.products._save_manifest_file(self.products.root / self.job["id"] / "job.json", manifest)
        with patch.object(self.products, "apply_ai_result", wraps=self.products.apply_ai_result) as apply:
            response = self.post()
        self.assertFalse(response["duplicate"])
        self.assertEqual(apply.call_count, 1)
        self.assertEqual(len(response["job"]["generated_images"]), 3)

    def test_pipeline_owned_and_terminal_jobs_do_not_get_automatic_flow(self):
        for status in ("running", "completed", "error"):
            with self.subTest(status=status):
                self.products.set_automation_state(self.job["id"], status, "test")
                response = self.post(dict(self.payload, caption_short=status))
                self.assertIsNone(response["flow_command"])
        self.assertEqual(self.bridge._extension_commands, [])

    def test_callback_cancellation_prevents_followup_browser_command(self):
        self.on_import.side_effect = lambda *_args: self.products.set_automation_state(
            self.job["id"], "cancelled", "cancelled"
        )
        response = self.post()
        self.assertIsNone(response["flow_command"])
        self.assertEqual(response["job"]["automation_status"], "cancelled")
        self.assertEqual(self.bridge._extension_commands, [])


class ProductFlowShotResolverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "JOB-SHOTS"
        (self.folder / "videos").mkdir(parents=True)
        self.job = {
            "id": "JOB-SHOTS", "generated_images": ["one.png", "two.png", "three.png"],
            "flow_shot_prompts": ["one", "two", "three"], "flow_clips": {},
            "flow_local_motion_clips": {}, "flow_policy_fallbacks": {},
        }
        products = SimpleNamespace(root=Path(self.temp.name), list_jobs=lambda: [self.job])
        self.bridge = LocalBridge("127.0.0.1", 0, products, logging.getLogger("flow-shot-resolver"))

    def resolve(self):
        return self.bridge._resolve_product_flow_shot(self.job["id"])

    def client(self, shot, *, age=0, version=None):
        return {
            "flow_job_id": self.job["id"], "flow_shot_index": shot,
            "last_seen_epoch": time.time() - age,
            "version": version or LocalBridge.REQUIRED_EXTENSION_VERSION,
        }

    def test_policy_slot_never_returns_to_flow_even_with_missing_local_file(self):
        self.job["flow_policy_fallbacks"]["1"] = {"failure_code": "FLOW_POLICY_BLOCKED"}
        self.job["flow_local_motion_clips"]["1"] = "videos/missing-local.mp4"
        self.bridge._extension_clients["previous"] = self.client(1)
        self.assertEqual(self.resolve(), 2)

    def test_attachment_pending_or_cleaned_slot_is_skipped_by_default_handoff(self):
        evidence = {
            "schema_version": 1, "phase": "before_submit", "attempt_key": "JOB-SHOTS:1:project-a",
            "attempt_started_at": 1000, "grace_started_at": 2000, "grace_elapsed_ms": 30000,
            "project_id": "project-a", "run_id": "RUN-A", "attachment_attempt_count": 1,
            "submission_absent": True, "generation_absent": True, "result_absent": True,
            "confirmation_absent": True, "terminal_latched": True,
        }
        self.job["flow_attachment_fallbacks"] = {"1": {
            "failure_code": "FLOW_ATTACHMENT_UNCONFIRMED", "flow_run_id": "RUN-A",
            "failure_card_fingerprint": "attachment:JOB-SHOTS:1:RUN-A:project-a:1000",
            "attachment_failure_evidence": evidence, "status": "render_pending",
        }}
        self.bridge._extension_clients["previous"] = self.client(1)
        self.assertEqual(self.resolve(), 2)
        self.job["flow_local_motion_clips"]["1"] = "videos/cleaned-local.mp4"
        self.assertEqual(self.resolve(), 2)
        evidence["submission_absent"] = False
        self.assertEqual(self.resolve(), 1, "Invalid evidence is not a local checkpoint")

    def test_local_motion_file_counts_as_completed_slot(self):
        (self.folder / "videos/local.mp4").write_bytes(b"local")
        self.job["flow_local_motion_clips"]["1"] = "videos/local.mp4"
        self.assertEqual(self.resolve(), 2)

    def test_expired_and_wrong_version_clients_cannot_choose_the_next_shot(self):
        self.job["flow_policy_fallbacks"]["1"] = {"failure_code": "FLOW_POLICY_BLOCKED"}
        self.bridge._extension_clients["expired"] = self.client(3, age=71)
        self.bridge._extension_clients["old-version"] = self.client(3, version="0.0.1")
        self.assertEqual(self.resolve(), 2)

    def test_current_compatible_unfinished_shot_keeps_ownership(self):
        self.bridge._extension_clients["older"] = self.client(2, age=5)
        self.bridge._extension_clients["active"] = self.client(3)
        self.assertEqual(self.resolve(), 3)

    def test_completed_remote_heartbeat_does_not_hide_missing_next_shot(self):
        (self.folder / "videos/remote.mp4").write_bytes(b"remote")
        self.job["flow_clips"]["1"] = "videos/remote.mp4"
        self.bridge._extension_clients["previous"] = self.client(1)
        self.assertEqual(self.resolve(), 2)

    def test_all_local_job_has_no_flow_slot_but_all_remote_job_can_focus_last_result(self):
        self.job["flow_policy_fallbacks"] = {
            str(index): {"failure_code": "FLOW_POLICY_BLOCKED"} for index in range(1, 4)
        }
        self.assertEqual(self.resolve(), 0)
        (self.folder / "videos/remote.mp4").write_bytes(b"remote")
        self.job["flow_policy_fallbacks"] = {}
        self.job["flow_clips"] = {str(index): "videos/remote.mp4" for index in range(1, 4)}
        self.assertEqual(self.resolve(), 3)


if __name__ == "__main__":
    unittest.main()
