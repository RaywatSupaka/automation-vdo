import copy
import subprocess
import threading
import unittest
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import patch
from core.atomic_json import AtomicJsonFile
from core.flow_review import ready_home_replacement, request_scene_repair_resume
from core.scene_pipeline import ScenePipeline
from core.scene_progress_view import scene_progress_view
from core.cancellable_process import hidden_process_kwargs
from ui.story_flow_resume import start_saved_flow_scene, finish_saved_flow_scene
import test_flow_replacement as replacement_fixture


class FlowDirectResume408Tests(unittest.TestCase):
    setUp = replacement_fixture.FlowReplacementTests.setUp
    image = replacement_fixture.FlowReplacementTests.image
    act = replacement_fixture.FlowReplacementTests.act

    def prepared(self):
        self.act('begin'); self.act('image', image=self.image())
        prompt = 'Vertical 9:16. A newly invented adult character quietly sorts papers in a workshop. All spoken dialogue must be in Thai only.'
        self.act('ready', candidate=dict(prompt=prompt, needs_review=False, reference_compatible=True, material_change=False))
        self.job.update(status='error', last_error='ภาพใหม่หรือหลักฐานก่อนเปิดโปรเจกต์ยังไม่ตรง ไม่ส่งสร้างซ้ำ',
                        scene_pipeline_version=1, video_generation_mode='google_flow', scene_count=2,
                        audio_choices={'mode': 'none'})
        source=dict(phase='needs_review',request_id='prior',project_path='/project/old',fingerprint='fp',original_prompt='original')
        ready=dict(phase='ready',request_id=self.body['request_id'],run_id='OLD',project_path='/',fingerprint='fp',
                   original_prompt='original',prompt=prompt,alternative=True,alternative_stage='motion_sent')
        review={**ready,'phase':'needs_review','digest':'home-review','pause_reason':'ต้องตรวจผลเดิมก่อนย้ายโปรเจกต์','at':'2026-09-22'}
        self.rows=[source,{**ready,'phase':'requested'},ready,review]
        self.store=AtomicJsonFile(self.folder/'prompts/flow_recovery.json')
        self.store.write({'scenes':{'1':self.rows}})
        self.permit=request_scene_repair_resume(self.folder,self.job)
        return ready_home_replacement(self.folder,self.job,1,self.permit)

    def test_desktop_proves_ready_without_browser_storage(self):
        proof=self.prepared()
        self.assertEqual(proof['request_id'],self.body['request_id'])
        self.assertEqual(proof['source_project_path'],'/project/old')
        self.assertTrue((self.folder/proof['image_file']).is_file())
        self.assertEqual(request_scene_repair_resume(self.folder,self.job),self.permit)

    def test_no_unknown_video_or_changed_media_replay(self):
        proof=self.prepared()
        for mode in ['submitted','fresh','no-ready','wrong-digest','wrong-source','different-prompt','completed-clip']:
            with self.subTest(mode=mode):
                rows=copy.deepcopy(self.rows);permit=dict(self.permit);job=dict(self.job)
                if mode=='submitted': rows.insert(-1,{**rows[-2],'phase':'submitted'})
                if mode=='fresh': rows[-2]['fresh_project']={'phase':'opening'}
                if mode=='no-ready': rows[-2]['phase']='rewrite_sent'
                if mode=='wrong-digest': permit['event_digest']='OTHER'
                if mode=='wrong-source': rows[0]['fingerprint']='OTHER'
                if mode=='different-prompt': rows[-1]['prompt']='OTHER'
                if mode=='completed-clip': job['flow_clips']={'1':'saved.mp4'}
                self.store.write({'scenes':{'1':rows}})
                self.assertIsNone(ready_home_replacement(self.folder,job,1,permit))
        self.store.write({'scenes':{'1':self.rows}})
        (self.folder/proof['image_file']).write_bytes(b'changed')
        with self.assertRaises(ValueError):ready_home_replacement(self.folder,self.job,1,self.permit)

    def app(self):
        self.prepared();calls=[]
        # Match the fixture folder without creating or reading any live Job.
        # Proof reads a package context including job ID, so keep the actual
        # job id in the fake manager root instead of renaming fixture media.
        class FolderRoot:
            def __truediv__(inner, name):return self.folder
        self.job['id']='STORY-TEST';self.permit['job_id']='STORY-TEST'
        app=SimpleNamespace(_story_cancel_event=threading.Event(),_story_pipeline_job_id='STORY-TEST',
            _story_scene_threads={},cfg={},events=Queue(),
            stories=SimpleNamespace(root=FolderRoot(),get=lambda _:self.job,
                prepare_scene_pipeline=lambda *a:self.job,mark_running=lambda *a:calls.append(('running',a))),
            bridge=SimpleNamespace(_extension_runs={},clear_ai_progress=lambda *a:calls.append(('clear',a)),
                queue_extension_command=lambda *a:calls.append(('command',a))),
            root=SimpleNamespace(after=lambda ms,fn:calls.append(('monitor',ms))),
            _update_story_progress=lambda p:calls.append(('progress',p)),
            _start_story_scene_worker=lambda p:calls.append(('worker',p)),
            _monitor_story_browser_progress=lambda *a:None)
        return app,calls

    def test_flow_first_no_ai_command_until_media_complete(self):
        from ui.main_window import MainWindow
        app,calls=self.app()
        self.assertTrue(start_saved_flow_scene(app,self.job,self.permit))
        self.assertFalse(any(c[0]=='command' for c in calls))
        payload=next(c[1] for c in calls if c[0]=='worker')
        pipeline=ScenePipeline(self.folder)
        segment=self.folder/'ready.mp4';segment.write_bytes(b'x'*2048)
        app._collect_story_flow_clips=lambda *a,**kw: [segment]
        def render(*args):return {'segment':'ready.mp4','duration':1,'voice':''}
        with patch('core.scene_voice.render_scene_asset',side_effect=render):
            MainWindow._run_story_scene_worker(app,payload,'','','',{},app._story_cancel_event)
        self.assertEqual(pipeline.get(1)['phase'],'complete')
        kind,done=app.events.get_nowait();self.assertEqual(kind,'story_saved_scene_done')
        finish_saved_flow_scene(app,done);finish_saved_flow_scene(app,done)
        self.assertEqual([c for c in calls if c[0]=='command'],[('command',('resume_chatgpt','STORY-TEST'))])

    def test_cancel_and_wrong_worker_cannot_advance_or_fail_new_scene(self):
        from ui.main_window import MainWindow
        app,calls=self.app();start_saved_flow_scene(app,self.job,self.permit)
        payload=next(c[1] for c in calls if c[0]=='worker');pipeline=ScenePipeline(self.folder)
        row=pipeline.get(1);pipeline.request(1,2,row['identity'],run_id='NEWER')
        MainWindow._run_story_scene_worker(app,payload,'','','',{},app._story_cancel_event)
        self.assertEqual(pipeline.get(1)['phase'],'requested');self.assertTrue(app.events.empty())
        app._story_cancel_event.set()
        self.assertFalse(start_saved_flow_scene(app,self.job,self.permit))
        finish_saved_flow_scene(app,{**payload,'cancel_event':app._story_cancel_event})
        self.assertFalse(any(c[0]=='command' for c in calls))

    def test_desktop_resume_entry_chooses_flow_before_ai(self):
        from ui.main_window import MainWindow
        app,calls=self.app();app._story_pipeline_job_id=''
        app.story_job_id=SimpleNamespace(set=lambda _:None)
        app.stories.load_analysis_checkpoint=lambda _: {'saved':True}
        app.stories.reset_recovery_attempts=lambda _:None
        app._compatible_extension=lambda: ({},True)
        app._close_story_progress=lambda:None
        app._show_story_progress=lambda _:None
        MainWindow._retry_story_job(app,'STORY-TEST')
        self.assertEqual(len([c for c in calls if c[0]=='worker']),1)
        self.assertFalse(any(c[0]=='command' for c in calls))

    def test_preparing_status_does_not_claim_generation(self):
        self.prepared();p=ScenePipeline(self.folder);r=p.request(1,2,{'image':'fixture'})
        p.update(1,r['revision'],phase='video',message='กำลังเตรียม Google Flow • ภาพและพรอมต์พร้อมแล้ว')
        view=scene_progress_view({**self.job,'status':'running'},self.folder,True,30)
        self.assertIn('กำลังเตรียม Google Flow',view['message'])
        self.assertNotIn('กำลังสร้างวิดีโอ',view['message'])

    def test_completed_images_finish_locally_without_opening_ai(self):
        app,calls=self.app();start_saved_flow_scene(app,self.job,self.permit)
        payload=next(c[1] for c in calls if c[0]=='worker')
        p=ScenePipeline(self.folder);row=p.get(1)
        (self.folder/'ready.mp4').write_bytes(b'x'*2048)
        p.update(1,row['revision'],phase='complete',segment='ready.mp4')
        self.job.update(ai_status='ready',scene_count=1)
        app._render_story=lambda:None
        finish_saved_flow_scene(app,{**payload,'cancel_event':app._story_cancel_event})
        self.assertFalse(any(c[0]=='command' for c in calls))
        self.assertIn(('monitor',300),calls)

    def test_real_bridge_proof_urls_and_media_hash(self):
        import json, logging, urllib.request
        from urllib.error import HTTPError
        from core.local_bridge import LocalBridge
        from core.product_manager import ProductManager
        app,_=self.app()
        app.stories.flow_package=lambda *a,**kw: {'job_id':self.job['id'],'image_files':[]}
        bridge=LocalBridge('127.0.0.1',0,ProductManager(self.folder/'isolated-products'),logging.getLogger('408-test')).start()
        bridge.stories=app.stories
        try:
            base=f'http://127.0.0.1:{bridge.server.server_address[1]}'
            route=base+'/api/jobs/STORY-TEST/flow-package?shot_index=1'
            with urllib.request.urlopen(route,timeout=5) as response:pkg=json.load(response)['package']
            proof=pkg['ready_home_replacement']
            self.assertEqual(proof['image_url'],pkg['image_urls'][0])
            self.assertEqual(proof['prompt'],pkg['video_prompt'])
            self.assertEqual(proof['event_digest'],pkg['manual_flow_repair']['event_digest'])
            self.assertEqual(proof['request_id'],pkg['replacement_id'])
            with urllib.request.urlopen(proof['image_url'],timeout=5) as response:
                self.assertEqual(response.read(),(self.folder/proof['image_file']).read_bytes())
            self.rows[-2]['fresh_project']={'phase':'opening'}
            self.store.write({'scenes':{'1':self.rows}})
            with urllib.request.urlopen(route,timeout=5) as response:
                self.assertNotIn('ready_home_replacement',json.load(response)['package'])
            (self.folder/proof['image_file']).write_bytes(b'changed')
            with self.assertRaises(HTTPError):urllib.request.urlopen(route,timeout=5)
        finally:bridge.stop()

    def test_actual_extension_missing_cache_and_old407_red(self):
        if not (Path(__file__).resolve().parents[1] / 'deliverables/SmartFlow_AI_Extension_0.15.407/background.js').is_file():
            self.skipTest('Historical 407 Extension is not available in this checkout')
        result=subprocess.run(['node','tests/flow_desktop_proof_408.cjs'],cwd=Path(__file__).resolve().parents[1],
            capture_output=True,text=True,encoding='utf-8',timeout=45,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
