import copy
import tempfile
import time
import unittest
from contextlib import ExitStack, nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from core.shopee_posting.contract import flow_version
from core.shopee_posting.device import ReviewRequired
from core.shopee_posting.options import DEFAULT_OPTIONS
from core.shopee_posting.result import await_upload
from core.shopee_posting.service import ShopeePosting
from core.shopee_posting.workflow import P, S, prepare_queue_account, prepare_post_page, own_profile_name, close_completed_post
from shopee_preflight_fixture import ready_device

PACKAGE='com.shopee.th'
NOTICE='<hierarchy><node package="com.shopee.th" enabled="true" class="android.view.ViewGroup" clickable="true"><node package="com.shopee.th" enabled="true" text="อัปโหลดสำเร็จ"/><node package="com.shopee.th" enabled="true" text="คลิกที่นี่เพื่อดูวิดีโอ"/></node></hierarchy>'


def node(**attrs):
    return {'package':PACKAGE,'enabled':'true',**attrs}


def profile(name):
    return [node(**{'content-desc':'user name of me'}),node(text='ชื่อผู้ใช้: '+name),node(**{'content-desc':'click to get back'})]


class ContinuousQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.wifi=Mock()
        self.wifi.state.return_value={'selected':{'device_id':'phone','model':'fixture'}}
        self.wifi.verified_device.side_effect=lambda:nullcontext(Mock())
        self.service=ShopeePosting(self.root,Mock(),self.wifi,validator=Mock())
        self.store=self.service.store;self.details=[]
        for i in range(3):
            video=self.root/f'clip-{i}.mp4';video.write_bytes(f'unique video {i}'.encode())
            self.details.append(dict(item_id=f'clip:{i}',title=f'Clip {i}',caption='same caption',
                                     product_url='https://s.shopee.co.th/test',video_path=str(video)))
        self.ids=self.store.add(self.details)
        self.store.change(lambda s:s.update(account={'name':'owner','device_id':'phone'}))
        self.service.detail=lambda id:next(d for d in self.details if d['item_id']==id)
        self.service.validator.validate.return_value={'duration':10}
        self.public=[];self.closed=[];self.initial_closed=[];self.app_closed=False;self.device=Mock(identity='phone',package=PACKAGE)
        self.device.ui.info={'screenOn':True,'currentPackageName':PACKAGE}
        self.device.ui.app_start.side_effect=lambda package:setattr(self,'app_closed',False)
        self.device.open.side_effect=lambda:setattr(self,'app_closed',False)
        self.device.snapshot.side_effect=self.snapshot
        def tap(**kw):
            if kw.get('resource-id')==P+'btn_post':
                claimed=[r for r in self.store.read()['items'] if r['phase']=='send_pending']
                self.assertEqual(len(claimed),1)
                self.assertTrue(self.initial_closed,'First new clip must close the old Shopee first')
                self.assertEqual(self.closed,self.public,'Every previous successful clip must close before the next Post')
                self.public.append(claimed[0]['id'])
        self.device.tap.side_effect=tap
        self.device.commit_observed_post.side_effect=lambda observation,claim:(claim(),tap(**{'resource-id':P+'btn_post'}))
        def close(*args,**kwargs):
            self.assertEqual(args,('am','force-stop',PACKAGE))
            current=self.store.read()['posting_run']['current_id']
            row=next(r for r in self.store.read()['items'] if r['id']==current)
            if row['phase']=='prepared':
                self.assertEqual(current,self.store.read()['posting_run']['ids'][0])
                self.assertNotIn('publish_intent',row);self.initial_closed.append(current)
            else:
                self.assertEqual(row['phase'],'published');self.assertTrue(row['receipt']['upload_confirmed'])
                self.closed.append(current)
            self.app_closed=True
            return Mock(returncode=0)
        self.device.adb.shell.side_effect=close

    def snapshot(self):
        self.assertFalse(self.app_closed,'Must reopen Shopee before reading the next posting page')
        pending=[r for r in self.store.read()['items'] if r['phase']=='processing']
        if pending:
            return (NOTICE if pending[0]['id']!=getattr(self,'missing_notice',None) else '<hierarchy/>'),[]
        return '<hierarchy/>',[node(**{'resource-id':P+'tv_product_title'}),node(**{'content-desc':'click me page icon'}),node(**{'content-desc':'click top right create icon'})]

    def begin(self, ids=None):
        selected=ids or self.ids
        with patch('core.shopee_posting.service.threading.Thread'):
            self.service.action('shopee_post_start',{'ids':selected,'revision':self.store.read()['revision'],'confirm':True})
        return self.store.read()['posting_run']['id']

    def fixtures(self):
        stack=ExitStack()
        stack.enter_context(patch('core.shopee_posting.service.ShopeeDevice',return_value=self.device))
        stack.enter_context(patch('core.shopee_posting.service.transfer',return_value={'album':'fixture'}))
        self.account=stack.enter_context(patch('core.shopee_posting.service.prepare_queue_account'))
        self.old=stack.enter_context(patch('core.shopee_posting.workflow.latest_baseline',side_effect=AssertionError('must not open old posts')))
        stack.enter_context(patch('core.shopee_posting.workflow.account_on_home',side_effect=AssertionError('must not read account per clip')))
        stack.enter_context(patch('core.shopee_posting.workflow.choose_video'))
        stack.enter_context(patch('core.shopee_posting.workflow.add_product',return_value='Product'))
        observed={'options':dict(DEFAULT_OPTIONS),'sharing_off':True}
        stack.enter_context(patch('core.shopee_posting.workflow.apply_options',return_value=observed))
        screen_device=ready_device(caption='same caption')
        from core.shopee_posting.settings import observe_options
        stack.enter_context(patch('core.shopee_posting.publish.observe_options',side_effect=lambda d,*a,**kw:observe_options(screen_device,*a,**kw)))
        stack.enter_context(patch('core.shopee_posting.workflow.await_upload',side_effect=lambda d,s,i:await_upload(d,s,i,timeout=0)))
        return stack

    def test_three_real_workflows_in_selected_order_without_account_tour_or_old_posts(self):
        order=[self.ids[2],self.ids[0],self.ids[1]];rid=self.begin(order)
        with self.fixtures():
            self.service._post(order,'owner',rid)
        self.assertEqual(self.public,order);self.account.assert_not_called();self.old.assert_not_called()
        self.assertEqual(self.closed,order)
        self.assertEqual(self.initial_closed,order[:1])
        self.device.ui.app_start.assert_called_once_with(PACKAGE)
        self.assertEqual(self.device.open.call_count,3);self.assertTrue(self.app_closed)
        self.assertNotIn('click video 0',repr(self.device.mock_calls))
        state=self.service.state();self.assertEqual(state['posting_run']['completed'],3)
        self.assertEqual(state['posting_run']['status'],'complete');self.assertFalse(state['busy'])
        for row in state['items']:
            self.assertNotIn('latest_baseline',row)
            self.assertEqual(row['publish_intent']['posting_flow_version'],2)
            self.assertEqual(row['publish_intent']['queue_account_receipt']['run_id'],rid)
            self.assertEqual(row['publish_intent']['queue_account_receipt']['source'],'confirmed_selection')
            self.assertNotIn('verified_at',row['publish_intent']['queue_account_receipt'])
            self.assertTrue(row['receipt']['upload_confirmed'])
        self.assertNotIn('account',[event['step'] for event in state['posting_run']['events']])

    def test_unknown_second_stops_without_old_profile_or_third_post(self):
        self.missing_notice=self.ids[1];rid=self.begin()
        with self.fixtures():self.service._post(self.ids,'owner',rid)
        self.assertEqual(self.public,self.ids[:2]);self.account.assert_not_called();self.old.assert_not_called()
        self.assertEqual(self.closed,self.ids[:1])
        state=self.service.state();self.assertEqual([r['phase'] for r in state['items']],['published','unknown','draft'])
        self.assertEqual(state['posting_run']['completed'],1)
        with self.assertRaises(ValueError):self.service.action('shopee_post_start',{'ids':[self.ids[1]],'revision':state['revision'],'confirm':True})

    def test_wrong_account_stops_before_any_publication(self):
        rid=self.begin()
        self.device.snapshot.side_effect=lambda:('',profile('other'))
        with self.fixtures():
            self.service._post(self.ids,'owner',rid)
        self.assertEqual(self.public,[]);self.old.assert_not_called();self.account.assert_not_called()
        self.assertEqual([r['phase'] for r in self.store.read()['items']],['review','draft','draft'])

    def test_unselected_rows_untouched(self):
        before=copy.deepcopy(self.store.read()['items'][1:]);rid=self.begin(self.ids[:1])
        with self.fixtures():self.service._post(self.ids[:1],'owner',rid)
        self.assertEqual(self.store.read()['items'][1:],before)

    def test_duplicate_video_hash_still_blocks_second_publication(self):
        self.details[1]['video_path']=self.details[0]['video_path']
        self.store.change(lambda s:s['items'][1].update(video_path=self.details[0]['video_path']))
        rid=self.begin()
        with self.fixtures():self.service._post(self.ids,'owner',rid)
        self.assertEqual(self.public,self.ids[:1]);self.assertIn('เคยเริ่มโพสต์',self.service.state()['message'])

    def test_pause_between_clips_does_not_continue(self):
        rid=self.begin()
        real=self.store.confirm_uploaded
        def completed(*a,**kw):
            real(*a,**kw);self.service._pause.set()
        with self.fixtures(),patch.object(self.store,'confirm_uploaded',side_effect=completed):
            self.service._post(self.ids,'owner',rid)
        self.assertEqual(self.public,self.ids[:1]);self.assertEqual(self.service.state()['posting_run']['status'],'paused')
        self.assertEqual(self.closed,[])

    def test_close_failure_keeps_first_published_and_stops_before_next(self):
        rid=self.begin()
        close=self.device.adb.shell.side_effect
        self.device.adb.shell.side_effect=lambda *a,**kw:close(*a,**kw) if not self.public else Mock(returncode=1)
        with self.fixtures():self.service._post(self.ids,'owner',rid)
        self.assertEqual(self.public,self.ids[:1]);self.assertEqual(self.device.adb.shell.call_count,2)
        self.assertEqual([r['phase'] for r in self.store.read()['items']],['published','draft','draft'])
        self.assertEqual(self.service.state()['posting_run']['completed'],1)

    def test_first_close_failure_stops_before_account_or_any_post(self):
        rid=self.begin();self.device.adb.shell.side_effect=None;self.device.adb.shell.return_value=Mock(returncode=1)
        with self.fixtures():self.service._post(self.ids,'owner',rid)
        self.assertEqual(self.public,[]);self.account.assert_not_called();self.device.ui.app_start.assert_not_called()
        self.device.adb.shell.assert_called_once()
        self.assertEqual([r['phase'] for r in self.store.read()['items']],['review','draft','draft'])

    def test_new_start_captures_both_close_boundaries(self):
        self.begin()
        for row in self.store.read()['items']:
            self.assertIs(row['run_contract']['close_before_first_post'],True)
            self.assertIs(row['run_contract']['close_after_publish'],True)

    def test_cancel_at_any_unsent_step_starts_fresh_and_closes_before_post(self):
        stages=[('queued','queued'),('checking','checking'),('transferring','transfer'),
                ('prepared','restart_app'),('prepared','account'),('prepared','prepare_post'),
                ('editing','select_video'),('editing','caption'),('editing','product'),
                ('settings','settings'),('ready','preflight')]
        for number,(phase,step) in enumerate(stages):
            with self.subTest(step=step):
                self.app_closed=False  # Each case starts with its own old Shopee page still open.
                video=self.root/f'cancel-{number}.mp4';video.write_bytes(f'cancelled clip {number}'.encode())
                detail=dict(self.details[0],item_id=f'cancel:{number}',video_path=str(video))
                self.details.append(detail);row_id=self.store.add([detail])[0]
                old_run=self.begin([row_id]);self.store.bind_queue_account(old_run,'owner','phone')
                self.store.transition(row_id,{'queued'},phase)
                if phase in {'prepared','editing','settings'}:
                    self.store.progress(row_id,step,'old cancelled step')
                self.service.action('shopee_post_pause',{'run_id':old_run})
                # Simulate the old worker's finally block; never clear a running worker.
                self.store.settle_run([row_id],old_run,'cancelled before Post',paused=True)
                self.service._busy=False
                cancelled=next(r for r in self.store.read()['items'] if r['id']==row_id)
                self.assertNotIn('publish_intent',cancelled)
                self.assertIn(cancelled['phase'],{'draft','review'})

                new_run=self.begin([row_id]);state=self.store.read();run=state['posting_run']
                self.assertNotEqual(new_run,old_run);self.assertFalse(self.service._pause.is_set())
                self.assertNotIn('account_receipt',run);self.assertIsNone(run['current_id'])
                self.assertEqual(run['rows'][row_id]['step'],'queued')
                self.assertNotIn('last_step',run['rows'][row_id])
                before=len(self.initial_closed)
                with self.fixtures():
                    self.service._post([row_id],'owner',new_run)
                    self.account.assert_not_called()
                self.assertEqual(self.initial_closed[before:],[row_id])
                self.assertEqual(self.public[-1],row_id)
                events=self.store.read()['posting_run']['events']
                steps=[event['step'] for event in events]
                self.assertLess(steps.index('checking'),steps.index('restart_app'))
                self.assertNotIn('account',steps)
                self.assertLess(steps.index('restart_app'),steps.index('sending'))
                self.assertEqual(self.service.state()['posting_run']['status'],'complete')

    def test_cancel_after_publish_intent_never_becomes_fresh_unsent_work(self):
        for row_id,phase in zip(self.ids,['send_pending','processing','unknown']):
            with self.subTest(phase=phase):
                run_id=self.begin([row_id]);intent={'id':f'intent-{phase}','device_id':'phone'}
                self.store.transition(row_id,{'queued'},phase,publish_intent=intent)
                self.service.action('shopee_post_pause',{'run_id':run_id})
                self.store.settle_run([row_id],run_id,'cancelled after claim',paused=True)
                self.service._busy=False
                before=self.store.read();row=next(r for r in before['items'] if r['id']==row_id)
                self.assertEqual(row['phase'],'unknown');self.assertEqual(row['publish_intent'],intent)
                with self.assertRaises(ValueError):self.begin([row_id])
                self.assertEqual(self.store.read(),before)
        self.device.adb.shell.assert_not_called();self.assertEqual(self.public,[])

    def test_old_account_receipt_cannot_be_used_by_new_round(self):
        rid=self.begin();self.store.bind_queue_account(rid,'owner','phone')
        proof=self.store.read()['posting_run']['account_receipt']
        self.service=ShopeePosting(self.root,Mock(),self.wifi,validator=Mock())
        self.store=self.service.store;rid2=self.begin()
        self.store.change(lambda s:s['posting_run'].update(account_receipt=proof))
        with self.assertRaises(ValueError):self.store.queue_account(self.ids[0],'owner','phone')
        self.assertNotEqual(rid,rid2);self.assertEqual(self.public,[])

    def test_missing_or_wrong_phone_proof_fails(self):
        rid=self.begin()
        with self.assertRaises(ValueError):self.store.queue_account(self.ids[0],'owner','phone')
        self.store.bind_queue_account(rid,'owner','phone')
        with self.assertRaises(ValueError):self.store.queue_account(self.ids[0],'owner','other')
        with self.assertRaises(ValueError):self.store.bind_queue_account(rid,'owner','phone')

    def test_legacy_queue_keeps_live_account_policy(self):
        rid=self.begin(self.ids[:1])
        def legacy(state):
            state['items'][0]['run_contract'].pop('account_check_mode')
            state['posting_run'].pop('start_confirmation')
            state['posting_run'].pop('account_check_mode')
        self.store.change(legacy)
        with self.fixtures():self.service._post(self.ids[:1],'owner',rid)
        self.account.assert_called_once();self.assertEqual(self.public,self.ids[:1])
        proof=self.store.read()['posting_run']['account_receipt']
        self.assertEqual(proof['source'],'live_ui');self.assertIn('verified_at',proof)

    def test_new_start_goes_from_home_to_video_without_me_tab(self):
        rid=self.begin(self.ids[:1]);normal=self.snapshot
        def home():
            if any(r['phase']=='processing' for r in self.store.read()['items']):return normal()
            self.assertFalse(self.app_closed)
            return '',[node(**{'content-desc':'tab_bar_button_home'}),
                       node(**{'content-desc':'tab_bar_button_video_and_live'}),
                       node(**{'resource-id':P+'tv_product_title'})]
        self.device.snapshot.side_effect=home
        with self.fixtures():self.service._post(self.ids[:1],'owner',rid)
        self.assertEqual(self.public,self.ids[:1]);self.account.assert_not_called()
        self.assertIn({'content-desc':'tab_bar_button_video_and_live'},[c.kwargs for c in self.device.tap.call_args_list])
        self.assertNotIn('tab_bar_button_me',repr(self.device.mock_calls))
        self.assertNotIn('click me page icon',repr(self.device.tap.call_args_list))

    def test_user_confirmation_cannot_be_missing_or_rebound_to_other_run_phone_account(self):
        rid=self.begin();original=copy.deepcopy(self.store.read())
        mutations=[lambda s:s['posting_run'].pop('start_confirmation'),
                   lambda s:s['posting_run']['start_confirmation'].update(run_id='old'),
                   lambda s:s['posting_run']['start_confirmation'].update(account='other'),
                   lambda s:s['posting_run']['start_confirmation'].update(device_id='other'),
                   lambda s:s['posting_run']['start_confirmation'].update(confirmed_at=0),
                   lambda s:s['posting_run']['start_confirmation'].update(confirmed_at=True),
                   lambda s:s['posting_run']['start_confirmation'].update(confirmed_at=float('inf')),
                   lambda s:s['items'][1]['run_contract'].update(account_check_mode='live_ui')]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.store.file.write(copy.deepcopy(original));self.store.change(mutation)
                before=self.store.read()
                with self.assertRaises(ValueError):self.store.bind_queue_account(rid,'owner','phone')
                self.assertEqual(self.store.read(),before)

    def test_bound_user_proof_cannot_masquerade_as_live_read(self):
        rid=self.begin();self.store.bind_queue_account(rid,'owner','phone')
        original=copy.deepcopy(self.store.read())
        mutations=[lambda s:s['posting_run']['account_receipt'].update(source='live_ui'),
                   lambda s:s['posting_run']['account_receipt'].pop('source'),
                   lambda s:s['posting_run']['account_receipt'].update(confirmed_at=0),
                   lambda s:s['posting_run']['start_confirmation'].update(account='other'),
                   lambda s:s['items'][0]['run_contract'].update(account_check_mode='unknown')]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.store.file.write(copy.deepcopy(original));self.store.change(mutation)
                with self.assertRaises(ValueError):self.store.queue_account(self.ids[0],'owner','phone')

    def test_legacy_version_not_rewritten_by_read(self):
        row=self.store.read()['items'][0];self.assertEqual(flow_version(row),1)
        self.service.state();self.assertNotIn('run_contract',self.store.read()['items'][0])
        for bad in (True,'2',3):
            with self.subTest(bad=bad),self.assertRaises(ValueError):flow_version({'run_contract':{'posting_flow_version':bad}})


