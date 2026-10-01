"""Exercise worker heartbeat selection without importing Tk or starting processes."""

import ast
import copy
import os
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.local_bridge import LocalBridge
from core.product_pipeline import product_ai_recovery_action, product_ai_recovery_command, product_runtime_recovery_action


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ui" / "main_window.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
WINDOW = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "MainWindow")
METHODS = {node.name: node for node in WINDOW.body if isinstance(node, ast.FunctionDef)}
CURRENT = LocalBridge.REQUIRED_EXTENSION_VERSION
OLD = "0.0.0"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class CancelEvent:
    def __init__(self, clock):
        self.clock = clock
        self.waits = 0

    def is_set(self):
        return False

    def wait(self, seconds):
        self.waits += 1
        self.clock.sleep(seconds)
        return False


class Bridge:
    REQUIRED_EXTENSION_VERSION = CURRENT

    def __init__(self, *snapshots):
        self.snapshots = list(snapshots)
        self.calls = 0
        self.commands = []

    def extension_status(self):
        self.calls += 1
        return self.snapshots.pop(0) if len(self.snapshots) > 1 else self.snapshots[0]

    def queue_extension_command(self, *args, **kwargs):
        self.commands.append((args, kwargs))


def flow_client(version=CURRENT, **fields):
    return {
        "version": version, "flow_job_id": "JOB-GUARD", "flow_shot_index": 2,
        "flow_step": "generation_complete", **fields,
    }


def ai_client(version=CURRENT, **fields):
    return {
        "version": version, "ai_job_id": "JOB-GUARD", "ai_provider": "chatgpt",
        "ai_step": "generating_image", "ai_image_count": 1, **fields,
    }


def load_method(name, clock, **extra):
    namespace = {"time": clock, "Path": Path, "check_cancelled": lambda event: None, **extra}
    module = ast.Module(body=[copy.deepcopy(METHODS[name])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)
    return namespace[name]


def load_checkpoint_selector(name):
    """Extract the real probe selector; avoid executing the render/browser worker."""
    assignment = next(
        node for node in ast.walk(METHODS[name])
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "client" for target in node.targets)
        and "flow_job_id" in ast.unparse(node.value)
    )
    wrapper = ast.parse("def select(self, status, job_id, shot_index):\n    pass\n").body[0]
    wrapper.body = [copy.deepcopy(assignment), ast.Return(value=ast.Name(id="client", ctx=ast.Load()))]
    module = ast.Module(body=[wrapper], type_ignores=[])
    namespace = {}
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), namespace)
    return namespace["select"]


class WorkerClientGuardTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.event = CancelEvent(self.clock)
        self.product_temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.product_temp.cleanup)

    def window(self, bridge):
        return SimpleNamespace(
            bridge=bridge, events=queue.Queue(), _product_progress_event=Mock(),
            _write_console=Mock(), _ensure_flow_extension=Mock(),
        )

    def test_flow_wait_ignores_newest_incompatible_complete_and_policy_events(self):
        for step in ("generation_complete", "generation_failed"):
            with self.subTest(step=step):
                current = flow_client(flow_message="current result", flow_run_id="CURRENT-RUN")
                old = flow_client(OLD, flow_step=step, flow_failure_code="FLOW_POLICY_BLOCKED")
                bridge = Bridge({"clients": [old, current]})
                window = self.window(bridge)
                result = load_method("_wait_flow_step", self.clock)(
                    window, "JOB-GUARD", 2, timeout=3, cancel_event=self.event,
                )
                self.assertIs(result, current)
                self.assertEqual(bridge.commands, [])

    def test_flow_wait_requires_compatible_job_evidence_not_just_any_compatible_client(self):
        for version in (OLD, "99.99.99", ""):
            with self.subTest(version=version):
                current = flow_client()
                bridge = Bridge(
                    {"clients": [flow_client(version), {"version": CURRENT}]},
                    {"clients": [current]},
                )
                window = self.window(bridge)
                result = load_method("_wait_flow_step", self.clock)(
                    window, "JOB-GUARD", 2, timeout=8, cancel_event=self.event,
                )
                self.assertIs(result, current)
                self.assertEqual(bridge.calls, 2)
                window._ensure_flow_extension.assert_not_called()
                self.assertEqual(bridge.commands, [])

    def test_flow_wait_uses_bridge_freshness_filter_before_reading_completion(self):
        bridge = LocalBridge.__new__(LocalBridge)
        bridge._extension_lock = threading.Lock()
        bridge._extension_trace_lock = threading.Lock()
        bridge._extension_trace = []
        bridge._extension_clients = {
            "expired": flow_client(last_seen_epoch=self.clock.now - 71),
            "online": {"version": CURRENT, "last_seen_epoch": self.clock.now},
        }
        window = self.window(bridge)
        with patch("core.local_bridge.time.time", return_value=self.clock.now):
            with self.assertRaises(TimeoutError):
                load_method("_wait_flow_step", self.clock)(
                    window, "JOB-GUARD", 2, timeout=2, cancel_event=self.event,
                )
        window._ensure_flow_extension.assert_not_called()

    def story_window(self, bridge):
        window = self.window(bridge)
        window._story_pipeline_job_id = "JOB-GUARD"
        window._story_cancel_event = self.event
        window.stories = SimpleNamespace(get=lambda job_id: {"image_ai_provider": "chatgpt", "scene_count": 6})
        window.root = SimpleNamespace(after=Mock(return_value="scheduled"))
        window._story_browser_launches = {}
        window._story_verification_jobs = {}
        window._launch_story_browser = Mock()
        window._update_story_progress = Mock()
        return window

    def test_story_monitor_ignores_old_error_cancel_and_wrong_provider(self):
        for step in ("error", "cancelled", "user_action_required"):
            with self.subTest(step=step):
                old = ai_client(OLD, ai_step=step, ai_provider="gemini")
                current = ai_client()
                window = self.story_window(Bridge({"clients": [old, current]}))
                progress = Mock(return_value={"step": "generating_image", "percent": 25})
                load_method("_monitor_story_browser_progress", self.clock, browser_progress=progress)(window, "JOB-GUARD")
                progress.assert_called_once_with(current, "JOB-GUARD", 6)
                self.assertTrue(window.events.empty())
                window._launch_story_browser.assert_not_called()
                window.root.after.assert_called_once()

    def test_story_monitor_does_not_use_old_job_progress_with_unrelated_current_client(self):
        window = self.story_window(Bridge({"clients": [ai_client(OLD, ai_step="error"), {"version": CURRENT}]}))
        progress = Mock()
        load_method("_monitor_story_browser_progress", self.clock, browser_progress=progress)(window, "JOB-GUARD")
        progress.assert_not_called()
        self.assertTrue(window.events.empty())
        window._launch_story_browser.assert_not_called()
        window.root.after.assert_called_once()

    def test_story_monitor_ignores_same_job_from_previous_run(self):
        old = ai_client(ai_run_id='RUN-OLD', ai_step='error', ai_message='old error')
        bridge = Bridge({'clients': [old]})
        bridge._extension_runs = {('ai', 'JOB-GUARD', 0): {'run_id': 'RUN-NEW'}}
        window = self.story_window(bridge)
        progress = Mock()
        load_method('_monitor_story_browser_progress', self.clock, browser_progress=progress)(window, 'JOB-GUARD')
        progress.assert_not_called()
        self.assertTrue(window.events.empty())
        window._launch_story_browser.assert_not_called()
        window.root.after.assert_called_once()

    def test_story_monitor_current_provider_mismatch_still_errors(self):
        window = self.story_window(Bridge({"clients": [ai_client(ai_provider="gemini")]}))
        load_method("_monitor_story_browser_progress", self.clock, browser_progress=Mock())(window, "JOB-GUARD")
        self.assertEqual(window.events.get_nowait()[0], "story_error")
        window.root.after.assert_not_called()

    def test_product_ai_wait_ignores_old_error_and_retains_current_progress(self):
        current = ai_client(ai_message="current image")
        bridge = Bridge({"clients": [ai_client(OLD, ai_step="error", ai_provider="gemini"), current]})
        window = self.window(bridge)
        window.products = SimpleNamespace(get_job=lambda job_id: {"image_ai_provider": "chatgpt"})
        window._chrome_window_available = lambda: True
        with self.assertRaises(TimeoutError):
            load_method("_wait_product_job", self.clock)(
                window, "JOB-GUARD", lambda job: False, self.event, 1, "ai", "waiting",
            )
        self.assertEqual(window._product_progress_event.call_args.args[3], "current image")
        self.assertEqual(bridge.commands, [])

    def test_product_ai_wait_ignores_same_job_old_run_error(self):
        bridge = Bridge({'clients': [ai_client(ai_run_id='RUN-OLD', ai_step='error',
            ai_message='old run failed')]})
        bridge._extension_runs = {('ai', 'JOB-GUARD', 0): {'run_id': 'RUN-NEW'}}
        window = self.window(bridge)
        window.products = SimpleNamespace(get_job=lambda job_id: {'image_ai_provider': 'chatgpt'})
        window._chrome_window_available = lambda: True
        with self.assertRaises(TimeoutError):
            load_method('_wait_product_job', self.clock)(
                window, 'JOB-GUARD', lambda job: False, self.event, 1, 'ai', 'waiting')
        self.assertEqual(bridge.commands, [])

    def test_analysis_progress_renews_wait_but_replayed_heartbeat_does_not(self):
        for fresh in (True, False):
            with self.subTest(fresh=fresh):
                self.clock.now = 1000
                bridge = Bridge({})
                bridge.extension_status = lambda: {"clients": [ai_client(
                    ai_step="waiting_for_analysis",
                    ai_updated_at=str(self.clock.now) if fresh else "fixed-report") ]}
                window = self.window(bridge)
                window.products = SimpleNamespace(get_job=lambda job_id: {"image_ai_provider": "chatgpt"})
                window._chrome_window_available = lambda: True
                run = lambda: load_method("_wait_product_job", self.clock)(
                    window, "JOB-GUARD", lambda job: self.clock.now >= 1012,
                    self.event, 5, "ai", "waiting")
                if fresh:
                    self.assertEqual(run()["image_ai_provider"], "chatgpt")
                else:
                    with self.assertRaises(TimeoutError):
                        run()
                self.assertEqual(bridge.commands, [])

    def test_product_timeout_retains_observed_send_when_extension_disappears(self):
        for step, diagnostics in (
            ("waiting_for_analysis", {}),
            ("ai_send_accepted", {}),
            ("ai_send_waiting_acceptance", {}),
            ("analysis_ready", {}),
            ("analysis_saved", {}),
            ("repairing_analysis", {}),
            ("preparing_flow_prompt", {"dispatch_completed": True}),
        ):
            with self.subTest(step=step):
                clock = Clock()
                bridge = Bridge({"clients": [ai_client(ai_step=step, ai_send_diagnostics=diagnostics)]}, {"clients": []})
                window = self.window(bridge)
                job = {"image_ai_provider": "chatgpt", "ai_status": "request_ready"}
                window.products = SimpleNamespace(root=Path(self.product_temp.name), get_job=lambda job_id: job)
                window._chrome_window_available = lambda: True
                window._activate_or_launch_chrome = Mock()
                window._ai_web_url = lambda provider: "https://chatgpt.com/"
                with self.assertRaisesRegex(TimeoutError, "AI_WEB_WAIT_REVIEW") as raised:
                    load_method("_wait_product_job", clock)(window, "JOB-GUARD", lambda job: False,
                        CancelEvent(clock), 5, "ai", "หมดเวลารอ AI Web")
                self.assertEqual(product_ai_recovery_action(job, str(raised.exception)), "")
                self.assertEqual(product_runtime_recovery_action({**job, "partial_generated_images": ["saved.png"]}, str(raised.exception)), "")
                self.assertEqual(bridge.commands, [])

    def test_product_no_send_startup_timeout_can_still_recover(self):
        for clients in ([], [ai_client(OLD, ai_step="waiting_for_analysis")],
                        [ai_client(ai_job_id="OTHER-JOB", ai_step="waiting_for_analysis")]):
            with self.subTest(clients=clients):
                clock = Clock()
                window = self.window(Bridge({"clients": clients}))
                job = {"image_ai_provider": "chatgpt", "ai_status": "request_ready"}
                window.products = SimpleNamespace(get_job=lambda job_id: job)
                window._chrome_window_available = lambda: True
                window._activate_or_launch_chrome = Mock()
                window._ai_web_url = lambda provider: "https://chatgpt.com/"
                with self.assertRaises(TimeoutError) as raised:
                    load_method("_wait_product_job", clock)(window, "JOB-GUARD", lambda job: False,
                        CancelEvent(clock), 5, "ai", "หมดเวลารอ AI Web")
                self.assertNotIn("AI_WEB_WAIT_REVIEW", str(raised.exception))
                self.assertEqual(product_ai_recovery_action(job, str(raised.exception)), "resume_chatgpt")
                self.assertEqual(product_ai_recovery_command(job, 1), "open_chatgpt")

    def test_product_disconnected_browser_activation_is_bounded(self):
        for chrome_available, expected_activations in ((True, 1), (False, 5)):
            with self.subTest(chrome_available=chrome_available):
                clock = Clock()
                window = self.window(Bridge({"clients": []}))
                window.products = SimpleNamespace(get_job=lambda job_id: {"image_ai_provider": "gemini"})
                window._chrome_window_available = lambda: chrome_available
                window._activate_or_launch_chrome = Mock()
                window._ai_web_url = lambda provider: "https://gemini.google.com/app"
                with self.assertRaises(TimeoutError):
                    load_method("_wait_product_job", clock)(window, "JOB-GUARD", lambda job: False,
                        CancelEvent(clock), 120, "ai", "หมดเวลารอ AI Web")
                self.assertEqual(window._activate_or_launch_chrome.call_count, expected_activations)

    def test_both_checkpoint_probes_select_only_exact_version_job_and_shot(self):
        for method in ("_collect_story_flow_clips", "_multi_flow_worker"):
            with self.subTest(method=method):
                current = flow_client()
                old = flow_client(OLD, flow_step="checkpoint_missing")
                unrelated = flow_client(flow_job_id="OTHER-JOB")
                other_shot = flow_client(flow_shot_index=3)
                window = self.window(Bridge({}))
                selector = load_checkpoint_selector(method)
                self.assertIs(selector(window, {"clients": [old, unrelated, other_shot, current]}, "JOB-GUARD", 2), current)
                self.assertIsNone(selector(window, {"clients": [flow_client(OLD), unrelated, other_shot]}, "JOB-GUARD", 2))

    def download_fixture(self, home):
        target = home / "Downloads" / "SmartPost" / "JOB-GUARD" / "flow-shot-02.mp4"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"\0\0\0\x18ftypmp42" + bytes(65536))
        os.utime(target, (10, 10))
        return target

    def test_old_download_receipt_cannot_accept_file_from_previous_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            target = self.download_fixture(home)
            bridge = Bridge({"clients": [flow_client(OLD, flow_download_path=str(target)), {"version": CURRENT}]})
            window = self.window(bridge)
            with patch.object(Path, "home", return_value=home):
                with self.assertRaises(TimeoutError):
                    load_method("_wait_download", self.clock)(window, "JOB-GUARD", 2, timeout=3, cancel_event=self.event, started_at=100)
            self.assertEqual(bridge.commands, [])

    def test_current_download_receipt_still_accepts_completed_exact_file_immediately(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            target = self.download_fixture(home)
            bridge = Bridge({"clients": [
                flow_client(OLD, flow_step="error"),
                flow_client(flow_download_path=str(target)),
            ]})
            with patch.object(Path, "home", return_value=home):
                result = load_method("_wait_download", self.clock)(
                    self.window(bridge), "JOB-GUARD", 2, timeout=3, cancel_event=self.event, started_at=100,
                )
            self.assertEqual(result, target)
            self.assertEqual(self.event.waits, 0)
            self.assertEqual(bridge.commands, [])


if __name__ == "__main__":
    unittest.main()
