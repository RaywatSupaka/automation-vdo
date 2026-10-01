import importlib.util
import json
import logging
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.membership import Membership, MembershipError, guard_action
from core.local_bridge import LocalBridge
from core.product_manager import ProductManager

SERVER = Path('C:/Users/keera/AppData/Local/SmartSubAI/VoiceCloneOnline/backend/services/smartflow_membership.py')


class MemoryStore:
    def __init__(self): self.value = ''
    def load(self): return self.value
    def save(self, value): self.value = value
    def delete(self): self.value = ''


class ClientSafetyTests(unittest.TestCase):
    def setUp(self):
        self.stores={scope:MemoryStore() for scope in ('identity','desktop','extension')}
        self.result={'scope':'desktop','session':'sfs_'+'x'*43,'credential':'sfr_'+'x'*43,
                     'member_id':'a'*32,'server_time':10000,'lease_until':10300,'expires_at':20000}
        self.now=1.0
        self.client=Membership(self.stores,'fixture',transport=lambda *args:dict(self.result),clock=lambda:self.now)

    def test_malformed_lease_never_unlocks(self):
        for value in [10000,9999,11000,float('nan'),float('inf'),None]:
            self.result['lease_until']=value
            with self.assertRaises(MembershipError): self.client.login('x'*46)
            self.assertFalse(self.client.allowed())

    def test_server_request_latency_consumes_lease(self):
        def slow(*args): self.now+=20; return dict(self.result)
        self.client.transport=slow; self.client.login('x'*46)
        self.assertEqual(self.client.status()['desktop']['lease_seconds'],280)

    def test_desktop_login_alone_can_dispatch_browser_jobs(self):
        self.client.login('x'*46)
        self.assertFalse(self.client.browser_allowed())
        with self.assertRaises(MembershipError): self.client.require_browser()
        guard_action(SimpleNamespace(membership=self.client),'create_story')
        guard_action(SimpleNamespace(membership=self.client),'voice_create')

    def test_queue_gate_does_not_claim_or_fail_row(self):
        from ui.creation_queue import CreationQueueMixin
        owner=SimpleNamespace(membership=self.client,_start_next_story_queue_item=lambda:self.fail('must not claim'))
        CreationQueueMixin._creation_queue_tick(owner)
        self.client.login('x'*46)
        calls=[]
        owner._start_next_story_queue_item=lambda:calls.append('next')
        CreationQueueMixin._creation_queue_tick(owner)
        self.assertEqual(calls,['next'])

    def test_corrupt_vault_is_fail_closed_not_new_identity(self):
        self.stores['identity'].value='corrupt'
        client=Membership(self.stores,'fixture')
        self.assertEqual(client.status()['desktop']['code'],'SECURE_STORAGE_UNAVAILABLE')
        self.assertEqual(self.stores['identity'].value,'corrupt')
        with self.assertRaises(MembershipError):client.login('x'*46)

    def test_scopes_server_fields_must_be_valid(self):
        for changes in [{'scope':'extension'},{'member_id':''},{'session':''},{'expires_at':float('nan')}]:
            with self.subTest(keys=list(changes)):
                old=dict(self.result);self.result.update(changes)
                with self.assertRaises(MembershipError):self.client.login('x'*46)
                self.assertFalse(self.client.allowed());self.result=old

    def test_new_renewal_does_not_retain_activation_token(self):
        token='test_activation_'+'x'*40
        self.client.login(token)
        self.assertNotIn(token,'|'.join(store.value for store in self.stores.values()))
        self.client.logout();self.assertTrue(self.stores['identity'].value)
        self.assertFalse(self.stores['desktop'].value)

    @unittest.skipUnless(__import__('sys').platform=='win32','Windows vault only')
    def test_real_windows_vault_unique_fixture_roundtrip_and_cleanup(self):
        from core.secure_store import WindowsCredentialStore
        import uuid
        store=WindowsCredentialStore('SmartFlowAI/Tests/Membership/'+uuid.uuid4().hex)
        try:
            value='synthetic-test-value-'+uuid.uuid4().hex
            store.save(value);self.assertEqual(store.load(),value)
        finally:store.delete()
        self.assertEqual(store.load(),'')


