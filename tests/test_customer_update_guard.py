"""Actual controller and isolated update transaction regressions. No live jobs."""
import ast
import hashlib
import json
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from desktop.update_api import UpdateApi
from core.job_file_guard import uses_job_files
from ui.update_guard import direct_action, idle_reason, prepare


ROOT = Path(__file__).resolve().parents[1]


def actual_method(name):
    tree = ast.parse((ROOT / 'ui/main_window.py').read_text(encoding='utf-8-sig'))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = {'uses_job_files': uses_job_files}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'ui/main_window.py', 'exec'), scope)
    return scope[name]


class UpdateBarrierTests(unittest.TestCase):
    def owner(self):
        return types.SimpleNamespace(
            _app_update_lock=threading.RLock(),
            _creation_idle_reason=lambda: '',
            story_queue=types.SimpleNamespace(pause=Mock()),
            shopee_posting=types.SimpleNamespace(_busy=False, action=Mock(return_value={'ok': True})),
            facebook_post=types.SimpleNamespace(workers={}, state=lambda: {'planner': {'batch': {}}}, action=Mock(return_value={'ok': True})),
            android_wifi=types.SimpleNamespace(state=lambda: {'busy': False}, action=Mock(return_value={'ok': True})),
        )

    def test_active_workers_block_without_changing_queue_or_existing_gates(self):
        for kind in ('creation', 'shopee', 'facebook', 'planner', 'wifi'):
            with self.subTest(kind=kind):
                owner = self.owner()
                if kind == 'creation': owner._creation_idle_reason = lambda: 'active'
                if kind == 'shopee': owner.shopee_posting._busy = True
                if kind == 'facebook': owner.facebook_post.workers = {'live': types.SimpleNamespace(is_alive=lambda: True)}
                if kind == 'planner': owner.facebook_post.state = lambda: {'planner': {'batch': {'active': True}}}
                if kind == 'wifi': owner.android_wifi.state = lambda: {'busy': True}
                self.assertTrue(idle_reason(owner))
                with self.assertRaises(ValueError): prepare(owner, {})
                owner.story_queue.pause.assert_not_called()
                self.assertFalse(getattr(owner, '_app_update_pending', False))

    def test_idle_commits_once_and_cancel_requires_exact_nonce_without_resume(self):
        owner = self.owner()
        reply = prepare(owner, {})
        self.assertTrue(reply['ok'])
        self.assertTrue(owner._app_update_pending)
        self.assertEqual(len(reply['nonce']), 32)
        owner.story_queue.pause.assert_called_once_with('app_update')
        with self.assertRaises(ValueError): prepare(owner, {})
        with self.assertRaises(ValueError): prepare(owner, {'cancel': True, 'nonce': 'other'})
        self.assertTrue(owner._app_update_pending)
        self.assertTrue(prepare(owner, {'cancel': True, 'nonce': reply['nonce']})['cancelled'])
        self.assertFalse(owner._app_update_pending)
        owner.story_queue.pause.assert_called_once()
        with self.assertRaises(ValueError): prepare(owner, {'cancel': True, 'nonce': reply['nonce']})

    def test_extension_update_preserves_existing_user_pause(self):
        owner = self.owner()
        owner.story_queue.snapshot = Mock(return_value={'paused': True})
        reply = prepare(owner, {'extension_update': True})
        self.assertTrue(reply['ok'])
        owner.story_queue.pause.assert_not_called()
        self.assertTrue(prepare(owner, {'cancel': True, 'nonce': reply['nonce']})['cancelled'])

    def test_direct_live_routes_block_after_barrier_but_reads_and_pause_remain(self):
        route = actual_method('_desktop_action_request')
        owner = self.owner()
        prepare(owner, {})
        with patch('core.membership.guard_action'):
            for action in ('shopee_post_start', 'shopee_post_check', 'shopee_post_account',
                           'facebook_publish', 'facebook_planner_start', 'android_wifi_pair'):
                with self.subTest(action=action), self.assertRaises(ValueError): route(owner, action, {})
            for action in ('shopee_post_status', 'shopee_post_pause', 'facebook_status',
                           'facebook_planner_pause', 'android_wifi_status'):
                with self.subTest(action=action): self.assertTrue(route(owner, action, {})['ok'])

    def test_actual_prepare_routes_use_update_barrier_and_cancel_when_pending(self):
        execute = actual_method('_desktop_execute_action')
        owner = self.owner()
        with patch('core.membership.guard_action'):
            owner.shopee_posting._busy = True
            with self.assertRaises(ValueError): execute(owner, 'prepare_app_update', {})
            owner.shopee_posting._busy = False
            reply = execute(owner, 'prepare_app_update', {})
            self.assertTrue(execute(owner, 'prepare_app_update', {'cancel': True, 'nonce': reply['nonce']})['ok'])

    def test_prepare_cannot_race_new_post_or_wait_for_tk_deadlock(self):
        owner = self.owner()
        entered, release = threading.Event(), threading.Event()
        def start():
            def callback():
                entered.set()
                release.wait(3)
                owner.shopee_posting._busy = True
            direct_action(owner, 'shopee_post_start', callback)
        worker = threading.Thread(target=start)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            with self.assertRaises(ValueError): prepare(owner, {})
        finally:
            release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        with self.assertRaises(ValueError): prepare(owner, {})
        owner.story_queue.pause.assert_not_called()


class UpdateInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'app'
        self.app.mkdir()
        (self.app / 'customer-release.json').write_text(json.dumps({'version': '0.3.0-beta.8'}))
        (self.app / 'SmartFlow Updater.exe').write_bytes(b'non-executable-test-fixture')
        self.patch_file = self.root / 'patch.zip'
        self.patch_file.write_bytes(b'synthetic patch')
        self.release = {'version': '0.3.0-beta.9', 'supported_from': ['0.3.0-beta.8'], 'patch': {
            'size': self.patch_file.stat().st_size,
            'sha256': hashlib.sha256(self.patch_file.read_bytes()).hexdigest(),
        }}
        self.api = UpdateApi(types.SimpleNamespace(base_url='http://127.0.0.1:0', engine_pid=123))
        self.api._envelope = {'release': self.release}
        self.api._downloaded = {'patch': self.patch_file}
        self.api._window = types.SimpleNamespace(destroy=Mock())
        self.api._update_barrier = Mock(side_effect=lambda payload: {'ok': True, 'nonce': 'synthetic-nonce'})
        for patcher in (
            patch('desktop.update_api.RESOURCE_ROOT', self.app),
            patch('desktop.update_api.verify_release', return_value=self.release),
            patch('sys.frozen', True, create=True),
            patch.dict('os.environ', {'LOCALAPPDATA': str(self.root / 'local')}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_success_launches_only_one_updater_for_repeat_clicks(self):
        with patch('desktop.update_api.subprocess.Popen') as launch, patch('desktop.update_api.threading.Timer'):
            self.assertTrue(self.api.update_install()['ok'])
            self.assertFalse(self.api.update_install()['ok'])
        launch.assert_called_once()
        self.api._update_barrier.assert_called_once_with({})

    def test_launch_failure_releases_matching_barrier_without_closing_window(self):
        with patch('desktop.update_api.subprocess.Popen', side_effect=OSError('fixture failure')):
            self.assertFalse(self.api.update_install()['ok'])
        self.assertEqual(self.api._update_barrier.call_args_list[-1].args,
                         ({'cancel': True, 'nonce': 'synthetic-nonce'},))
        self.api._window.destroy.assert_not_called()
        self.assertFalse(self.api._install_started)

    def test_unknown_launch_after_start_does_not_release_barrier(self):
        with patch('desktop.update_api.subprocess.Popen'), patch('desktop.update_api.threading.Timer', side_effect=RuntimeError('timer failure')):
            self.assertFalse(self.api.update_install()['ok'])
        self.api._update_barrier.assert_called_once_with({})
        self.assertTrue(self.api._install_started)

    def test_wrong_download_rejected_before_barrier_and_close(self):
        self.patch_file.write_bytes(b'changed payload')
        with patch('desktop.update_api.subprocess.Popen') as launch:
            self.assertFalse(self.api.update_install()['ok'])
        self.api._update_barrier.assert_not_called()
        launch.assert_not_called()
        self.api._window.destroy.assert_not_called()

    def test_unsupported_base_rejected_before_barrier(self):
        self.release['supported_from'] = []
        with patch('desktop.update_api.subprocess.Popen') as launch:
            self.assertFalse(self.api.update_install()['ok'])
        self.api._update_barrier.assert_not_called()
        launch.assert_not_called()

    def test_failed_release_of_barrier_does_not_claim_recovery(self):
        self.api._update_barrier.side_effect = [{'ok': True, 'nonce': 'synthetic-nonce'}, {'ok': False}]
        with patch('desktop.update_api.subprocess.Popen', side_effect=OSError('fixture failure')):
            reply = self.api.update_install()
        self.assertFalse(reply['ok'])
        self.assertIn('ยังยืนยันการปลดสถานะไม่ได้', reply['error'])

    def test_busy_service_response_does_not_launch_or_clear_others_barrier(self):
        self.api._update_barrier = Mock(return_value={'ok': False, 'error': 'busy'})
        with patch('desktop.update_api.subprocess.Popen') as launch:
            self.assertFalse(self.api.update_install()['ok'])
        self.api._update_barrier.assert_called_once_with({})
        launch.assert_not_called()

    def test_install_lock_rejects_concurrent_prepare(self):
        self.api._install_lock.acquire()
        try:
            self.assertFalse(self.api.update_install()['ok'])
        finally:
            self.api._install_lock.release()
        self.api._update_barrier.assert_not_called()


if __name__ == '__main__':
    unittest.main()
