"""Observed split Duet/Stitch layout; fixture phone I/O, never a real Post."""
import copy
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.shopee_posting.device import ReviewRequired
from core.shopee_posting.options import DEFAULT_OPTIONS, validate_options, proof_matches_options
from core.shopee_posting.settings import apply_options, read_options, observe_options, P
from core.shopee_posting.settings_layout import detect_layout, SPLIT, AI
from core.shopee_posting.publish import publish_current
from core.shopee_posting.progress import start_run
from core.shopee_posting.store import PostingStore, file_hash
from shopee_preflight_fixture import ready_device

ADAPTIVE = {**DEFAULT_OPTIONS, 'allow_missing_controls':True}


def alternate_device(*, ai=False, reuse=('allow_duet_toggle','allow_stitch_toggle')):
    d=ready_device(caption='caption')
    d.fixture_nodes=[n for n in d.fixture_nodes if n['resource-id'].rsplit('/',1)[-1] in {'et_caption','tv_product_title','btn_post'}]
    def node(resource, text='', bounds='[150,10][390,40]'):
        return dict(package=d.package,enabled='true',**{'resource-id':P+resource,'text':text,'bounds':bounds,'visible-to-user':'true'})
    for control,label,text in SPLIT:
        if control in reuse:d.fixture_nodes.append(node(label,text))
    if ai:d.fixture_nodes.append(node(AI[1],AI[2]))
    controls=list(reuse)+(['ai_generated_toggle'] if ai else [])+['iv_whatsapp','iv_facebook']
    d.fixture_resources=[P+c for c in controls]
    d.fixture_values={P+c:c not in ('iv_facebook',) for c in controls}
    for i,c in enumerate(controls):
        y=100+i*100;width=100 if c.endswith('_toggle') else 56
        d.fixture_nodes.append(node(c,bounds=f'[10,{y}][{10+width},{y+56}]'))
    def press(*args,**kwargs):
        x,y=int(args[3]),int(args[4])
        for n in d.fixture_nodes:
            resource=n['resource-id']
            if resource in d.fixture_values and d.center(n['bounds'])==(x,y):
                d.fixture_values[resource]=not d.fixture_values[resource]
        return Mock(returncode=0)
    d.adb.shell.side_effect=press
    return d


