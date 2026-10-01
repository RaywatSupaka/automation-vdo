"""Only temporary fixtures/ports. Never use the user's running desktop/jobs."""
import json
import logging
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.membership import guard_action, MembershipError


class NoExtensionMembershipTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        # Every membership access raises, proving browser work never consults it.
        self.member=Mock()
        for name in ('require','require_browser','allowed','browser_allowed','status','observe_extension','forget_extension'):
            getattr(self.member,name).side_effect=AssertionError('Extension must not inspect membership')
        self.products=ProductManager(Path(self.temp.name))
        self.bridge=LocalBridge('127.0.0.1',0,self.products,logging.getLogger('no-ext-license'),membership=self.member).start()
        self.addCleanup(self.bridge.stop)
        from tests.extension_identity_fixture import pair_fixture
        pair_fixture(self.bridge)
        self.base=f'http://127.0.0.1:{self.bridge.server.server_address[1]}'
        self.headers={'Content-Type':'application/json','Origin':'chrome-extension://'+'a'*32,
                      'X-SmartFlow-Token':self.bridge._extension_token}

    def call(self,path,body=None,headers=None):
        path=path.replace('client_id=fixture','client_id='+'a'*32)
        request=urllib.request.Request(self.base+path,data=None if body is None else json.dumps(body).encode(),
                                       headers={**self.headers,**(headers or {})})
        try:
            with urllib.request.urlopen(request,timeout=3) as result:return result.status,json.load(result)
        except urllib.error.HTTPError as error:return error.code,json.load(error)

    def heartbeat(self,version=None):
        return self.call('/api/extension/heartbeat',{'client_id':'a'*32,'version':version or self.bridge.REQUIRED_EXTENSION_VERSION})

    def test_create_capture_dispatch_without_any_extension_membership(self):
        with patch.object(self.products,'list_jobs',return_value=[{'id':'JOB-FIXTURE'}]):
            command=self.bridge.queue_extension_command('capture_shopee_product','JOB-FIXTURE')
        code,hb=self.heartbeat();self.assertEqual(code,200);self.assertNotIn('membership',hb)
        code,reply=self.call('/api/extension/commands?client_id=fixture')
        self.assertEqual(code,200);self.assertEqual([r['id'] for r in reply['commands']],[command['id']])
        self.assertEqual(self.member.mock_calls,[])
        # No duplicated delivery while the owned command lease is valid.
        self.assertEqual(self.call('/api/extension/commands?client_id=fixture')[1]['commands'],[])

    def test_version_and_local_transport_still_protect_job_ownership(self):
        command=self.bridge.queue_extension_command('focus_browser')
        self.heartbeat('old');self.assertEqual(self.call('/api/extension/commands?client_id=fixture')[1]['commands'],[])
        self.heartbeat()
        self.assertEqual(self.call('/api/extension/commands?client_id=fixture',headers={'X-SmartFlow-Token':'wrong'})[0],403)
        self.assertEqual(self.call('/api/extension/commands?client_id=fixture')[1]['commands'][0]['id'],command['id'])
        self.assertEqual(self.call('/api/extension/heartbeat',{'client_id':'foreign'}, {'Origin':'https://evil.invalid'})[0],403)

    def test_old_extension_token_endpoints_removed_not_silently_activated(self):
        for name in ('login','logout','status','authorize'):
            code,result=self.call('/api/membership/extension/'+name,{})
            self.assertEqual(code,410);self.assertEqual(result['code'],'EXTENSION_MEMBERSHIP_REMOVED')
        self.assertEqual(self.member.mock_calls,[])

    def test_cover_and_meta_events_no_license_gate_but_keep_version_and_receipt_handlers(self):
        self.bridge.meta_video=SimpleNamespace(event=Mock(return_value={'phase':'sending'}))
        with patch.object(self.bridge.ai_covers,'event',return_value={'phase':'claimed'}) as event:
            self.assertEqual(self.call('/api/ai-covers/event',{'request_id':'fixture','phase':'claimed','version':self.bridge.REQUIRED_EXTENSION_VERSION})[0],200)
            event.assert_called_once()
        self.assertEqual(self.call('/api/meta-video/event',{'stage':'send_intent','version':self.bridge.REQUIRED_EXTENSION_VERSION})[0],200)
        self.bridge.meta_video.event.assert_called_once()
        self.assertEqual(self.member.mock_calls,[])

    def test_desktop_login_still_required_but_never_extension_presence(self):
        member=Mock();owner=SimpleNamespace(membership=member)
        for action in ('create_product','product_story_prepare','create_story','creation_resume'):
            guard_action(owner,action)
        self.assertEqual(member.require.call_count,4);member.require_browser.assert_not_called()
        member.require.side_effect=MembershipError('LOGIN_REQUIRED')
        with self.assertRaises(MembershipError):guard_action(owner,'create_product')
        guard_action(owner,'cancel_product')
