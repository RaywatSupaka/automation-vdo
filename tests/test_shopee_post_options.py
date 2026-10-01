import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw
from core.shopee_posting.options import DEFAULT_OPTIONS, validate_options
from core.shopee_posting.store import PostingStore, file_hash
from core.shopee_posting.settings import apply_options, ensure_toggle, verify_options, P
from core.shopee_posting.device import ShopeeDevice, ReviewRequired
from core.shopee_posting.publish import publish_current
from core.shopee_posting.workflow import latest_baseline, verify_result, return_to_feed
from core.shopee_posting.service import ShopeePosting
from shopee_preflight_fixture import ready_device


class OptionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.store = PostingStore(self.root)
        self.video = self.root/'final.mp4'; self.video.write_bytes(b'fixture')
        self.ids = self.store.add([dict(item_id=str(i), title='Product', caption='new caption '+str(i),
                          product_url='https://s.shopee.co.th/test', video_path=str(self.video)) for i in range(2)])

    def row(self, index=0):
        return self.store.read()['items'][index]

    def prepared(self):
        opts = dict(DEFAULT_OPTIONS)
        self.store.transition(self.ids[0], {'draft'}, 'prepared', video_sha256=file_hash(self.video), transfer={'album':'test'},
            run_contract={'account':'test','device_id':'phone','post_options':opts,'video_sha256':file_hash(self.video)},
            latest_baseline={'account':'test','latest_caption':'old caption'})
        return ready_device()

    def test_strict_options_schema(self):
        for bad in (None, {}, {'schema':True,'allow_reuse':False,'ai_label':True},
                    {**DEFAULT_OPTIONS,'ai_label':'false'}, {**DEFAULT_OPTIONS,'allow_reuse':0},
                    {**DEFAULT_OPTIONS,'extra':True}, {**DEFAULT_OPTIONS,'schema':2}):
            with self.subTest(value=bad), self.assertRaises(ValueError):validate_options(bad)

    def test_defaults_only_affect_new_rows_and_persist(self):
        new={'schema':1,'allow_reuse':True,'ai_label':False}
        self.store.save_options(self.store.read()['revision'],new)
        self.store.add([dict(self.row(),item_id='third')])
        state=PostingStore(self.root).read()
        self.assertEqual(state['items'][0]['post_options'],DEFAULT_OPTIONS)
        self.assertEqual(state['items'][2]['post_options'],new)
        self.assertEqual(state['defaults'],new)

    def test_selected_only_and_stale_revision(self):
        rev=self.store.read()['revision']; opts={**DEFAULT_OPTIONS,'allow_reuse':True}
        self.store.save_options(rev,opts,[self.ids[0]])
        self.assertEqual(self.row()['post_options'],opts)
        self.assertEqual(self.row(1)['post_options'],DEFAULT_OPTIONS)
        with self.assertRaises(ValueError):self.store.save_options(rev,DEFAULT_OPTIONS)

    def test_bulk_is_atomic_if_one_started(self):
        self.store.transition(self.ids[1],{'draft'},'queued')
        before=self.store.read()
        with self.assertRaises(ValueError):self.store.save_options(before['revision'],{**DEFAULT_OPTIONS,'ai_label':False},self.ids)
        self.assertEqual(self.store.read(),before)

    def test_history_not_backfilled_and_unsent_display_safe(self):
        def legacy(s):
            for r in s['items']:r.pop('post_options')
            s['items'][1]['phase']='published'
        self.store.change(legacy)
        service=ShopeePosting(self.root,Mock(),Mock(),validator=Mock())
        state=service.state()
        self.assertEqual(state['items'][0]['post_options'],DEFAULT_OPTIONS)
        self.assertNotIn('post_options',state['items'][1])
        self.assertNotIn('post_options',self.row())

    def test_any_intent_makes_review_uneditable(self):
        self.store.transition(self.ids[0],{'draft'},'review',publish_intent={'id':'old'})
        with self.assertRaises(ValueError):self.store.edit(self.ids[0],self.row()['revision'],post_options=DEFAULT_OPTIONS)

    def test_settings_restart_keeps_options_and_no_intent(self):
        self.store.transition(self.ids[0],{'draft'},'settings',post_options={**DEFAULT_OPTIONS,'allow_reuse':True})
        self.store.recover()
        self.assertEqual(self.row()['phase'],'review');self.assertTrue(self.row()['post_options']['allow_reuse'])
        self.assertNotIn('publish_intent',self.row())

    def test_busy_service_rejects_settings(self):
        service=ShopeePosting(self.root,Mock(),Mock(),validator=Mock());service._busy=True
        for action in ('shopee_post_defaults','shopee_post_apply_options','shopee_post_edit'):
            with self.subTest(action=action),self.assertRaises(ValueError):service.action(action,{'post_options':DEFAULT_OPTIONS})

    def test_start_freezes_options_not_defaults(self):
        wifi=Mock();wifi.state.return_value={'selected':{'device_id':'phone'}}
        service=ShopeePosting(self.root,Mock(),wifi,validator=Mock())
        service.store.change(lambda s:s.update(account={'name':'test','device_id':'phone'}))
        with patch('core.shopee_posting.service.threading.Thread'):
            service.action('shopee_post_start',{'ids':[self.ids[0]],'confirm':True,'revision':self.store.read()['revision']})
        row=self.row();self.assertEqual(row['phase'],'queued');self.assertEqual(row['run_contract']['post_options'],{**DEFAULT_OPTIONS,'allow_missing_controls':True})
        with self.assertRaises(ValueError):self.store.edit(row['id'],row['revision'],post_options=DEFAULT_OPTIONS)

    def test_preflight_mismatch_no_post(self):
        d=self.prepared();d.fixture_values[P+'ai_generated_toggle']=False
        with self.assertRaises(ReviewRequired):publish_current(d,self.store,self.ids[0],'test','Product',self.root)
        d.tap.assert_not_called();self.assertNotIn('publish_intent',self.row())

    def test_stale_device_contract_no_post(self):
        d=self.prepared();d.identity='other'
        with self.assertRaises((ValueError,ReviewRequired)):publish_current(d,self.store,self.ids[0],'test','Product',self.root)
        d.tap.assert_not_called();self.assertNotIn('publish_intent',self.row())

    def test_same_caption_baseline_no_post(self):
        d=self.prepared();self.store.transition(self.ids[0],{'prepared'},'prepared',latest_baseline={'account':'test','latest_caption':self.row()['caption']})
        with self.assertRaises(ValueError):publish_current(d,self.store,self.ids[0],'test','Product',self.root)
        d.tap.assert_not_called()

    def test_intent_has_frozen_options_and_proof(self):
        d=self.prepared();publish_current(d,self.store,self.ids[0],'test','Product',self.root)
        intent=self.row()['publish_intent'];self.assertEqual(intent['post_options'],DEFAULT_OPTIONS)
        self.assertTrue(intent['observed_options']['sharing_off']);self.assertEqual(intent['latest_baseline']['latest_caption'],'old caption')
        self.store.recover();self.assertEqual(self.row()['phase'],'unknown')
        self.assertEqual(self.row()['publish_intent'],intent);self.assertEqual(d.adb.shell.call_count,1)

    def test_result_ai_off_does_not_wait_for_label(self):
        opts={**DEFAULT_OPTIONS,'ai_label':False}
        self.store.transition(self.ids[0],{'draft'},'processing',post_options=opts,
            publish_intent={'post_options':opts,'latest_baseline':{'account':'test','latest_caption':'previous'}})
        d=Mock();d.snapshot.return_value=('',[])
        with patch('core.shopee_posting.workflow.time.sleep'),patch('core.shopee_posting.workflow.return_to_feed'):
            verify_result(d,self.store,self.ids[0],'test','Product',self.root)
        self.assertEqual(self.row()['phase'],'published')
        self.assertFalse(any(c.kwargs.get('text')=='ครีเอเตอร์เพิ่มป้ายกำกับ AI' for c in d.wait.call_args_list))

    def test_result_ai_off_but_label_present_not_published(self):
        opts={**DEFAULT_OPTIONS,'ai_label':False}
        self.store.transition(self.ids[0],{'draft'},'processing',post_options=opts,
            publish_intent={'post_options':opts,'latest_baseline':{'account':'test','latest_caption':'previous'}})
        d=Mock();d.snapshot.return_value=('',[{'text':'ครีเอเตอร์เพิ่มป้ายกำกับ AI'}])
        with self.assertRaises(ReviewRequired):verify_result(d,self.store,self.ids[0],'test','Product',self.root)
        self.assertEqual(self.row()['phase'],'processing')


