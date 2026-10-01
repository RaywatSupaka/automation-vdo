import json
import logging
import tempfile
import time
import urllib.request
import unittest
from pathlib import Path

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        unittest.FunctionTestCase(value, description=name)
        for name, value in sorted(globals().items())
        if name.startswith('test_') and callable(value)
    )


def test_explicit_focus_requests_keep_distinct_command_ids():
    with tempfile.TemporaryDirectory() as temp:
        bridge = LocalBridge("127.0.0.1", 0, ProductManager(Path(temp)), logging.getLogger("lease-test"))
        first = bridge.queue_extension_command("focus_flow_web")
        second = bridge.queue_extension_command("focus_flow_web")
        # Explicit focus requests have separate ACKs, but retain their current
        # run. Physical Generate deduplication belongs to the Send receipt.
        assert first["id"] != second["id"]
        assert first["run_id"] == second["run_id"]
        changed = bridge.queue_extension_command("focus_flow_web", run_id="RUN-NEW")
        assert changed["id"] not in {first["id"], second["id"]}
        assert changed["run_id"] == "RUN-NEW"


def test_delivered_command_uses_long_lease_before_redelivery():
    with tempfile.TemporaryDirectory() as temp:
        bridge = LocalBridge("127.0.0.1", 0, ProductManager(Path(temp)), logging.getLogger("lease-http-test")).start()
        port = bridge.server.server_address[1]
        try:
            command = bridge.queue_extension_command("focus_flow_web")
            with bridge._extension_lock:
                bridge._extension_clients["lease-client"] = {
                    "client_id": "lease-client",
                    "version": bridge.REQUIRED_EXTENSION_VERSION,
                    "last_seen_epoch": time.time(),
                }
                stored = next(item for item in bridge._extension_commands if item["id"] == command["id"])
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/extension/commands?client_id=lease-client", timeout=10
            ) as response:
                initial = json.load(response)["commands"]
            assert [item["id"] for item in initial] == [command["id"]]
            original_token = initial[0]["lease_token"]
            payload = json.load(urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/extension/commands?client_id=lease-client", timeout=10
            ))
            assert payload["commands"] == []

            with bridge._extension_lock:
                assert stored["lease_expires_at"] - stored["delivered_at"] == bridge.COMMAND_LEASE_SECONDS
                stored["lease_expires_at"] = time.time() - 1
            payload = json.load(urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/extension/commands?client_id=lease-client", timeout=10
            ))
            assert [item["id"] for item in payload["commands"]] == [command["id"]]
            assert payload["commands"][0]["lease_token"] != original_token
        finally:
            bridge.stop()
