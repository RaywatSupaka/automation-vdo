import json
import logging
import tempfile
import unittest
import urllib.request
from urllib.error import HTTPError
from pathlib import Path
from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.story_manager import StoryManager
from core.flow_motion_plan import motion_plan_action


class FlowMotionBridgeTests(unittest.TestCase):
    def test_current_run_provider_and_actual_file_url(self):
        with tempfile.TemporaryDirectory() as temp:
            products=ProductManager(Path(temp));stories=StoryManager(Path(temp))
            job=stories.create('เรื่องสมมติ',scene_count=6,image_ai_provider='gemini',video_generation_mode='google_flow')
            folder=stories.root/job['id'];(folder/'generated/scene_01.png').write_bytes(b'image fixture')
            bridge=LocalBridge('127.0.0.1',0,products,logging.getLogger('motion-test')).start()
            bridge.stories=stories
            try:
                base=f'http://127.0.0.1:{bridge.server.server_address[1]}'
                def post(route,body):
                    request=urllib.request.Request(base+route,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(request,timeout=5) as response:return json.load(response)
                post('/api/extension/heartbeat',{'client_id':'motion-test','version':bridge.REQUIRED_EXTENSION_VERSION,'browser':'Google Chrome','page':'gemini'})
                bridge._extension_runs[('ai',job['id'],0)]={'run_id':'RUN-X'}
                body={'client_id':'motion-test','job_id':job['id'],'run_id':'RUN-X','provider':'gemini','index':1,'action':'status'}
                result=post('/api/extension/flow-motion-plan',body)
                self.assertEqual(result['context']['provider'],'gemini')
                self.assertTrue(result['context']['image_url'].startswith(base+'/api/stories/'))
                for patch in ({'run_id':'OLD'},{'provider':'chatgpt'}):
                    with self.assertRaises(HTTPError):post('/api/extension/flow-motion-plan',{**body,**patch})
            finally:bridge.stop()

    def test_saved_prompt_reaches_real_story_package(self):
        import base64
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);stories=StoryManager(root)
            job=stories.create('ทดสอบ',scene_count=6,image_ai_provider='gemini',video_generation_mode='google_flow')
            image=root/'input.png';Image.new('RGB',(64,96),'orange').save(image)
            encoded=base64.b64encode(image.read_bytes()).decode()
            stories.apply_ai_result({'job_id':job['id'],'video_title':'ทดสอบ','video_description':'เรื่องสมมติ','narration_script':'ทดสอบเรื่องต่อเนื่อง','story_entities':[],'scene_entities':[[] for _ in range(6)],'scene_prompts':['scene']*6,'scene_narrations':['เดินช้า ๆ']*6,'scene_durations':[5]*6,'generated_images':[encoded]*6})
            job=stories.get(job['id']);folder=stories.root/job['id']
            for index in range(1,7):
                body={'index':index,'provider':'gemini'};ctx=motion_plan_action(folder,job,body)['context'];body['context_id']=ctx['context_id']
                motion_plan_action(folder,job,{**body,'action':'claim','request':'motion request'})
                motion_plan_action(folder,job,{**body,'action':'save','result':{'job_id':job['id'],'index':index,'context_id':ctx['context_id'],'prompt':'สร้างวิดีโอเดียว 9:16 จากภาพ ตัวละครเดินช้า ๆ กล้องเคลื่อนเข้าหาตัวละคร','needs_review':False,'reference_compatible':True,'material_change':False}})
            package=stories.flow_package(job['id'],shot_index=2)
            self.assertTrue(package['motion_prompt_ready']);self.assertEqual(package['image_ai_provider'],'gemini')
            self.assertNotIn('Preserve the exact character identity',package['video_prompt'])
            self.assertEqual([Path(p).as_posix() for p in package['image_files']],['generated/scene_02.png'])