class SwitchTests(unittest.TestCase):
    def test_already_correct_zero_taps(self):
        d=ready_device()
        proof=apply_options(d,DEFAULT_OPTIONS);d.tap.assert_not_called();self.assertEqual(proof['options'],DEFAULT_OPTIONS)

    def test_lost_tap_ack_recheck_no_second_tap(self):
        d=Mock();d.visual_green.side_effect=[False,True];d.tap.side_effect=OSError('lost ACK')
        ensure_toggle(d,'ai_generated_toggle',True);d.tap.assert_called_once()

    def test_unknown_first_read_zero_taps(self):
        d=Mock();d.visual_green.side_effect=ReviewRequired('unclear')
        with self.assertRaises(ReviewRequired):ensure_toggle(d,'ai_generated_toggle',True)
        d.tap.assert_not_called()

    def test_failed_change_no_second_tap(self):
        d=Mock();d.visual_green.return_value=False
        with patch('core.shopee_posting.settings.time.monotonic',side_effect=[0,1,6]),patch('core.shopee_posting.settings.time.sleep'),self.assertRaises(ReviewRequired):ensure_toggle(d,'ai_generated_toggle',True)
        d.tap.assert_called_once()

    def test_occluded_unknown_not_off(self):
        for color in ('white','black','red',(220,220,220),(0,200,30)):
            with self.subTest(color=color):self.assertIsNone(ShopeeDevice.classify_control(Image.new('RGB',(100,56),color),'allow_reuse_toggle'))

    def test_realistic_switch_on_off_scaled(self):
        for size in ((100,56),(130,73),(200,112)):
            for desired in (True,False):
                im=Image.new('RGB',(100,56),'white');draw=ImageDraw.Draw(im)
                draw.rounded_rectangle((0,0,99,55),27,fill=(0,200,30) if desired else (220,220,220))
                x=51 if desired else 5;draw.ellipse((x,5,x+44,49),fill='white')
                self.assertIs(ShopeeDevice.classify_control(im.resize(size),'allow_reuse_toggle'),desired)

    def test_motion_settles_before_only_gesture(self):
        d=ShopeeDevice.__new__(ShopeeDevice);d.stop=None;d.ui=Mock();d.ui.info={'displayWidth':1080,'displayHeight':2340};d.adb=Mock();d.adb.shell.return_value.returncode=0
        d.find=Mock(side_effect=[{'bounds':b} for b in ['[0,0][20,20]','[0,10][20,30]','[0,10][20,30]','[0,10][20,30]']])
        with patch('core.shopee_posting.device.time.sleep'):d.tap(text='next')
        self.assertEqual(d.adb.shell.call_count,1)
        self.assertEqual(d.adb.shell.call_args.args,('input','touchscreen','swipe','10','20','10','20','100'))

    def test_negative_transition_bounds_wait_until_in_view(self):
        d=ShopeeDevice.__new__(ShopeeDevice);d.stop=None;d.ui=Mock();d.ui.info={'displayWidth':1080,'displayHeight':2340};d.adb=Mock();d.adb.shell.return_value.returncode=0
        d.find=Mock(side_effect=[{'bounds':b} for b in ['[-50,0][-30,20]','[0,0][0,0]','[0,10][20,30]','[0,10][20,30]','[0,10][20,30]']])
        with patch('core.shopee_posting.device.time.sleep'):d.tap(text='next')
        self.assertEqual(d.adb.shell.call_count,1)

    def test_close_panel_animation_must_finish_before_back(self):
        d=Mock();count=[0]
        def snapshot():
            count[0]+=1
            return ('',[{'content-desc':'video caption content'}]+([{'content-desc':'close the comment panels'}] if count[0]<3 else []))
        d.snapshot.side_effect=snapshot
        d.ui.press.side_effect=lambda key:self.assertGreaterEqual(count[0],5)
        with patch('core.shopee_posting.workflow.time.sleep'):return_to_feed(d,'test')
        d.ui.press.assert_called_once_with('back')

    def test_baseline_same_caption_rejected_without_create_or_post(self):
        d=Mock();d.snapshot.return_value=('',[{'text':'same  ซ่อน'}])
        with self.assertRaises(ReviewRequired):latest_baseline(d,'test','same',Path('.'))
        self.assertNotIn('btn_post',repr(d.mock_calls));self.assertNotIn('create icon',repr(d.mock_calls))
