import base64
import io
import json
import logging
import os
import tempfile
import subprocess
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch
from PIL import Image
from core.extension_identity import ExtensionIdentity
from core.product_manager import ProductManager
from core.product_story import ProductCast, prepare_link
from core.local_bridge import LocalBridge
from tests.extension_identity_fixture import pair_fixture
from tests import test_meta_video as meta_fixture


def picture(color='blue',size=(256,456)):
    out=io.BytesIO();Image.new('RGB',size,color).save(out,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()


class ProductFreeze426(unittest.TestCase):
    def test_restart_resume_freezes_all_options_and_reuses_first_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);products=ProductManager(root);cast=ProductCast(root)
            person=cast.add('คนในคลัง',picture());cast.set_outfit(person['id'],picture('green'))
            bridge=Mock();bridge.queue_extension_command.return_value={'id':'capture'}
            bridge.extension_command_status.return_value={'status':'pending'}
            payload={'link':'https://shopee.co.th/item/1','request_id':'PSP-regression-426',
                     'cast_id':person['id'],'outfit_mode':'saved','handoff_mode':'queue',
                     'provider':'gemini','scene_count':8,'video_generation_mode':'meta_ai',
                     'audio_choices':{'mode':'none'},'flow_settings':{'model':'saved-model'},
                     'intro_options':{'enabled':True},'subtitle_enabled':False}
            prepared=prepare_link(products,cast,bridge,payload)
            for key in ('outfit_mode','handoff_mode','audio_choices','flow_settings','intro_options','subtitle_enabled'):
                self.assertEqual(prepared['prepare_options'][key],payload[key])
            ident=prepared['product_id'];folder=products.root/ident
            (folder/'original').mkdir(exist_ok=True)
            Image.new('RGB',(256,456),'red').save(folder/'original/product.jpg')
            products._manifest_store(folder/'job.json').update(lambda r:{**r,'product_name':'เสื้อ','source_images':['original/product.jpg']})
            products=ProductManager(root)  # actual disk reload; no UI settings
            first=prepare_link(products,cast,bridge,{'product_id':ident})
            snap=first['creative_context']['snapshot_id'];saved=cast.validate_snapshot(snap,ident)
            self.assertEqual(saved['outfit_mode'],'saved');self.assertEqual(saved['reference_roles'],['product','person','outfit'])
            cast.clear_outfit(person['id']);cast.edit(person['id'],hidden=True)
            (folder/'original/product.jpg').unlink()
            second=prepare_link(products,cast,bridge,{'product_id':ident,'outfit_mode':'auto'})
            self.assertEqual(second['creative_context'],first['creative_context'])
            self.assertEqual(len(list((cast.root/'snapshots').iterdir())),1)
            self.assertEqual(second['prepare_options']['handoff_mode'],'queue')

    def test_missing_and_corrupt_cast_dont_hide_good_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            cast=ProductCast(temp)
            good=cast.add('good',picture());bad=cast.add('bad',picture())
            (cast.root/bad['id']/'preview.jpg').unlink()
            rows={r['id']:r for r in cast.state()}
            self.assertTrue(rows[good['id']]['available']);self.assertFalse(rows[bad['id']]['available'])
            (cast.root/good['id']/'reference.jpg').write_bytes(b'corrupt')
            self.assertFalse(next(r for r in cast.state() if r['id']==good['id'])['available'])


