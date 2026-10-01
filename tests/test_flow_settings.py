import tempfile
import json
import os
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from core.flow_settings import flow_settings, flow_capabilities, snapshot_flow
from core.creation_queue import CreationQueue, clean_settings
from core.drama_options import drama_render_options
from core.drama_series import DramaSeriesManager
from core.story_queue import StoryBatchQueue
from ui.flow_settings import flow_settings_action


class FlowSettingsTests(unittest.TestCase):
    def test_compact_snapshot_and_capability_context(self):
        defaults={'display':'compact','duration':'4s'}
        saved=snapshot_flow({},defaults)
        defaults['display']='unchanged'
        self.assertEqual(saved,{'display':'compact','duration':'4s'})
        self.assertEqual(flow_settings({'display':'unchanged'}),{'display':'compact'})
        self.assertEqual(clean_settings({'flow_settings':saved})['flow_settings'],saved)
        observed=flow_capabilities({'available':True,'states':{'resolution':'fixed_from_summary','duration':'invented'},
                                   'context':{'model':'Veo 3.1 - Fast','layout':'compact','secret':'discard'}})
        self.assertEqual(observed['states'],{'resolution':'fixed_from_summary'})
        self.assertEqual(observed['context']['layout'],'compact')
        self.assertNotIn('secret',observed['context'])

    def test_discovery_authenticated_bridge_roundtrip(self):
        from test_extension_command_reliability import _start_bridge, _heartbeat, _request_json
        with tempfile.TemporaryDirectory() as tmp:
            bridge,base=_start_bridge(Path(tmp))
            try:
                _heartbeat(base,'settings-client')
                queued=bridge.queue_extension_command('read_flow_settings')
                command=_request_json(base+'/api/extension/commands?client_id=settings-client')['commands'][0]
                ack={'command_id':queued['id'],'client_id':'settings-client','run_id':command['run_id'],
                     'lease_token':command['lease_token'],'ok':True,
                     'flow_capabilities':{'available':True,'model':['Observed'],'selected':{'model':'Observed'}}}
                self.assertTrue(_request_json(base+'/api/extension/command-ack',method='POST',payload=ack)['ok'])
                stored=bridge.extension_command_status(queued['id'])
                self.assertEqual(stored['flow_capabilities']['model'],['Observed'])
                self.assertEqual(stored['status'],'completed')
                self.assertTrue(_request_json(base+'/api/extension/command-ack',method='POST',payload=ack)['duplicate'])
            finally:
                bridge.stop()

    def test_offline_precreate_ui_contract(self):
        env=dict(os.environ)
        env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        from core.cancellable_process import hidden_process_kwargs
        run=subprocess.run(['node',str(Path(__file__).with_name('flow_settings_ui_harness.js'))],capture_output=True,text=True,encoding='utf-8',timeout=30,env=env,**hidden_process_kwargs())
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertEqual(json.loads(run.stdout),{'ok':True,'panels':7,'routes':9})

    def test_empty_legacy_does_not_force_model(self):
        self.assertEqual(flow_settings(), {'display':'compact'})
        self.assertEqual(snapshot_flow({}, {}), {'display':'compact'})
        self.assertNotIn('flow_settings', clean_settings({}))
        self.assertNotIn('flow_settings', drama_render_options({}))

    def test_first_login_and_failed_read_recover_without_replaying_creation(self):
        env = dict(os.environ)
        env.setdefault('NODE_PATH', str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        from core.cancellable_process import hidden_process_kwargs
        run = subprocess.run(['node', str(Path(__file__).with_name('flow_settings_login_recovery.cjs'))],
                             capture_output=True, text=True, encoding='utf-8', timeout=30,
                             env=env, **hidden_process_kwargs())
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertTrue(json.loads(run.stdout)['lateReadIgnored'])

    def test_invalid_choices_fail_before_dispatch(self):
        for value in ([], {'outputs':2}, {'outputs':True}, {'display':'mobile'}, {'model':42},
                      {'duration':'4s\n'}, {'video_type':'anything'}, {'aspect_ratio':'16:9'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                flow_settings(value)

    def test_snapshot_separate_from_defaults(self):
        defaults={'model':'Observed model','duration':'4s'}
        value=snapshot_flow({},defaults);defaults['duration']='8s'
        self.assertEqual(value['duration'],'4s')
        self.assertEqual(snapshot_flow({'flow_settings':{}},defaults),{'display':'compact'})

    def test_queue_reload_and_defaults_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue=CreationQueue(Path(tmp)/'queue.json')
            options={'flow_settings':{'duration':'4s','resolution':'720p'}}
            queue.enqueue('product',['https://s.shopee.co.th/test1','https://s.shopee.co.th/test2'],settings=options)
            options['flow_settings']['duration']='8s'
            items=CreationQueue(Path(tmp)/'queue.json').snapshot()['items']
            self.assertEqual([i['settings']['flow_settings']['duration'] for i in items],['4s','4s'])

    def test_series_and_each_ep_keep_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=DramaSeriesManager(Path(tmp));queue=StoryBatchQueue(Path(tmp)/'queue.json')
            options={'video_generation_mode':'google_flow','flow_settings':{'duration':'6s'}}
            series=manager.create('test',episode_count=2,characters=[{'name':'A'}],render_options=options)
            result=queue.enqueue_drama_series(series['id'],'test',2,render_options=series['render_options'])
            options['flow_settings']['duration']='10s'
            self.assertEqual(manager.episode_context(series['id'],1)['render_options']['flow_settings']['duration'],'6s')
            self.assertTrue(all(i['render_options']['flow_settings']['duration']=='6s' for i in result['items']))

    def test_capabilities_have_no_unobserved_model_or_price(self):
        result=flow_capabilities({'available':True,'model':['One'], 'selected':{'model':'One'},'cookie':'secret'})
        self.assertEqual(result['model'],['One']);self.assertEqual(result['credit_notice'],'')
        self.assertNotIn('cookie',result);self.assertEqual(result['scope'],'visible_menu_only')

    def test_discovery_busy_guard_and_result_identity(self):
        app=SimpleNamespace(cfg={},bridge=Mock(),_creation_idle_reason=lambda:'งานกำลังทำ')
        self.assertEqual(flow_settings_action(app,'flow_settings_read',{}),
                         {'ok':False,'blocked':True,'error':'งานกำลังทำ','command_id':None})
        app.bridge.queue_extension_command.assert_not_called()
        app.bridge.extension_command_status.return_value={'action':'open_flow','status':'completed'}
        with self.assertRaises(ValueError):flow_settings_action(app,'flow_settings_result',{'command_id':'x'})

    def test_save_only_flow_defaults(self):
        app=SimpleNamespace(cfg={'subtitle_auto_after_voice':True})
        store=Mock();store.update.side_effect=lambda f:f({'audio_background_volume':0.3})
        with patch('core.config._config_store',return_value=store):
            self.assertEqual(flow_settings_action(app,'flow_settings_save',{'settings':{'duration':'4s'}})['settings'],{'display':'compact','duration':'4s'})
        self.assertTrue(app.cfg['subtitle_auto_after_voice'])
        self.assertEqual(store.update.call_args.args[0]({'audio_background_volume':0.3})['audio_background_volume'],0.3)
