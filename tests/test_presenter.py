import base64
import io
import json
import logging
import subprocess
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image
from core.presenter import PresenterManager, PresenterRenderer, presenter_settings, screen_quality, apply_presenter
from core.presenter_pipeline import PresenterPipeline
from core.product_manager import ProductManager
from core.local_bridge import LocalBridge
from core.cancellable_process import OperationCancelled, hidden_process_kwargs


def image_data(color='#00ff00'):
    stream = io.BytesIO()
    Image.new('RGB', (360,640), color).save(stream, format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()


class PresenterTests(unittest.TestCase):
    def test_extension_single_image_protocol(self):
        harness=Path(__file__).with_name('presenter_extension_harness.js')
        result=subprocess.run(['node',str(harness)],capture_output=True,text=True,timeout=15,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout),{'ok':True,'cases':9})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='SmartFlow-presenter-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager = PresenterManager(self.root)
        self.job = self.manager.create('Guide', 'Friendly navy clothed speaker')
        self.ident = self.job['id']

    def saved_image(self, **changes):
        self.manager.update(self.ident, status='running', run_id='run1', **changes)
        self.manager.claim_image(self.ident, 'run1')
        return self.manager.save_image(self.ident, 'run1', image_data())

    def test_new_image_is_text_first_and_no_voice(self):
        pkg = self.manager.plugin_request(self.ident)
        self.assertEqual(pkg['mode'], 'presenter')
        self.assertEqual(pkg['request']['image_count'], 1)
        self.assertFalse(pkg['job']['source_images'])
        self.assertIn('no reference image is required', pkg['prompt'])
        self.assertNotIn('scene before', pkg['prompt'])
        self.assertNotIn('narration', pkg['prompt'])

    def test_reference_is_copied_with_consent_and_not_changed(self):
        ref=self.root/'source.png'; Image.new('RGB',(360,640),'red').save(ref)
        before=ref.read_bytes()
        with self.assertRaises(ValueError): self.manager.create('Ref','Person',reference=ref)
        job=self.manager.create('Ref','Person',reference=ref,consent=True,screen='blue',style='anime')
        self.assertEqual(before,ref.read_bytes())
        self.assertEqual(job['source_images'],['source/reference.png'])
        self.assertIn('same identity',self.manager.image_prompt(job))
        self.assertIn('2D anime',self.manager.image_prompt(job))

    def test_invalid_options_and_path_are_rejected(self):
        for bad in ['../x','PRESENTER-/x','JOB-123']:
            with self.assertRaises(ValueError): self.manager.folder(bad)
        for fields in [{'screen':'red'},{'provider':'API'},{'style':'unknown'},{'description':''}]:
            with self.assertRaises(ValueError): self.manager.create(**{'name':'name','description':'person',**fields})
        for fields in [{'id':'../x'},{'size':90},{'x':-1},{'y':float('nan')},{'blend':1},{'timing':'whatever'}]:
            with self.assertRaises(ValueError): presenter_settings({'enabled':True,'id':self.ident,**fields})
        self.assertEqual(presenter_settings(None),{'enabled':False})

    def test_image_claim_is_durable_and_single(self):
        job=self.saved_image()
        self.assertEqual(job['status'],'running')
        self.assertTrue(job['image_quality']['passed'])
        restored=PresenterManager(self.root)
        self.assertEqual(restored.get(self.ident)['intents']['image'],'run1')
        with self.assertRaises(ValueError): restored.claim_image(self.ident,'run1')

    def test_stale_cancelled_or_unclaimed_image_is_rejected(self):
        self.manager.update(self.ident,status='running',run_id='run1')
        with self.assertRaises(ValueError): self.manager.save_image(self.ident,'run1',image_data())
        self.manager.claim_image(self.ident,'run1')
        with self.assertRaises(ValueError): self.manager.save_image(self.ident,'old',image_data())
        self.manager.update(self.ident,status='cancelled')
        with self.assertRaises(ValueError): self.manager.save_image(self.ident,'run1',image_data())
        self.assertFalse((self.manager.folder(self.ident)/'generated/character.png').exists())

    def test_bad_screen_and_requested_review_pause(self):
        job=self.saved_image(review_image=True)
        self.assertEqual(job['status'],'image_review')
        self.assertFalse(screen_quality(Image.new('RGB',(100,100),'red'),'green')['passed'])
        self.assertTrue(screen_quality(Image.new('RGB',(100,100),'blue'),'blue')['passed'])

    def test_three_flow_packages_use_same_canonical_portrait(self):
        self.saved_image()
        packages=[self.manager.flow_package(self.ident,i) for i in (1,2,3)]
        self.assertEqual([p['image_files'] for p in packages],[['generated/character.png']]*3)
        self.assertEqual(len({p['video_prompt'] for p in packages}),3)
        for pkg in packages:
            self.assertIn('Static locked camera',pkg['video_prompt'])
            self.assertIn('No specific dialogue',pkg['video_prompt'])
            self.assertIn('solid flat saturated green',pkg['video_prompt'])
        with self.assertRaises(ValueError): self.manager.flow_package(self.ident,4)

    def test_missing_assets_do_not_trigger_generation(self):
        with self.assertRaises(ValueError): self.manager.assets({'enabled':True,'id':self.ident})
        with patch('core.presenter.PresenterRenderer.overlay') as render:
            output,plan=apply_presenter(self.root,'original.mp4','new.mp4',{'enabled':False})
            self.assertEqual(str(output),'original.mp4');self.assertFalse(plan['enabled']);render.assert_not_called()

    def test_bridge_routes_and_stale_run_guard(self):
        bridge=LocalBridge('127.0.0.1',0,ProductManager(self.root),logging.getLogger('presenter-test'),presenters=self.manager).start()
        self.addCleanup(bridge.stop)
        base=f'http://127.0.0.1:{bridge.server.server_address[1]}'
        def post(data):
            req=urllib.request.Request(base+'/api/presenters/image', data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
            return json.load(urllib.request.urlopen(req))
        self.manager.update(self.ident,status='running',run_id='RUN-test1')
        bridge.queue_extension_command('open_chatgpt',self.ident,run_id='RUN-test1')
        pkg=json.load(urllib.request.urlopen(base+f'/api/presenters/{self.ident}/chatgpt-package'))['package']
        self.assertEqual(pkg['image_urls'],[])
        self.assertTrue(post({'job_id':self.ident,'run_id':'RUN-test1','action':'claim'})['ok'])
        with self.assertRaises(urllib.error.HTTPError): post({'job_id':self.ident,'run_id':'stale','action':'save','image':image_data()})
        self.assertTrue(post({'job_id':self.ident,'run_id':'RUN-test1','action':'save','image':image_data()})['ok'])
        pkg=json.load(urllib.request.urlopen(base+f'/api/jobs/{self.ident}/flow-package?shot_index=2'))['package']
        self.assertIn('/api/presenters/',pkg['image_urls'][0])
        self.assertTrue(urllib.request.urlopen(pkg['image_urls'][0]).read().startswith(b'\x89PNG'))
        with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(base+f'/api/presenters/{self.ident}/files/../presenter.json/../../nope')

    def test_pipeline_checkpoint_skips_first_take_and_inspects_second(self):
        self.saved_image()
        folder=self.manager.folder(self.ident)
        first=folder/'clips/take_01.mp4';first.write_bytes(b'fixture-only')
        self.manager.update(self.ident,clips={'1':{'path':'clips/take_01.mp4'}},intents={'image':'run1','flow_1':'run1','flow_2':'old-flow'})
        bridge=Mock(); bridge.REQUIRED_EXTENSION_VERSION='test'
        download=Mock(return_value=first)
        pipeline=PresenterPipeline(self.manager,bridge,Mock(),download,threading.Event())
        def save(ident,index,path,run):
            job=self.manager.get(ident);job['clips'][str(index)]={'path':'clips/take_01.mp4'}
            return self.manager.update(ident,clips=job['clips'])
        with patch.object(pipeline,'wait'),patch.object(self.manager,'save_clip',side_effect=save),patch('core.presenter_pipeline.PresenterRenderer') as renderer:
            pipeline.run(self.ident,'run1')
        commands=bridge.queue_extension_command.call_args_list
        self.assertEqual([c.args[0] for c in commands],['inspect_flow','download_flow_result','open_flow','download_flow_result'])
        self.assertEqual(commands[0].kwargs['run_id'],'old-flow')
        self.assertEqual(download.call_count,2)
        self.assertEqual(self.manager.get(self.ident)['status'],'ready')
        renderer.return_value.join.assert_called_once()

    def test_pipeline_stops_before_submit_when_image_claim_uncertain(self):
        self.manager.update(self.ident,status='running',run_id='run1',intents={'image':'run1'})
        bridge=Mock();pipeline=PresenterPipeline(self.manager,bridge,Mock(),Mock(),threading.Event())
        with self.assertRaises(RuntimeError):pipeline.run(self.ident,'run1')
        bridge.queue_extension_command.assert_not_called()

    def test_cancel_does_not_make_commands(self):
        self.saved_image();event=threading.Event();event.set();bridge=Mock()
        pipeline=PresenterPipeline(self.manager,bridge,Mock(),Mock(),event)
        with self.assertRaises(OperationCancelled):pipeline.run(self.ident,'run1')
        bridge.queue_extension_command.assert_not_called()

    def test_cancelling_pending_commands_is_scoped(self):
        self.saved_image()
        bridge=LocalBridge('127.0.0.1',0,ProductManager(self.root),logging.getLogger('presenter-cancel'),presenters=self.manager)
        queued=bridge.queue_extension_command('open_flow',self.ident,1,run_id='RUN-test')
        other=self.manager.create('Other','person')
        unrelated=bridge.queue_extension_command('open_chatgpt',other['id'],run_id='RUN-other')
        self.manager.update(self.ident,status='cancelled')
        bridge.cancel_presenter_pending_commands(self.ident)
        self.assertEqual(bridge.extension_command_status(queued['id'])['status'],'cancelled')
        self.assertEqual(bridge.extension_command_status(unrelated['id'])['status'],'pending')
        with self.assertRaises(ValueError):self.manager.flow_package(self.ident,1)

    def test_approval_is_sent_once_for_current_flow_run(self):
        client={'version':'test','flow_job_id':self.ident,'flow_run_id':'RUN-current','flow_shot_index':2,'flow_step':'awaiting_credit_approval'}
        bridge=Mock();bridge.REQUIRED_EXTENSION_VERSION='test'
        bridge.extension_status.side_effect=[{'clients':[client]},{'clients':[client]}, {'clients':[{**client,'flow_step':'generation_complete'}]}]
        event=Mock();event.is_set.return_value=False;event.wait.return_value=False
        pipeline=PresenterPipeline(self.manager,bridge,Mock(),Mock(),event)
        pipeline.wait(self.ident,'flow','RUN-current',lambda c:c['flow_step']=='generation_complete',shot=2)
        bridge.queue_extension_command.assert_called_once_with('approve_flow_credit',self.ident,2,run_id='RUN-current')

    def test_policy_failure_stops_without_new_generation(self):
        bridge=Mock();bridge.REQUIRED_EXTENSION_VERSION='test'
        bridge.extension_status.return_value={'clients':[{'version':'test','flow_job_id':self.ident,'flow_run_id':'RUN-current','flow_shot_index':1,'flow_step':'generation_failed','flow_message':'policy refusal'}]}
        pipeline=PresenterPipeline(self.manager,bridge,Mock(),Mock(),threading.Event())
        with self.assertRaisesRegex(RuntimeError,'policy refusal'):pipeline.wait(self.ident,'flow','RUN-current',lambda c:False,shot=1)
        bridge.queue_extension_command.assert_not_called()

    def test_ui_reference_upload_does_not_change_story_and_snapshot_survives(self):
        from ui.main_window import MainWindow
        from core.creation_queue import clean_settings
        from types import SimpleNamespace
        fake=SimpleNamespace(story_main_image=Mock())
        with patch('ui.main_window.ROOT',self.root):
            result=MainWindow._save_desktop_reference_image(fake,{'data_url':image_data(),'purpose':'presenter'})
        self.assertTrue(Path(result['path']).is_file())
        fake.story_main_image.set.assert_not_called()
        selected=presenter_settings({'enabled':True,'id':self.ident,'x':5,'size':40})
        snapshot=clean_settings({'presenter':selected,'api_key':'not-to-save'})
        self.assertEqual(snapshot['presenter'],selected)
        self.assertNotIn('api_key',snapshot)

    def test_ui_create_and_media_adapter_without_a_browser(self):
        from ui.presenter import PresenterMixin
        from types import SimpleNamespace
        fake=SimpleNamespace(presenters=self.manager,_presenter_busy=lambda:False,
            _creation_idle_reason=lambda **kwargs:'',
            _creation_workers_alive=lambda:False,_creation_remote_busy_jobs=lambda:set(),
            _resolve_desktop_reference_image=lambda x:x)
        result=PresenterMixin._presenter_action(fake,'presenter_create',{'name':'Test2','description':'a guide'})
        self.assertTrue(result['ok']);self.assertEqual(result['job']['status'],'draft')
        self.saved_image()
        image=PresenterMixin._presenter_media(fake,f'presenter:{self.ident}:image')
        self.assertTrue(Path(image).is_file())
        with self.assertRaises(ValueError):PresenterMixin._presenter_media(fake,f'presenter:{self.ident}:../presenter.json')

    def test_no_ready_before_three_valid_saved_clips(self):
        self.saved_image();source=self.root/'download.mp4';source.write_bytes(b'fake-media')
        with patch('core.presenter.PresenterRenderer') as renderer:
            renderer.return_value.info.return_value={'duration':3,'width':360,'height':640}
            renderer.return_value.inspect_screen.return_value={'passed':False}
            job=self.manager.save_clip(self.ident,1,source,'run1')
            self.assertEqual(job['status'],'clip_review')
            self.manager.update(self.ident,status='running')
            with self.assertRaisesRegex(ValueError,'ซ้ำ'):self.manager.save_clip(self.ident,2,source,'run1')
        self.assertEqual(len(self.manager.get(self.ident)['clips']),1)


class PresenterRenderTests(unittest.TestCase):
    def test_real_silent_join_keying_loop_audio_and_cancellation(self):
        with tempfile.TemporaryDirectory(prefix='SmartFlow-presenter-render-') as temp:
            root=Path(temp);renderer=PresenterRenderer()
            def ff(args):
                result=subprocess.run([str(renderer.ffmpeg),'-v','error','-y',*args],capture_output=True,**hidden_process_kwargs())
                self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            clips=[]
            for i in range(3):
                path=root/f'take{i}.mp4';clips.append(path)
                ff(['-f','lavfi','-i','color=c=0x00ff00:s=180x320:r=12:d=1.1','-vf','drawbox=x=65:y=70:w=50:h=170:color=red:t=fill','-c:v','libx264','-pix_fmt','yuv420p',str(path)])
            joined=renderer.join(clips,root/'joined.mp4')
            self.assertTrue(renderer.inspect_screen(joined,'green')['passed'])
            main=root/'main.mp4'
            ff(['-f','lavfi','-i','color=c=blue:s=180x320:r=12:d=4.5','-f','lavfi','-i','sine=frequency=440:duration=4.5','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(main)])
            result=renderer.overlay(main,joined,root/'overlay.mp4',{'enabled':True,'id':'PRESENTER-123456ABCDEF','size':50},'green')
            data=json.loads(subprocess.check_output([str(renderer.ffprobe),'-v','error','-show_streams','-show_format','-of','json',str(result)],**hidden_process_kwargs()))
            video=next(s for s in data['streams'] if s['codec_type']=='video')
            self.assertEqual(video['codec_name'],'h264');self.assertEqual(video['pix_fmt'],'yuv420p');self.assertEqual(video['profile'],'High')
            self.assertEqual(len([s for s in data['streams'] if s['codec_type']=='audio']),1)
            self.assertAlmostEqual(float(data['format']['duration']),4.5,delta=.2)
            raw=subprocess.check_output([str(renderer.ffmpeg),'-v','error','-ss','4','-i',str(result),'-frames:v','1','-f','image2pipe','-vcodec','png','-'],**hidden_process_kwargs())
            with Image.open(io.BytesIO(raw)) as im:
                pixels=list(im.convert('RGB').getdata())
                self.assertGreater(sum(r>b*2 and r>g*2 for r,g,b in pixels),200)
                self.assertLess(sum(g>r*2 and g>b*2 for r,g,b in pixels),30)
            silent=json.loads(subprocess.check_output([str(renderer.ffprobe),'-v','error','-show_streams','-of','json',str(joined)],**hidden_process_kwargs()))
            self.assertFalse(any(s['codec_type']=='audio' for s in silent['streams']))
            event=threading.Event();event.set();before=result.read_bytes()
            with self.assertRaises(OperationCancelled):renderer.overlay(main,joined,result,{'enabled':True,'id':'PRESENTER-123456ABCDEF'},'green',event)
            self.assertEqual(result.read_bytes(),before)


if __name__=='__main__':unittest.main()
