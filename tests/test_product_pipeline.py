import base64
import json
import logging
import tempfile
import unittest
import urllib.request
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest import mock
from pathlib import Path

from PIL import Image

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.product_pipeline import ai_package_complete, completed_flow_clips, completed_product_segments, interrupted_product_candidate, product_ai_recovery_action, product_ai_recovery_command, product_progress, product_provider_failover_action, product_runtime_recovery_action, real_product_data, recoverable_product_candidate


class ProductPipelineTests(unittest.TestCase):
    def test_gemini_text_send_review_stops_both_recovery_layers(self):
        for partial in ([], ["generated/image_01.png"]):
            job = {"ai_status": "request_ready", "partial_generated_images": partial,
                   "runtime_recovery_count": 0, "automation_status": "error"}
            before = json.dumps(job, sort_keys=True)
            for code in ("GEMINI_TEXT_SEND_REVIEW", "gemini_text_send_review"):
                message = f"{code} • Google Flow • timeout • เก็บคำขอเดิม"
                with self.subTest(partial=partial, code=code):
                    self.assertEqual(product_ai_recovery_action(job, message), "")
                    self.assertEqual(product_runtime_recovery_action(job, message), "")
                    self.assertEqual(json.dumps(job, sort_keys=True), before)
            self.assertEqual(product_ai_recovery_action(job, "หน้าเว็บขาดการเชื่อมต่อ"), "resume_chatgpt")

    def test_accepted_analysis_timeout_does_not_trigger_either_recovery_layer(self):
        for partial in ([], ["generated/image_01.png"]):
            job = {"ai_status": "request_ready", "partial_generated_images": partial,
                   "runtime_recovery_count": 0, "automation_status": "error"}
            before = json.dumps(job, sort_keys=True)
            for message in (
                "AI_ANALYSIS_TIMEOUT • ChatGPT Web",
                "ChatGPT Web ใช้เวลาตอบนานเกิน 6 นาที • ระบบไม่ส่ง Prompt ซ้ำ",
                "Gemini Web ใช้เวลาตอบนานเกิน 6 นาที • ระบบไม่ส่ง Prompt ซ้ำ",
                "Google Flow / คลิปสินค้า • AI_ANALYSIS_TIMEOUT • ChatGPT Web",
            ):
                with self.subTest(partial=partial, message=message):
                    self.assertEqual(product_ai_recovery_action(job, message), "")
                    self.assertEqual(product_runtime_recovery_action(job, message), "")
                    self.assertEqual(json.dumps(job, sort_keys=True), before)

    def test_flow_runtime_failure_can_resume_same_checkpoint_but_manual_states_cannot(self):
        job = {
            "id": "JOB-FLOW-RUNTIME",
            "automation_status": "error",
            "status": "waiting_video",
            "ai_status": "ready",
            "voice_status": "ready",
            "generated_images": ["one", "two", "three"],
            "runtime_recovery_count": 0,
        }
        self.assertEqual(
            product_runtime_recovery_action(job, "Google Flow ช็อต 1: รูปหรือ Prompt ยังไม่พร้อม"),
            "resume_pipeline",
        )
        self.assertEqual(product_runtime_recovery_action(job, "Google Flow ต้อง Login ก่อน"), "")
        self.assertEqual(product_runtime_recovery_action(job, "Google Flow รออนุมัติเครดิต"), "")
        self.assertEqual(
            product_runtime_recovery_action(
                job,
                "Google Flow ช็อต 1: หยุดอย่างปลอดภัยหลังลองแนบรูปหนึ่งครั้ง • ระบบจะไม่อัปโหลดรูปซ้ำ",
            ),
            "",
        )
        self.assertEqual(
            product_runtime_recovery_action(job, "FLOW_ATTACH_SAFE_TARGET_MISSING"),
            "",
        )
        self.assertEqual(product_runtime_recovery_action(dict(job, runtime_recovery_count=2), "Google Flow ไม่รับคำสั่ง"), "")

    def test_recent_terminal_flow_error_is_recovered_after_engine_exit(self):
        now = datetime(2026, 8, 29, 21, 45, 0)
        job = {
            "id": "JOB-ENGINE-EXIT",
            "automation_status": "error",
            "automation_error": "Google Flow ช็อต 1 ไม่พบไฟล์ดาวน์โหลด",
            "status": "waiting_video",
            "ai_status": "ready",
            "voice_status": "ready",
            "runtime_recovery_count": 0,
            "updated_at": (now - timedelta(seconds=20)).isoformat(),
        }
        self.assertEqual(recoverable_product_candidate([job], now=now)["id"], job["id"])
        self.assertIsNone(recoverable_product_candidate([dict(job, automation_error="Google Flow ต้อง Login ก่อน")], now=now))

    def test_startup_recovery_selects_only_newest_recent_running_job(self):
        now = datetime(2026, 8, 29, 1, 30, 0)
        jobs = [
            {"id": "JOB-COMPLETED", "automation_status": "completed", "automation_stage": "flow", "updated_at": now.isoformat()},
            {"id": "JOB-OLD", "automation_status": "running", "automation_stage": "flow", "updated_at": (now - timedelta(hours=2)).isoformat()},
            {"id": "JOB-VOICE", "automation_status": "running", "automation_stage": "voice", "updated_at": (now - timedelta(minutes=8)).isoformat()},
            {"id": "JOB-FLOW", "automation_status": "running", "automation_stage": "flow", "updated_at": (now - timedelta(minutes=2)).isoformat()},
        ]
        selected = interrupted_product_candidate(jobs, now=now)
        self.assertEqual(selected["id"], "JOB-FLOW")
        self.assertIsNone(interrupted_product_candidate([jobs[1]], now=now))

        exhausted = dict(jobs[3], runtime_recovery_count=2)
        self.assertIsNone(interrupted_product_candidate([exhausted], now=now))
        self.assertEqual(
            interrupted_product_candidate([exhausted], now=now, recovery_limit=None)["id"],
            "JOB-FLOW",
        )

    def test_automation_errors_keep_bounded_failure_history(self):
        with tempfile.TemporaryDirectory() as temp:
            manager, job, _source = self._ready_request_job(Path(temp))
            manager.set_automation_state(job["id"], "running", "flow")
            failed = manager.set_automation_state(job["id"], "error", "stopped", "Chrome หลุด")
            self.assertEqual(failed["automation_failure_total"], 1)
            self.assertEqual(failed["automation_failure_history"][-1]["stage"], "flow")
            self.assertIn("Chrome หลุด", failed["automation_failure_history"][-1]["error"])

    def test_atomic_manifest_replace_retries_transient_windows_file_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            manager, job, _source = self._ready_request_job(Path(temp))
            real_replace = __import__("os").replace
            attempts = {"count": 0}

            def flaky_replace(source, target):
                attempts["count"] += 1
                if attempts["count"] < 4:
                    raise PermissionError(5, "Access is denied", str(target))
                return real_replace(source, target)

            with mock.patch("core.product_manager.os.replace", side_effect=flaky_replace):
                saved = manager.set_subtitle_requested(job["id"], True)

            self.assertTrue(saved["subtitle_requested"])
            # Three transient failures, one primary replace and one durable
            # recovery-backup replace.
            self.assertEqual(attempts["count"], 5)
            self.assertTrue(json.loads((manager.root / job["id"] / "job.json").read_text(encoding="utf-8"))["subtitle_requested"])

    def test_job_manifest_writes_are_atomic_and_serialized_across_managers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager, job, _source = self._ready_request_job(root)
            second_manager = ProductManager(root)

            def update_automation(_index):
                manager.set_automation_state(job["id"], "running", "flow")

            def update_subtitle(_index):
                second_manager.set_subtitle_requested(job["id"], True)

            def update_provider(_index):
                manager.set_image_ai_provider(job["id"], "chatgpt")

            with ThreadPoolExecutor(max_workers=9) as pool:
                futures = []
                for index in range(30):
                    futures.extend((
                        pool.submit(update_automation, index),
                        pool.submit(update_subtitle, index),
                        pool.submit(update_provider, index),
                    ))
                for future in futures:
                    future.result()

            manifest_path = manager.root / job["id"] / "job.json"
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["automation_stage"], "flow")
            self.assertTrue(saved["subtitle_requested"])
            self.assertEqual(saved["image_ai_provider"], "chatgpt")
            self.assertFalse(list(manifest_path.parent.glob(".job.json.*.tmp")))

    def test_product_jobs_are_sorted_by_actual_creation_time_not_random_id_suffix(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = ProductManager(root)
            for job_id in ("JOB-20260827-ZZZZZZ", "JOB-20260827-000001"):
                folder = manager.root / job_id
                folder.mkdir(parents=True)
                (folder / "job.json").write_text(json.dumps({
                    "id": job_id,
                    "product_name": job_id,
                    "product_url": "https://shopee.co.th/product/1/2",
                    "ai_status": "not_generated",
                    "ai_review_status": "not_generated",
                    "voice_status": "not_generated",
                    "subtitle_status": "not_generated",
                    "created_at": "2026-08-27T10:00:00",
                    "updated_at": "2026-08-27T10:00:00",
                }), encoding="utf-8")
                (folder / "ai_request.json").write_text(json.dumps({"schema_version": 7}), encoding="utf-8")
            manager.list_jobs()  # Normalize the intentionally minimal manifests.
            older = manager.root / "JOB-20260827-ZZZZZZ" / "job.json"
            newer = manager.root / "JOB-20260827-000001" / "job.json"
            older_data = json.loads(older.read_text(encoding="utf-8"))
            newer_data = json.loads(newer.read_text(encoding="utf-8"))
            older_data["created_at"] = "2026-08-27T10:00:00"
            newer_data["created_at"] = "2026-08-27T18:00:00"
            older.write_text(json.dumps(older_data), encoding="utf-8")
            newer.write_text(json.dumps(newer_data), encoding="utf-8")

            jobs = manager.list_jobs()
            self.assertEqual(jobs[0]["id"], "JOB-20260827-000001")

    def _ready_request_job(self, root):
        manager = ProductManager(root)
        job, _ = manager.import_product({
            "product_name": "กระเป๋าทดสอบ",
            "product_url": "https://shopee.co.th/product/123/456",
            "posting_product_url": "https://s.shopee.co.th/test",
            "images": [],
        })
        source = Path(root) / "source.png"
        Image.new("RGB", (48, 72), "orange").save(source)
        job = manager.attach_images(job["id"], [source])
        return manager, job, source

    def _ai_payload(self, job_id, source):
        image = base64.b64encode(Path(source).read_bytes()).decode()
        return {
            "job_id": job_id,
            "caption_short": "แคปชั่นขายสินค้า",
            "spoken_script": "บทพูดภาษาไทยสำหรับขายสินค้า",
            "flow_shot_prompts": ["ช็อตหนึ่ง", "ช็อตสอง", "ช็อตสาม"],
            "generated_images": [image, image, image],
        }

    def test_checkpoints_are_based_on_real_files(self):
        with tempfile.TemporaryDirectory() as temp:
            manager, job, source = self._ready_request_job(Path(temp))
            self.assertTrue(real_product_data(job))
            manager.set_automation_state(job["id"], "running", "ai")
            job = manager.apply_ai_result(self._ai_payload(job["id"], source))
            folder = manager.root / job["id"]
            self.assertEqual(job["automation_status"], "running")
            self.assertTrue(ai_package_complete(job, folder))
            self.assertEqual(product_progress(job, folder), 38)
            for index in (1, 2):
                clip = Path(temp) / f"clip-{index}.mp4"
                clip.write_bytes(f"flow-{index}".encode())
                job = manager.attach_flow_clip(job["id"], index, clip)
            self.assertEqual(completed_flow_clips(job, folder), [1, 2])

    def test_product_progress_counts_local_policy_segment_without_calling_it_flow(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for name in ("one.mp4", "two-local.mp4", "three.mp4"):
                (folder / name).write_bytes(name.encode())
            job = {
                "flow_target_clip_count": 3,
                "flow_clips": {"1": "one.mp4", "3": "three.mp4"},
                "flow_local_motion_clips": {"2": "two-local.mp4"},
            }
            self.assertEqual(completed_flow_clips(job, folder), [1, 3])
            self.assertEqual(completed_product_segments(job, folder), [1, 2, 3])

    def test_one_click_mode_owns_flow_queue_after_ai_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager, job, source = self._ready_request_job(root)
            manager.set_automation_state(job["id"], "running", "ai")
            bridge = LocalBridge("127.0.0.1", 0, manager, logging.getLogger("product-pipeline-test")).start()
            try:
                port = bridge.server.server_address[1]
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/ai/result",
                    data=json.dumps(self._ai_payload(job["id"], source)).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                result = json.load(urllib.request.urlopen(request))
                self.assertTrue(result["ok"])
                self.assertIsNone(result["flow_command"])
                self.assertFalse(any(item["action"] == "open_flow" for item in bridge._extension_commands))
            finally:
                bridge.stop()

    def test_product_images_checkpoint_and_recovery_without_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            manager, job, source = self._ready_request_job(Path(temp))
            encoded = base64.b64encode(source.read_bytes()).decode()
            checkpointed = manager.save_partial_image(job["id"], 1, encoded)
            self.assertEqual(checkpointed["partial_image_count"], 1)
            self.assertTrue((manager.root / job["id"] / checkpointed["partial_generated_images"][0]).is_file())
            package = manager.plugin_request(job["id"])
            self.assertEqual(len(package["checkpoint_images"]), 1)
            self.assertEqual(product_ai_recovery_action(checkpointed, "ChatGPT Web ไม่ส่งรูปใหม่ภายใน 6 นาที"), "resume_chatgpt")
            recovering = manager.mark_ai_recovering(job["id"], "timeout")
            self.assertEqual(recovering["ai_auto_recovery_attempts"], 1)
            reset = manager.reset_ai_recovery_attempts(job["id"])
            self.assertNotIn("ai_auto_recovery_attempts", reset)

    def test_product_ai_recovery_stops_for_user_action_errors(self):
        job = {"ai_status": "request_ready", "partial_generated_images": ["generated/selling_image_01.png"]}
        self.assertEqual(product_ai_recovery_action(job, "กรุณาเข้าสู่ระบบ ChatGPT"), "")
        self.assertEqual(product_ai_recovery_action(job, "เครดิตไม่พอ"), "")
        self.assertEqual(product_ai_recovery_action(job, "กรุณายืนยัน reCAPTCHA ใน Google Chrome"), "")

    def test_product_ai_can_fall_back_from_google_verification_redirect(self):
        job = {"ai_status": "request_ready", "partial_generated_images": []}
        self.assertEqual(product_ai_recovery_action(job, "Gemini Web ถูกเปลี่ยนเส้นทางไปหน้าตรวจสอบของ Google"), "resume_chatgpt")

    def test_product_ai_recovers_from_incomplete_gemini_json_without_checkpoint(self):
        job = {"ai_status": "request_ready", "partial_generated_images": [], "generated_images": []}
        self.assertEqual(
            product_ai_recovery_action(job, "JSON ขาดข้อมูล: warnings หลังลองจัดรูปแบบอัตโนมัติ 2 รอบ"),
            "resume_chatgpt",
        )

    def test_product_ai_retries_attachment_failure_but_not_uncertain_send(self):
        job = {"ai_status": "request_ready", "partial_generated_images": [], "generated_images": []}
        self.assertEqual(
            product_ai_recovery_action(job, "แนบรูปเข้า Gemini Web ยังไม่ขึ้นในช่องพิมพ์ • ระบบยังไม่กดส่ง"),
            "resume_chatgpt",
        )
        self.assertEqual(
            product_ai_recovery_action(job, "กดปุ่มส่ง Gemini Web แล้ว แต่หน้าเว็บยังไม่ยืนยัน"),
            "",
        )

    def test_product_gemini_refusal_fails_over_to_chatgpt_without_reusing_provider(self):
        job = {"image_ai_provider": "gemini", "ai_status": "request_ready", "generated_images": [], "partial_generated_images": []}
        message = "Gemini Web ปฏิเสธการวิเคราะห์และไม่ส่ง JSON สำหรับ Job นี้"
        self.assertEqual(product_provider_failover_action(job, message), "")
        self.assertEqual(product_provider_failover_action(dict(job, image_ai_provider="chatgpt"), message), "")

    def test_product_request_treats_warnings_as_optional(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = ProductManager(Path(temporary))
            job, _created = manager.import_product({
                "product_name": "สินค้า Gemini",
                "product_url": "https://shopee.co.th/product/123/456",
                "product_images": [],
            })
            package = manager.plugin_request(job["id"])
            self.assertNotIn("warnings", package["request"]["required_fields"])
            self.assertIn("spoken_script", package["request"]["required_fields"])

    def test_product_ai_recovery_reanalyzes_when_browser_analysis_was_not_saved(self):
        no_checkpoint = {"ai_status": "request_ready", "partial_generated_images": [], "generated_images": []}
        self.assertEqual(product_ai_recovery_command(no_checkpoint, 1), "open_chatgpt")
        self.assertEqual(product_ai_recovery_command(no_checkpoint, 2), "open_chatgpt")
        checkpointed = {"ai_status": "request_ready", "partial_generated_images": ["generated/selling_image_01.png"]}
        self.assertEqual(product_ai_recovery_command(checkpointed, 1), "resume_chatgpt")
        self.assertEqual(product_ai_recovery_command(checkpointed, 2), "restart_chatgpt_images")


if __name__ == "__main__":
    unittest.main()
