import json
import tempfile
import threading
import subprocess
import shlex
from contextlib import nullcontext
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.shopee_posting.store import PostingStore, file_hash, product_url
from core.shopee_posting.device import ShopeeDevice, ReviewRequired
from core.shopee_posting.service import ShopeePosting
from core.shopee_posting.publish import publish_current, P
from core.shopee_posting.media import transfer
from core.shopee_posting.workflow import add_product, choose_video, run as run_workflow, S, product_link_target, wait_product_link, retry_product_navigation, ProductPickerNotReady
from core.shopee_posting.options import DEFAULT_OPTIONS
from shopee_preflight_fixture import ready_device


class PostingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root/'workspace'/'products'/'JOB-1'/'videos'/'final.mp4'
        self.path.parent.mkdir(parents=True); self.path.write_bytes(b'fake media test only')
        self.detail = dict(item_id='product:JOB-1', title='เสื้อ Anata', video_path=str(self.path), cover_path='',
                           caption='เสื้อขาว #AI', product_url='https://s.shopee.co.th/example')
        self.store = PostingStore(self.root)
        self.id = self.store.add([self.detail])[0]

    def row(self):
        return self.store.read()['items'][0]

    def ready(self):
        self.store.transition(self.id, {'draft'}, 'ready', video_sha256=file_hash(self.path), **self.proof())

    def proof(self):
        return dict(run_contract={'account':'testuser','device_id':'testphone','post_options':dict(DEFAULT_OPTIONS),'video_sha256':file_hash(self.path)},
                    observed_options={'options':dict(DEFAULT_OPTIONS)}, latest_baseline={'account':'testuser','latest_caption':'previous post'})

    def claim(self):
        return self.store.claim_publish(self.id, account='testuser', device_id='testphone', video_sha256=file_hash(self.path))

    def test_add_is_idempotent(self):
        self.assertEqual(self.store.add([self.detail]), [self.id]); self.assertEqual(len(self.store.read()['items']),1)

    def test_stale_edit_rejected(self):
        self.store.edit(self.id,0,caption='ใหม่')
        with self.assertRaises(ValueError): self.store.edit(self.id,0,caption='เก่า')

    def test_caption_limit_and_unicode(self):
        for value in ['', 'ก'*151, '😀'*76]:
            with self.subTest(value=value), self.assertRaises(ValueError): self.store.edit(self.id,0,caption=value)
        self.store.edit(self.id,0,caption='ทดสอบภาษาไทย 😀')
        self.assertEqual(self.row()['caption'],'ทดสอบภาษาไทย 😀')

    def test_intent_before_send_and_not_twice(self):
        self.ready(); self.claim()
        self.assertEqual(self.row()['phase'],'send_pending')
        self.assertTrue(self.row()['publish_intent']['caption_sha256'])
        with self.assertRaises(ValueError): self.claim()
        with self.assertRaises(ValueError): self.store.edit(self.id,self.row()['revision'],removed=True)

    def test_recover_never_retries_sent(self):
        self.ready(); self.claim(); self.store.recover()
        self.assertEqual(self.row()['phase'],'unknown')
        with self.assertRaises(ValueError): self.claim()

    def test_recover_unsent_keeps_assets(self):
        self.store.transition(self.id,{'draft'},'transferring');self.store.recover()
        self.assertEqual(self.row()['phase'],'review');self.assertTrue(self.path.exists())

    def test_duplicate_hash_across_jobs(self):
        self.ready();self.claim()
        other=self.store.add([{**self.detail,'item_id':'story:STORY-2'}])[0]
        self.store.transition(other,{'draft'},'ready',video_sha256=file_hash(self.path),**self.proof())
        with self.assertRaises(ValueError):self.store.claim_publish(other,account='testuser',device_id='testphone',video_sha256=file_hash(self.path))

    def test_concurrent_claim_one_wins(self):
        self.ready();wins=[]
        def run():
            try:self.claim();wins.append(True)
            except ValueError:pass
        threads=[threading.Thread(target=run) for _ in range(5)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(len(wins),1)

    def test_removed_draft_does_not_delete_media(self):
        self.store.edit(self.id,0,removed=True);self.assertTrue(self.path.exists());self.assertEqual(self.row()['phase'],'removed')

    def test_urls(self):
        self.assertEqual(product_url(self.detail['product_url']),self.detail['product_url'])
        for bad in ['http://s.shopee.co.th/a','https://shopee.co.th.evil.test/a','https://evil@shopee.co.th/a','https://shopee.co.th/','https://shopee.co.th:44/a','file:///x']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):product_url(bad)

    def test_service_only_product_final(self):
        library=Mock()
        library.item_detail.return_value=dict(item_id='product:JOB-1',path=str(self.path),title='สินค้า',content_kind='story',kind='story',affiliate_link=self.detail['product_url'])
        service=ShopeePosting(self.root,library,Mock(),validator=Mock())
        with self.assertRaises(ValueError):service.detail('product:JOB-1')
        library.item_detail.return_value['content_kind']='product'
        self.assertEqual(service.detail('product:JOB-1')['caption'],'สินค้า')

    def test_explicit_confirmation_required(self):
        service=ShopeePosting(self.root,Mock(),Mock(),validator=Mock())
        with self.assertRaises(ValueError):service.action('shopee_post_start',{'ids':[self.id]})

    def test_transfer_then_restart_enters_workflow_without_account_tour(self):
        wifi=Mock();wifi.state.return_value={'selected':{'device_id':'testphone','model':'test'}}
        wifi.verified_device.side_effect=lambda:nullcontext(Mock())
        service=ShopeePosting(self.root,Mock(),wifi,validator=Mock())
        service.validator.validate.return_value={'duration':10}
        service.detail=Mock(return_value=self.detail)
        service.store.change(lambda state:state.update(account={'name':'testuser','device_id':'testphone'}))
        with patch('core.shopee_posting.service.threading.Thread'):
            service.action('shopee_post_start',{'ids':[self.id],'confirm':True,'revision':service.store.read()['revision']})
        run_id=service.store.read()['posting_run']['id']
        with patch('core.shopee_posting.service.ShopeeDevice'),patch('core.shopee_posting.service.restart_before_first_post') as restart,patch('core.shopee_posting.service.account_on_home') as duplicate,patch('core.shopee_posting.service.prepare_queue_account') as once,patch('core.shopee_posting.service.transfer',return_value={'album':'test'}) as moved,patch('core.shopee_posting.service.run') as workflow:
            service._post([self.id],'testuser',run_id)
        duplicate.assert_not_called();once.assert_not_called();moved.assert_called_once();workflow.assert_called_once()
        restart.assert_called_once()
        self.assertFalse(service.state()['busy'])

    def test_failed_post_transport_is_unknown(self):
        self.store.transition(self.id,{'draft'},'prepared',video_sha256=file_hash(self.path),transfer={'album':'test'},**self.proof())
        device=ready_device(caption=self.row()['caption'],identity='testphone')
        def tap(*args,**kwargs):
            self.assertEqual(self.row()['phase'],'send_pending')
            self.assertTrue(self.row().get('publish_intent'))
            raise OSError('Disconnected after tap')
        device.adb.shell.side_effect=tap
        with self.assertRaises(OSError):publish_current(device,self.store,self.id,'testuser','Product',self.root/'evidence')
        self.assertEqual(self.row()['phase'],'unknown');self.assertEqual(device.adb.shell.call_count,1)

    def test_send_guard_missing_product(self):
        self.store.transition(self.id,{'draft'},'prepared',video_sha256=file_hash(self.path),transfer={'album':'test'})
        device=ready_device(caption=self.row()['caption']);device.fixture_nodes=[n for n in device.fixture_nodes if n['resource-id'] != P+'tv_product_title']
        with self.assertRaises(ReviewRequired):publish_current(device,self.store,self.id,'testuser','Product',self.root/'evidence')
        device.tap.assert_not_called();self.assertNotIn('publish_intent',self.row())

    def test_workflow_skips_cover_picker(self):
        self.store.transition(self.id, {'draft'}, 'prepared', transfer={'album':'test'})
        device = Mock(); device.snapshot.return_value=('',[])
        with patch('core.shopee_posting.workflow.account_on_home', return_value='testuser'), \
             patch('core.shopee_posting.workflow.choose_video'), \
             patch('core.shopee_posting.workflow.add_product', return_value='Product'), \
             patch('core.shopee_posting.workflow.latest_baseline', return_value={'account':'testuser','latest_caption':'old'}), \
             patch('core.shopee_posting.workflow.apply_options', return_value={'options':dict(DEFAULT_OPTIONS)}), \
             patch('core.shopee_posting.workflow.publish_current'), \
             patch('core.shopee_posting.workflow.verify_result'):
            run_workflow(device, self.store, self.id, 'testuser', self.root/'proof')
        actions = repr(device.mock_calls)
        self.assertNotIn('tv_select_cover', actions)
        self.assertNotIn('thumbnail_frame_rv', actions)
        self.assertNotIn('save_btn', actions)


