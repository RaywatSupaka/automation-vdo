import tempfile
import unittest
import os
import subprocess
from pathlib import Path
from core.flow_smoke import smoke_payload
from core.story_manager import StoryManager


class FlowSmokeTests(unittest.TestCase):
    def test_ui_confirmation(self):
        env=dict(os.environ)
        env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result=subprocess.run(['node','tests/flow_smoke_ui_harness.js'],cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_choices_are_isolated(self):
        original={'topic':'กระต่ายกับไก่','provider':'gemini','flow_settings':{'model':'Omni 1.1 Flash','duration':'4s'},
                  'scene_count':10,'main_image':'user.png','audio_choices':{'mode':'api'},'long_video':{}}
        result=smoke_payload(original)
        self.assertEqual(result['scene_count'],1)
        self.assertEqual(result['provider'],'gemini')
        self.assertEqual(result['flow_settings'],original['flow_settings'])
        self.assertEqual(result['audio_choices']['mode'],'api')
        self.assertEqual(result['topic'],original['topic'])
        self.assertEqual(result['main_image'],'user.png')
        self.assertNotIn('long_video',result)
        self.assertEqual(original['scene_count'],10)
        result['audio_choices']['mode']='none'
        self.assertEqual(original['audio_choices']['mode'],'api')
        with self.assertRaises(ValueError):smoke_payload({})

    def test_queue_one_scene_preserves_options(self):
        from core.creation_queue import CreationQueue
        with tempfile.TemporaryDirectory() as tmp:
            q=CreationQueue(tmp)
            q.enqueue('story',['test'],flow_smoke_test=True,queue_only=True,video_generation_mode='google_flow',settings={'audio_choices':{'mode':'api','subtitle':True}})
            row=CreationQueue(tmp).snapshot()['items'][0]
            self.assertEqual(row['scene_count'],1)
            self.assertTrue(row['flow_smoke_test'])
            self.assertTrue(row['settings']['audio_choices']['subtitle'])

    def test_one_scene_and_normal_minimum(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=StoryManager(tmp)
            smoke=manager.create('test',scene_count=1,video_generation_mode='google_flow',flow_smoke_test=True)
            normal=manager.create('normal',scene_count=1)
            self.assertEqual(smoke['scene_count'],1)
            self.assertTrue(smoke['flow_smoke_test'])
            smoke['flow_settings']={'duration':'4s'}
            manager._write_request(manager.root/smoke['id'],smoke)
            prompt=(manager.root/smoke['id']/'prompts/chatgpt_request.txt').read_text(encoding='utf-8')
            self.assertIn('ความยาววิดีโอ 4s',prompt)
            self.assertNotIn('มีฮุกใน 2 วินาทีแรก',prompt)
            self.assertNotIn('ช่วง 3-7 วินาที',prompt)
            self.assertNotIn('ฉากสุดท้ายต้องปิดเรื่องให้จบก่อน',prompt)
            self.assertEqual(normal['scene_count'],6)
            with self.assertRaises(ValueError):
                manager.create('bad',flow_smoke_test=True)

    def test_exact_spoken_line_is_not_doubled(self):
        from core.media_audio import flow_audio_instruction
        job={'audio_choices':{'mode':'flow_original'},'scene_narrations':['long old narration and CTA']}
        self.assertEqual(flow_audio_instruction(job,1,'The only spoken line is: วันนี้ร้านเปิดแล้วครับ'), '')
        self.assertIn('long old narration',flow_audio_instruction(job,1,'Vertical 9:16. A man opens his shop.'))

    def test_real_collector_reuses_single_smoke_clip(self):
        from ui.main_window import MainWindow
        from queue import Queue
        with tempfile.TemporaryDirectory() as tmp:
            manager=StoryManager(tmp)
            job=manager.create('test',scene_count=1,video_generation_mode='google_flow',flow_smoke_test=True)
            clip=Path(tmp)/'one.mp4';clip.write_bytes(b'fixture-video'*200)
            manager.attach_flow_clip(job['id'],1,clip)
            window=MainWindow.__new__(MainWindow)
            window.stories=manager;window.events=Queue()
            paths=window._collect_story_flow_clips(job['id'],None)
            self.assertEqual(len(paths),1)
            self.assertEqual(paths[0].read_bytes(),clip.read_bytes())
