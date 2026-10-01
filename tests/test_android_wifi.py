import ast
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from core.adb_manager import AdbManager
from core.android_wifi import AndroidWifi, WifiError, endpoint, parse_services

ROOT = Path(__file__).resolve().parents[1]
ADDRESS = '192.168.1.103:35157'
PAIR = '192.168.1.103:36245'
GUID = 'adb-TEST-fixture'
ALIAS = GUID + '._adb-tls-connect._tcp'
SERVICES = f'{GUID}\t_adb-tls-pairing._tcp\t{PAIR}\n{GUID}\t_adb-tls-connect._tcp\t{ADDRESS}\n'


class AndroidWifiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exe = self.root / 'adb.exe'; self.exe.touch()
        self.save = Mock(); self.notify = Mock()
        self.manager = AndroidWifi(AdbManager(self.exe, root=self.root), save_selection=self.save, notify=self.notify)
        self.sent = []; self.devices = f'{ADDRESS} device model:Test_Phone\n{ALIAS} device model:Test_Phone\n'
        self.services = SERVICES; self.identity = 'TEST-IDENTITY'; self.failure = None
        self.runner = patch('core.android_wifi.subprocess.run', side_effect=self.run_adb).start()
        self.addCleanup(patch.stopall)

    def run_adb(self, argv, **kwargs):
        args = tuple(argv[1:]); self.sent.append((args, kwargs))
        if self.failure:
            raise self.failure
        result = ''
        if args == ('mdns', 'services'): result = self.services
        elif args == ('devices', '-l'): result = 'List of devices attached\n' + self.devices
        elif args == ('connect', ADDRESS): result = 'connected to ' + ADDRESS
        elif args == ('pair', PAIR): result = f'Enter pairing code: Successfully paired to {PAIR} [guid={GUID}]'
        elif args[:1] == ('-s',):
            if args[1] not in (ADDRESS, ALIAS): raise AssertionError('wrong device')
            values = {('getprop','ro.serialno'):self.identity, ('getprop','ro.product.model'):'Test Phone',
                      ('getprop','ro.build.version.release'):'16', ('pm','path','com.shopee.th'):'package:/fixture/shopee.apk'}
            result = values[args[3:]]
        else: raise AssertionError(args)
        return subprocess.CompletedProcess(argv, 0, result, '')

    def action(self, action, payload=None):
        result = self.manager.action('android_wifi_' + action, payload)
        if result.get('accepted'):
            self.manager._thread.join(5)
            self.assertFalse(self.manager._thread.is_alive())
        return result

    def test_endpoint_validation(self):
        self.assertEqual(endpoint(' 192.168.1.2:03515 '), '192.168.1.2:3515')
        for value in ('127.0.0.1:5555','8.8.8.8:5555','localhost:1','192.168.1.1:0',
                      '192.168.1.1:65536','192.168.1.1:12;whoami','http://192.168.1.1:1','::1:9','-a',''):
            with self.subTest(value=value), self.assertRaises(WifiError): endpoint(value)

    def test_discovery_filters_and_deduplicates(self):
        rows = parse_services(SERVICES + SERVICES + 'evil _adb-tls-connect._tcp 8.8.8.8:22\n')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['kind'], 'pairing')

    def test_refresh_never_auto_selects_first_device(self):
        self.manager.adb.serial = 'MISSING-SAVED-USB'
        self.action('refresh')
        state = self.manager.state()
        self.assertEqual(state['phase'], 'selection_required')
        self.assertIsNone(state['selected'])
        self.assertEqual(len(state['devices']), 1)
        self.assertEqual(set(state['devices'][0]['aliases']), {ADDRESS, ALIAS})
        self.save.assert_not_called()

    def test_select_verified_device_and_save_only_identity(self):
        self.action('select', {'serial':ADDRESS})
        self.assertEqual(self.manager.state()['phase'], 'connected')
        self.save.assert_called_once_with(ADDRESS, 'TEST-IDENTITY')
        self.assertEqual(self.manager.adb.serial, ADDRESS)

    def test_refresh_rebinds_only_unique_saved_hardware_after_port_change(self):
        self.manager.adb.serial='192.168.1.103:30001';self.manager.saved_identity=self.identity
        self.action('refresh')
        self.assertEqual(self.manager.state()['phase'],'connected')
        self.save.assert_called_once_with(ADDRESS,self.identity)
        self.assertFalse(any(args[0] in ('connect','pair') for args,_ in self.sent))

    def test_refresh_does_not_rebind_different_hardware(self):
        self.manager.adb.serial='192.168.1.103:30001';self.manager.saved_identity='OTHER'
        self.action('refresh');self.save.assert_not_called()
        self.assertIsNone(self.manager.state()['selected'])

    def test_rebind_ambiguous_or_unreadable_peer_stays_unselected(self):
        self.manager.saved_identity=self.identity
        rows=[{'state':'device','transport':'Wi-Fi','serial':'a'},{'state':'device','transport':'Wi-Fi','serial':'b'}]
        with patch.object(self.manager,'_probe',return_value={'device_id':self.identity}):
            self.assertFalse(self.manager._recover_connected_identity([],rows))
        with patch.object(self.manager,'_probe',side_effect=WifiError('offline')):
            self.assertFalse(self.manager._recover_connected_identity([],rows))
        self.save.assert_not_called()

    def test_pair_uses_stdin_and_only_matching_service_for_connect(self):
        with patch.dict(os.environ, {'ADB_TRACE':'all'}):
            self.action('pair', {'endpoint':PAIR, 'code':'001234'})
        pair = next(r for r in self.sent if r[0][0] == 'pair')
        self.assertEqual(pair[0], ('pair', PAIR)); self.assertEqual(pair[1]['input'], '001234\n')
        self.assertNotIn('ADB_TRACE', pair[1]['env'])
        self.assertNotIn('001234', json.dumps(self.manager.state()))
        self.assertNotIn('001234', str(self.save.call_args_list) + str(self.notify.call_args_list))
        self.assertEqual(self.manager.state()['phase'], 'connected')
        self.assertFalse(list(self.root.glob('*.json')))

    def test_pair_without_discovery_stays_paired_not_connected(self):
        self.services = ''
        self.action('pair', {'endpoint':PAIR, 'code':'001234'})
        self.assertEqual(self.manager.state()['phase'], 'paired')
        self.assertFalse(any(args[0] == 'connect' for args, _ in self.sent))
        self.save.assert_not_called()

    def test_pair_does_not_connect_to_other_guid(self):
        self.services = SERVICES.replace(GUID, 'adb-OTHER-phone')
        self.action('pair', {'endpoint':PAIR, 'code':'001234'})
        self.assertEqual(self.manager.state()['phase'], 'paired')
        self.assertFalse(any(args[0] == 'connect' for args, _ in self.sent))

    def test_pair_failure_does_not_echo_secret_or_auto_retry(self):
        self.runner.side_effect = lambda *a, **k: subprocess.CompletedProcess([], 0, 'Failed 001234', '001234')
        self.action('pair', {'endpoint':PAIR, 'code':'001234'})
        state = self.manager.state()
        self.assertEqual(state['phase'], 'error'); self.assertNotIn('001234', json.dumps(state))
        self.assertEqual(self.runner.call_count, 1)

    def test_invalid_code_never_runs_adb(self):
        result = self.action('pair', {'endpoint':PAIR,'code':'12345; bad'})
        self.assertFalse(result['ok']); self.runner.assert_not_called()

    def test_connect_requires_actual_device_not_success_prose(self):
        self.devices = ''
        self.action('connect', {'endpoint':ADDRESS})
        self.assertEqual(self.manager.state()['phase'], 'error')
        self.save.assert_not_called()

    def test_recycled_ip_cannot_be_used_on_refresh_or_reconnect(self):
        self.manager.adb.serial = ADDRESS; self.manager.saved_identity = 'ORIGINAL'
        for action, payload in [('refresh', {}), ('connect', {'endpoint':ADDRESS})]:
            self.action(action, payload)
            self.assertEqual(self.manager.state()['phase'], 'error')
            self.assertIsNone(self.manager.state()['selected'])
        self.save.assert_not_called()

    def test_offline_and_unauthorized_cannot_be_selected(self):
        for status in ('offline','unauthorized'):
            self.devices = f'{ADDRESS} {status}\n'
            self.action('select', {'serial':ADDRESS})
            self.assertEqual(self.manager.state()['phase'], 'error')
        self.save.assert_not_called()

    def test_timeout_and_missing_adb_are_safe(self):
        self.failure = subprocess.TimeoutExpired(['secret-fixture'], 2, output='001234')
        self.action('pair', {'endpoint':PAIR,'code':'001234'})
        self.assertEqual(self.manager.state()['phase'], 'error')
        self.assertNotIn('001234', json.dumps(self.manager.state()))
        self.exe.unlink(); self.failure = None
        self.action('refresh')
        self.assertIn('ADB', self.manager.state()['error'])

    def test_second_operation_is_rejected_and_status_is_nonblocking(self):
        entered, release = threading.Event(), threading.Event()
        original = self.run_adb
        def blocking(argv, **kwargs):
            entered.set(); release.wait(3); return original(argv, **kwargs)
        self.runner.side_effect = blocking
        self.manager.action('android_wifi_refresh'); self.assertTrue(entered.wait(1))
        try:
            self.assertFalse(self.manager.action('android_wifi_connect', {'endpoint':ADDRESS})['ok'])
            self.assertTrue(self.manager.action('android_wifi_status')['android_wifi']['busy'])
        finally:
            release.set(); self.manager._thread.join(5)

    def test_selection_save_failure_keeps_previous_selection(self):
        self.manager.adb.serial = 'PREVIOUS'; self.save.side_effect = OSError('disk full')
        self.action('select', {'serial':ADDRESS})
        self.assertEqual(self.manager.adb.serial, 'PREVIOUS')
        self.assertEqual(self.manager.state()['phase'], 'error')

    def test_manual_tools_require_fresh_exact_identity(self):
        with self.assertRaises(WifiError):
            with self.manager.verified_device(): pass
        self.action('select', {'serial':ADDRESS})
        with self.manager.verified_device() as adb:
            self.assertEqual(adb.serial, ADDRESS)
        self.identity = 'OTHER'
        with self.assertRaises(WifiError):
            with self.manager.verified_device(): self.fail('wrong phone')

    def test_safe_config_save_preserves_existing_values(self):
        from core.config import save_android_selection
        from core.atomic_json import AtomicJsonFile
        target = self.root / 'settings.json'; target.write_text('{"keep":"original"}', encoding='utf-8')
        with patch('core.config._config_store', return_value=AtomicJsonFile(target)):
            save_android_selection(ADDRESS, 'TEST-IDENTITY')
        result = json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual(result, {'keep':'original','device_serial':ADDRESS,'android_device_identity':'TEST-IDENTITY'})

    def test_actual_desktop_action_bypasses_tk_and_extension(self):
        source = (ROOT/'ui/main_window.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_desktop_action_request')
        module = ast.Module(body=[function], type_ignores=[])
        scope = {}; exec(compile(ast.fix_missing_locations(module), '<desktop action>', 'exec'), scope)
        host = Mock(android_wifi=self.manager)
        result = scope['_desktop_action_request'](host, 'android_wifi_status', {})
        self.assertTrue(result['ok']); host._desktop_request.assert_not_called(); self.runner.assert_not_called()

    def test_actual_browser_panel(self):
        patch.stopall()
        result = subprocess.run(['node',str(ROOT/'tests/android_wifi_ui.cjs')], capture_output=True,
                                text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