class TransferTests(unittest.TestCase):
    def test_video_only_thai_album_and_resume_without_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            video, cover = Path(tmp)/'original.mp4', Path(tmp)/'original.png'
            video.write_bytes(b'video fixture'); cover.write_bytes(b'cover fixture')
            row = dict(id='a'*32, title='เสื้อ Anata / สีขาว', video_path=str(video),
                       cover_path=str(cover), video_sha256=file_hash(video))
            adb, remote_files = Mock(), {}
            def run(*args, **kwargs):
                self.assertEqual(args[0], 'push')
                remote_files[args[2]] = Path(args[1]).read_bytes()
                return SimpleNamespace(returncode=0, stdout='')
            def shell(*args):
                if args[0] == 'sha256sum':
                    path = shlex.split(args[1])[0]
                    if path not in remote_files:
                        return SimpleNamespace(returncode=1, stdout='')
                    import hashlib
                    return SimpleNamespace(returncode=0, stdout=hashlib.sha256(remote_files[path]).hexdigest()+'  '+path)
                if args[0] == 'content':
                    where = shlex.split(args[-1])[0]
                    canonical = where[len("_data='"):-1]
                    path = canonical.replace('/storage/emulated/0/', '/sdcard/', 1)
                    return SimpleNamespace(returncode=0, stdout=f'_size={len(remote_files[path])}, _data={canonical}')
                return SimpleNamespace(returncode=0, stdout='')
            adb.run.side_effect, adb.shell.side_effect = run, shell
            receipt = transfer(adb, row)
            self.assertEqual(receipt['album'], 'SF_เสื้อ_Anata_สีขาว_aaaaaaaa')
            self.assertEqual(set(receipt['files']), {'video'})
            for kind, suffix in [('video','.mp4')]:
                self.assertEqual(receipt['files'][kind]['path'], '/sdcard/Movies/'+receipt['album']+'/'+receipt['album']+'_'+kind+suffix)
            self.assertEqual(adb.run.call_count, 1)
            row.update(transfer=receipt, title='Changed title must not move previous files')
            self.assertEqual(transfer(adb, row), receipt)
            self.assertEqual(adb.run.call_count, 1)
            self.assertEqual(video.read_bytes(), b'video fixture')
            self.assertEqual(cover.read_bytes(), b'cover fixture')

    def test_unsafe_album_is_rejected_before_device_write(self):
        adb = Mock()
        with self.assertRaises(ValueError):
            transfer(adb, {'id':'a'*32, 'transfer':{'album':'../DCIM'}})
        adb.shell.assert_not_called(); adb.run.assert_not_called()


