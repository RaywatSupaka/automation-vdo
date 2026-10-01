import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.shopee_posting.device import ReviewRequired
from core.shopee_posting.options import DEFAULT_OPTIONS
from core.shopee_posting.progress import start_run, snapshot
from core.shopee_posting.result import upload_notice, await_upload, reconcile_saved_upload
from core.shopee_posting.service import ShopeePosting
from core.shopee_posting.store import PostingStore
from core.shopee_posting.workflow import verify_result


def notice(account='owner', package='com.shopee.th'):
    return f'''<hierarchy><node package="{package}" enabled="true" visible-to-user="true" class="android.view.ViewGroup" clickable="true" bounds="[1114,245][2126,408]">
    <node package="{package}" enabled="true" text="อัปโหลดสำเร็จ" />
    <node package="{package}" enabled="true" text="คลิกที่นี่เพื่อดูวิดีโอ" /></node>
    <node package="{package}" text="ชื่อผู้ใช้: {account}" /></hierarchy>'''


class UploadResultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.store = PostingStore(self.root)
        self.id = self.store.add([dict(item_id='a', title='A', caption='new clip', video_path='final.mp4',
                                      product_url='https://s.shopee.co.th/test')])[0]
        self.other = self.store.add([dict(item_id='b', title='B', caption='other')])[0]
        opts = dict(DEFAULT_OPTIONS)
        self.run_id = self.store.change(lambda s:start_run(s, [self.id], 'owner', 'phone'))
        self.store.transition(self.id, {'draft'}, 'ready', video_sha256='a'*64, upload_notice_absent=True,
                              run_contract=dict(account='owner', device_id='phone', video_sha256='a'*64, post_options=opts),
                              observed_options={'options':opts}, latest_baseline={'account':'owner','latest_caption':'old clip'})
        self.store.claim_publish(self.id, account='owner', device_id='phone', video_sha256='a'*64)
        self.store.transition(self.id, {'send_pending'}, 'processing')

    def row(self):
        return self.store.read()['items'][0]

    def saved(self, xml=None):
        folder=self.store.file.path.parent/'receipts'/self.id; folder.mkdir(parents=True,exist_ok=True)
        path=folder/'profile_after.xml'; path.write_text(xml or notice(),encoding='utf-8')
        stamp=time.time();os.utime(path,(stamp,stamp))
        self.store.transition(self.id, {'processing'}, 'unknown')
        self.store.settle_run([self.id],self.run_id,'old verifier failed')
        return path

    def test_native_sibling_banner_even_during_exit_animation(self):
        self.assertTrue(upload_notice(notice()))

    def test_not_success_from_feed_or_success_word_only(self):
        for xml in ('', '<hierarchy/>', notice().replace('คลิกที่นี่เพื่อดูวิดีโอ','กำลังอัปโหลด'),
                    notice(package='other.app'), notice().replace('enabled="true"','enabled="false"'),
                    notice().replace('visible-to-user="true"','visible-to-user="false"'),
                    notice().replace('</hierarchy>', '<node package="com.shopee.th" enabled="true" resource-id="x:id/et_caption" /></hierarchy>')):
            with self.subTest(xml=xml): self.assertFalse(upload_notice(xml))

    def test_preflight_can_detect_old_banner_in_composer(self):
        xml=notice().replace('</hierarchy>', '<node package="com.shopee.th" enabled="true" resource-id="x:id/et_caption" /></hierarchy>')
        self.assertTrue(upload_notice(xml,allow_composer=True))

    def test_success_finishes_without_profile_navigation_or_second_post(self):
        d=Mock(); d.snapshot.return_value=(notice(),[])
        verify_result(d,self.store,self.id,'owner','product',self.root)
        self.assertEqual(self.row()['phase'],'published');d.tap.assert_not_called();d.wait.assert_not_called()
        self.assertTrue(self.row()['receipt']['upload_confirmed'])
        self.assertNotIn('caption_verified',self.row()['receipt'])
        self.store.settle_run([self.id],self.run_id,'done')
        run=snapshot(self.store.read()['posting_run'])
        self.assertEqual((run['status'],run['completed'],run['current']['step']),('complete',1,'done'))

    def test_pending_then_success_uses_passive_observation_only(self):
        d=Mock(); d.snapshot.side_effect=[('<hierarchy/>',[]),(notice(),[])]
        with patch('core.shopee_posting.result.time.sleep'):
            self.assertTrue(await_upload(d,self.store,self.id))
        self.assertEqual(d.snapshot.call_count,2);d.tap.assert_not_called()

    def test_no_notice_cannot_mark_success_or_resend(self):
        d=Mock();d.snapshot.return_value=('<hierarchy/>',[])
        self.assertFalse(await_upload(d,self.store,self.id,timeout=0))
        self.assertEqual(self.row()['phase'],'processing');d.tap.assert_not_called()

    def test_legacy_intent_uses_original_result_verifier(self):
        self.store.change(lambda s:s['items'][0]['publish_intent'].pop('upload_notice_absent'))
        d=Mock();self.assertFalse(await_upload(d,self.store,self.id));d.snapshot.assert_not_called()

    def test_saved_success_repairs_owned_run_without_changing_other_rows(self):
        self.saved(); before=self.store.read()['items'][1]; intent=self.row()['publish_intent']
        reconcile_saved_upload(self.store,self.id,self.row()['revision'])
        self.assertEqual(self.row()['phase'],'published')
        self.assertEqual(self.row()['publish_intent'],intent)
        self.assertEqual(self.store.read()['items'][1],before)
        run=snapshot(self.store.read()['posting_run'])
        self.assertEqual((run['status'],run['completed'],run['uncertain_count']),('complete',1,0))
        with self.assertRaises(ReviewRequired):reconcile_saved_upload(self.store,self.id,self.row()['revision'])

    def test_old_or_wrong_account_capture_keeps_unknown(self):
        path=self.saved(notice(account='different'))
        with self.assertRaises(ReviewRequired):reconcile_saved_upload(self.store,self.id,self.row()['revision'])
        path.write_text(notice(),encoding='utf-8');os.utime(path,(1,1))
        with self.assertRaises(ReviewRequired):reconcile_saved_upload(self.store,self.id,self.row()['revision'])
        self.assertEqual(self.row()['phase'],'unknown')

    def test_missing_capture_and_stale_revision_do_not_change_state(self):
        self.saved();before=self.store.read()
        with self.assertRaises(ReviewRequired):reconcile_saved_upload(self.store,self.id,-1)
        self.assertEqual(self.store.read(),before)
        (self.store.file.path.parent/'receipts'/self.id/'profile_after.xml').unlink()
        with self.assertRaises(ReviewRequired):reconcile_saved_upload(self.store,self.id,self.row()['revision'])

    def test_mismatched_intent_or_caption_cannot_complete(self):
        with self.assertRaises(ValueError):self.store.confirm_uploaded(self.id,'wrong',time.time(),'test')
        intent=self.row()['publish_intent'];self.store.change(lambda s:s['items'][0].update(caption='changed'))
        with self.assertRaises(ValueError):self.store.confirm_uploaded(self.id,intent['id'],time.time(),'test')

    def test_reconcile_action_never_starts_phone_worker(self):
        self.saved();service=ShopeePosting(self.root,Mock(),Mock(),validator=Mock())
        with patch('core.shopee_posting.service.threading.Thread') as thread:
            service.action('shopee_post_reconcile',{'id':self.id,'revision':self.row()['revision']})
        thread.assert_not_called();service.wifi.verified_device.assert_not_called()
        self.assertEqual(self.row()['phase'],'published')

    def test_busy_reconcile_blocked(self):
        service=ShopeePosting(self.root,Mock(),Mock(),validator=Mock());service._busy=True
        with self.assertRaises(ValueError):service.action('shopee_post_reconcile',{'id':self.id,'revision':self.row()['revision']})
