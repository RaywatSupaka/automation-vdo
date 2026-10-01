import copy
import json
import logging
import shutil
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager


ROOT = Path(__file__).resolve().parents[1]


def terminal_payload():
    return {
        "client_id": "attachment-client", "tab_id": 12, "scope": "flow",
        "step": "attachment_failed", "job_id": "JOB-A", "shot_index": 2, "run_id": "RUN-A",
        "page_url": "https://flow.google.com/project/project-a", "image_ready": False, "prompt_ready": True,
        "failure_code": "FLOW_ATTACHMENT_UNCONFIRMED",
        "failure_card_fingerprint": "attachment:JOB-A:2:RUN-A:project-a:1000",
        "attachment_failure_evidence": {
            "schema_version": 1, "phase": "before_submit", "attempt_key": "JOB-A:2:project-a",
            "attempt_started_at": 1000, "grace_started_at": 2000, "grace_elapsed_ms": 30000,
            "project_id": "project-a", "run_id": "RUN-A", "attachment_attempt_count": 1,
            "submission_absent": True, "generation_absent": True, "result_absent": True,
            "confirmation_absent": True, "terminal_latched": True,
        },
    }


class FlowAttachmentTerminalTests(unittest.TestCase):
    def test_executable_extension_grace_and_terminal_races(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the executable Extension contract")
        result = subprocess.run([node, str(ROOT / "tests/flow_attachment_terminal_harness.js")],
                                cwd=ROOT, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_bridge_rejects_missing_or_inconsistent_pre_submit_evidence(self):
        valid = terminal_payload()
        self.assertEqual(LocalBridge.validate_flow_attachment_failure(valid), valid["attachment_failure_evidence"])
        for key in ("submission_absent", "generation_absent", "result_absent", "confirmation_absent", "terminal_latched"):
            for value in (False, "true", None):
                with self.subTest(key=key, value=value):
                    bad = copy.deepcopy(valid)
                    bad["attachment_failure_evidence"][key] = value
                    with self.assertRaises(ValueError):
                        LocalBridge.validate_flow_attachment_failure(bad)
        mutations = (
            ("step", "generation_failed"), ("image_ready", True), ("prompt_ready", False),
            ("run_id", "RUN-B"), ("shot_index", 3), ("failure_card_fingerprint", "policy-card"),
            ("tab_id", 0), ("download_path", "some.mp4"), ("confirmation_kind", "credit"),
            ("page_url", "https://example.org/project/project-a"),
        )
        for key, value in mutations:
            bad = copy.deepcopy(valid)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                LocalBridge.validate_flow_attachment_failure(bad)
        for key, value in (("grace_elapsed_ms", 29999), ("grace_elapsed_ms", float("nan")),
                           ("attempt_started_at", 3000), ("attachment_attempt_count", 2),
                           ("attachment_attempt_count", True), ("attempt_key", "JOB-A:1:project-a")):
            bad = copy.deepcopy(valid)
            bad["attachment_failure_evidence"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                LocalBridge.validate_flow_attachment_failure(bad)
        policy = {"failure_code": "FLOW_POLICY_BLOCKED"}
        self.assertEqual(LocalBridge.validate_flow_attachment_failure(policy), {}, "Existing policy gate remains independent")

    def test_bridge_round_trip_keeps_terminal_and_discards_extra_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            products = ProductManager(Path(temp))
            bridge = LocalBridge("127.0.0.1", 0, products, logging.getLogger("attachment-terminal-test")).start()
            base = f"http://127.0.0.1:{bridge.server.server_address[1]}"

            def post(route, body):
                request = urllib.request.Request(base + route, data=json.dumps(body).encode(),
                                                 headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(request, timeout=5) as response:
                    return json.load(response)

            try:
                post("/api/extension/heartbeat", {"client_id": "attachment-client", "version": LocalBridge.REQUIRED_EXTENSION_VERSION})
                body = terminal_payload()
                body["attachment_failure_evidence"]["arbitrary_field"] = "discard me"
                body["attachment_failure_evidence"]["selection_recovery_available"] = True
                self.assertTrue(post("/api/extension/progress", body)["ok"])
                status = bridge.extension_status()["client"]
                self.assertEqual(status["flow_failure_code"], "FLOW_ATTACHMENT_UNCONFIRMED")
                self.assertNotIn("arbitrary_field", status["flow_attachment_failure_evidence"])
                self.assertTrue(status["flow_attachment_failure_evidence"]["selection_recovery_available"])
                post("/api/extension/progress", {
                    "client_id": "attachment-client", "scope": "flow", "step": "package_loaded",
                    "job_id": "JOB-A", "shot_index": 2, "run_id": "RUN-A", "tab_id": 12,
                })
                self.assertEqual(bridge.extension_status()["client"]["flow_step"], "attachment_failed")
                log = products.root / "JOB-A/logs/flow_extension.jsonl"
                saved = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
                self.assertTrue(saved["attachment_failure_evidence"]["terminal_latched"])
                invalid = terminal_payload()
                invalid["attachment_failure_evidence"]["submission_absent"] = False
                with self.assertRaises(urllib.error.HTTPError):
                    post("/api/extension/progress", invalid)
            finally:
                bridge.stop()


if __name__ == "__main__":
    unittest.main()
