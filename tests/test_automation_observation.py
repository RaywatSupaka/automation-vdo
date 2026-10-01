import unittest
from core.automation_observation import attach_observation, public_observations

class ObservationTests(unittest.TestCase):
    def test_post_refresh_steps_are_recovering_not_failed_or_saved(self):
        for step in ('image_refresh_check', 'image_restart_pending', 'image_restart_started'):
            progress = {'ai_job_id': 'STORY-X', 'ai_run_id': 'RUN-1', 'ai_tab_id': 1, 'ai_step': step}
            self.assertTrue(attach_observation({}, progress, {'observed_at_ms': 100}, 'ai', now=50))
            self.assertEqual(progress['ai_observation']['phase'], 'recovering')
            self.assertFalse(progress['ai_observation']['desktop_saved'])

    def test_real_extension_functions(self):
        import subprocess
        from pathlib import Path
        result=subprocess.run(['node','tests/observation_368.js'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_http_progress_ack_and_stale_report(self):
        import tempfile, logging, json, urllib.request
        from core.local_bridge import LocalBridge
        from core.product_manager import ProductManager
        with tempfile.TemporaryDirectory() as root:
            bridge=LocalBridge('127.0.0.1',0,ProductManager(root),logging.getLogger('observation-test')).start()
            def post(path,data):
                req=urllib.request.Request(f'http://127.0.0.1:{bridge.server.server_address[1]}'+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req) as response:return json.load(response)
            try:
                post('/api/extension/heartbeat',{'client_id':'test','version':bridge.REQUIRED_EXTENSION_VERSION})
                p={'client_id':'test','scope':'chatgpt','job_id':'STORY-X','run_id':'RUN-TEST','tab_id':1,'step':'image_checkpoint_saved','observed_at_ms':200}
                self.assertTrue(post('/api/extension/progress',p)['ok'])
                self.assertTrue(post('/api/extension/progress',{**p,'step':'waiting_for_image','observed_at_ms':199})['ignored'])
                self.assertEqual(bridge.extension_status()['client']['ai_step'],'image_checkpoint_saved')
                post('/api/extension/progress',{**p,'scope':'observation','channel':'repair','step':'waiting_for_analysis'})
                self.assertEqual(bridge.extension_status()['client']['ai_step'],'image_checkpoint_saved')
                self.assertEqual(len(public_observations(bridge.extension_status())),2)
            finally:bridge.stop()

    def test_recovery_progress_keeps_completed_count_for_same_run(self):
        import tempfile, logging, json, urllib.request
        from core.local_bridge import LocalBridge
        from core.product_manager import ProductManager
        with tempfile.TemporaryDirectory() as root:
            bridge=LocalBridge('127.0.0.1',0,ProductManager(root),logging.getLogger('observation-recovery-test')).start()
            def post(data):
                req=urllib.request.Request(
                    f'http://127.0.0.1:{bridge.server.server_address[1]}/api/extension/progress',
                    data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req) as response:return json.load(response)
            try:
                client='recovery-test'
                req=urllib.request.Request(
                    f'http://127.0.0.1:{bridge.server.server_address[1]}/api/extension/heartbeat',
                    data=json.dumps({'client_id':client,'version':bridge.REQUIRED_EXTENSION_VERSION}).encode(),
                    headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req):pass
                base={'client_id':client,'scope':'chatgpt','job_id':'STORY-X','run_id':'RUN-1'}
                self.assertTrue(post({**base,'step':'waiting_for_image','image_count':3,'observed_at_ms':100})['ok'])
                self.assertTrue(post({**base,'step':'recovering_response','image_count':0,'observed_at_ms':101})['ok'])
                current=bridge.extension_status()['client']
                self.assertEqual(current['ai_step'],'recovering_response')
                self.assertEqual(current['ai_image_count'],3)
                self.assertTrue(post({**base,'job_id':'STORY-Y','run_id':'RUN-2',
                    'step':'preparing','image_count':0,'observed_at_ms':102})['ok'])
                self.assertEqual(bridge.extension_status()['client']['ai_image_count'],0)
            finally:bridge.stop()
    def test_result_is_not_saved_or_final(self):
        for step,expected in [('generation_complete','result_detected'),('complete','step_complete'),('image_checkpoint_saved','desktop_saved')]:
            p={'ai_job_id':'J','ai_run_id':'R','ai_tab_id':1,'ai_step':step}
            self.assertTrue(attach_observation({},p,{'observed_at_ms':100},'ai',now=50))
            self.assertEqual(p['ai_observation']['phase'],expected)
            self.assertEqual(p['ai_observation']['desktop_saved'],step=='image_checkpoint_saved')

    def test_out_of_order_and_duplicate_dont_replace_latest(self):
        client={}
        def send(ts):
            p={'ai_job_id':'J','ai_run_id':'R','ai_tab_id':1,'ai_step':'waiting_for_image'}
            ok=attach_observation(client,p,{'observed_at_ms':ts},'ai',now=50)
            if ok:
                p['ai_observation']['acknowledged'] = True
                client.update(p)
            return ok
        self.assertTrue(send(200));self.assertFalse(send(199));self.assertFalse(send(200));self.assertTrue(send(201))

    def test_busy_signal_and_public_filter(self):
        p={'flow_job_id':'J','flow_run_id':'R','flow_tab_id':1,'flow_step':'waiting_for_image'}
        attach_observation({},p,{'observed_at_ms':100,'response_active':True},'flow',now=40)
        self.assertEqual(public_observations({'clients':[p]})[0]['phase'],'generating')
