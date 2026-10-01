"""Offline startup connection regressions: no Tk, Chrome, provider or job work."""

import ast
import heapq
import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ui.main_window import MainWindow


class _ClockRoot:
    """A Tk after queue driven by virtual time, including already queued callbacks."""

    def __init__(self):
        self.now = 100.0
        self.pending = []
        self.scheduled = []
        self.destroyed = False
        self._serial = 0

    def after(self, delay, callback):
        self._serial += 1
        self.scheduled.append((delay, callback))
        heapq.heappush(self.pending, (self.now + delay / 1000, self._serial, callback))
        return self._serial

    def advance(self, seconds):
        end = self.now + seconds
        calls = 0
        while self.pending and self.pending[0][0] <= end:
            self.now, _serial, callback = heapq.heappop(self.pending)
            callback()
            calls += 1
            if calls > 1000:
                raise AssertionError("Connection observation did not remain bounded")
        self.now = end

    def destroy(self):
        self.destroyed = True


class _DeferredThread:
    """start returns immediately; the test decides when its worker actually runs."""

    def __init__(self, target, *, name=None, daemon=None):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        self.finished = False

    def start(self):
        self.started = True

    def is_alive(self):
        return self.started and not self.finished

    def run(self):
        if not self.started or self.finished:
            raise AssertionError("Worker must be started and may only execute once")
        try:
            self.target()
        finally:
            self.finished = True