class DeviceTests(unittest.TestCase):
    def picker(self):
        def node(**kw):return dict(package='com.shopee.th', enabled='true', **kw)
        return [node(text='เพิ่มสินค้า', **{'class':'android.widget.TextView','bounds':'[100,100][900,160]'}),
                node(**{'class':'android.widget.ImageView','content-desc':'click to get back','bounds':'[40,100][100,160]'}),
                node(text='ค้นหาสินค้า', **{'class':'android.widget.EditText','bounds':'[100,200][950,260]'}),
                node(**{'class':'android.widget.ImageView','bounds':'[900,100][960,160]'})]

    def test_product_picker_does_not_accept_composer_label(self):
        nodes=self.picker()+[{'package':'com.shopee.th','enabled':'true','resource-id':P+'et_caption'}]
        self.assertIsNone(product_link_target(nodes,'com.shopee.th'))
        self.assertIsNone(product_link_target(self.picker()[::2],'com.shopee.th'))

    def test_product_picker_waits_for_navigation_and_stable_icon(self):
        d=Mock(package='com.shopee.th')
        d.snapshot.side_effect=[('',[]),('',self.picker()),('',self.picker())]
        with patch('core.shopee_posting.workflow.time.sleep'):
            self.assertEqual(wait_product_link(d)['bounds'],'[900,100][960,160]')
        self.assertEqual(d.snapshot.call_count,3);d.tap.assert_not_called()

    def test_product_picker_ambiguity_and_timeout_never_click(self):
        nodes=self.picker();nodes.append(dict(nodes[-1]))
        self.assertIsNone(product_link_target(nodes,'com.shopee.th'))
        d=Mock(package='com.shopee.th');d.snapshot.return_value=('',nodes)
        with patch('core.shopee_posting.workflow.time.monotonic',side_effect=[0,1,21]),patch('core.shopee_posting.workflow.time.sleep'),self.assertRaises(ReviewRequired):wait_product_link(d)
        d.tap.assert_not_called()

    def composer(self, caption='owned'):
        return [dict(package='com.shopee.th',enabled='true',bounds='[0,0][100,100]',**{'resource-id':P+name,'text':text})
                for name,text in [('et_caption',caption),('ll_add_product_symbol',''),('btn_post','โพสต์')]]

    def test_ignored_navigation_retries_once_only_after_three_owned_reads(self):
        d=Mock(package='com.shopee.th');d.snapshot.side_effect=[('',self.composer())]*3+[('',self.picker())]*2
        with patch('core.shopee_posting.workflow.time.sleep'):
            self.assertEqual(retry_product_navigation(d,'owned')['bounds'],'[900,100][960,160]')
        d.tap.assert_called_once_with(**{'resource-id':P+'ll_add_product_symbol'})

    def test_picker_appearing_late_is_not_clicked_again(self):
        d=Mock(package='com.shopee.th');d.snapshot.return_value=('',self.picker())
        with patch('core.shopee_posting.workflow.time.sleep'):retry_product_navigation(d,'owned')
        d.tap.assert_not_called()

    def test_changed_caption_or_existing_product_never_retries_navigation(self):
        for nodes in [self.composer('changed'),self.composer()+[{'resource-id':P+'tv_product_title'}],
                      self.composer()+[{'resource-id':'android:id/input_method_nav_back'}]]:
            d=Mock(package='com.shopee.th');d.snapshot.return_value=('',nodes)
            with self.assertRaises(ProductPickerNotReady):retry_product_navigation(d,'owned')
            d.tap.assert_not_called()

    def test_second_ignored_navigation_cannot_loop(self):
        d=Mock(package='com.shopee.th');d.find.return_value={'text':'owned'};d.snapshot.return_value=('',self.composer())
        with patch('core.shopee_posting.workflow.wait_product_link',side_effect=ProductPickerNotReady('not open')),patch('core.shopee_posting.workflow.time.sleep'),self.assertRaises(ProductPickerNotReady):
            add_product(d,'https://s.shopee.co.th/test')
        self.assertEqual(d.tap.call_count,2)
        self.assertTrue(all(c.kwargs=={'resource-id':P+'ll_add_product_symbol'} for c in d.tap.call_args_list))

    def test_nested_import_card_title(self):
        d=Mock(package='com.shopee.th')
        d.wait.return_value={'bounds':'[100,100][900,160]'}
        d.find.return_value={'text':'owned caption'}
        d.snapshot.side_effect=[('',self.picker()),('',self.picker())]
        imported={'state':'product','product':'เสื้อ Anata'}
        with patch('core.shopee_posting.workflow.import_product',return_value=imported) as read, \
             patch('core.shopee_posting.workflow.attach_imported',return_value='เสื้อ Anata') as attach:
            self.assertEqual(add_product(d,'https://s.shopee.co.th/test'),'เสื้อ Anata')
        read.assert_called_once_with(d,'https://s.shopee.co.th/test',None)
        attach.assert_called_once_with(d,imported,'owned caption',None)

    def test_select_duration_tile_not_cover(self):
        d=Mock();d.wait.return_value={'text':'SF_Test'}
        xml=f'<hierarchy><node><node resource-id="{S}ll_check" bounds="[0,0][20,20]"/></node><node><node resource-id="{S}ll_check" bounds="[50,0][70,20]"/><node resource-id="{S}tv_duration" text="01:20"/></node></hierarchy>'
        d.snapshot.return_value=(xml,[])
        choose_video(d,{'transfer':{'album':'SF_Test', 'files':{'cover':{'path':'old-cover.png'}}},'media':{'duration':80},'cover_path':'cover.jpg'})
        self.assertEqual(d.tap.call_args_list[1].kwargs['bounds'],'[50,0][70,20]')

    def test_new_video_only_album_ignores_desktop_cover_path(self):
        d=Mock();d.wait.return_value={'text':'SF_Test'}
        xml=f'<hierarchy><node><node resource-id="{S}ll_check" bounds="[50,0][70,20]"/><node resource-id="{S}tv_duration" text="01:20"/></node></hierarchy>'
        d.snapshot.return_value=(xml,[])
        choose_video(d,{'transfer':{'album':'SF_Test','files':{'video':{}}},'media':{'duration':80},'cover_path':'must-not-upload.png'})
        self.assertEqual(d.tap.call_args_list[1].kwargs['bounds'],'[50,0][70,20]')

    def test_foreign_album_rejected(self):
        d=Mock();d.wait.return_value={'text':'Camera'}
        with self.assertRaises(ReviewRequired):choose_video(d,{'transfer':{'album':'SF_Test'}})

    def test_actual_browser_ui(self):
        result=subprocess.run(['node',str(Path(__file__).with_name('shopee_posting_ui.cjs'))],capture_output=True,text=True,encoding='utf-8',timeout=80)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def device(self):
        d=ShopeeDevice.__new__(ShopeeDevice);d.adb=Mock();d.identity='phone';d.adb.prop.return_value='phone';d.stop=None;d.ui=Mock()
        d.ui.info={'currentPackageName':'com.shopee.th','screenOn':True,'displayWidth':1080,'displayHeight':2340}
        return d

    def test_foreground_not_stale_app_current(self):
        d=self.device();d.ui.app_current.return_value={'package':'com.lazada.android'}
        self.assertEqual(d.foreground()['currentPackageName'],'com.shopee.th');d.ui.app_current.assert_not_called()

    def test_wrong_phone(self):
        d=self.device();d.adb.prop.return_value='other'
        with self.assertRaises(ReviewRequired):d.verify()

    def test_locked_phone(self):
        d=self.device();d.ui.info['screenOn']=False
        with self.assertRaises(ReviewRequired):d.foreground()

    def test_missing_or_multiple_targets(self):
        d=self.device();d.snapshot=Mock(return_value=('',[]))
        with self.assertRaises(ReviewRequired):d.tap(text='next')
        n={'text':'next','enabled':'true','package':'com.shopee.th','bounds':'[0,0][20,20]'}
        d.snapshot.return_value=('',[n,n])
        with self.assertRaises(ReviewRequired):d.tap(text='next')
        d.ui.click.assert_not_called()

    def test_placeholder_requeries_new_text(self):
        d=self.device();d.find=Mock(side_effect=[{'class':'android.widget.EditText','text':'placeholder'}, {'text':'ภาษาไทย'}])
        d.set_text('ภาษาไทย',text='placeholder')
        self.assertEqual(d.find.call_args.kwargs,{'class':'android.widget.EditText','text':'ภาษาไทย'})
        d.ui.return_value.get_text.assert_not_called()

    def test_reject_changed_bounds(self):
        d=self.device();d.find=Mock(side_effect=[{'bounds':'[0,0][20,20]'},{'bounds':'[0,10][20,30]'}])
        with patch('core.shopee_posting.device.time.monotonic',side_effect=[0,1,2,21]), patch('core.shopee_posting.device.time.sleep'), self.assertRaises(ReviewRequired):d.tap(text='next')
        d.ui.click.assert_not_called()

    def test_one_adb_gesture_no_rpc_retry(self):
        d=self.device();d.find=Mock(return_value={'bounds':'[0,0][20,20]'})
        d.adb.shell.return_value=SimpleNamespace(returncode=1)
        with self.assertRaises(ReviewRequired):d.tap(text='โพสต์')
        self.assertEqual(d.adb.shell.call_count,1);d.ui.click.assert_not_called()

    def test_visual_switch(self):
        from PIL import Image, ImageDraw
        d=self.device();d.find=Mock(return_value={'bounds':'[0,0][100,56]'})
        for expected in [True,False]:
            shot=Image.new('RGB',(100,56),'white');draw=ImageDraw.Draw(shot)
            draw.rounded_rectangle((0,0,99,55),radius=27,fill=(0,200,30) if expected else (220,220,220))
            x=51 if expected else 5;draw.ellipse((x,5,x+44,49),fill='white')
            d.ui.screenshot.return_value=shot
            self.assertEqual(d.visual_green(P+'ai_generated_toggle'),expected)
        d.ui.screenshot.return_value=Image.new('RGB',(100,56),(255,0,0))
        with self.assertRaises(ReviewRequired):d.visual_green(P+'ai_generated_toggle')


if __name__=='__main__':unittest.main()
