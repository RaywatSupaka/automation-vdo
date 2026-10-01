import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.shopee_posting.service import ShopeePosting
from core.shopee_posting.progress import start_run
from core.shopee_posting.restart import PREPARATION_FIELDS, restartable


class RestartRemainingTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.wifi=Mock();self.wifi.state.return_value={'selected':{'device_id':'phone','model':'fixture'}}
        self.service=ShopeePosting(Path(temp.name),Mock(),self.wifi,validator=Mock())
        self.store=self.service.store
        self.ids=self.store.add([dict(item_id=f'clip:{i}',title=f'Clip {i}',caption='caption',
            product_url='https://s.shopee.co.th/test',video_path=f'clip-{i}.mp4') for i in range(30)])
        def stopped(state):
            state['account']={'name':'owner','device_id':'phone'}
            start_run(state,self.ids,'owner','fixture')
            run=state['posting_run'];run.update(status='review',current_id=self.ids[13],message='old stuck error')
            for i,row in enumerate(state['items']):
                if i<13:
                    row.update(phase='published',publish_intent={'id':f'sent-{i}'},receipt={'upload_confirmed':True},published_at=1)
                    run['rows'][row['id']].update(phase='published',step='done')
                else:
                    row.update(phase='review',observed_options={'stale':True},dispatch_state='prepared',
                               run_contract={'old':True},waiting_for_device=True,device_observation={'old':True},
                               preflight_version=2,upload_notice_absent=True,attached_product_title='old',
                               transfer={'album':'preserved'},video_sha256='a'*64,message='old stuck error')
                    run['rows'][row['id']].update(phase='review',step='review',last_step='account')
        self.store.change(stopped)
        self.original=copy.deepcopy(self.store.read());self.service._message='old stuck error';self.service._pause.set()

    def reset(self,**overrides):
        state=self.store.read();payload=dict(confirm=True,revision=state['revision'],run_id=state['posting_run']['id'])
        payload.update(overrides)
        return self.service.action('shopee_post_reset_unsent',payload)['posting']

    def begin(self,ids):
        with patch('core.shopee_posting.service.threading.Thread'):
            self.service.action('shopee_post_start',dict(ids=ids,confirm=True,revision=self.store.read()['revision']))
        return self.service.state()

    def test_13_published_17_unsent_reset_to_zero_then_start_at_one_of_17(self):
        with patch('core.shopee_posting.service.threading.Thread') as worker:
            result=self.reset();worker.assert_not_called()
        run=result['posting_run'];self.assertEqual(run['status'],'ready')
        self.assertEqual((run['completed'],run['total'],run['remaining'],run['current_index']),(0,17,17,0))
        self.assertEqual(run['events'],[]);self.assertIsNone(run['current'])
        self.assertEqual(run['ids'],self.ids[13:]);self.assertFalse(result['paused']);self.assertFalse(result['busy'])
        self.assertEqual(result['items'][:13],self.original['items'][:13])
        self.assertNotIn('old stuck error',result['message'])
        self.wifi.verified_device.assert_not_called()
        state=self.begin(run['ids']);new_run=state['posting_run']
        self.assertNotEqual(run['id'],new_run['id']);self.assertEqual(new_run['completed'],0)
        self.store.transition(self.ids[13],{'queued'},'checking')
        self.assertEqual(self.service.state()['posting_run']['current_index'],1)
        self.assertEqual(self.service.state()['posting_run']['total'],17)

    def test_old_preparation_cleared_but_media_choices_and_history_retained(self):
        state=self.reset()
        for old,row in zip(self.original['items'][13:],state['items'][13:]):
            for key in PREPARATION_FIELDS-{'posting_run_id','message','waiting_for_device'}:
                self.assertNotIn(key,row)
            for key in ('id','item_id','video_path','caption','product_url','post_options','transfer','video_sha256'):
                self.assertEqual(row[key],old[key])
        history=state['restart_history'][-1]
        self.assertEqual(history['posting_run'],self.original['posting_run'])
        self.assertEqual(history['rows'][self.ids[13]]['dispatch_state'],'prepared')

    def test_normal_start_also_clears_preparation_without_requiring_reset_button(self):
        state=self.begin(self.ids[13:]);run=state['posting_run']
        self.assertEqual((run['total'],run['completed'],run['review_count']),(17,0,0))
        self.assertEqual(run['events'],[]);self.assertNotIn('account_receipt',run)
        self.assertEqual(state['items'][:13],self.original['items'][:13])
        for row in state['items'][13:]:
            self.assertNotIn('dispatch_state',row);self.assertNotIn('observed_options',row)
            self.assertEqual(row['run_contract']['account_check_mode'],'confirmed_selection')

    def test_every_abandoned_unsent_phase_is_restartable_only_when_worker_idle(self):
        phases=['queued','checking','transferring','prepared','editing','settings','ready','review']
        self.store.change(lambda s:[r.update(phase=phase) for r,phase in zip(s['items'][13:],phases)])
        state=self.begin(self.ids[13:]);self.assertEqual(state['posting_run']['total'],17)
        self.assertTrue(all(row['phase']=='queued' for row in state['items'][13:]))

    def test_any_send_or_receipt_evidence_is_excluded_without_being_cleared(self):
        variants=[{'publish_intent':{'id':'unknown'}},{'phase':'send_pending'},{'phase':'processing'},
                  {'phase':'unknown'},{'dispatch_state':'press_committed'},{'receipt':{'upload_confirmed':True}},
                  {'published_at':123},{'phase':'removed'}]
        self.store.change(lambda s:[r.update(v) for r,v in zip(s['items'][13:],variants)])
        before=copy.deepcopy(self.store.read())
        state=self.reset()
        self.assertEqual(state['posting_run']['ids'],self.ids[21:])
        self.assertEqual(state['items'][:21],before['items'][:21])
        self.assertTrue(all(not restartable(row) for row in state['items'][13:21]))

    def test_active_worker_missing_confirm_stale_revision_or_run_cannot_reset(self):
        before=self.store.read()
        self.service._busy=True
        with self.assertRaises(ValueError):self.reset()
        self.service._busy=False
        for change in ({'confirm':False},{'revision':-1},{'run_id':'old'}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.reset(**change)
        self.assertEqual(self.store.read(),before)

    def test_completed_only_has_nothing_to_reset(self):
        self.store.change(lambda s:[r.update(phase='published') for r in s['items']])
        before=self.store.read()
        with self.assertRaises(ValueError):self.reset()
        self.assertEqual(self.store.read(),before)

    def test_start_subset_preserves_every_unselected_row(self):
        selected=[self.ids[16],self.ids[13]];state=self.begin(selected)
        self.assertEqual(state['posting_run']['ids'],selected)
        for old,row in zip(self.original['items'],state['items']):
            if row['id'] not in selected:self.assertEqual(row,old)

    def test_old_worker_and_old_popup_cannot_change_reset_round(self):
        old_run=self.original['posting_run']['id'];state=self.reset();before=self.store.read()
        self.store.settle_run(self.ids,old_run,'late old result')
        after=self.store.read();after['revision']=before['revision'];self.assertEqual(after,before)
        with self.assertRaises(ValueError):self.service.action('shopee_post_pause',{'run_id':old_run})
        self.assertEqual(self.service.state()['posting_run']['id'],state['posting_run']['id'])

    def test_reset_order_keeps_previous_selected_order_then_other_unsent_rows(self):
        self.store.change(lambda s:s['posting_run'].update(ids=[self.ids[20],self.ids[13]]))
        state=self.reset();self.assertEqual(state['posting_run']['ids'][:2],[self.ids[20],self.ids[13]])
        self.assertEqual(len(set(state['posting_run']['ids'])),17)