@unittest.skipUnless(SERVER.is_file(), 'Owner-server source contract not available on this test host')
class MembershipContractTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('smartflow_member_contract', SERVER)
        self.server_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.server_module)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 100000.0
        self.db = self.server_module.MembershipStore(Path(self.temp.name)/'test.sqlite3', clock=lambda:self.now)
        self.member_id = self.db.create_member('Fixture only', self.now + 86400, 'test')['id']
        self.desktop = self.db.issue_token(self.member_id, 'desktop', 'test')
        self.extension = self.db.issue_token(self.member_id, 'extension', 'test')
        self.stores = {scope:MemoryStore() for scope in ('identity','desktop','extension')}
        self.calls = []
        self.offline = False
        self.client = self.make_client()
        self.profile = 'a' * 48

    def transport(self, route, body, bearer=''):
        self.calls.append(route)  # Never record secret request bodies.
        if self.offline:
            raise MembershipError('SERVER_UNAVAILABLE')
        try:
            if route == 'activate': return self.db.activate(**body)
            if route == 'renew': return self.db.renew(bearer, **body)
            return self.db.heartbeat(bearer, **body)
        except self.server_module.MembershipError as error:
            raise MembershipError(error.code) from None

    def make_client(self, stores=None):
        return Membership(stores or self.stores, 'test-client', transport=self.transport, clock=lambda:self.now)

    def login(self, extension=False):
        self.client.login(self.desktop['token'])
        if extension: self.client.login(self.extension['token'], 'extension', self.profile, '0.15.384')

    def advance(self, seconds):
        self.now += seconds
        self.client.observe_extension(self.profile, '0.15.384')
        self.client.tick()

    def test_starts_locked_and_does_not_start_network_from_status(self):
        self.assertFalse(self.client.status()['desktop']['allowed'])
        self.client.tick()
        self.assertEqual(self.calls, [])
        with self.assertRaises(MembershipError): guard_action(SimpleNamespace(membership=self.client), 'create_story')

    def test_activation_and_secure_persistence_no_activation_or_session(self):
        self.login()
        self.assertTrue(self.client.allowed())
        persisted = '|'.join(store.value for store in self.stores.values())
        self.assertNotIn(self.desktop['token'], persisted)
        self.assertNotIn(self.client.sessions['desktop']['session'], persisted)
        for secret in [self.desktop['token'], self.client.saved['desktop']['credential'], self.client.identity['device_proof']]:
            self.assertNotIn(secret, json.dumps(self.client.status()))

    def test_wrong_token_and_wrong_scope(self):
        for token, code in [('x'*46,'LOGIN_REQUIRED'), (self.extension['token'],'TOKEN_SCOPE_MISMATCH')]:
            with self.assertRaises(MembershipError) as raised: self.client.login(token)
            self.assertEqual(raised.exception.code, code)
        self.assertFalse(self.client.allowed())

    def test_wrong_shape_cannot_leak_error(self):
        for token in [None, {}, [], '', 'bad', 'x'*1000]:
            with self.assertRaises(MembershipError): self.client.login(token)
        self.assertEqual(self.calls, [])

    def test_one_token_one_machine(self):
        self.login()
        other = self.make_client({scope:MemoryStore() for scope in self.stores})
        with self.assertRaises(MembershipError) as raised: other.login(self.desktop['token'])
        self.assertEqual(raised.exception.code, 'TOKEN_BOUND_TO_ANOTHER_DEVICE')
        self.assertTrue(self.client.allowed())

    def test_kick_requires_manual_same_token_and_preserves_identity(self):
        self.login(True)
        identity = self.stores['identity'].value
        self.db.token_action(self.desktop['id'], 'kick', 'test')
        self.advance(30)
        self.assertFalse(self.client.allowed())
        self.assertFalse(self.client.allowed('extension', self.profile))
        calls = len(self.calls)
        self.advance(60)
        self.assertEqual(len(self.calls), calls)
        self.assertEqual(identity, self.stores['identity'].value)
        self.login(True)
        self.assertTrue(self.client.allowed('extension', self.profile))

    def test_block_then_unblock_still_requires_manual_login(self):
        self.login()
        self.db.update_member(self.member_id, 'block', 'test')
        self.advance(30)
        self.assertFalse(self.client.allowed())
        self.db.update_member(self.member_id, 'unblock', 'test')
        self.advance(60)
        self.assertFalse(self.client.allowed())
        self.login()
        self.assertTrue(self.client.allowed())

    def test_expiry_and_revocation(self):
        self.login()
        self.db.token_action(self.desktop['id'], 'revoke', 'test')
        self.advance(30)
        self.assertFalse(self.client.allowed())
        with self.assertRaises(MembershipError): self.login()

    def test_expiry_bounds_lease(self):
        self.db.update_member(self.member_id, 'renew', 'test', self.now+40)
        self.login()
        self.assertLessEqual(self.client.status()['desktop']['lease_seconds'],40)
        self.offline = True
        self.now += 41
        self.assertFalse(self.client.allowed())

    def test_restart_requires_server_renew_not_activation(self):
        self.login()
        again = self.make_client()
        self.assertFalse(again.allowed())
        again.tick()
        self.assertTrue(again.allowed())
        self.assertEqual(self.calls, ['activate','renew'])

    def test_version_upgrade_restores_same_profile_without_new_activation(self):
        self.login(True)
        saved = {key: store.value for key, store in self.stores.items()}
        again = self.make_client()
        again.version = 'fixture-desktop-upgrade'
        before = again.status(self.profile)
        self.assertTrue(before['desktop']['restoring'])
        self.assertTrue(before['extension']['remembered'])
        self.assertTrue(before['extension']['restoring'])
        self.assertEqual(before['extension']['code'], 'RESTORING_SESSION')
        self.assertFalse(before['extension']['allowed'])
        again.observe_extension(self.profile, '0.15.386')
        again.tick()
        self.assertTrue(again.allowed('extension', self.profile))
        self.assertFalse(again.status(self.profile)['extension']['restoring'])
        self.assertEqual(self.calls, ['activate', 'activate', 'renew', 'renew'])
        self.assertEqual(saved, {key: store.value for key, store in self.stores.items()})

    def test_other_installation_reports_migration_not_automatic_adoption(self):
        self.login(True)
        saved = self.stores['extension'].value
        again = self.make_client()
        other = 'b' * 48
        state = again.status(other)['extension']
        self.assertTrue(state['profile_changed'])
        self.assertEqual(state['code'], 'EXTENSION_PROFILE_CHANGED')
        self.assertFalse(state['remembered'])
        self.assertFalse(state['restoring'])
        again.observe_extension(other, '0.15.386')
        again.tick()
        self.assertFalse(again.allowed('extension', other))
        self.assertEqual(self.calls, ['activate', 'activate', 'renew'])
        self.assertEqual(saved, self.stores['extension'].value)

    def test_remembered_outage_and_kick_have_different_status(self):
        self.login(True)
        again = self.make_client()
        again.observe_extension(self.profile, '0.15.386')
        self.offline = True
        again.tick()
        self.assertTrue(again.status(self.profile)['desktop']['restoring'])
        self.assertEqual(again.status(self.profile)['desktop']['code'], 'SERVER_UNAVAILABLE')
        self.offline = False
        self.now += 31
        again.observe_extension(self.profile, '0.15.386'); again.tick()
        self.assertTrue(again.allowed('extension', self.profile))
        self.db.token_action(self.extension['id'], 'kick', 'test')
        self.now += 31
        again.observe_extension(self.profile, '0.15.386'); again.tick()
        state = again.status(self.profile)['extension']
        self.assertFalse(state['remembered'])
        self.assertFalse(state['restoring'])
        self.assertFalse(state['allowed'])
        calls = list(self.calls)
        again.tick()
        self.assertEqual(calls, self.calls)

    def test_kick_while_app_closed_disallows_renew(self):
        self.login()
        self.db.token_action(self.desktop['id'], 'kick', 'test')
        again = self.make_client(); again.tick()
        self.assertFalse(again.allowed())
        self.assertEqual(again.saved['desktop'],{})

    def test_outage_only_original_lease_then_recovery_renew(self):
        self.login()
        self.offline=True
        self.advance(30)
        self.assertTrue(self.client.allowed())
        self.advance(270)
        self.assertFalse(self.client.allowed())
        self.offline=False
        self.advance(30)
        self.assertTrue(self.client.allowed())
        self.assertEqual(self.calls.count('activate'),1)
        self.assertEqual(self.calls[-1],'renew')

    def test_offline_restart_never_trusts_disk_lease(self):
        self.login(); self.offline=True
        again=self.make_client(); again.tick()
        self.assertFalse(again.allowed())

    def test_extension_scope_profile_and_member_pairing(self):
        self.login(True)
        self.assertTrue(self.client.allowed('extension',self.profile))
        self.assertFalse(self.client.allowed('extension','b'*48))
        self.assertFalse(self.client.allowed('extension',''))
        with self.assertRaises(MembershipError): self.client.login(self.extension['token'],'extension','b'*48,'test')
        other = self.db.create_member('other', self.now+86400, 'test')['id']
        token = self.db.issue_token(other,'extension','test')['token']
        with self.assertRaises(MembershipError): self.client.login(token,'extension',self.profile,'test')

    def test_change_desktop_member_drops_old_extension(self):
        self.login(True)
        other = self.db.create_member('other', self.now+86400, 'test')['id']
        token = self.db.issue_token(other,'desktop','test')['token']
        self.client.login(token)
        self.assertFalse(self.client.allowed('extension',self.profile))
        self.assertEqual(self.client.saved['extension'],{})

    def test_extension_stops_presence_when_chrome_closed(self):
        self.login(True)
        self.now += 60; self.client.tick()
        self.assertEqual(self.calls.count('heartbeat'),1)  # desktop only

    def test_extension_kick_does_not_kick_desktop(self):
        self.login(True)
        self.db.token_action(self.extension['id'],'kick','test'); self.advance(30)
        self.assertTrue(self.client.allowed())
        self.assertFalse(self.client.allowed('extension',self.profile))

    def test_storage_failure_never_unlocks(self):
        with patch.object(self.stores['desktop'],'save',side_effect=OSError('fixture only')):
            with self.assertRaises(MembershipError): self.login()
        self.assertFalse(self.client.allowed())

    def test_status_remains_responsive_while_server_waits(self):
        self.login()
        entered, release = threading.Event(),threading.Event()
        def wait(*args):
            entered.set(); release.wait(3); raise MembershipError('SERVER_UNAVAILABLE')
        self.client.transport=wait; self.now+=30
        worker=threading.Thread(target=self.client.tick); worker.start()
        try:
            self.assertTrue(entered.wait(2)); start=time.monotonic()
            self.assertTrue(self.client.status()['desktop']['allowed'])
            self.assertLess(time.monotonic()-start,.2)
        finally: release.set(); worker.join(3)

    def test_safe_actions_available_locked_unknown_action_denied(self):
        owner=SimpleNamespace(membership=self.client)
        for action in ['prepare_app_update','shutdown','cancel_story','cancel_product','shopee_post_pause']:
            guard_action(owner,action)
        for action in ['create_product','create_story','creation_resume','creation_retry','shopee_post_start','facebook_publish','future_unknown_action']:
            with self.assertRaises(MembershipError): guard_action(owner,action)

    def test_broker_http_requires_origin_host_and_profile_preserves_queued_work(self):
        calls=[]
        bridge=LocalBridge('127.0.0.1',0,ProductManager(Path(self.temp.name)/'products'),logging.getLogger('membership-fixture'),
                           membership=self.client,desktop_action=lambda action,payload:calls.append(action) or {'ok':True}).start()
        self.addCleanup(bridge.stop)
        base=f'http://127.0.0.1:{bridge.server.server_address[1]}'
        def post(path,body,headers=None):
            request=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**(headers or {})})
            try:
                with urllib.request.urlopen(request,timeout=3) as result:return result.status,json.load(result)
            except urllib.error.HTTPError as error:return error.code,json.load(error)
        status,data=post('/api/desktop/action',{'action':'create_story'})
        self.assertNotEqual(status,200); self.assertEqual(calls,[])
        self.assertEqual(post('/api/desktop/action',{'action':'prepare_app_update'})[0],200)
        for headers in [{'Origin':'https://evil.invalid'},{'Host':'evil.invalid'}]:
            self.assertEqual(post('/api/membership/desktop/login',{'token':self.desktop['token']},headers)[0],403)
        self.assertEqual(post('/api/membership/desktop/login',{'token':self.desktop['token']})[0],200)
        self.assertEqual(post('/api/membership/extension/login',{'token':self.extension['token'],'version':'test'})[0],410)
        headers={'Origin':'chrome-extension://fixture','X-SmartFlow-Token':bridge._extension_token,'X-SmartFlow-Profile':self.profile}
        self.assertEqual(post('/api/membership/extension/login',{'token':self.extension['token'],'version':'test'},headers)[0],410)
        self.assertEqual(post('/api/membership/extension/authorize',{},headers)[0],410)
        self.client.logout()
        self.assertEqual(post('/api/membership/extension/authorize',{},headers)[0],410)
        # Transport/receipts remain available; membership loss is not engine loss.
        self.assertEqual(post('/api/extension/heartbeat',{'client_id':'fixture','version':bridge.REQUIRED_EXTENSION_VERSION})[0],200)
        with urllib.request.urlopen(base+'/health') as response:self.assertTrue(json.load(response)['ok'])


if __name__ == '__main__': unittest.main()
