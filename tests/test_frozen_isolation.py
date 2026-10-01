"""Frozen smoke isolation without real credentials, app launches or HTTP calls."""
import ctypes
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.secure_store import WindowsCredentialStore, credential_target
from desktop.hybrid import HybridHost, run_hybrid


class CredentialIsolationTests(unittest.TestCase):
    TARGETS = (
        'SmartFlowAI/Membership/identity', 'SmartFlowAI/Membership/desktop',
        'SmartFlowAI/Membership/extension', 'SmartFlowAI/FacebookPage',
        'SmartPostAI/CatfufuExternalTTS', 'SmartPostAI/CatfufuSmartSubOnlineSOD',
    )

    def test_production_targets_are_byte_identical(self):
        with patch.dict(os.environ, {'SMARTFLOW_TEST_DATA_ROOT': ''}):
            for target in self.TARGETS:
                self.assertEqual(credential_target(target), target)

    def test_all_store_operations_use_only_namespace_even_after_env_changes(self):
        for target in (None, *self.TARGETS):
            with self.subTest(target=target), patch.dict(os.environ, {'SMARTFLOW_TEST_DATA_ROOT': 'C:/isolated/smoke'}), \
                 patch('core.secure_store.ctypes.WinDLL', create=True) as dll, \
                 patch('core.secure_store.sys.platform', 'win32'), \
                 patch('core.secure_store.ctypes.get_last_error', return_value=1168, create=True):
                api = dll.return_value
                api.CredReadW.return_value = False
                api.CredWriteW.return_value = True
                api.CredDeleteW.return_value = True
                store = WindowsCredentialStore(target)
                expected = store.target
                self.assertTrue(expected.startswith('SmartFlowAI/Test/'))
                self.assertNotIn('C:/isolated', expected)
                self.assertNotIn(expected, self.TARGETS)
                with patch.dict(os.environ, {'SMARTFLOW_TEST_DATA_ROOT': ''}):
                    self.assertEqual(store.load(), '')
                    store.save('synthetic-only')
                    self.assertTrue(store.delete())
                self.assertEqual(api.CredReadW.call_args.args[0], expected)
                self.assertEqual(api.CredDeleteW.call_args.args[0], expected)
                written = api.CredWriteW.call_args.args[0]._obj
                self.assertEqual(written.TargetName, expected)

    def test_namespace_is_stable_per_canonical_path_but_distinct_per_test_root(self):
        with patch.dict(os.environ, {'SMARTFLOW_TEST_DATA_ROOT': 'C:/isolated/a/../smoke'}):
            first = credential_target('fixture')
        with patch.dict(os.environ, {'SMARTFLOW_TEST_DATA_ROOT': 'C:/isolated/smoke'}):
            self.assertEqual(first, credential_target('fixture'))
        with patch.dict(os.environ, {'SMARTFLOW_TEST_DATA_ROOT': 'C:/isolated/other'}):
            self.assertNotEqual(first, credential_target('fixture'))


class FrozenEngineIdentityTests(unittest.TestCase):
    def host(self, *, test=False, frozen=True):
        with patch('sys.frozen', frozen, create=True), \
             patch.dict(os.environ, {'SMARTFLOW_TEST_DATA_ROOT': 'C:/isolated/smoke' if test else ''}), \
             patch('core.app_updates.customer_version', return_value='0.3.0-beta.9'):
            return HybridHost(port=19065)

    @staticmethod
    def health(version='0.3.0-beta.9', pid=999999):
        return {'ok': True, 'desktop_ui': 'hybrid', 'release_version': version, 'engine_pid': pid}

    def assert_conflict_never_touches_existing_process(self, host, health):
        with patch.object(host, '_health', return_value=health), \
             patch('desktop.hybrid.subprocess.Popen') as launch, \
             patch('desktop.hybrid.urlopen') as request, \
             patch('desktop.hybrid.os.kill') as kill:
            self.assertFalse(host._ready())
            self.assertTrue(host._engine_conflict)
            self.assertIsNone(host.engine_pid)
            with self.assertRaises(RuntimeError): host.start_engine()
            host.stop()
        launch.assert_not_called()
        request.assert_not_called()
        kill.assert_not_called()

    def test_frozen_different_or_missing_version_never_adopts_or_stops_old_engine(self):
        for version in ('0.3.0-beta.8', 'development', None):
            with self.subTest(version=version):
                self.assert_conflict_never_touches_existing_process(self.host(), self.health(version))

    def test_isolated_test_never_adopts_unowned_engine_even_if_same_release(self):
        self.assert_conflict_never_touches_existing_process(self.host(test=True), self.health())

    def test_same_release_normal_orphan_adoption_retained(self):
        host = self.host()
        with patch.object(host, '_health', return_value=self.health()):
            self.assertTrue(host._ready())
        self.assertEqual(host.engine_pid, 999999)

    def test_source_legacy_orphan_adoption_retained(self):
        host = self.host(frozen=False)
        health = self.health()
        health.pop('release_version')
        with patch.object(host, '_health', return_value=health):
            self.assertTrue(host._ready())

    def test_testmode_accepts_only_the_launched_child_pid(self):
        host = self.host(test=True)
        host.owns_engine = True
        host.process = types.SimpleNamespace(pid=101)
        with patch.object(host, '_health', return_value=self.health(pid=101)):
            self.assertTrue(host._ready())
        with patch.object(host, '_health', return_value=self.health(pid=102)):
            self.assertFalse(host._ready())
        self.assertEqual(host.engine_pid, 101)

    def test_frozen_wrong_version_does_not_focus_or_refresh_the_other_window(self):
        with patch('sys.frozen', True, create=True), \
             patch.dict(os.environ, {'SMARTFLOW_TEST_DATA_ROOT': ''}), \
             patch.dict('sys.modules', {'webview': types.ModuleType('webview')}), \
             patch('core.app_updates.customer_version', return_value='0.3.0-beta.9'), \
             patch.object(HybridHost, '_health', return_value=self.health('0.3.0-beta.8')), \
             patch('desktop.hybrid._focus_existing_window') as focus, \
             patch('desktop.hybrid.subprocess.Popen') as launch:
            with self.assertRaises(RuntimeError): run_hybrid(port=19065)
        focus.assert_not_called()
        launch.assert_not_called()

    def test_frozen_engine_logs_go_to_customer_data_not_install_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            resource, data = Path(tmp) / 'app', Path(tmp) / 'data'
            resource.mkdir()
            data.mkdir()
            host = self.host(test=True)
            with patch('sys.frozen', True, create=True), \
                 patch('desktop.hybrid.ROOT', resource), \
                 patch.dict('sys.modules', {'core.config': types.SimpleNamespace(ROOT=data)}), \
                 patch.object(host, '_ready', return_value=False), \
                 patch('desktop.hybrid.subprocess.Popen', side_effect=OSError('synthetic launch failure')):
                try:
                    with self.assertRaises(OSError): host.start_engine()
                finally:
                    if host._engine_log:
                        host._engine_log.close()
            self.assertTrue((data / 'logs/hybrid_engine.log').is_file())
            self.assertFalse((resource / 'logs').exists())


if __name__ == '__main__':
    unittest.main()
