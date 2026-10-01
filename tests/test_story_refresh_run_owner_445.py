"""The refresh collector may reattach only for a live desktop-owned Story run."""

import ast
import json
import logging
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import Mock

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from tests.extension_identity_fixture import pair_fixture


class StoryRefreshRunOwnerTests(unittest.TestCase):
    def test_main_window_callback_requires_live_nonterminal_worker(self):
        source = Path(__file__).resolve().parents[1] / "ui" / "main_window.py"
        tree = ast.parse(source.read_text(encoding="utf-8-sig"))
        method = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef) and node.name == "_story_run_active")
        scope = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), scope)
        event = threading.Event()
        app = types.SimpleNamespace(
            _story_pipeline_job_id="STORY-TEST", _story_cancel_event=event,
            stories=Mock(),
        )
        app.stories.get.return_value = {"status": "running", "cancel_requested": False}
        active = types.MethodType(scope["_story_run_active"], app)
        self.assertTrue(active("STORY-TEST"))
        self.assertFalse(active("STORY-OTHER"))
        event.set()
        self.assertFalse(active("STORY-TEST"))
        event.clear()
        for status in ("cancelled", "error", "ready"):
            app.stories.get.return_value = {"status": status}
            self.assertFalse(active("STORY-TEST"))
        app.stories.get.return_value = {"status": "running", "cancel_requested": True}
        self.assertFalse(active("STORY-TEST"))
        app._story_pipeline_job_id = ""
        self.assertFalse(active("STORY-TEST"))

    def test_run_owner_is_authenticated_exact_and_non_disclosing(self):
        desktop = {"active": True}
        with tempfile.TemporaryDirectory() as temp:
            bridge = LocalBridge(
                "127.0.0.1", 0, ProductManager(Path(temp)),
                logging.getLogger("story-refresh-run-owner-test"),
                story_run_active=lambda job_id: desktop["active"] and job_id == "STORY-TEST",
            ).start()
            origin = "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            pair_fixture(bridge, origin)
            base = f"http://127.0.0.1:{bridge.server.server_address[1]}"
            try:
                heartbeat = urllib.request.Request(
                    base + "/api/extension/heartbeat",
                    data=json.dumps({
                        "client_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        "version": LocalBridge.REQUIRED_EXTENSION_VERSION,
                        "browser": "Google Chrome", "page": "chatgpt_web",
                    }).encode(),
                    headers={"Content-Type": "application/json", "Origin": origin},
                    method="POST",
                )
                token = json.load(urllib.request.urlopen(heartbeat))["extension_token"]

                def request(job_id="STORY-TEST", run_id="RUN-LIVE123", supplied_token=token,
                            supplied_origin=origin):
                    query = urllib.parse.urlencode({"job_id": job_id, "run_id": run_id})
                    headers = {"Origin": supplied_origin}
                    if supplied_token:
                        headers["X-SmartFlow-Token"] = supplied_token
                    return urllib.request.Request(
                        base + "/api/extension/run-owner?" + query, headers=headers)

                for invalid_token in ("", "wrong-token"):
                    with self.assertRaises(urllib.error.HTTPError) as denied:
                        urllib.request.urlopen(request(supplied_token=invalid_token))
                    self.assertEqual(denied.exception.code, 403)
                with self.assertRaises(urllib.error.HTTPError) as denied_origin:
                    urllib.request.urlopen(request(supplied_origin="https://evil.example"))
                self.assertEqual(denied_origin.exception.code, 403)

                self.assertEqual(json.load(urllib.request.urlopen(request())),
                                 {"ok": True, "active": False})
                with bridge._extension_lock:
                    bridge._extension_runs[("ai", "STORY-TEST", 0)] = {
                        "run_id": "RUN-LIVE123", "updated_at": 1,
                    }
                active_bytes = urllib.request.urlopen(request()).read()
                self.assertEqual(json.loads(active_bytes), {"ok": True, "active": True})
                self.assertNotIn(token.encode(), active_bytes)
                self.assertNotIn(b"RUN-LIVE123", active_bytes)
                self.assertEqual(json.load(urllib.request.urlopen(
                    request(run_id="RUN-STALE123"))), {"ok": True, "active": False})
                self.assertEqual(json.load(urllib.request.urlopen(
                    request(job_id="STORY-OTHER"))), {"ok": True, "active": False})
                desktop["active"] = False  # Worker cancelled or finished; mapping remains.
                self.assertEqual(json.load(urllib.request.urlopen(request())),
                                 {"ok": True, "active": False})
                desktop["active"] = True
                bridge.story_run_active = None  # Standalone bridge cannot prove a live worker.
                self.assertEqual(json.load(urllib.request.urlopen(request())),
                                 {"ok": True, "active": False})
                bridge.story_run_active = lambda _job_id: (_ for _ in ()).throw(RuntimeError("unavailable"))
                self.assertEqual(json.load(urllib.request.urlopen(request())),
                                 {"ok": True, "active": False})
                bridge.story_run_active = lambda job_id: job_id == "STORY-TEST"
                with bridge._extension_lock:
                    bridge._extension_runs.clear()  # Equivalent to a desktop restart.
                self.assertEqual(json.load(urllib.request.urlopen(request())),
                                 {"ok": True, "active": False})
            finally:
                bridge.stop()


if __name__ == "__main__":
    unittest.main()
