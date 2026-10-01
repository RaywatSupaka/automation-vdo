import json
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from desktop.hybrid import HybridHost, run_hybrid


class BrowserStartupHostTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {'SMARTFLOW_TEST_DATA_ROOT': ''})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.frozen = patch.object(sys, 'frozen', False, create=True)
        self.frozen.start()
        self.addCleanup(self.frozen.stop)

    @staticmethod
    def response(raw=b'{"ok":true}'):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = raw
        return response

    def test_ready_host_posts_only_connection_action_once_with_bounded_timeout(self):
        host = HybridHost(port=19065)
        with (
            patch.object(host, '_ready', return_value=True) as ready,
            patch('desktop.hybrid.urlopen', return_value=self.response()) as request,
        ):
            self.assertTrue(host.ensure_browser_connection())
            self.assertFalse(host.ensure_browser_connection())
        ready.assert_called_once_with()
        request.assert_called_once()
        sent = request.call_args.args[0]
        self.assertEqual(sent.full_url, 'http://127.0.0.1:19065/api/desktop/action')
        self.assertEqual(sent.get_method(), 'POST')
        self.assertEqual(json.loads(sent.data), {'action': 'connect_browser', 'payload': {}})
        self.assertEqual(request.call_args.kwargs['timeout'], 1.0)

    def test_unready_or_conflicting_host_never_posts(self):
        for ready_result, conflict in ((False, ''), (False, 'different release'), (True, 'different engine')):
            with self.subTest(ready=ready_result, conflict=conflict):
                host = HybridHost()
                host._engine_conflict = conflict
                with (
                    patch.object(host, '_ready', return_value=ready_result) as ready,
                    patch('desktop.hybrid.urlopen') as request,
                ):
                    self.assertFalse(host.ensure_browser_connection())
                ready.assert_called_once_with()
                request.assert_not_called()

    def test_isolated_test_does_not_probe_or_connect_real_browser(self):
        for set_before_construction in (True, False):
            with self.subTest(set_before_construction=set_before_construction):
                if set_before_construction:
                    with patch.dict(os.environ, {'SMARTFLOW_TEST_DATA_ROOT': 'fixture'}):
                        host = HybridHost()
                else:
                    host = HybridHost()
                with (
                    patch.dict(os.environ, {'SMARTFLOW_TEST_DATA_ROOT': '' if set_before_construction else 'fixture'}),
                    patch.object(host, '_ready') as ready,
                    patch('desktop.hybrid.urlopen') as request,
                ):
                    self.assertFalse(host.ensure_browser_connection())
                ready.assert_not_called()
                request.assert_not_called()

    def test_failed_or_malformed_response_is_not_retried(self):
        for raw in (b'{"ok":false}', b'not json', b'[]', b'{"ok":"true"}'):
            with self.subTest(raw=raw):
                host = HybridHost()
                with (
                    patch.object(host, '_ready', return_value=True),
                    patch('desktop.hybrid.urlopen', return_value=self.response(raw)) as request,
                ):
                    self.assertFalse(host.ensure_browser_connection())
                    self.assertFalse(host.ensure_browser_connection())
                request.assert_called_once()

    def test_network_failure_or_invalid_health_does_not_escape_startup(self):
        for failure_at in ('health', 'request', 'response'):
            with self.subTest(failure_at=failure_at):
                host = HybridHost()
                response = self.response()
                if failure_at == 'response':
                    response.__enter__.return_value.read.side_effect = TimeoutError('read timeout')
                with (
                    patch.object(host, '_ready', side_effect=ValueError('bad health') if failure_at == 'health' else None, return_value=True),
                    patch('desktop.hybrid.urlopen', side_effect=OSError('offline') if failure_at == 'request' else None, return_value=response) as request,
                ):
                    self.assertFalse(host.ensure_browser_connection())
                    self.assertFalse(host.ensure_browser_connection())
                self.assertEqual(request.call_count, 0 if failure_at == 'health' else 1)

    def test_existing_window_requests_connection_without_starting_another_host(self):
        host = Mock()
        webview = Mock()
        with (
            patch.dict(sys.modules, {'webview': webview}),
            patch('desktop.hybrid.HybridHost', return_value=host),
            patch('desktop.hybrid._focus_existing_window', return_value=True),
        ):
            self.assertTrue(run_hybrid())
        host.ensure_browser_connection.assert_called_once_with()
        host.start_engine.assert_not_called()
        host.start_watchdog.assert_not_called()
        host.stop.assert_not_called()
        webview.create_window.assert_not_called()

    def test_new_or_adopted_window_connects_after_engine_ready_and_still_opens_on_failure(self):
        for owns_engine in (True, False):
            with self.subTest(owns_engine=owns_engine):
                host = Mock(base_url='http://127.0.0.1:19065', owns_engine=owns_engine)
                host.ensure_browser_connection.return_value = False
                webview = MagicMock()
                update_api = SimpleNamespace(UpdateApi=Mock())
                with (
                    patch.dict(sys.modules, {'webview': webview, 'desktop.update_api': update_api}),
                    patch('desktop.hybrid.HybridHost', return_value=host),
                    patch('desktop.hybrid._focus_existing_window', return_value=False),
                    patch('desktop.hybrid.threading.Thread'),
                ):
                    self.assertTrue(run_hybrid(port=19065))
                self.assertEqual([call[0] for call in host.method_calls], [
                    'start_engine', 'ensure_browser_connection', 'start_watchdog', 'stop',
                ])
                host.ensure_browser_connection.assert_called_once_with()
                webview.create_window.assert_called_once()
                webview.start.assert_called_once()


if __name__ == '__main__':
    unittest.main()
