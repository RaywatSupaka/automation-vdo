import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from core.presenter import PresenterManager
from core.creation_queue import CreationQueue, clean_settings
from core.cancellable_process import hidden_process_kwargs
from ui.creation_queue import CreationQueueMixin
from ui.presenter import PresenterMixin


class Harness(PresenterMixin, CreationQueueMixin):
    pass


class PresenterSettingsProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='SmartFlow-settings-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = Harness()
        self.app.presenters = PresenterManager(self.root)
        self.job = self.app.presenters.create('Guide', 'Navy shirt speaker')
        self.ident = self.job['id']
        self.app.bridge = Mock()
        self.app.bridge.extension_status.return_value = {'connected': False}
        self.app.products = SimpleNamespace(get_job=lambda ident: {'automation_status': 'completed'})
        self.app.stories = SimpleNamespace(get=lambda ident: {'status': 'ready'})

    def ready(self):
        folder = self.app.presenters.folder(self.ident)
        (folder / 'clips').mkdir(exist_ok=True)
        (folder / 'exports').mkdir(exist_ok=True)
        clips = {}
        for i in range(1,4):
            name = f'clips/take_{i:02d}.mp4'
            (folder / name).write_bytes(b'synthetic checkpoint')
            clips[str(i)] = {'path': name}
        (folder / 'exports/presenter_green_screen.mp4').write_bytes(b'synthetic export')
        self.app.presenters.update(self.ident, status='ready', clips=clips)
        return {'enabled':True, 'id':self.ident, 'x':5, 'size':40}

    def test_defaults_empty_does_not_enable_new_jobs(self):
        state=self.app.presenters.defaults_state()
        self.assertFalse(state['available'])
        self.assertEqual(state['settings'], {'enabled':False})

    def test_atomic_saved_defaults_reload_and_snapshot_stays_frozen(self):
        selection=self.ready()
        saved=self.app._presenter_action('presenter_save_settings', {'settings':selection})['settings']
        snapshot=clean_settings({'presenter':self.app._presenter_selection({'enabled':True,'use_saved':True})})
        self.app.presenters.save_defaults({**selection,'x':95,'size':25})
        self.assertEqual(snapshot['presenter']['size'],40)
        self.assertEqual(snapshot['presenter']['x'],5)
        self.assertEqual(PresenterManager(self.root).defaults()['size'],25)
        self.assertEqual(saved['id'],self.ident)
        self.app.bridge.queue_extension_command.assert_not_called()

    def test_unready_and_missing_export_cannot_be_saved(self):
        with self.assertRaises(ValueError):self.app.presenters.save_defaults({'enabled':True,'id':self.ident})
        selection=self.ready()
        (self.app.presenters.folder(self.ident)/'exports/presenter_green_screen.mp4').unlink()
        with self.assertRaisesRegex(ValueError,'ไม่พร้อม'):self.app.presenters.save_defaults(selection)

    def test_missing_saved_clip_rejected_without_creating_media(self):
        self.app.presenters.save_defaults(self.ready())
        (self.app.presenters.folder(self.ident)/'clips/take_01.mp4').unlink()
        self.assertFalse(self.app.presenters.defaults_state()['available'])
        with self.assertRaises(ValueError):self.app._presenter_selection({'enabled':True,'use_saved':True})
        self.app.bridge.queue_extension_command.assert_not_called()

    def test_defaults_save_is_allowed_while_worker_runs(self):
        selection=self.ready()
        self.app._presenter_worker=Mock();self.app._presenter_worker.is_alive.return_value=True
        self.assertTrue(self.app._presenter_action('presenter_save_settings',{'settings':selection})['ok'])

    def remote(self, **values):
        client={'flow_job_id':'JOB-20260906-B13566','flow_step':'user_action_resolved',
                'flow_run_id':'','flow_tab_id':0,'flow_shot_index':0,**values}
        self.app.bridge.extension_status.return_value={'connected':True,'clients':[client]}

    def test_exact_completed_job_login_ghost_does_not_block(self):
        self.remote()
        self.assertEqual(self.app._creation_remote_busy_jobs(),set())
        self.app._product_pipeline_job_id='JOB-20260906-B13566'
        self.assertEqual(self.app._creation_idle_reason(),'')

    def test_fresh_owned_login_still_blocks_even_for_completed_manifest(self):
        self.remote(flow_run_id='RUN-current',flow_tab_id=5)
        self.assertTrue(self.app._creation_remote_busy_jobs())

    def test_generation_unknown_never_expires_by_age(self):
        self.remote(flow_step='generation_status_unknown',flow_updated_at='2020-01-01')
        self.assertTrue(self.app._creation_remote_busy_jobs())

    def test_nonterminal_job_passive_state_still_blocks(self):
        self.remote();self.app.products.get_job=lambda ident:{'automation_status':'running'}
        self.assertTrue(self.app._creation_remote_busy_jobs())

    def test_active_workers_and_manual_flow_still_block(self):
        self.remote();self.app._creation_product_worker=Mock()
        self.app._creation_product_worker.is_alive.return_value=True
        self.assertTrue(self.app._creation_idle_reason())
        self.app._creation_product_worker=None;self.app._manual_multi_flow_job_id='JOB-manual'
        self.assertTrue(self.app._creation_idle_reason())

    def test_progress_terminal_keeps_same_owner_and_stops_elapsed_clock(self):
        self.ready()
        self.app._presenter_progress={'id':self.ident,'run_id':'RUN-one','stage':'ready','started_at':100,'updated_at':160}
        progress=self.app._presenter_status()
        self.assertFalse(progress['active']);self.assertEqual(progress['clips'],3)
        self.assertEqual(progress['job_id'],self.ident);self.assertEqual(progress['elapsed'],60)
        self.app.bridge.queue_extension_command.assert_not_called()

    def test_progress_and_defaults_poll_never_starts_work(self):
        state=self.app._presenter_action('presenter_state',{})
        self.assertEqual(state['ui_version'],2);self.assertFalse(state['active'])
        self.app.bridge.queue_extension_command.assert_not_called()

    def test_unreadable_job_does_not_unlock_remote_worker(self):
        self.remote()
        def broken(ident):raise RuntimeError('bad checkpoint')
        self.app.products.get_job=broken
        self.assertTrue(self.app._creation_remote_busy_jobs())

    def test_focus_is_only_for_current_job_and_never_submits(self):
        self.app._activate_or_launch_chrome=Mock()
        self.app._presenter_progress={'id':self.ident,'service':'flow'}
        self.app.presenters.update(self.ident,run_id='RUN-present',intents={'flow_1':'RUN-owned'})
        self.app._presenter_action('presenter_focus',{'id':self.ident})
        self.app.bridge.queue_extension_command.assert_called_once_with('focus_flow_web',self.ident,1,run_id='RUN-owned')
        self.app._presenter_progress={'id':'another'}
        with self.assertRaises(ValueError):self.app._presenter_action('presenter_focus',{'id':self.ident})

    def test_missing_export_rejected_before_new_job_or_queue(self):
        selection=self.ready();self.app.presenters.save_defaults(selection)
        (self.app.presenters.folder(self.ident)/'exports/presenter_green_screen.mp4').unlink()
        with self.assertRaises(ValueError):self.app._presenter_selection(selection)
        self.assertFalse(self.app.presenters.defaults_state()['available'])

    def test_ui_actual_source_harness(self):
        result=subprocess.run(['node',str(Path(__file__).with_name('presenter_progress_ui_harness.js'))],capture_output=True,text=True,timeout=15,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])

    def queue_harness(self):
        self.app.story_queue=CreationQueue(self.root)
        self.app.cfg={}
        self.app._product_pipeline_options=lambda **kwargs:{'provider':'chatgpt','subtitle_enabled':True}
        self.app._resolve_desktop_reference_image=lambda value:''
        self.app._write_console=Mock()
        self.app._schedule_next_story_queue_item=Mock()  # Never dispatch real work.

    def test_real_batch_routes_persist_presenter_per_item_and_restart(self):
        self.queue_harness()
        selection=self.ready()
        for action,payload in [('enqueue_story_batch',{'topics':['เรื่องหนึ่ง','เรื่องสอง','เรื่องสาม']}),
                               ('creation_enqueue',{'mode':'product','values':['https://s.shopee.co.th/one','https://s.shopee.co.th/two']})]:
            result=self.app._creation_queue_action(action,{**payload,'presenter':selection})
            self.assertTrue(result['ok'])
        selection['size']=55
        self.app.presenters.save_defaults({**selection,'x':95})
        restored=CreationQueue(self.root)
        rows=restored.snapshot()['items']
        self.assertEqual(len(rows),5)
        for row in rows:
            self.assertEqual(row['settings']['presenter']['id'],self.ident)
            self.assertEqual(row['settings']['presenter']['size'],40)
            self.assertEqual(row['settings']['presenter']['x'],5)
        rows[0]['settings']['presenter']['size']=15
        self.assertEqual(restored.get_item(rows[0]['queue_id'])['settings']['presenter']['size'],40)
        self.assertTrue(restored.snapshot()['paused'])
        self.app.bridge.queue_extension_command.assert_not_called()

    def test_batch_off_does_not_inherit_saved_defaults(self):
        self.queue_harness();self.app.presenters.save_defaults(self.ready())
        for payload in [{'topics':['off'],'presenter':{'enabled':False}},{'topics':['legacy']}]:
            self.app._creation_queue_action('enqueue_story_batch',payload)
        for row in self.app.story_queue.snapshot()['items']:
            self.assertEqual(row['settings']['presenter'],{'enabled':False})
        self.app.bridge.queue_extension_command.assert_not_called()

    def test_missing_presenter_batch_rejected_without_partial_queue_or_submit(self):
        self.queue_harness();selection=self.ready()
        (self.app.presenters.folder(self.ident)/'exports/presenter_green_screen.mp4').unlink()
        with self.assertRaises(ValueError):
            self.app._creation_queue_action('enqueue_story_batch',{'topics':['one','two'],'presenter':selection})
        self.assertEqual(self.app.story_queue.snapshot()['items'],[])
        self.app._schedule_next_story_queue_item.assert_not_called()
        self.app.bridge.queue_extension_command.assert_not_called()

    def test_batch_ui_actual_controls_and_submit_harness(self):
        result=subprocess.run(['node',str(Path(__file__).with_name('presenter_queue_ui_harness.js'))],capture_output=True,text=True,timeout=15,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),{'ok':True,'cases':12})


if __name__=='__main__':unittest.main()
