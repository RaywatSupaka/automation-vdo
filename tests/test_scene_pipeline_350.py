import tempfile
import unittest
import subprocess
from pathlib import Path
from core.scene_pipeline import ScenePipeline
from core.scene_voice import scene_turns
from unittest.mock import patch


class ScenePipeline350Tests(unittest.TestCase):
    def test_barrier_revision_and_saved_file_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);p=ScenePipeline(folder)
            row=p.request(1,2,{'image':'one','narration':'first'})
            self.assertEqual(p.request(1,2,{'image':'one','narration':'first'}),row)
            with self.assertRaises(ValueError):p.request(2,2,{'image':'two'})
            with self.assertRaises(ValueError):p.update(1,'other',phase='complete')
            with self.assertRaises(ValueError):p.update(1,row['revision'],phase='complete',segment='missing')
            (folder/'one.mp4').write_bytes(b'x'*2048)
            p.update(1,row['revision'],phase='complete',segment='one.mp4')
            self.assertEqual(p.segments(1),[folder/'one.mp4'])
            p.request(2,2,{'image':'two'})
            (folder/'one.mp4').write_bytes(b'y'*2048)
            with self.assertRaises(ValueError):p.segments(1)

    def test_error_keeps_same_identity_for_voice_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            p=ScenePipeline(temp);row=p.request(1,1,{'video':'paid'})
            p.update(1,row['revision'],phase='error',error='voice download pending')
            self.assertEqual(p.request(1,1,{'video':'paid'})['revision'],row['revision'])
            with self.assertRaises(ValueError):p.request(1,1,{'video':'different'})

    def test_speakers_are_bound_to_exact_scene(self):
        job={'scene_narrations':['ก ข','ค'], 'dialogue_turns':[
            {'speaker':'A','text':'ก'},{'speaker':'B','text':'ข'},{'speaker':'C','text':'ค'}]}
        self.assertEqual([t['speaker'] for t in scene_turns(job,1)],['A','B'])
        self.assertEqual(scene_turns(job,2)[0]['speaker'],'C')
        job['scene_narrations'][0]='unknown'
        with self.assertRaises(ValueError):scene_turns(job,1)

    def test_extension_waits_before_next_scene(self):
        result=subprocess.run(['node','tests/scene_gate_350_harness.js'],cwd=Path(__file__).resolve().parents[1],
            capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_worker_releases_only_after_scene_render(self):
        from types import SimpleNamespace
        from queue import Queue
        from ui.main_window import MainWindow
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'STORY-TEST';folder.mkdir()
            segment=folder/'ready.mp4';segment.write_bytes(b'x'*2048)
            pipeline=ScenePipeline(folder);row=pipeline.request(1,2,{'image':'one'})
            events=[]
            app=SimpleNamespace(stories=SimpleNamespace(root=root,get=lambda _: {
                'id':'STORY-TEST','scene_count':2,'scene_narrations':['one','two'],'audio_choices':{'mode':'none'}}),
                cfg={},events=Queue(),bridge=SimpleNamespace(_extension_runs={('ai','STORY-TEST',0):{'run_id':'run'}}))
            def collect(job_id,cancel_event,only_scene=None):
                self.assertEqual(only_scene,1);events.append('video');return [segment]
            app._collect_story_flow_clips=collect
            def render(*args):
                self.assertEqual(pipeline.get(1)['phase'],'voice');events.append('render')
                return {'segment':'ready.mp4','voice':'','duration':1}
            payload={'job_id':'STORY-TEST','index':1,'revision':row['revision'],'run_id':'run'}
            with patch('core.scene_voice.render_scene_asset',side_effect=render):
                MainWindow._run_story_scene_worker(app,payload,'','','',{},None)
            self.assertEqual(events,['video','render'])
            self.assertEqual(pipeline.get(1)['phase'],'complete')
            self.assertEqual(pipeline.get(2),{})

    def test_partial_analysis_can_start_first_scene_without_all_images(self):
        from core.story_manager import StoryManager
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            manager=StoryManager(Path(temp));job=manager.create('แมวเดินเล่น',scene_count=2,video_generation_mode='google_flow')
            manager.save_analysis_checkpoint(job['id'],{'video_title':'แมวเดินเล่น','narration_script':'แมวเดินเล่น แมวกลับบ้าน '*3,
                'scene_narrations':['แมวเดินเล่น','แมวกลับบ้าน']*3,'scene_prompts':['A cat walks outside','A cat returns home']*3,
                'scene_dialogue_turns':[[{'speaker':'ผู้บรรยาย','text':'แมวเดินเล่น'}],[{'speaker':'ผู้บรรยาย','text':'แมวกลับบ้าน'}]]*3,
                'story_entities':[],'scene_entities':[[] for _ in range(6)]})
            folder=manager.root/job['id']
            Image.new('RGB',(64,96),'blue').save(folder/'generated/scene_01.png')
            prepared=manager.prepare_scene_pipeline(job['id'],1)
            self.assertNotEqual(prepared.get('ai_status'),'ready')
            self.assertEqual(scene_turns(prepared,1)[0]['text'],'แมวเดินเล่น')
            with self.assertRaises(ValueError):manager.prepare_scene_pipeline(job['id'],2)

    def test_actual_scene_audio_and_final_merge(self):
        import wave
        from core.scene_voice import render_scene_asset
        from core.video_composer import MultiFlowComposer
        from core.video_logo import locate_ffmpeg
        ffmpeg=str(locate_ffmpeg(''))
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);video=folder/'source.mp4'
            subprocess.run([ffmpeg,'-y','-f','lavfi','-i','testsrc2=size=180x320:rate=12',
                '-t','1','-c:v','libx264','-pix_fmt','yuv420p',str(video)],capture_output=True,check=True)
            def voice(client,text,reference,target,**kwargs):
                with wave.open(str(target),'wb') as stream:
                    stream.setparams((1,2,24000,0,'NONE','not compressed'))
                    stream.writeframes(b'\x01\x00'*24000)
                return {}
            job={'id':'LOCAL-TEST','scene_narrations':['Re:Zero กับ UnknownHero เดินเล่น'],
                 'audio_choices':{'mode':'api','keep_video_audio':False}}
            with patch('core.scene_voice.render_chunked_voice',side_effect=voice) as speech:
                row=render_scene_asset(folder,job,1,video,object(),'ref',
                    {'width':360,'height':640,'fps':24,'crf':30},'',None,lambda _:None)
                self.assertEqual(speech.call_count,1)
                self.assertEqual(speech.call_args.args[1], 'Re:Zero กับ UnknownHero เดินเล่น')
            self.assertGreater(row['duration'],.9)
            self.assertTrue((folder/row['voice']).is_file())
            final=folder/'final.mp4'
            plan=MultiFlowComposer(ffmpeg).compose([folder/row['segment']]*2,final,
                width=360,height=640,fps=24,crf=30,transition_sec=0,
                audio_choices={'mode':'flow_original','video_audio_volume':100,'allow_silent':True})
            self.assertGreater(plan['duration'],1.8)
            probe=subprocess.run([str(Path(ffmpeg).with_name('ffprobe.exe')),'-v','error',
                '-select_streams','a','-show_entries','stream=codec_type','-of','csv=p=0',str(final)],
                capture_output=True,text=True,check=True)
            self.assertIn('audio',probe.stdout)