class QueueEntryTests(unittest.TestCase):
    def device(self,nodes):
        d=Mock(package=PACKAGE);d.snapshot.return_value=('',nodes);return d

    def test_feed_ready_zero_navigation(self):
        d=self.device([node(**{'content-desc':'click me page icon'}),node(**{'content-desc':'click top right create icon'})])
        prepare_post_page(d,'owner');d.tap.assert_not_called()
        d.open.assert_called_once()

    def test_reopened_home_uses_only_live_video_bottom_tab(self):
        d=self.device([node(**{'content-desc':'tab_bar_button_home'}),node(**{'content-desc':'tab_bar_button_video_and_live'})])
        prepare_post_page(d,'owner')
        d.open.assert_called_once();d.tap.assert_called_once_with(**{'content-desc':'tab_bar_button_video_and_live'})
        self.assertEqual(d.wait.call_count,2)

    def test_existing_main_me_page_uses_video_tab_without_profile_tour(self):
        nodes=[node(**{'resource-id':'meCircleView'}),node(**{'resource-id':'labelUserName','text':'owner'}),
               node(**{'content-desc':'tab_bar_button_video_and_live'})]
        d=self.device(nodes);prepare_post_page(d,'owner')
        d.tap.assert_called_once_with(**{'content-desc':'tab_bar_button_video_and_live'})
        d.profile_account.assert_not_called()

    def test_already_visible_wrong_main_me_account_blocks_without_extra_navigation(self):
        d=self.device([node(**{'resource-id':'meCircleView'}),node(**{'resource-id':'labelUserName','text':'other'}),
                       node(**{'content-desc':'tab_bar_button_video_and_live'})])
        with self.assertRaises(ReviewRequired):prepare_post_page(d,'owner')
        d.tap.assert_not_called();d.profile_account.assert_not_called()

    def test_profile_returns_to_feed_without_opening_video(self):
        d=self.device(profile('owner'));prepare_queue_account(d,'owner')
        self.assertEqual(d.tap.call_args.kwargs,{'content-desc':'click to get back'})
        self.assertEqual(d.tap.call_count,1);self.assertNotIn('click video 0',repr(d.mock_calls))

    def test_wrong_own_profile_no_navigation(self):
        d=self.device(profile('other'))
        with self.assertRaises(ReviewRequired):prepare_queue_account(d,'owner')
        d.tap.assert_not_called()

    def test_composer_is_never_discarded(self):
        d=self.device([node(**{'resource-id':P+'et_caption'})])
        for fn in (prepare_post_page,prepare_queue_account):
            with self.assertRaises(ReviewRequired):fn(d,'owner')
        d.tap.assert_not_called();d.ui.press.assert_not_called()

    def test_leave_known_own_old_panel_only_once(self):
        d=self.device([node(**{'content-desc':'close the comment panels'}),node(**{'content-desc':'meaning this is the creator'})])
        with patch('core.shopee_posting.workflow.return_to_feed') as leave,patch('core.shopee_posting.workflow.account_on_home',return_value='owner') as account,patch('core.shopee_posting.workflow.prepare_post_page'):
            prepare_queue_account(d,'owner')
        leave.assert_called_once_with(d,'owner');account.assert_not_called()

    def test_unknown_page_does_not_back_or_open_any_post(self):
        d=self.device([node(text='random feed text')])
        with self.assertRaises(ReviewRequired):prepare_post_page(d,'owner')
        d.tap.assert_not_called();d.ui.press.assert_not_called()

    def test_profile_label_requires_own_profile_marker(self):
        self.assertIsNone(own_profile_name([node(text='ชื่อผู้ใช้: owner')]))
        self.assertIsNone(own_profile_name(profile('owner')+[node(text='ชื่อผู้ใช้: other')]))