class LayoutTests(unittest.TestCase):
    def apply(self,d,options=ADAPTIVE):
        with patch('core.shopee_posting.device.time.sleep'),patch('core.shopee_posting.settings.time.sleep'):
            return apply_options(d,options)

    def test_live_layout_ids_recognized_with_no_ai_not_false(self):
        d=alternate_device();cap=detect_layout(d.fixture_nodes)
        self.assertEqual(cap['layout'],'split_duet_stitch');self.assertFalse(cap['ai_label_available'])
        proof,_=read_options(d);self.assertIsNone(proof['options']['ai_label'])
        self.assertEqual(proof['unavailable_options'],['ai_label']);d.adb.shell.assert_not_called()

    def test_split_duet_stitch_and_whatsapp_off_before_post_with_ai_absent(self):
        d=alternate_device();proof=self.apply(d)
        self.assertEqual(d.adb.shell.call_count,3)
        for c in ('allow_duet_toggle','allow_stitch_toggle','iv_whatsapp','iv_facebook'):
            self.assertIs(proof['control_values'][c],False)
        self.assertIsNone(proof['options']['ai_label'])
        self.assertTrue(proof['requested_options']['ai_label'])
        self.assertTrue(proof_matches_options(proof,ADAPTIVE))
        self.apply(d);self.assertEqual(d.adb.shell.call_count,3,'Repeated setting must not toggle again')

    def test_missing_ai_requires_captured_permission_not_silent_false(self):
        for opts in (DEFAULT_OPTIONS,{**DEFAULT_OPTIONS,'allow_missing_controls':False}):
            d=alternate_device()
            with self.subTest(opts=opts),self.assertRaisesRegex(ReviewRequired,'SHOPEE_AI_LABEL_UNAVAILABLE'):
                self.apply(d,opts)
            d.adb.shell.assert_not_called()

    def test_each_present_reuse_switch_is_set_even_when_other_absent(self):
        for controls in (('allow_duet_toggle',),('allow_stitch_toggle',),()):
            d=alternate_device(reuse=controls);proof=self.apply(d)
            self.assertTrue(proof_matches_options(proof,ADAPTIVE))
            self.assertEqual(d.adb.shell.call_count,len(controls)+1)
            self.assertEqual(proof['capabilities']['reuse_controls'],list(controls))
            if not controls:self.assertIsNone(proof['options']['allow_reuse'])

    def test_present_ai_respects_all_user_choices_for_both_layouts(self):
        for split in (False,True):
            for reuse in (False,True):
                for ai in (False,True):
                    d=alternate_device(ai=True) if split else ready_device()
                    if not split:
                        def tap(*args,**kw):
                            for n in d.fixture_nodes:
                                if n['resource-id'] in d.fixture_values and d.center(n['bounds'])==(int(args[3]),int(args[4])):
                                    r=n['resource-id'];d.fixture_values[r]=not d.fixture_values[r]
                            return Mock(returncode=0)
                        d.adb.shell.side_effect=tap
                    opts={**ADAPTIVE,'allow_reuse':reuse,'ai_label':ai}
                    with self.subTest(split=split,reuse=reuse,ai=ai):
                        proof=self.apply(d,opts);self.assertTrue(proof_matches_options(proof,opts))
                        self.assertIs(proof['options']['ai_label'],ai)

    def test_partial_or_loading_controls_only_passively_retry_three_reads(self):
        for resource in ('allow_duet_toggle','tv_allow_stitch','iv_whatsapp','et_caption'):
            d=alternate_device();d.fixture_nodes=[n for n in d.fixture_nodes if n['resource-id']!=P+resource]
            with self.subTest(resource=resource),self.assertRaises(ReviewRequired):self.apply(d)
            self.assertEqual(d.ui.dump_hierarchy.call_count,3);d.adb.shell.assert_not_called()

    def test_delayed_known_control_can_finish_without_reset_or_gesture_replay(self):
        d=alternate_device();node=next(n for n in d.fixture_nodes if n['resource-id']==P+'allow_duet_toggle')
        d.fixture_nodes.remove(node);original=d.ui.dump_hierarchy.side_effect;calls=[0]
        def delayed(**kw):
            calls[0]+=1
            if calls[0]==2:d.fixture_nodes.append(node)
            return original(**kw)
        d.ui.dump_hierarchy.side_effect=delayed
        self.assertTrue(proof_matches_options(self.apply(d),ADAPTIVE))
        self.assertEqual(d.adb.shell.call_count,3)

    def test_ambiguous_disabled_hidden_wrong_label_are_not_missing_controls(self):
        for kind in ('duplicate','disabled','hidden','wrong_label','mixed'):
            d=alternate_device();n=next(n for n in d.fixture_nodes if n['resource-id']==P+'allow_duet_toggle')
            if kind=='duplicate':d.fixture_nodes.append(dict(n))
            if kind=='disabled':n['enabled']='false'
            if kind=='hidden':n['visible-to-user']='false'
            if kind=='wrong_label':next(n for n in d.fixture_nodes if n['resource-id']==P+'tv_allow_duet')['text']='other meaning'
            if kind=='mixed':d.fixture_nodes.append({**n,'resource-id':P+'allow_reuse_toggle'})
            with self.subTest(kind=kind),self.assertRaisesRegex(ReviewRequired,'SHOPEE_SETTINGS_REVIEW'):self.apply(d)
            d.adb.shell.assert_not_called();self.assertEqual(d.ui.dump_hierarchy.call_count,1)

    def test_lost_toggle_ack_rechecks_without_second_gesture(self):
        d=alternate_device();original=d.adb.shell.side_effect;raised=[False]
        def lost(*a,**kw):
            result=original(*a,**kw)
            if not raised[0]:raised[0]=True;raise OSError('lost ack')
            return result
        d.adb.shell.side_effect=lost
        self.assertTrue(proof_matches_options(self.apply(d),ADAPTIVE));self.assertEqual(d.adb.shell.call_count,3)

    def test_layout_switch_during_observation_never_becomes_permission(self):
        d=alternate_device();shot=d.ui.screenshot.side_effect
        def changing():
            image=shot();d.fixture_nodes=[n for n in d.fixture_nodes if n['resource-id'] not in {P+'allow_stitch_toggle',P+'tv_allow_stitch'}]
            return image
        d.ui.screenshot.side_effect=changing
        with self.assertRaises(ReviewRequired):self.apply(d)
        d.adb.shell.assert_not_called()

    def test_ai_control_half_present_is_not_authorized_absence(self):
        for missing in ('ai_generated_toggle','tv_ai_generated_title'):
            d=alternate_device(ai=True);d.fixture_nodes=[n for n in d.fixture_nodes if n['resource-id']!=P+missing]
            with self.subTest(missing=missing),self.assertRaises(ReviewRequired):self.apply(d)
            d.adb.shell.assert_not_called()

    def test_available_page_after_evidence_cannot_downgrade_final_guard(self):
        d=alternate_device();self.apply(d)
        _,screen=observe_options(d,ADAPTIVE)
        # A different layout after evidence must not reuse prior settings proof.
        d.fixture_nodes=[n for n in d.fixture_nodes if n['resource-id'] not in {P+'allow_stitch_toggle',P+'tv_allow_stitch'}]
        d.adb.shell.reset_mock()
        with self.assertRaises(ReviewRequired):observe_options(d,ADAPTIVE,previous=screen)
        d.adb.shell.assert_not_called()

    def test_proof_does_not_allow_claiming_ai_set_or_changing_permission(self):
        proof=self.apply(alternate_device())
        mutations=[lambda p:p['options'].update(ai_label=True),lambda p:p['control_values'].update(ai_generated_toggle=False),
                   lambda p:p['control_values'].update(allow_duet_toggle=True),lambda p:p['control_values'].update(iv_whatsapp=True),
                   lambda p:p['requested_options'].update(allow_missing_controls=False),lambda p:p.update(method='other'),
                   lambda p:p['capabilities'].update(ai_label_available=True),lambda p:p.update(unavailable_options=[])]
        for mutate in mutations:
            changed=copy.deepcopy(proof);mutate(changed)
            self.assertFalse(proof_matches_options(changed,ADAPTIVE))
        for value in ('true',1,None):
            with self.assertRaises(ValueError):validate_options({**ADAPTIVE,'allow_missing_controls':value})

    def test_new_start_freezes_policy_and_respects_explicit_strict(self):
        from core.shopee_posting.service import ShopeePosting
        for explicit in (None,False,True):
            with tempfile.TemporaryDirectory() as folder:
                wifi=Mock();wifi.state.return_value={'selected':{'device_id':'phone'}}
                service=ShopeePosting(Path(folder),Mock(),wifi,validator=Mock())
                ids=service.store.add([dict(item_id='clip',title='Clip',caption='caption',video_path='clip.mp4',product_url='https://s.shopee.co.th/test')])
                def setup(s):
                    s['account']={'name':'owner','device_id':'phone'}
                    if explicit is not None:s['items'][0]['post_options']['allow_missing_controls']=explicit
                service.store.change(setup)
                with patch('core.shopee_posting.service.threading.Thread'):
                    service.action('shopee_post_start',dict(ids=ids,confirm=True,revision=service.state()['revision']))
                row=service.store.read()['items'][0]
                self.assertIs(row['run_contract']['post_options']['allow_missing_controls'],explicit if explicit is not None else True)

    def test_legacy_result_does_not_wait_for_authorized_unavailable_ai(self):
        from core.shopee_posting.workflow import verify_result
        proof=self.apply(alternate_device());row={'id':'clip','caption':'caption','phase':'processing',
            'publish_intent':{'post_options':ADAPTIVE,'observed_options':proof,'latest_baseline':{'account':'owner','latest_caption':'older'}}}
        store=Mock();store.read.return_value={'items':[row]};device=Mock()
        with patch('core.shopee_posting.workflow.await_upload',return_value=False),patch('core.shopee_posting.workflow.return_to_feed'):
            verify_result(device,store,'clip','owner','Product',Path('fixture'))
        self.assertFalse(any(c.kwargs.get('text')=='ครีเอเตอร์เพิ่มป้ายกำกับ AI' for c in device.wait.call_args_list))
        self.assertIsNone(store.transition.call_args.kwargs['receipt']['ai_label'])

    def test_actual_publisher_captures_absence_then_sends_once_and_confirms_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);video=root/'final.mp4';video.write_bytes(b'fixture-video')
            store=PostingStore(root);row_id=store.add([dict(item_id='clip',title='Clip',caption='caption',video_path=str(video),product_url='https://s.shopee.co.th/test')])[0]
            store.change(lambda s:start_run(s,[row_id],'owner','phone'))
            store.transition(row_id,{'draft'},'settings',post_options=dict(ADAPTIVE),video_sha256=file_hash(video),transfer={'album':'fixture'},
                run_contract=dict(account='owner',device_id='phone',post_options=dict(ADAPTIVE),video_sha256=file_hash(video)),
                latest_baseline=dict(account='owner',latest_caption='older'))
            d=alternate_device();self.apply(d);d.adb.shell.reset_mock()
            publish_current(d,store,row_id,'owner','Product',root/'evidence')
            row=store.read()['items'][0];self.assertEqual(row['phase'],'processing');self.assertEqual(d.adb.shell.call_count,1)
            self.assertIsNone(row['publish_intent']['observed_options']['options']['ai_label'])
            store.confirm_uploaded(row_id,row['publish_intent']['id'],time.time(),'live_native_upload_banner')
            self.assertEqual(store.read()['items'][0]['phase'],'published')
            with self.assertRaises(ReviewRequired):publish_current(d,store,row_id,'owner','Product',root/'evidence')
            self.assertEqual(d.adb.shell.call_count,1)
