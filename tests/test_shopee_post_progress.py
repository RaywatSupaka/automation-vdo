import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.shopee_posting.service import ShopeePosting
from core.shopee_posting.options import DEFAULT_OPTIONS
from core.shopee_posting.progress import snapshot, selection_ids, start_run
from core.shopee_posting.store import PostingStore


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.wifi=Mock()
        self.wifi.state.return_value={'selected':{'device_id':'phone','model':'Test phone'}}
        self.service=ShopeePosting(self.root,Mock(),self.wifi,validator=Mock());self.store=self.service.store
        self.ids=self.store.add([dict(item_id='fixture:'+str(i),title='Product '+str(i),caption='Caption '+str(i),
            product_url='https://s.shopee.co.th/fixture',video_path='fixture.mp4') for i in range(35)])
        self.store.change(lambda s:s.update(account={'name':'test','device_id':'phone'}))

    def begin(self,ids=None):
        with patch('core.shopee_posting.service.threading.Thread'):
            self.service.action('shopee_post_start',{'ids':ids or self.ids,'confirm':True,'revision':self.store.read()['revision']})
        return self.store.read()['posting_run']['id']

    def run_state(self):
        return self.service.state()['posting_run']

    def test_select_over_30_is_single_owned_sequential_run(self):
        self.begin();r=self.run_state();self.assertEqual(r['total'],35);self.assertEqual(r['ids'],self.ids)
        self.assertEqual(r['account'],'test');self.assertEqual(r['phone'],'Test phone')
        self.assertTrue(all(x['phase']=='queued' for x in self.store.read()['items']))

    def test_preexisting_published_is_not_current_success(self):
        self.store.transition(self.ids[0],{'draft'},'published')
        self.begin(self.ids[1:]);r=self.run_state();self.assertEqual(r['completed'],0);self.assertEqual(r['total'],34)
        self.assertNotIn(self.ids[0],r['rows'])

    def test_invalid_ids_abort_atomically(self):
        before=self.store.read()
        with self.assertRaises(ValueError):self.begin([self.ids[0],'missing'])
        self.assertEqual(self.store.read(),before)
        for bad in ([],None,[1],[self.ids[0]]*2):
            with self.subTest(bad=bad),self.assertRaises(ValueError):selection_ids(bad)

    def test_sent_is_not_complete_until_verified(self):
        self.begin(self.ids[:2]);i=self.ids[0]
        self.store.transition(i,{'queued'},'checking',message='checking')
        self.store.transition(i,{'checking'},'processing',message='sent waiting')
        self.assertEqual(self.run_state()['completed'],0);self.assertEqual(self.run_state()['current']['step'],'verify')
        self.store.transition(i,{'processing'},'published',message='verified')
        self.assertEqual(self.run_state()['completed'],1);self.assertEqual(self.run_state()['remaining'],1)

    def test_fast_completions_not_lost_between_ui_polls(self):
        rid=self.begin(self.ids[:2])
        for i in self.ids[:2]:self.store.transition(i,{'queued'},'published',message='verified')
        self.store.settle_run(self.ids[:2],rid,'complete')
        r=self.run_state();self.assertEqual(r['status'],'complete');self.assertEqual(r['completed'],2)
        self.assertEqual(sum(e['phase']=='published' for e in r['events']),2)

    def test_progress_persists_and_has_actual_substeps(self):
        self.begin(self.ids[:1]);i=self.ids[0]
        self.store.transition(i,{'queued'},'editing',message='select')
        self.store.progress(i,'caption','writing caption');self.store.progress(i,'product','attaching product')
        r=snapshot(PostingStore(self.root).read()['posting_run'])
        self.assertEqual(r['current']['step'],'product');self.assertEqual(r['current_index'],1)
        self.assertEqual([e['step'] for e in r['events']],['select_video','caption','product'])

    def test_error_remembers_where_it_stopped(self):
        rid=self.begin(self.ids[:2]);i=self.ids[0]
        self.store.transition(i,{'queued'},'editing');self.store.progress(i,'product','attaching')
        self.store.settle_run(self.ids[:2],rid,'cannot attach')
        r=self.run_state();self.assertEqual(r['status'],'review');self.assertEqual(r['review_count'],1)
        self.assertEqual(r['current']['last_step'],'product');self.assertEqual(r['remaining'],1)

    def test_pause_before_first_row_no_fake_error_or_success(self):
        rid=self.begin(self.ids[:2]);self.service.action('shopee_post_pause',{'run_id':rid})
        self.assertEqual(self.run_state()['status'],'pausing')
        self.store.settle_run(self.ids[:2],rid,'paused',True)
        r=self.run_state();self.assertEqual(r['status'],'paused');self.assertEqual(r['completed'],0);self.assertEqual(r['remaining'],2)

    def test_restart_keeps_intent_and_requires_review_not_replay(self):
        self.begin(self.ids[:2]);i=self.ids[0]
        self.store.transition(i,{'queued'},'send_pending',publish_intent={'id':'durable'})
        self.store.recover();r=self.run_state()
        self.assertEqual(r['status'],'interrupted');self.assertEqual(r['rows'][i]['phase'],'unknown')
        self.assertEqual(self.store.read()['items'][0]['publish_intent'],{'id':'durable'})
        self.assertEqual(r['completed'],0)

    def test_recover_prepared_owned_row_not_left_running(self):
        self.begin(self.ids[:1]);self.store.transition(self.ids[0],{'queued'},'prepared');self.store.recover()
        self.assertEqual(self.run_state()['current']['phase'],'review')

    def test_finished_run_is_not_rewritten_on_restart(self):
        rid=self.begin(self.ids[:1]);self.store.transition(self.ids[0],{'queued'},'published');self.store.settle_run(self.ids[:1],rid,'done')
        before=self.run_state();self.store.recover();self.assertEqual(self.run_state(),before)

    def test_old_worker_or_popup_cannot_change_new_run(self):
        old=self.begin(self.ids[:1]);self.store.settle_run(self.ids[:1],old,'paused',True);self.service._busy=False
        new=self.begin(self.ids[1:2]);before=self.run_state()
        self.store.settle_run(self.ids[:1],old,'late old error');self.assertEqual(self.run_state(),before)
        with self.assertRaises(ValueError):self.service.action('shopee_post_pause',{'run_id':old})
        self.assertFalse(self.service._pause.is_set());self.assertEqual(self.run_state()['id'],new)

    def test_old_row_transition_not_observed_by_new_run(self):
        rid=self.begin(self.ids[:1]);self.store.settle_run(self.ids[:1],rid,'paused',True);self.service._busy=False
        self.begin(self.ids[1:2]);before=self.run_state()
        self.store.transition(self.ids[0],{'draft'},'review',message='old');self.assertEqual(self.run_state(),before)

    def test_events_are_bounded_and_duplicate_messages_deduped(self):
        self.begin(self.ids[:1]);i=self.ids[0];self.store.transition(i,{'queued'},'editing')
        for n in range(95):self.store.progress(i,'caption',str(n))
        r=self.run_state();self.assertEqual(len(r['events']),80);seq=r['sequence']
        self.store.progress(i,'caption','94');self.assertEqual(self.run_state()['sequence'],seq)

    def test_invalid_stage_preserves_data(self):
        before=self.store.read()
        with self.assertRaises(ValueError):self.store.progress(self.ids[0],'made_up','no')
        self.assertEqual(self.store.read(),before)

    def test_thread_start_failure_settles_queue(self):
        with patch('core.shopee_posting.service.threading.Thread') as cls:
            cls.return_value.start.side_effect=RuntimeError('cannot start')
            with self.assertRaises(RuntimeError):self.service.action('shopee_post_start',{'ids':self.ids,'confirm':True,'revision':self.store.read()['revision']})
        self.assertFalse(self.service.state()['busy']);self.assertEqual(self.run_state()['status'],'review')
        self.assertTrue(all(r['phase']=='draft' for r in self.store.read()['items']))

    def test_bulk_options_over_30_stays_selected_only(self):
        self.store.save_options(self.store.read()['revision'],{**DEFAULT_OPTIONS,'allow_reuse':True},self.ids[1:])
        rows=self.store.read()['items'];self.assertFalse(rows[0]['post_options']['allow_reuse'])
        self.assertTrue(all(r['post_options']['allow_reuse'] for r in rows[1:]))

    def test_actual_source_progress_ui(self):
        result=subprocess.run(['node',str(Path(__file__).with_name('shopee_post_progress_ui.cjs'))],capture_output=True,text=True,encoding='utf-8',timeout=100)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_device_wait_preserves_step_and_terminal_is_not_running(self):
        rid=self.begin(self.ids[:1]);i=self.ids[0]
        self.store.transition(i,{'queued'},'editing');self.store.progress(i,'product','attach')
        self.store.device_observation(i,True,'waiting',{'foreground_package':'android'})
        self.assertTrue(self.run_state()['current']['waiting_for_device'])
        self.assertEqual(self.run_state()['current']['step'],'product')
        self.store.settle_run([i],rid,'phone not ready')
        self.assertFalse(self.run_state()['current']['waiting_for_device'])
        self.assertEqual(self.run_state()['uncertain_count'],0)

    def test_sent_state_is_uncertain_even_in_legacy_progress(self):
        rid=self.begin(self.ids[:1]);i=self.ids[0]
        self.store.transition(i,{'queued'},'processing',publish_intent={'id':'test'})
        self.assertEqual(self.run_state()['uncertain_count'],1)
        self.store.settle_run([i],rid,'unconfirmed')
        self.assertEqual(self.run_state()['uncertain_count'],1)
