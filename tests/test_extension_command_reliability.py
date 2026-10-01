from __future__ import annotations

import json
import logging
import tempfile
import time
import urllib.error
import urllib.request
import unittest
from pathlib import Path

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager


def load_tests(loader, tests, pattern):
    """Run these bridge/lease regressions in the project's unittest suite too."""
    return unittest.TestSuite(
        unittest.FunctionTestCase(value, description=name)
        for name, value in sorted(globals().items())
        if name.startswith('test_') and callable(value)
    )


def _request_json(url: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def _start_bridge(root: Path) -> tuple[LocalBridge, str]:
    bridge = LocalBridge(
        "127.0.0.1",
        0,
        ProductManager(root),
        logging.getLogger("extension-command-reliability"),
    ).start()
    return bridge, f"http://127.0.0.1:{bridge.server.server_address[1]}"


def _heartbeat(base_url: str, client_id: str) -> None:
    payload = {
        "client_id": client_id,
        "version": LocalBridge.REQUIRED_EXTENSION_VERSION,
        "browser": "Google Chrome",
        "page": "other",
    }
    result = _request_json(f"{base_url}/api/extension/heartbeat", method="POST", payload=payload)
    assert result["ok"] is True


def test_delivered_command_is_not_redelivered_until_lease_expires():
    with tempfile.TemporaryDirectory() as temp:
        bridge, base_url = _start_bridge(Path(temp))
        try:
            _heartbeat(base_url, "lease-client")
            command = bridge.queue_extension_command("focus_ai_web", provider_hint="chatgpt")

            first = _request_json(f"{base_url}/api/extension/commands?client_id=lease-client")
            assert [item["id"] for item in first["commands"]] == [command["id"]]

            immediate = _request_json(f"{base_url}/api/extension/commands?client_id=lease-client")
            assert immediate["commands"] == []

            stored = bridge.extension_command_status(command["id"])
            assert stored["status"] == "delivered"
            assert stored["lease_expires_at"] > time.time()
            original_lease = stored["lease_token"]
            assert original_lease

            with bridge._extension_lock:
                live = next(item for item in bridge._extension_commands if item["id"] == command["id"])
                live["lease_expires_at"] = time.time() - 0.01

            redelivered = _request_json(f"{base_url}/api/extension/commands?client_id=lease-client")
            assert [item["id"] for item in redelivered["commands"]] == [command["id"]]
            renewed = bridge.extension_command_status(command["id"])
            assert renewed["lease_token"] != original_lease
            assert renewed["run_id"] == stored["run_id"]
        finally:
            bridge.stop()


def test_long_flow_commands_receive_current_bounded_delivery_lease():
    with tempfile.TemporaryDirectory() as temp:
        bridge, base_url = _start_bridge(Path(temp))
        try:
            _heartbeat(base_url, "long-lease-client")
            command = bridge.queue_extension_command("open_flow", job_id="", shot_index=0)
            delivered = _request_json(f"{base_url}/api/extension/commands?client_id=long-lease-client")
            assert [item["id"] for item in delivered["commands"]] == [command["id"]]
            stored = bridge.extension_command_status(command["id"])
            assert bridge.COMMAND_LEASE_SECONDS >= 150
            assert stored["lease_expires_at"] - stored["delivered_at"] == bridge.COMMAND_LEASE_SECONDS
        finally:
            bridge.stop()


def test_command_ack_from_different_extension_client_is_rejected():
    with tempfile.TemporaryDirectory() as temp:
        bridge, base_url = _start_bridge(Path(temp))
        try:
            _heartbeat(base_url, "owner-client")
            _heartbeat(base_url, "other-client")
            command = bridge.queue_extension_command("focus_ai_web", provider_hint="chatgpt")
            delivered = _request_json(f"{base_url}/api/extension/commands?client_id=owner-client")
            assert [item["id"] for item in delivered["commands"]] == [command["id"]]
            lease = delivered["commands"][0]
            ack = {"command_id": command["id"], "ok": True,
                   "run_id": lease["run_id"], "lease_token": lease["lease_token"]}

            try:
                _request_json(
                    f"{base_url}/api/extension/command-ack",
                    method="POST",
                    payload={"client_id": "other-client", **ack},
                )
            except urllib.error.HTTPError as exc:
                assert exc.code == 400
                body = json.loads(exc.read().decode("utf-8"))
                assert "Client ID" in body["error"]
            else:
                raise AssertionError("Bridge accepted an ACK from the wrong Extension client")

            assert bridge.extension_command_status(command["id"])["status"] == "delivered"
            accepted = _request_json(
                f"{base_url}/api/extension/command-ack",
                method="POST",
                payload={"client_id": "owner-client", **ack},
            )
            assert accepted["ok"] is True
            assert bridge.extension_command_status(command["id"])["status"] == "completed"
        finally:
            bridge.stop()


def test_owned_flow_observation_round_trips_through_status_endpoint():
    with tempfile.TemporaryDirectory() as temp:
        bridge, base_url = _start_bridge(Path(temp))
        try:
            _heartbeat(base_url, "evidence-client")
            payload = {
                "client_id": "evidence-client",
                "step": "generation_status_unknown",
                "job_id": "STORY-TEST-EVIDENCE",
                "shot_index": 4,
                "message": "result card hydrated",
                "tab_id": 91,
                "run_id": "RUN-EVIDENCE",
                "page_url": "https://flow.google.com/project/project-abc",
                "observed_at_ms": 123456,
                "image_ready": True,
                "prompt_ready": True,
                "continuous_wait": True,
                "result_reason": "waiting_response",
            }
            posted = _request_json(
                f"{base_url}/api/extension/progress",
                method="POST",
                payload=payload,
            )
            assert posted["ok"] is True
            client = _request_json(f"{base_url}/api/extension/status")["client"]
            assert client["flow_tab_id"] == 91
            assert client["flow_page_url"] == payload["page_url"]
            assert client["flow_image_ready"] is True
            assert client["flow_prompt_ready"] is True
            assert client["flow_continuous_wait"] is True
            observation = client["flow_observation"]
            assert observation["identity"] == [payload["job_id"], "RUN-EVIDENCE", 91]
            assert observation["scene_index"] == 4
            assert observation["observed_at_ms"] == 123456
            assert observation["result_reason"] == "waiting_response"
            assert observation["acknowledged"] is True
        finally:
            bridge.stop()