class CompletedCloseTests(unittest.TestCase):
    def setUp(self):
        self.row={'id':'one','phase':'published','posting_run_id':'run',
                  'run_contract':{'close_after_publish':True},
                  'publish_intent':{'id':'send','device_id':'phone'},
                  'receipt':{'upload_confirmed':True,'source':'live_native_upload_banner','intent_id':'send','account':'owner'}}
        self.state={'posting_run':{'id':'run','current_id':'one'},'items':[self.row]}
        self.store=Mock();self.store.read.side_effect=lambda:self.state
        self.device=Mock(identity='phone',package=PACKAGE)
        self.device.snapshot.return_value=('',[node(**{'content-desc':'click me page icon'}),node(**{'content-desc':'click top right create icon'})])
        self.device.adb.shell.return_value=Mock(returncode=0)

    def close(self):
        return close_completed_post(self.device,self.store,'one','owner','run')

    def test_verified_success_closes_only_shopee_once(self):
        self.assertTrue(self.close())
        self.store.queue_account.assert_called_once_with('one','owner','phone')
        self.device.adb.shell.assert_called_once_with('am','force-stop',PACKAGE,timeout=10)

    def test_legacy_has_no_automatic_close(self):
        self.row['run_contract']={};self.assertFalse(self.close())
        self.device.snapshot.assert_not_called();self.device.adb.shell.assert_not_called()

    def test_unconfirmed_or_wrong_receipt_never_closes(self):
        original=copy.deepcopy(self.row)
        for change in ({'phase':'processing'},{'phase':'unknown'},{'phase':'review'},
                       {'receipt':{}},{'receipt':dict(original['receipt'],intent_id='other')},
                       {'receipt':dict(original['receipt'],source='saved_native_upload_banner')},
                       {'receipt':dict(original['receipt'],account='other')},
                       {'publish_intent':{'id':'send','device_id':'other'}}):
            with self.subTest(change=change):
                self.row.clear();self.row.update(copy.deepcopy(original));self.row.update(change)
                with self.assertRaises(ReviewRequired):self.close()
        self.device.adb.shell.assert_not_called()

    def test_old_run_or_wrong_current_row_never_closes(self):
        for run in ({'id':'old','current_id':'one'},{'id':'run','current_id':'two'}):
            self.state['posting_run']=run
            with self.assertRaises(ReviewRequired):self.close()
        self.device.adb.shell.assert_not_called()

    def test_new_draft_or_unknown_page_not_discarded(self):
        feed=self.device.snapshot.return_value[1]
        for resource in (P+'et_caption',S+'ll_gallery_entrance',S+'tv_pick_title',S+'tv_compress'):
            self.device.snapshot.return_value=('',feed+[node(**{'resource-id':resource})])
            with self.assertRaises(ReviewRequired):self.close()
        self.device.snapshot.return_value=('',[node(text='unexpected page')])
        with self.assertRaises(ReviewRequired):self.close()
        self.device.adb.shell.assert_not_called()

    def test_cancel_identity_or_lost_batch_proof_never_closes(self):
        self.store.queue_account.side_effect=ValueError('expired run')
        with self.assertRaises(ValueError):self.close()
        self.store.queue_account.side_effect=None
        self.device.verify.side_effect=ReviewRequired('cancelled or wrong phone')
        with self.assertRaises(ReviewRequired):self.close()
        self.device.adb.shell.assert_not_called()

    def test_wrong_profile_vetoes_even_with_bottom_navigation(self):
        self.device.snapshot.return_value=('',profile('other')+[node(**{'content-desc':'tab_bar_button_home'}),node(**{'content-desc':'tab_bar_button_video_and_live'})])
        with self.assertRaises(ReviewRequired):self.close()
        self.device.adb.shell.assert_not_called()

    def test_failed_close_is_not_retried(self):
        self.device.adb.shell.return_value=Mock(returncode=1)
        with self.assertRaises(ReviewRequired):self.close()
        self.device.adb.shell.assert_called_once()
        self.assertEqual(self.row['phase'],'published')
