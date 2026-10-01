import json
import logging
import tempfile
import unittest
import urllib.request
from pathlib import Path

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager


REASON = "ไม่สามารถสร้างวิดีโอที่อาจทำให้เกิดความเสี่ยงต่อชื่อเสียงหรือแสดงเหตุการณ์ปัจจุบันอย่างไม่ถูกต้อง โปรดลองใช้พรอมต์อื่นหรือส่งความคิดเห็น"


class FlowFailureReasonTests(unittest.TestCase):
    def test_reason_is_bounded_plain_text_not_arbitrary_object(self):
        for value in (None, {}, [REASON], 123, True):
            self.assertEqual(LocalBridge.flow_failure_reason(value), "")
        self.assertEqual(LocalBridge.flow_failure_reason("\n" + REASON + "\x00\x85\t"), REASON)
        self.assertEqual(len(LocalBridge.flow_failure_reason("ก" * 9000)), 600)

    def test_owned_bridge_round_trip_log_heartbeat_stale_and_clear(self):
        with tempfile.TemporaryDirectory() as temp:
            products = ProductManager(Path(temp))
            bridge = LocalBridge("127.0.0.1", 0, products, logging.getLogger("flow-reason-test")).start()
            base = f"http://127.0.0.1:{bridge.server.server_address[1]}"

            def post(route, body):
                request = urllib.request.Request(base + route, data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.load(response)

            try:
                heartbeat = {"client_id": "reason-client", "version": LocalBridge.REQUIRED_EXTENSION_VERSION}
                post("/api/extension/heartbeat", heartbeat)
                with bridge._extension_lock:
                    bridge._extension_runs[("flow", "JOB-REASON", 2)] = {"run_id": "RUN-CURRENT"}
                payload = {
                    "client_id": "reason-client", "tab_id": 12, "step": "generation_failed",
                    "job_id": "JOB-REASON", "shot_index": 2, "run_id": "RUN-CURRENT",
                    "failure_code": "FLOW_POLICY_BLOCKED", "failure_card_fingerprint": "CARD-2",
                    "policy_failure_category": "general_policy", "failure_reason": REASON,
                }
                self.assertTrue(post("/api/extension/progress", payload)["ok"])
                self.assertEqual(bridge.extension_status()["client"]["flow_failure_reason"], REASON)
                post("/api/extension/heartbeat", heartbeat)
                self.assertEqual(bridge.extension_status()["client"]["flow_failure_reason"], REASON)
                log = products.root / "JOB-REASON/logs/flow_extension.jsonl"
                saved = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
                self.assertEqual(saved["failure_reason"], REASON)
                self.assertEqual(saved["failure_card_fingerprint"], "CARD-2")
                stale = post("/api/extension/progress", {**payload, "run_id": "RUN-OLD", "failure_reason": "stale"})
                self.assertTrue(stale["ignored"])
                self.assertEqual(bridge.extension_status()["client"]["flow_failure_reason"], REASON)
                post("/api/extension/progress", {**payload, "step": "generation_in_progress", "failure_code": ""})
                self.assertEqual(bridge.extension_status()["client"]["flow_failure_reason"], "")
            finally:
                bridge.stop()