class Identity426(unittest.TestCase):
    def test_generation_reminder_ui_without_provider_requests(self):
        result=subprocess.run(['node','tests/generation_notice_426.cjs'],cwd=Path(__file__).resolve().parents[1],
                              text=True,capture_output=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_discovery_rejects_name_spoof_accepts_identical_copy_and_own_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();copy=root/'copy';copy.mkdir()
            source.joinpath('manifest.json').write_text('{"name":"SmartFlow AI"}')
            source.joinpath('background.js').write_text('trusted source')
            for p in source.iterdir(): (copy/p.name).write_bytes(p.read_bytes())
            profile=root/'chrome/Default';profile.mkdir(parents=True)
            entries={'a'*32:{'path':str(source)},'b'*32:{'path':str(copy)}}
            (profile/'Preferences').write_text(json.dumps({'extensions':{'settings':entries}}))
            identities=ExtensionIdentity(root,source,root/'chrome')
            self.assertEqual(identities.discover(),{'a'*32,'b'*32})
            (copy/'background.js').write_text('spoofed')
            self.assertEqual(identities.discover(),{'a'*32})

    def test_previous_local_release_can_report_version_but_random_folder_is_not_trusted(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'browser_extension';source.mkdir()
            (source/'manifest.json').write_text('{"version":"0.15.426"}')
            old=root/'deliverables/SmartFlow_AI_Extension_0.15.425';old.mkdir(parents=True)
            (old/'manifest.json').write_text('{"name":"SmartFlow AI","version":"0.15.425"}')
            profile=root/'chrome/Default';profile.mkdir(parents=True)
            (profile/'Preferences').write_text(json.dumps({'extensions':{'settings':{'a'*32:{'path':str(old)}}}}))
            self.assertEqual(ExtensionIdentity(root,source,root/'chrome').discover(),{'a'*32})

    def test_foreign_extension_cannot_bootstrap_or_read_state_media_with_stolen_token(self):
        with tempfile.TemporaryDirectory() as temp:
            bridge=LocalBridge('127.0.0.1',0,ProductManager(temp),logging.getLogger('security426'),
                               desktop_state=lambda:{'private':'fixture'}).start()
            origin=pair_fixture(bridge,profile='fixture-profile')
            base=f'http://127.0.0.1:{bridge.server.server_address[1]}'
            try:
                def request(path,origin,profile='fixture-profile',body=None):
                    return urllib.request.Request(base+path,data=json.dumps(body).encode() if body else None,
                        headers={'Origin':origin,'X-SmartFlow-Profile':profile,'X-SmartFlow-Token':bridge._extension_token,
                                 'Content-Type':'application/json'})
                for path in ('/api/desktop/state','/api/desktop/media?job_id=fixture','/api/stories/fixture/files/image.png'):
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(request(path,'chrome-extension://'+'b'*32))
                    self.assertEqual(caught.exception.code,403)
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(request('/api/extension/heartbeat','chrome-extension://'+'b'*32,
                        body={'client_id':'b'*32,'version':bridge.REQUIRED_EXTENSION_VERSION}))
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(request('/api/desktop/state',origin,profile='wrong-profile'))
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(urllib.request.Request(base+'/api/desktop/state',headers={'Sec-Fetch-Site':'none'}))
                native_get={'Sec-Fetch-Site':'none','X-SmartFlow-Token':bridge._extension_token,
                            'X-SmartFlow-Profile':'fixture-profile'}
                with urllib.request.urlopen(urllib.request.Request(base+'/api/desktop/state',headers=native_get)) as response:
                    self.assertEqual(response.status,200)
                with urllib.request.urlopen(urllib.request.Request(base+'/api/desktop/state',headers={**native_get,'Sec-Fetch-Site':'cross-site'})) as response:
                    self.assertEqual(response.status,200)  # Authenticated native download headers.
                for changes in ({'X-SmartFlow-Profile':'wrong'},{'X-SmartFlow-Token':'wrong'},{'Sec-Fetch-Site':'cross-site','X-SmartFlow-Token':''}):
                    with self.assertRaises(urllib.error.HTTPError):
                        urllib.request.urlopen(urllib.request.Request(base+'/api/desktop/state',headers={**native_get,**changes}))
                with urllib.request.urlopen(request('/api/desktop/state',origin)) as response:
                    self.assertEqual(response.status,200)
            finally: bridge.stop()

    def test_native_extension_originless_get_uses_bootstrap_capability(self):
        with tempfile.TemporaryDirectory() as temp:
            bridge=LocalBridge('127.0.0.1',0,ProductManager(temp),logging.getLogger('native426'),
                               desktop_state=lambda:{'private':'fixture'}).start()
            # Isolated fixture admits its synthetic identity; production discovery
            # is tested separately and never overridden outside this test object.
            bridge._extension_identity.allowed=lambda origin: origin.startswith('chrome-extension://')
            try:
                env={**os.environ,'SMARTFLOW_TEST_BRIDGE_URL':f'http://127.0.0.1:{bridge.server.server_address[1]}',
                     'SMARTFLOW_TEST_BRIDGE_VERSION':bridge.REQUIRED_EXTENSION_VERSION}
                result=subprocess.run(['node','tests/bridge_origin_426.cjs'],env=env,
                    cwd=Path(__file__).resolve().parents[1],text=True,capture_output=True,encoding='utf-8',timeout=30)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            finally: bridge.stop()


class MetaRedesign426(unittest.TestCase):
    setUp=meta_fixture.MetaVideoTests.setUp
    advance=meta_fixture.MetaVideoTests.advance

    def test_actual_extension_helper_owner_media_transport_and_successor(self):
        result=subprocess.run(['node','tests/meta_redesign_426.cjs'],cwd=Path(__file__).resolve().parents[1],
                              text=True,capture_output=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def failure(self,**changes):
        body=self.advance('generating')
        proof=dict(matched_request=True,answer_complete=True,answer_truncated=False,stop=False,busy=False,
                   video_count=0,samples=2,stable_ms=6000,answer_text='The starting image cannot animate into a video.')
        proof.update(changes)
        return {**body,'stage':'redesign_prepare','retry_evidence':proof}

    def test_redesign_new_context_new_video_chat_and_idempotent_complete(self):
        body=self.failure();old=self.manager.get(self.job_id,1)
        repair=self.manager.event(body);self.assertEqual(repair['stage'],'redesigning')
        self.assertEqual(self.manager.event(body)['redesign']['id'],repair['redesign']['id'])
        event={**body,'redesign_id':repair['redesign']['id'],'action':'claim'}
        self.assertTrue(self.manager.redesign_event(event)['send_authorized'])
        self.assertFalse(self.manager.redesign_event(event)['send_authorized'])
        image={**event,'action':'save_image','image':picture('orange')}
        saved=self.manager.redesign_event(image)
        self.assertEqual(saved['redesign']['phase'],'image_saved')
        done={**event,'action':'save_prompt',
              'proposal':{'needs_review':False,
                          'video_prompt':'Move slowly toward the table; keep the clothes and room.'}}
        new=self.manager.redesign_event(done)
        self.assertEqual(new['stage'],'prepared');self.assertNotEqual(new['context_id'],old['context_id'])
        self.assertNotEqual(new['request_id'],old['request_id']);self.assertNotIn('conversation_url',new)
        self.assertEqual(self.manager.redesign_event(done),new)
        self.assertEqual(self.manager.begin(self.job_id,1)['request_id'],new['request_id'])
        self.assertEqual(self.manager._store(self.job_id).read({})['attempt_history']['1'][0]['conversation_url'],old['conversation_url'])

    def test_busy_unknown_policy_quota_never_authorize_redesign(self):
        original=self.failure()
        for change in ({'busy':True},{'stop':True},{'matched_request':False},{'video_count':1},
                       {'answer_complete':False},{'answer_text':'Content violates policy'},
                       {'answer_text':'Quota limit reached'}):
            with self.subTest(change=change):
                body={**original,'retry_evidence':{**original['retry_evidence'],**change}}
                with self.assertRaises(ValueError): self.manager.event(body)


if __name__=='__main__': unittest.main()