class BrowserStartupUiTests(unittest.TestCase):
    def test_actual_ui_renderer_shows_connection_failure_but_not_stale_ready(self):
        from core.cancellable_process import hidden_process_kwargs
        result = subprocess.run(
            ["node", str(Path(__file__).with_name("browser_startup_status.cjs"))],
            capture_output=True, text=True, timeout=20, **hidden_process_kwargs(),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class BrowserStartupConnectionTests(unittest.TestCase):
    def setUp(self):
        self.root = _ClockRoot()
        self.window = MainWindow.__new__(MainWindow)
        self.window.root = self.root
        self.window.cfg = {}
        self.window.bridge = Mock(spec=[
            "REQUIRED_EXTENSION_VERSION", "extension_status", "queue_extension_command", "stop",
        ])
        self.window.bridge.REQUIRED_EXTENSION_VERSION = "test-paired-version"
        self.window.bridge.extension_status.return_value = {"connected": False, "clients": []}
        self.window.extension_status = Mock()
        self.window._write_console = Mock()
        self.window._story_cancel_event = None
        self.window._product_cancel_event = None
        self.threads = []

        def thread_factory(*args, **kwargs):
            thread = _DeferredThread(*args, **kwargs)
            self.threads.append(thread)
            return thread

        self.enterContext(patch.dict(os.environ, {"SMARTFLOW_TEST_DATA_ROOT": ""}))
        self.enterContext(patch("ui.main_window.time.monotonic", side_effect=lambda: self.root.now))
        self.enterContext(patch("ui.main_window.threading.Thread", side_effect=thread_factory))
        self.open_url = self.enterContext(patch.object(self.window, "_open_url"))
        self.visible = self.enterContext(patch.object(self.window, "_chrome_window_available", return_value=False))
        self.process = self.enterContext(patch("ui.main_window.subprocess.Popen", side_effect=AssertionError("No real process")))
        self.no_work = []
        for name in (
            "_bg", "_worker", "_product_pipeline_worker", "_story_worker", "_creation_queue_action",
            "_resume_interrupted_product_on_startup",
            "_resume_interrupted_story_on_startup", "_resume_story_queue_on_startup",
        ):
            self.no_work.append(self.enterContext(patch.object(
                self.window, name, side_effect=AssertionError("No job/ADB worker from browser startup"),
            )))
        for name in ("adb", "android_wifi", "products", "stories", "creation_queue", "story_queue"):
            dependency = Mock(name=name)
            setattr(self.window, name, dependency)
            self.no_work.append(dependency)

    def tearDown(self):
        self.process.assert_not_called()
        for dependency in self.no_work:
            self.assertEqual(dependency.mock_calls, [], "Browser startup touched unrelated work")

    def connect(self, version=None):
        self.window.bridge.extension_status.return_value = {
            "connected": True,
            "clients": [{"version": version or self.window.bridge.REQUIRED_EXTENSION_VERSION}],
        }

    def start_and_run(self):
        self.assertEqual(self.window._start_browser_connection()["phase"], "connecting")
        self.threads[-1].run()

    def assert_attention(self, expected):
        state = self.window._browser_connection
        self.assertEqual(state["phase"], "needs_attention")
        self.assertIn(expected, state["message"])
        self.window.extension_status.set.assert_called_once_with(state["message"])
        self.window._write_console.assert_called_once_with(state["message"], "warning")
        self.assertEqual(self.root.pending, [])
        self.window.bridge.queue_extension_command.assert_not_called()

    def test_start_is_nonblocking_and_repeated_requests_share_one_worker(self):
        state = self.window._start_browser_connection()
        self.assertEqual(state["phase"], "connecting")
        self.open_url.assert_not_called()
        self.assertIsNone(self.window._browser_connection_result)
        self.assertEqual(len(self.threads), 1)
        self.assertTrue(self.threads[0].started)
        self.assertTrue(self.threads[0].daemon)
        self.assertEqual(len(self.root.pending), 1)
        self.root.advance(10)
        for _ in range(3):
            self.assertEqual(self.window._start_browser_connection(), state)
        self.assertEqual(len(self.threads), 1)
        self.threads[0].run()
        self.root.advance(1)
        self.window._start_browser_connection()
        self.open_url.assert_called_once_with("about:blank")
        self.assertEqual(len(self.threads), 1)
        self.window.bridge.queue_extension_command.assert_not_called()

    def test_already_ready_focuses_only_existing_browser_without_opening_a_tab(self):
        self.connect()
        self.visible.return_value = True
        self.start_and_run()
        self.root.advance(1)
        self.assertEqual(self.window._browser_connection["phase"], "ready")
        self.open_url.assert_not_called()
        self.window.bridge.queue_extension_command.assert_called_once_with("focus_browser")
        self.assertEqual(self.root.pending, [])
        self.root.advance(120)
        self.assertEqual(len(self.threads), 1)
        self.window._write_console.assert_not_called()

    def test_delayed_compatible_connection_finishes_observation_without_relaunch(self):
        self.start_and_run()
        self.root.advance(35)
        self.assertEqual(self.window._browser_connection["phase"], "connecting")
        self.connect()
        self.visible.return_value = True
        self.root.advance(1)
        self.assertEqual(self.window._browser_connection["phase"], "ready")
        self.assertEqual(self.root.pending, [])
        self.open_url.assert_called_once_with("about:blank")
        self.assertEqual(len(self.threads), 1)
        self.window.bridge.queue_extension_command.assert_not_called()

    def test_stale_heartbeat_without_visible_chrome_is_not_ready(self):
        self.connect()
        self.start_and_run()
        self.root.advance(59)
        self.assertEqual(self.window._browser_connection["phase"], "connecting")
        self.root.advance(1)
        self.assert_attention("ยังเชื่อม Extension ไม่สำเร็จ")
        self.open_url.assert_called_once_with("about:blank")

    def test_missing_profile_error_is_visible_without_job_or_adb_dispatch(self):
        self.open_url.side_effect = lambda url: MainWindow._open_url(self.window, url)
        with patch("core.chrome_profile.smartflow_profiles", return_value=[]), patch("core.config.save_chrome_profile") as save:
            self.start_and_run()
        self.root.advance(1)
        self.assert_attention("ไม่พบ Chrome โปรไฟล์")
        save.assert_not_called()

    def test_wrong_saved_profile_never_falls_back_to_another_profile(self):
        self.window.cfg = {"chrome_profile_directory": "Profile 9"}
        self.open_url.side_effect = lambda url: MainWindow._open_url(self.window, url)
        with patch("core.chrome_profile.smartflow_profiles", return_value=["Profile 2"]), patch("core.config.save_chrome_profile") as save:
            self.start_and_run()
        self.root.advance(1)
        self.assert_attention("โปรไฟล์ Chrome ที่บันทึกไว้ไม่พบ")
        self.assertEqual(self.window.cfg, {"chrome_profile_directory": "Profile 9"})
        save.assert_not_called()

    def test_timeout_at_sixty_seconds_launches_once_and_does_not_retry_automatically(self):
        self.start_and_run()
        self.root.advance(59)
        self.assertEqual(self.window._browser_connection["phase"], "connecting")
        self.root.advance(1)
        self.assert_attention("ยังเชื่อม Extension ไม่สำเร็จ")
        self.root.advance(600)
        self.open_url.assert_called_once_with("about:blank")
        self.assertEqual(len(self.threads), 1)

    def test_explicit_request_after_timeout_can_make_one_new_attempt(self):
        self.start_and_run()
        self.root.advance(60)
        self.assertEqual(self.window._browser_connection["phase"], "needs_attention")
        self.start_and_run()
        self.assertEqual(len(self.threads), 2)
        self.assertEqual(self.open_url.call_count, 2)
        self.connect()
        self.visible.return_value = True
        self.root.advance(1)
        self.assertEqual(self.window._browser_connection["phase"], "ready")
        self.assertEqual(self.root.pending, [])

    def test_timeout_does_not_start_another_worker_while_first_launch_is_unfinished(self):
        self.window._start_browser_connection()
        self.root.advance(60)
        self.assert_attention("ยังเชื่อม Extension ไม่สำเร็จ")
        self.window._start_browser_connection()
        self.assertEqual(len(self.threads), 1)
        self.open_url.assert_not_called()

    def test_wrong_extension_version_shows_required_version_and_stops_observing(self):
        self.connect("old-version")
        self.visible.return_value = True
        self.start_and_run()
        self.root.advance(1)
        self.assert_attention("Extension รุ่นไม่ตรง")
        self.assertIn(self.window.bridge.REQUIRED_EXTENSION_VERSION, self.window._browser_connection["message"])
        self.root.advance(120)
        self.open_url.assert_called_once_with("about:blank")
        self.assertEqual(len(self.threads), 1)

    def test_isolated_test_data_root_skips_browser_startup(self):
        with patch.dict(os.environ, {"SMARTFLOW_TEST_DATA_ROOT": "isolated-fixture"}):
            self.assertEqual(self.window._start_browser_connection()["phase"], "skipped")
        self.assertEqual(self.threads, [])
        self.assertEqual(self.root.pending, [])
        self.open_url.assert_not_called()
        self.window.bridge.extension_status.assert_not_called()

    def test_pending_update_skips_browser_startup(self):
        self.window._app_update_pending = True
        self.assertEqual(self.window._start_browser_connection()["phase"], "skipped")
        self.assertEqual(self.threads, [])
        self.assertEqual(self.root.pending, [])
        self.open_url.assert_not_called()
        self.window.bridge.extension_status.assert_not_called()

    def test_update_pending_before_deferred_worker_runs_prevents_launch(self):
        self.window._start_browser_connection()
        self.window._app_update_pending = True
        self.threads[0].run()
        self.root.advance(1)
        self.assertEqual(self.window._browser_connection["phase"], "skipped")
        self.assertEqual(self.root.pending, [])
        self.open_url.assert_not_called()
        self.window.bridge.queue_extension_command.assert_not_called()
        self.window._write_console.assert_not_called()

    def test_connect_browser_action_routes_before_membership_renewal_without_work(self):
        self.window.membership = Mock()
        self.window.membership.require.side_effect = AssertionError("Browser connection needs no membership request")
        response = self.window._desktop_execute_action("connect_browser", {})
        self.assertTrue(response["ok"])
        self.assertEqual(response["browser_connection"]["phase"], "connecting")
        self.window.membership.require.assert_not_called()
        self.open_url.assert_not_called()
        self.assertEqual(len(self.threads), 1)
        self.threads[0].run()
        self.open_url.assert_called_once_with("about:blank")

    def test_close_makes_queued_worker_and_observer_inert(self):
        self.window._start_browser_connection()
        self.window._close()
        self.assertTrue(self.root.destroyed)
        self.window.bridge.stop.assert_called_once_with()
        self.threads[0].run()
        self.root.advance(120)
        self.open_url.assert_not_called()
        self.window.bridge.extension_status.assert_not_called()
        self.assertEqual(self.root.pending, [])
        self.assertEqual(self.window._start_browser_connection()["phase"], "skipped")
        self.assertEqual(len(self.threads), 1)

    def test_close_stops_observing_an_already_launched_browser(self):
        self.start_and_run()
        self.root.advance(1)
        reads_before_close = self.window.bridge.extension_status.call_count
        self.window._close()
        self.root.advance(120)
        self.assertEqual(self.window.bridge.extension_status.call_count, reads_before_close)
        self.assertEqual(self.root.pending, [])
        self.open_url.assert_called_once_with("about:blank")
        self.window._write_console.assert_not_called()

    def test_launch_error_cannot_be_hidden_by_cached_heartbeat_and_other_chrome_window(self):
        self.connect()
        self.open_url.side_effect = RuntimeError("saved SmartFlow profile unavailable")
        self.start_and_run()
        self.visible.return_value = True
        self.root.advance(1)
        self.assert_attention("saved SmartFlow profile unavailable")
        self.open_url.assert_called_once_with("about:blank")

    def test_init_schedules_one_connection_only_after_successful_bridge_start(self):
        # Structural supplement to the runtime cases above: do not construct the
        # live app merely to check registration among unrelated UI/services.
        tree = ast.parse(Path(MainWindow.__init__.__code__.co_filename).read_text(encoding="utf-8-sig"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MainWindow")
        init = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "__init__")

        def is_hook(node):
            return (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and ast.unparse(node.func) == "self.root.after"
                    and len(node.args) >= 2
                    and ast.unparse(node.args[1]) == "self._start_browser_connection")

        hooks = [node for node in ast.walk(init) if is_hook(node)]
        self.assertEqual(len(hooks), 1)
        block = next(node for node in init.body if isinstance(node, ast.Try)
                     and any(is_hook(child) for statement in node.body for child in ast.walk(statement)))
        statements = [ast.unparse(statement) for statement in block.body]
        bridge_index = statements.index("self.bridge.start()")
        hook_index = next(i for i, statement in enumerate(block.body) if any(is_hook(node) for node in ast.walk(statement)))
        self.assertLess(bridge_index, hook_index)
        self.assertGreater(hooks[0].args[0].value, 0)
        for handler in block.handlers:
            self.assertFalse(any(is_hook(node) for node in ast.walk(handler)))


if __name__ == "__main__":
    unittest.main()
