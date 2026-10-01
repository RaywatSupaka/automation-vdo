import base64
import io
import json
import logging
import os
import socket
import struct
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager


class LocalBridgeTests(unittest.TestCase):
    def test_extension_trace_is_visible_persisted_and_does_not_replace_flow_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            products = ProductManager(root)
            bridge = LocalBridge(
                "127.0.0.1", 0, products, logging.getLogger("extension-trace-test")
            ).start()
            port = bridge.server.server_address[1]

            def post(path, payload):
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}{path}",
                    data=json.dumps(payload).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                return json.load(urllib.request.urlopen(request))

            try:
                client_id = "trace-client"
                post("/api/extension/heartbeat", {
                    "client_id": client_id,
                    "version": LocalBridge.REQUIRED_EXTENSION_VERSION,
                    "browser": "Google Chrome",
                    "page": "flow",
                })
                post("/api/extension/progress", {
                    "client_id": client_id,
                    "scope": "flow",
                    "step": "image_upload_complete",
                    "job_id": "JOB-TRACE",
                    "shot_index": 2,
                    "message": "อัปโหลดรูปครบ 100%",
                })
                result = post("/api/extension/progress", {
                    "client_id": client_id,
                    "scope": "trace",
                    "service": "flow",
                    "action": "animate_action_clicked",
                    "job_id": "JOB-TRACE",
                    "shot_index": 2,
                    "message": "กดทำให้เคลื่อนไหวหนึ่งครั้ง",
                    "detail": {"target": "ทำให้เคลื่อนไหว"},
                })
                self.assertTrue(result["ok"])
                status = bridge.extension_status()
                self.assertEqual(status["client"]["flow_step"], "image_upload_complete")
                self.assertEqual(status["trace"][-1]["action"], "animate_action_clicked")
                self.assertEqual(status["trace"][-1]["shot_index"], 2)
                trace_path = products.root / "JOB-TRACE" / "logs" / "extension_trace.jsonl"
                self.assertTrue(trace_path.is_file())
                saved = json.loads(trace_path.read_text(encoding="utf-8").splitlines()[-1])
                self.assertEqual(saved["detail"]["target"], "ทำให้เคลื่อนไหว")
            finally:
                bridge.stop()

    def test_hybrid_desktop_routes_preserve_extension_bridge(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            web_root = root / "web_ui"
            web_root.mkdir()
            (web_root / "index.html").write_text("<!doctype html><title>Hybrid</title>", encoding="utf-8")
            (web_root / "app.js").write_text("window.hybridReady=true;", encoding="utf-8")
            preview = root / "preview.png"
            Image.new("RGB", (24, 24), "purple").save(preview)
            actions = []

            bridge = LocalBridge(
                "127.0.0.1",
                0,
                ProductManager(root),
                logging.getLogger("hybrid-bridge-test"),
                desktop_state=lambda: {"app": {"mode": "hybrid"}, "products": []},
                desktop_action=lambda action, payload: actions.append((action, payload)) or {"ok": True, "accepted": True},
                desktop_media=lambda item_id, kind: preview if item_id == "preview" and kind == "preview" else "",
                desktop_web_root=web_root,
            ).start()
            port = bridge.server.server_address[1]
            try:
                health = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/health"))
                self.assertEqual(health["desktop_ui"], "hybrid")
                self.assertEqual(health["engine_pid"], os.getpid())
                html = urllib.request.urlopen(f"http://127.0.0.1:{port}/desktop/").read().decode("utf-8")
                self.assertIn("Hybrid", html)
                script = urllib.request.urlopen(f"http://127.0.0.1:{port}/desktop/app.js").read().decode("utf-8")
                self.assertIn("hybridReady", script)
                state = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/desktop/state"))
                self.assertTrue(state["ok"])
                self.assertEqual(state["app"]["mode"], "hybrid")
                self.assertGreater(len(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/desktop/media?item_id=preview&kind=preview").read()), 40)

                body = json.dumps({"action": "refresh", "payload": {"source": "test"}}).encode("utf-8")
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/desktop/action",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"},
                )
                result = json.load(urllib.request.urlopen(request))
                self.assertTrue(result["accepted"])
                self.assertEqual(actions, [("refresh", {"source": "test"})])

                blocked = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/desktop/action",
                    data=body,
                    method="POST",
                    headers={"Content-Type": "application/json", "Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
                )
                with self.assertRaises(urllib.error.HTTPError) as blocked_error:
                    urllib.request.urlopen(blocked)
                self.assertEqual(blocked_error.exception.code, 403)
            finally:
                bridge.stop()

    def test_cancelled_media_stream_does_not_emit_socketserver_traceback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            media = root / "large-preview.mp4"
            with media.open("wb") as handle:
                handle.seek(24 * 1024 * 1024 - 1)
                handle.write(b"\0")
            bridge = LocalBridge(
                "127.0.0.1", 0, ProductManager(root), logging.getLogger("disconnect-stream-test"),
                desktop_media=lambda item_id, kind: media if item_id == "large" else "",
            ).start()
            port = bridge.server.server_address[1]
            captured = io.StringIO()
            try:
                with redirect_stderr(captured):
                    connection = socket.create_connection(("127.0.0.1", port), timeout=5)
                    connection.sendall(
                        b"GET /api/desktop/media?item_id=large&kind=video HTTP/1.1\r\n"
                        b"Host: 127.0.0.1\r\nConnection: close\r\n\r\n"
                    )
                    connection.recv(512)
                    connection.setsockopt(
                        socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
                    )
                    connection.close()
                    time.sleep(0.25)
                self.assertNotIn("Exception occurred during processing", captured.getvalue())
                self.assertNotIn("Traceback", captured.getvalue())
            finally:
                bridge.stop()

    def test_extension_session_capability_protects_browser_origin_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bridge = LocalBridge(
                "127.0.0.1", 0, ProductManager(root),
                logging.getLogger("extension-token-test"),
            ).start()
            port = bridge.server.server_address[1]
            extension_origin = "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            from tests.extension_identity_fixture import pair_fixture
            pair_fixture(bridge,extension_origin)

            def request(path, *, data=None, origin="", token=""):
                headers = {}
                if data is not None:
                    headers["Content-Type"] = "application/json"
                if origin:
                    headers["Origin"] = origin
                if token:
                    headers["X-SmartFlow-Token"] = token
                return urllib.request.Request(
                    f"http://127.0.0.1:{port}{path}",
                    data=json.dumps(data).encode() if data is not None else None,
                    method="POST" if data is not None else "GET",
                    headers=headers,
                )

            try:
                heartbeat_request = request(
                    "/api/extension/heartbeat",
                    data={
                        "client_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "version": LocalBridge.REQUIRED_EXTENSION_VERSION,
                        "browser": "Google Chrome",
                        "page": "other",
                    },
                    origin=extension_origin,
                )
                with urllib.request.urlopen(heartbeat_request) as response:
                    heartbeat = json.load(response)
                    self.assertEqual(
                        response.headers.get("Access-Control-Allow-Origin"), extension_origin
                    )
                    self.assertIn(
                        "X-SmartFlow-Token",
                        response.headers.get("Access-Control-Allow-Headers") or "",
                    )
                token = heartbeat.get("extension_token")
                self.assertTrue(isinstance(token, str) and len(token) >= 32)

                protected_path = "/api/extension/commands?client_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                with self.assertRaises(urllib.error.HTTPError) as missing_error:
                    urllib.request.urlopen(request(protected_path, origin=extension_origin))
                self.assertEqual(missing_error.exception.code, 403)
                with self.assertRaises(urllib.error.HTTPError) as wrong_error:
                    urllib.request.urlopen(
                        request(protected_path, origin=extension_origin, token="wrong-token")
                    )
                self.assertEqual(wrong_error.exception.code, 403)

                with urllib.request.urlopen(
                    request(protected_path, origin=extension_origin, token=token)
                ) as protected_response:
                    protected = json.load(protected_response)
                self.assertTrue(protected["ok"])

                with self.assertRaises(urllib.error.HTTPError) as evil_error:
                    urllib.request.urlopen(
                        request(protected_path, origin="https://evil.example", token=token)
                    )
                self.assertEqual(evil_error.exception.code, 403)

                progress_request = request(
                    "/api/extension/progress",
                    data={
                        "client_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "step": "package_ready",
                        "job_id": "",
                        "shot_index": 0,
                        "message": "token-authenticated progress",
                    },
                    origin=extension_origin,
                    token=token,
                )
                self.assertTrue(json.load(urllib.request.urlopen(progress_request))["ok"])

                # Local CLI/tests intentionally remain compatible without a
                # browser Origin or persistent credential.
                local_commands = json.load(urllib.request.urlopen(
                    f"http://127.0.0.1:{port}{protected_path}"
                ))
                self.assertTrue(local_commands["ok"])
                status_text = urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/extension/status"
                ).read().decode("utf-8")
                self.assertNotIn(token, status_text)
            finally:
                bridge.stop()

    def test_import_and_duplicate_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            products = ProductManager(root)
            bridge = LocalBridge("127.0.0.1", 0, products, logging.getLogger("bridge-test")).start()
            port = bridge.server.server_address[1]
            try:
                health = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/health"))
                self.assertTrue(health["ok"])
                self.assertEqual(health["ai_provider"], "browser_extension")
                self.assertEqual(health["ai_providers"], ["chatgpt_web", "gemini_web"])
                self.assertFalse(health["requires_api_key"])
                cors_request = urllib.request.Request(f"http://127.0.0.1:{port}/health", method="OPTIONS", headers={"Origin": "chrome-extension://test-extension"})
                with urllib.request.urlopen(cors_request) as cors_response:
                    self.assertIsNone(cors_response.headers.get("Access-Control-Allow-Origin"))
                blocked_origin = urllib.request.Request(f"http://127.0.0.1:{port}/health", method="OPTIONS", headers={"Origin": "https://evil.example"})
                with urllib.request.urlopen(blocked_origin) as blocked_response:
                    self.assertIsNone(blocked_response.headers.get("Access-Control-Allow-Origin"))
                payload = json.dumps({"product_name": "สินค้าทดสอบ", "product_url": "https://affiliate.shopee.co.th/test", "images": []}).encode()
                def send():
                    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/products/import", data=payload, headers={"Content-Type": "application/json"}, method="POST")
                    return json.load(urllib.request.urlopen(request))
                first, second = send(), send()
                self.assertTrue(first["created"])
                self.assertFalse(second["created"])
                folder = products.root / first["job"]["id"]
                self.assertTrue((folder / "job.json").exists())
                self.assertTrue((folder / "ai_request.json").exists())
                self.assertTrue((folder / "prompts" / "chatgpt_request.txt").exists())
                source_image = root / "source.png"; Image.new("RGB", (32, 32), "blue").save(source_image)
                with_images = products.attach_images(first["job"]["id"], [source_image])
                self.assertEqual(len(with_images["source_images"]), 1)
                plugin_queue = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ai/requests"))
                self.assertFalse(plugin_queue["requires_api_key"])
                self.assertEqual(len(plugin_queue["requests"]), 1)
                self.assertIn("สร้างผลลัพธ์", plugin_queue["requests"][0]["prompt"])
                self.assertGreater(len(urllib.request.urlopen(plugin_queue["requests"][0]["image_urls"][0]).read()), 50)
                ranged_image = urllib.request.Request(
                    plugin_queue["requests"][0]["image_urls"][0],
                    headers={"Range": "bytes=0-15"},
                )
                with urllib.request.urlopen(ranged_image) as ranged_response:
                    self.assertEqual(ranged_response.status, 206)
                    self.assertEqual(len(ranged_response.read()), 16)
                    self.assertTrue(str(ranged_response.headers.get("Content-Range") or "").startswith("bytes 0-15/"))
                checkpoint_payload = json.dumps({
                    "job_id": first["job"]["id"],
                    "index": 1,
                    "image": base64.b64encode(source_image.read_bytes()).decode(),
                }).encode()
                checkpoint_request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/jobs/partial-image",
                    data=checkpoint_payload,
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                checkpoint_result = json.load(urllib.request.urlopen(checkpoint_request))
                self.assertEqual(checkpoint_result["image_count"], 1)
                chatgpt_package = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/jobs/{first['job']['id']}/chatgpt-package"))
                self.assertEqual(chatgpt_package["package"]["provider"], "chatgpt_web_extension")
                self.assertFalse(chatgpt_package["package"]["requires_api_key"])
                self.assertEqual(chatgpt_package["package"]["checkpoint_images"][0]["index"], 1)
                self.assertGreater(len(urllib.request.urlopen(chatgpt_package["package"]["checkpoint_images"][0]["url"]).read()), 50)
                chatgpt_command = bridge.queue_extension_command("open_chatgpt", first["job"]["id"])
                self.assertEqual(chatgpt_command["action"], "open_chatgpt")
                self.assertEqual(chatgpt_command["provider"], "chatgpt")
                restart_command = bridge.queue_extension_command("restart_chatgpt_images", first["job"]["id"])
                self.assertEqual(restart_command["action"], "restart_chatgpt_images")
                self.assertEqual(restart_command["provider"], "chatgpt")
                with self.assertRaisesRegex(ValueError, "ไม่ตรงกับ Provider"):
                    bridge.queue_extension_command("restart_chatgpt_images", first["job"]["id"], provider_hint="gemini")
                products.set_image_ai_provider(first["job"]["id"], "gemini")
                gemini_package = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/jobs/{first['job']['id']}/chatgpt-package"))
                self.assertEqual(gemini_package["package"]["provider"], "gemini_web_extension")
                self.assertEqual(bridge.queue_extension_command("open_chatgpt", first["job"]["id"])["provider"], "gemini")
                self.assertEqual(bridge.queue_extension_command("inspect_chatgpt", provider_hint="gemini")["provider"], "gemini")
                self.assertEqual(bridge.queue_extension_command("focus_ai_web", first["job"]["id"], provider_hint="gemini")["action"], "focus_ai_web")
                products.set_image_ai_provider(first["job"]["id"], "chatgpt")
                encoded_image = base64.b64encode(source_image.read_bytes()).decode()
                ai_payload = json.dumps({"job_id": first["job"]["id"], "caption_short": "แคปชั่นสั้น", "hashtags": ["#สินค้า"], "video_prompt": "วิดีโอแนวตั้ง", "flow_shot_prompts": ["ช็อตหนึ่ง", "ช็อตสอง", "ช็อตสาม"], "spoken_script": "สคริปต์พูด", "spoken_script_segments": ["ตอนหนึ่ง", "ตอนสอง", "ตอนสาม"], "generated_images": [encoded_image, encoded_image, encoded_image], "warnings": []}).encode()
                ai_request = urllib.request.Request(f"http://127.0.0.1:{port}/api/ai/result", data=ai_payload, headers={"Content-Type": "application/json"}, method="POST")
                ai_result = json.load(urllib.request.urlopen(ai_request))
                self.assertTrue(ai_result["ok"])
                self.assertEqual(ai_result["flow_command"]["action"], "open_flow")
                self.assertEqual(ai_result["flow_command"]["shot_index"], 1)
                focus_command = bridge.queue_extension_command("focus_flow_web", first["job"]["id"])
                self.assertEqual(focus_command["shot_index"], 1)
                self.assertEqual(ai_result["job"]["ai_provider"], "chatgpt_web_extension")
                self.assertTrue(ai_result["job"]["image_generation_via_chatgpt_web"])
                self.assertEqual((folder / "captions" / "caption.txt").read_text(encoding="utf-8"), "แคปชั่นสั้น")
                self.assertTrue((folder / "prompts" / "google_flow_prompt.txt").exists())
                flow_package = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/jobs/{first['job']['id']}/flow-package"))
                self.assertTrue(flow_package["ok"])
                self.assertEqual(flow_package["package"]["cgi_prompt_policy"], "product_specific_v1")
                self.assertTrue(flow_package["package"]["video_prompt"].startswith("HIGHEST-PRIORITY PRODUCT-SPECIFIC CGI DIRECTION"))
                self.assertIn("วิดีโอแนวตั้ง", flow_package["package"]["video_prompt"])
                self.assertEqual(flow_package["package"]["caption"], "แคปชั่นสั้น")
                self.assertEqual(len(flow_package["package"]["image_urls"]), 3)
                shot_package = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/jobs/{first['job']['id']}/flow-package?shot_index=2"))
                self.assertEqual(shot_package["package"]["shot_index"], 2)
                self.assertIn("SHOT 2", shot_package["package"]["video_prompt"])
                self.assertIn("ช็อตสอง", shot_package["package"]["video_prompt"])
                self.assertEqual(len(shot_package["package"]["image_urls"]), 1)
                heartbeat_payload = json.dumps({"client_id": "chrome-test", "version": LocalBridge.REQUIRED_EXTENSION_VERSION, "browser": "Google Chrome", "page": "google_flow"}).encode()
                heartbeat_request = urllib.request.Request(f"http://127.0.0.1:{port}/api/extension/heartbeat", data=heartbeat_payload, headers={"Content-Type": "application/json"}, method="POST")
                self.assertTrue(json.load(urllib.request.urlopen(heartbeat_request))["connected"])
                extension_status = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/extension/status"))
                self.assertTrue(extension_status["connected"])
                progress_payload = json.dumps({"client_id": "chrome-test", "step": "user_action_required", "job_id": first["job"]["id"], "shot_index": 2, "message": "กรุณา Login Google Flow", "action_kind": "login_required", "service": "flow", "resume_action": "open_flow", "image_ready": True, "prompt_ready": True, "button_labels": ["เข้าสู่ระบบ"], "failure_code": "FLOW_POLICY_BLOCKED", "policy_failure_category": "face_or_public_figure", "failure_card_fingerprint": "face-policy-card-123"}).encode()
                progress_request = urllib.request.Request(f"http://127.0.0.1:{port}/api/extension/progress", data=progress_payload, headers={"Content-Type": "application/json"}, method="POST")
                self.assertTrue(json.load(urllib.request.urlopen(progress_request))["ok"])
                extension_status = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/extension/status"))
                self.assertEqual(extension_status["client"]["flow_step"], "user_action_required")
                self.assertEqual(extension_status["client"]["flow_shot_index"], 2)
                self.assertEqual(extension_status["client"]["flow_action_kind"], "login_required")
                self.assertEqual(extension_status["client"]["flow_service"], "flow")
                self.assertEqual(extension_status["client"]["flow_resume_action"], "open_flow")
                self.assertEqual(extension_status["client"]["flow_failure_code"], "FLOW_POLICY_BLOCKED")
                self.assertEqual(extension_status["client"]["flow_policy_failure_category"], "face_or_public_figure")
                self.assertEqual(extension_status["client"]["flow_failure_card_fingerprint"], "face-policy-card-123")
                self.assertEqual(extension_status["client"]["version"], LocalBridge.REQUIRED_EXTENSION_VERSION)
                self.assertTrue(json.load(urllib.request.urlopen(heartbeat_request))["connected"])
                extension_status = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/extension/status"))
                self.assertEqual(extension_status["client"]["flow_step"], "user_action_required")
                def send_flow_progress(step, shot_index):
                    payload = json.dumps({
                        "client_id": "chrome-test", "step": step,
                        "job_id": first["job"]["id"], "shot_index": shot_index,
                        "message": step,
                    }).encode()
                    request = urllib.request.Request(
                        f"http://127.0.0.1:{port}/api/extension/progress",
                        data=payload, headers={"Content-Type": "application/json"}, method="POST",
                    )
                    self.assertTrue(json.load(urllib.request.urlopen(request))["ok"])

                send_flow_progress("generation_complete", 2)
                send_flow_progress("package_loaded", 2)
                send_flow_progress("package_loaded", 0)
                sticky = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/extension/status"))["client"]
                self.assertEqual(sticky["flow_step"], "generation_complete")
                self.assertEqual(sticky["flow_shot_index"], 2)
                bridge.clear_flow_progress(first["job"]["id"], 2)
                send_flow_progress("package_loaded", 2)
                cleared = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/extension/status"))["client"]
                self.assertEqual(cleared["flow_step"], "package_loaded")
                queue_payload = json.dumps({"action": "open_flow", "job_id": first["job"]["id"], "shot_index": 2}).encode()
                queue_request = urllib.request.Request(f"http://127.0.0.1:{port}/api/extension/queue", data=queue_payload, headers={"Content-Type": "application/json"}, method="POST")
                queued = json.load(urllib.request.urlopen(queue_request))["command"]
                self.assertEqual(queued["shot_index"], 2)
                self.assertEqual(bridge.extension_command_status(queued["id"])["status"], "pending")
                commands = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/extension/commands?client_id=chrome-test"))
                self.assertIn(queued["id"], [command["id"] for command in commands["commands"]])
                delivered = next(command for command in commands["commands"] if command["id"] == queued["id"])
                self.assertTrue(delivered["run_id"].startswith("RUN-"))
                self.assertTrue(delivered["lease_token"].startswith("LEASE-"))
                self.assertGreater(delivered["lease_expires_at"], delivered["delivered_at"])
                bad_ack_payload = json.dumps({
                    "command_id": queued["id"], "client_id": "chrome-test",
                    "run_id": delivered["run_id"], "lease_token": "LEASE-WRONG", "ok": True,
                }).encode()
                bad_ack_request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/extension/command-ack",
                    data=bad_ack_payload, headers={"Content-Type": "application/json"}, method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as bad_ack_error:
                    urllib.request.urlopen(bad_ack_request)
                self.assertEqual(bad_ack_error.exception.code, 400)
                ack_payload = json.dumps({
                    "command_id": queued["id"], "client_id": "chrome-test",
                    "run_id": delivered["run_id"], "lease_token": delivered["lease_token"], "ok": True,
                }).encode()
                ack_request = urllib.request.Request(f"http://127.0.0.1:{port}/api/extension/command-ack", data=ack_payload, headers={"Content-Type": "application/json"}, method="POST")
                ack_result = json.load(urllib.request.urlopen(ack_request))
                self.assertTrue(ack_result["ok"])
                self.assertFalse(ack_result["duplicate"])
                duplicate_ack = json.load(urllib.request.urlopen(ack_request))
                self.assertTrue(duplicate_ack["duplicate"])
                command_status = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/extension/command/{queued['id']}"))
                self.assertEqual(command_status["command"]["status"], "completed")
                self.assertEqual(bridge.extension_command_status(queued["id"])["status"], "completed")
                close_command = bridge.queue_extension_command("close_automation_browser", first["job"]["id"])
                self.assertEqual(close_command["action"], "close_automation_browser")
                video = root / "sample.mp4"; video.write_bytes(b"test-video")
                updated = products.attach_video(first["job"]["id"], video)
                self.assertEqual(updated["video_status"], "ready")
                self.assertTrue((folder / updated["video_path"]).exists())
                readiness = products.check_readiness(first["job"]["id"])
                self.assertFalse(readiness["ready"])
                self.assertIn("ai_approval", readiness["missing"])
                products.approve_ai_result(first["job"]["id"])
                readiness = products.check_readiness(first["job"]["id"])
                self.assertTrue(readiness["ready"])
            finally:
                bridge.stop()

    def test_stale_progress_is_ignored_and_close_ack_retires_the_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            products = ProductManager(root)
            job, _ = products.import_product({
                "shop_id": "123", "product_id": "456", "product_name": "Progress ownership",
                "product_url": "https://shopee.co.th/product/123/456", "images": [],
            })
            bridge = LocalBridge("127.0.0.1", 0, products, logging.getLogger("progress-ownership-test")).start()
            port = bridge.server.server_address[1]

            def post(path, payload):
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}{path}",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                return json.load(urllib.request.urlopen(request))

            def get(path):
                return json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}{path}"))

            try:
                post("/api/extension/heartbeat", {
                    "client_id": "chrome-owner", "version": LocalBridge.REQUIRED_EXTENSION_VERSION,
                    "browser": "Google Chrome", "page": "google_flow",
                })
                queued = bridge.queue_extension_command("focus_flow_web", job["id"], 1)
                delivered = next(
                    item for item in get("/api/extension/commands?client_id=chrome-owner")["commands"]
                    if item["id"] == queued["id"]
                )
                accepted = post("/api/extension/progress", {
                    "client_id": "chrome-owner", "tab_id": 55,
                    "step": "generation_in_progress", "job_id": job["id"], "shot_index": 1,
                    "run_id": delivered["run_id"], "message": "current run",
                })
                self.assertFalse(accepted.get("ignored", False))
                current = get("/api/extension/status")["client"]
                self.assertEqual(current["flow_run_id"], delivered["run_id"])
                self.assertEqual(current["flow_tab_id"], 55)

                stale = post("/api/extension/progress", {
                    "client_id": "chrome-owner", "tab_id": 99,
                    "step": "generation_failed", "job_id": job["id"], "shot_index": 1,
                    "run_id": "RUN-STALE123", "message": "must not replace current run",
                })
                self.assertTrue(stale["ignored"])
                self.assertEqual(stale["reason"], "stale_flow_run")
                unchanged = get("/api/extension/status")["client"]
                self.assertEqual(unchanged["flow_step"], "generation_in_progress")
                self.assertEqual(unchanged["flow_message"], "current run")

                post("/api/extension/heartbeat", {
                    "client_id": "chrome-old", "version": "0.0.1",
                    "browser": "Google Chrome", "page": "google_flow",
                })
                outdated = post("/api/extension/progress", {
                    "client_id": "chrome-old", "tab_id": 88,
                    "step": "generation_failed", "job_id": job["id"], "shot_index": 1,
                    "run_id": delivered["run_id"], "message": "old extension",
                })
                self.assertTrue(outdated["ignored"])
                self.assertEqual(outdated["reason"], "version_mismatch")

                post("/api/extension/command-ack", {
                    "command_id": delivered["id"], "client_id": "chrome-owner",
                    "run_id": delivered["run_id"], "lease_token": delivered["lease_token"],
                    "ok": True,
                })
                close = bridge.queue_extension_command(
                    "close_automation_browser", job["id"], run_id=delivered["run_id"]
                )
                close_delivery = next(
                    item for item in get("/api/extension/commands?client_id=chrome-owner")["commands"]
                    if item["id"] == close["id"]
                )
                post("/api/extension/command-ack", {
                    "command_id": close_delivery["id"], "client_id": "chrome-owner",
                    "run_id": close_delivery["run_id"], "lease_token": close_delivery["lease_token"],
                    "ok": True,
                })
                owner = next(
                    item for item in get("/api/extension/status")["clients"]
                    if item["client_id"] == "chrome-owner"
                )
                self.assertNotIn("flow_job_id", owner)
                self.assertFalse(any(key[1] == job["id"] for key in bridge._extension_runs))
            finally:
                bridge.stop()

    def test_manual_shopee_link_and_product_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            products = ProductManager(Path(temp))
            canonical = "https://shopee.co.th/sample-product-i.123456.987654"
            with patch.object(products, "_resolve_product_link", return_value=(canonical, {"title": "สินค้าน่าสนใจ", "description": "รายละเอียด"})):
                job, created = products.import_link("https://s.shopee.co.th/abc123")
            self.assertTrue(created)
            self.assertEqual(job["shop_id"], "123456")
            self.assertEqual(job["product_id"], "987654")
            self.assertEqual(job["posting_product_url"], "https://s.shopee.co.th/abc123")
            self.assertEqual(job["product_url"], canonical)
            self.assertEqual(job["product_source"], "manual_link")
            self.assertEqual(job["ai_status"], "needs_product_data")
            updated = products.update_product_info(job["id"], "ชื่อสินค้าที่ตรวจแล้ว", "999", "10%", "รายละเอียดจริง")
            self.assertEqual(updated["product_name"], "ชื่อสินค้าที่ตรวจแล้ว")

    def test_chrome_capture_enriches_existing_manual_job(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            products = ProductManager(root)
            canonical = "https://shopee.co.th/opaanlp/1434345640/50902979965"
            with patch.object(products, "_resolve_product_link", return_value=(canonical, {})):
                job, _ = products.import_link("https://s.shopee.co.th/example")

            sample = root / "captured.png"
            Image.new("RGB", (48, 48), "orange").save(sample)

            def fake_download(_url, folder, index):
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / f"product_{index:02d}.png"
                target.write_bytes(sample.read_bytes())
                return target

            captured = {
                "shop_id": "1434345640",
                "product_id": "50902979965",
                "product_name": "ชื่อสินค้าจริงจากหน้า Shopee",
                "product_url": canonical,
                "price": "฿499",
                "description": "รายละเอียดจริงจากหน้า Shopee",
                "images": ["https://cf.shopee.co.th/file/example"],
            }
            with patch.object(products, "_download_image", side_effect=fake_download):
                enriched, created = products.import_product(captured)

            self.assertFalse(created)
            self.assertEqual(enriched["id"], job["id"])
            self.assertEqual(enriched["product_name"], "ชื่อสินค้าจริงจากหน้า Shopee")
            self.assertEqual(enriched["price"], "฿499")
            self.assertEqual(len(enriched["source_images"]), 1)
            self.assertEqual(enriched["ai_status"], "request_ready")

    def test_chrome_capture_targets_requested_fresh_job(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            products = ProductManager(root)
            canonical = "https://shopee.co.th/product/123/456"
            older, _ = products.import_product({
                "shop_id": "123", "product_id": "456", "product_name": "งานเดิม",
                "product_url": canonical, "images": [],
            }, force_new=True)
            fresh, _ = products.import_product({
                "shop_id": "123", "product_id": "456", "product_name": "สินค้า Shopee • ID 456",
                "product_url": canonical, "images": [],
            }, force_new=True)
            sample = root / "captured.png"
            Image.new("RGB", (48, 48), "orange").save(sample)

            def fake_download(_url, folder, index):
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / f"product_{index:02d}.png"
                target.write_bytes(sample.read_bytes())
                return target

            captured = {
                "shop_id": "123", "product_id": "456", "product_name": "ชื่อจริงรอบทดสอบใหม่",
                "product_url": canonical, "images": ["https://img.susercontent.com/file/example"],
            }
            with patch.object(products, "_download_image", side_effect=fake_download):
                enriched, created = products.import_product(captured, target_job_id=fresh["id"])

            self.assertFalse(created)
            self.assertEqual(enriched["id"], fresh["id"])
            self.assertEqual(enriched["product_name"], "ชื่อจริงรอบทดสอบใหม่")
            self.assertEqual(len(enriched["source_images"]), 1)
            self.assertEqual(products.get_job(older["id"])["product_name"], "งานเดิม")

    def test_rejects_non_shopee_link(self):
        with tempfile.TemporaryDirectory() as temp:
            products = ProductManager(Path(temp))
            with self.assertRaises(ValueError):
                products.import_link("https://example.com/product/123")

    def test_parses_real_shopee_affiliate_redirect_format(self):
        shop_id, product_id = ProductManager.product_ids_from_url("https://shopee.co.th/opaanlp/1719701576/43780341539?utm_source=affiliate")
        self.assertEqual(shop_id, "1719701576")
        self.assertEqual(product_id, "43780341539")


if __name__ == "__main__":
    unittest.main()
