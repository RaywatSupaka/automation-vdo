import unittest
import tempfile
from pathlib import Path
from core.product_scene_settings import product_scene_count
from core.media_audio import flow_audio_instruction
from core.product_story import story_brief
from core.story_manager import StoryManager


class ProductPlanningTests(unittest.TestCase):
    def test_count_range_and_default(self):
        self.assertEqual(product_scene_count(),3)
        for value in [3,5,10,15,'6']:
            self.assertEqual(product_scene_count(value),int(value))
        for value in [True,False,3.5,2,16,'3.5','abc']:
            with self.assertRaises(ValueError):product_scene_count(value)

    def test_job_count_reaches_extension_packet(self):
        with tempfile.TemporaryDirectory() as root:
            manager=StoryManager(Path(root))
            for count in [3,5,10,15]:
                job=manager.create('สินค้า',scene_count=count,product_short=True,video_generation_mode='google_flow')
                self.assertEqual(job['scene_count'],count)
                self.assertEqual(job['product_presentation_version'],1)
                self.assertEqual(manager.plugin_request(job['id'])['job']['scene_count'],count)
            self.assertEqual(manager.create('สินค้า',product_short=True)['scene_count'],3)
            self.assertEqual(manager.create('เรื่องเล่า')['scene_count'],10)

    def test_speech_mode_and_legacy_separation(self):
        job={'product_presentation_version':1,'product_story':{'name':'พัดลม'},
             'audio_choices':{'mode':'flow_original'},'scene_narrations':['ลองคล้องคอแบบนี้ค่ะ']}
        prompt=flow_audio_instruction(job,1)
        self.assertIn('AUDIO PERFORMANCE:',prompt)
        self.assertIn('ลองคล้องคอแบบนี้ค่ะ',prompt)
        self.assertIn('directly to camera',story_brief(job))
        self.assertEqual(flow_audio_instruction(job,1,prompt),'')
        self.assertNotIn('AUDIO PERFORMANCE:',flow_audio_instruction({**job,'product_presentation_version':0},1))
        self.assertEqual(flow_audio_instruction({**job,'audio_choices':{'mode':'api'}},1),'')

    def test_motion_request_does_not_defer_native_dialogue(self):
        from core.story_visual_plan import motion_request
        job={'product_presentation_version':1,'audio_choices':{'mode':'flow_original'},'scene_narrations':['คล้องคอได้แบบนี้ค่ะ']}
        request=motion_request({'job_id':'STORY-FIXTURE','index':1,'context_id':'fixture-context',
                                'audio_instruction':flow_audio_instruction(job,1)})
        self.assertIn('synchronized mouth movement',request)
        self.assertIn('คล้องคอได้แบบนี้ค่ะ',request)
        self.assertNotIn('calls to action are voiceover',request)

    def test_queue_counts_round_trip(self):
        from core.creation_queue import CreationQueue
        with tempfile.TemporaryDirectory() as root:
            queue=CreationQueue(Path(root))
            for count in [3,5,10,15]:
                row=queue.enqueue('story',[f'สินค้า {count}'],settings={'creative_context':{'kind':'product_story','product_short':True}},
                                  scene_count=count,video_generation_mode='google_flow')['items'][0]
                self.assertEqual(row['scene_count'],count)
            self.assertEqual([row['scene_count'] for row in CreationQueue(Path(root)).snapshot()['items']],[3,5,10,15])
