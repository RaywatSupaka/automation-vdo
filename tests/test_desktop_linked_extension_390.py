"""Ephemeral broker/vault/server fixtures only; never use the customer's port/DB."""
import json
import logging
import tempfile
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch

from core.membership import Membership, MembershipError, production_membership
from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
import test_membership as legacy
MemoryStore, SERVER = legacy.MemoryStore, legacy.SERVER


class LinkedClientTests(unittest.TestCase):
    def setUp(self):
        self.now = 10
        self.calls = []
        self.error = None
        self.profile = 'a' * 48
        self.stores = {name: MemoryStore() for name in ('identity', 'desktop', 'extension')}
        self.stores['extension'].value = 'legacy-vault-untouched-even-if-unreadable'
        self.client = self.new_client()

    def transport(self, route, body, bearer=''):
        self.calls.append((route, body.get('scope')))
        if self.error:
            raise MembershipError(self.error)
        return dict(scope='desktop', credential='r'*48, session='s'*48, member_id='a'*32,
                    server_time=10000, lease_until=10300, expires_at=20000)

    def new_client(self):
        return Membership(self.stores, 'fixture', transport=self.transport, clock=lambda: self.now, extension_from_desktop=True)

    def observe(self, version='paired'):
        self.client.observe_extension(self.profile, version, required_version='paired')

    def login(self):
        self.client.login('t'*48)
        self.observe()

    def test_production_enables_linked_mode(self):
        with patch('core.secure_store.WindowsCredentialStore', side_effect=lambda *a: MemoryStore()):
            self.assertTrue(production_membership('fixture').extension_from_desktop)

    def test_login_once_no_extension_cloud_request_or_vault_access(self):
        self.observe()
        self.assertFalse(self.client.browser_allowed())
        self.login()
        self.client.require_browser()
        self.assertTrue(self.client.allowed('extension', self.profile))
        status = self.client.status(self.profile)
        self.assertEqual(status['extension']['source'], 'desktop')
        self.assertEqual(status['extension']['lease_seconds'], status['desktop']['lease_seconds'])
        self.assertFalse(self.client.allowed('extension', 'b'*48))
        self.assertNotIn('credential', json.dumps(status))
        self.assertEqual(self.calls, [('activate', 'desktop')])
        self.assertEqual(self.stores['extension'].value, 'legacy-vault-untouched-even-if-unreadable')
        for action in (lambda: self.client.login('t'*48, 'extension', self.profile), lambda: self.client.logout('extension')):
            with self.assertRaisesRegex(MembershipError, 'โปรแกรม'): action()
        self.assertTrue(self.client.allowed())

    def test_presence_version_and_close_are_not_membership_identity(self):
        self.login()
        self.now += 46
        self.assertFalse(self.client.browser_allowed())
        self.observe('old')
        self.assertFalse(self.client.browser_allowed())
        self.observe()
        self.client.require_browser()
        self.client.forget_extension(self.profile)
        self.assertFalse(self.client.browser_allowed())
        self.assertTrue(self.client.allowed())

    def test_upgrade_and_restart_renew_only_desktop_no_token_input(self):
        self.login()
        self.client = self.new_client()
        self.observe()
        self.assertFalse(self.client.browser_allowed())
        self.client.tick()
        self.client.require_browser()
        self.assertEqual(self.calls, [('activate', 'desktop'), ('renew', None)])
        self.now += 30; self.observe(); self.client.tick()
        self.assertEqual(self.calls[-1], ('heartbeat', 'desktop'))

    def test_offline_lease_never_extends_extension_permission(self):
        self.login(); self.error = 'SERVER_UNAVAILABLE'
        self.now += 30; self.observe(); self.client.tick()
        self.client.require_browser()
        self.now += 271; self.observe(); self.client.tick()
        self.assertFalse(self.client.browser_allowed())
        self.assertEqual(self.client.status(self.profile)['extension']['lease_seconds'], 0)

    def test_logout_kick_expiry_lock_stop_both_without_autoactivation(self):
        for code in ['LOGIN_REQUIRED', 'MEMBERSHIP_EXPIRED', 'MEMBERSHIP_BLOCKED']:
            with self.subTest(code=code):
                self.error = None; self.login()
                self.error = code; self.now += 31; self.observe(); self.client.tick()
                self.assertFalse(self.client.browser_allowed())
                self.assertEqual(self.client.status(self.profile)['extension']['code'], code)
                calls = list(self.calls); self.now += 31; self.observe(); self.client.tick()
                self.assertEqual(self.calls, calls)
        self.error = None; self.login(); self.client.logout()
        self.assertFalse(self.client.browser_allowed())
        self.assertEqual(self.stores['extension'].value, 'legacy-vault-untouched-even-if-unreadable')

    def test_authenticated_broker_origin_version_profile_commands_and_results(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = LocalBridge('127.0.0.1', 0, ProductManager(Path(folder)), logging.getLogger('linked-fixture'), membership=self.client).start()
            try:
                base = f'http://127.0.0.1:{bridge.server.server_address[1]}'
                origin = 'chrome-extension://' + 'a'*32
                from tests.extension_identity_fixture import pair_fixture
                pair_fixture(bridge,origin,profile=self.profile)
                headers = {'Origin': origin, 'X-SmartFlow-Token': bridge._extension_token, 'X-SmartFlow-Profile': self.profile}
                def call(path, body=None, extra=None):
                    path=path.replace('client_id=fixture','client_id='+'a'*32)
                    request = urllib.request.Request(base+path, data=None if body is None else json.dumps(body).encode(),
                        headers={'Content-Type':'application/json', **headers, **(extra or {})})
                    try:
                        with urllib.request.urlopen(request, timeout=3) as r: return r.status, json.load(r)
                    except urllib.error.HTTPError as e: return e.code, json.load(e)
                hb = dict(client_id='a'*32, profile_id=self.profile, version=bridge.REQUIRED_EXTENSION_VERSION)
                for extra in [{'Origin': 'https://evil.invalid'}, {'Host': 'evil.invalid'}]:
                    self.assertEqual(call('/api/extension/heartbeat', hb, extra)[0], 403)
                self.assertEqual(call('/api/extension/heartbeat', hb)[0], 200)
                auth = {'version': bridge.REQUIRED_EXTENSION_VERSION}
                self.assertEqual(call('/api/membership/extension/authorize', auth)[0], 410)
                self.client.login('t'*48)
                self.assertEqual(call('/api/membership/extension/authorize', auth)[0], 410)
                for extra in [{'Origin': 'chrome-extension://'+'b'*32}, {'X-SmartFlow-Profile': 'b'*48}, {'X-SmartFlow-Token': 'wrong'}, {'Host': 'evil.invalid'}]:
                    self.assertEqual(call('/api/membership/extension/authorize', auth, extra)[0], 410)
                self.assertEqual(call('/api/membership/extension/authorize', {'version': 'old'})[0], 410)
                self.assertEqual(call('/api/membership/extension/login', {'token': 't'*48})[0], 410)
                with bridge._extension_lock:
                    bridge._extension_commands = [dict(id='new',action='open_chatgpt',status='pending'), dict(id='result',action='download_flow_result',status='pending')]
                self.client.logout()
                _, result = call('/api/extension/commands?client_id=fixture')
                self.assertEqual([row['id'] for row in result['commands']], ['new','result'])
                self.assertEqual(bridge._extension_commands[0]['status'], 'delivered')
                self.client.login('t'*48); call('/api/extension/heartbeat', hb)
                _, result = call('/api/extension/commands?client_id=fixture')
                self.assertEqual(result['commands'], [])
                call('/api/extension/heartbeat', {**hb, 'version':'old'})
                self.assertEqual(call('/api/membership/extension/authorize', auth)[0],410)
                call('/api/extension/heartbeat', hb)
                self.assertEqual(call('/api/extension/disconnect', {'client_id':'fixture'})[0],200)
                self.assertFalse(self.client.browser_allowed())
            finally: bridge.stop()


@unittest.skipUnless(SERVER.is_file(), 'Server source unavailable')
class LinkedServerContractTests(unittest.TestCase):
    transport = legacy.MembershipContractTests.transport
    make_client = legacy.MembershipContractTests.make_client

    def setUp(self):
        legacy.MembershipContractTests.setUp(self)
        self.client = Membership(self.stores, 'linked-fixture', transport=self.transport, clock=lambda:self.now, extension_from_desktop=True)

    def test_one_token_one_machine_and_manual_reentry_after_server_kick(self):
        self.client.login(self.desktop['token'])
        self.client.observe_extension(self.profile, 'paired', required_version='paired')
        self.client.require_browser()
        other = Membership({name:MemoryStore() for name in self.stores}, 'other', transport=self.transport,
                           clock=lambda:self.now, extension_from_desktop=True)
        with self.assertRaises(MembershipError): other.login(self.desktop['token'])
        self.db.token_action(self.desktop['id'], 'kick', 'test')
        self.now += 31; self.client.tick()
        self.assertFalse(self.client.browser_allowed())
        self.assertFalse(self.client.allowed())
        self.client.login(self.desktop['token'])
        self.client.observe_extension(self.profile, 'paired', required_version='paired')
        self.client.require_browser()
        self.assertEqual(self.client.saved['extension'], {})
