import tempfile
import unittest
from core.story_manager import StoryManager
from core.flow_scene_edit import save
from core.studio_review import story_review


class FlowSceneEditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = StoryManager(self.temp.name)
        self.job = self.manager.create('test', scene_count=6, video_generation_mode='google_flow')
        self.folder = self.manager._folder(self.job['id'])
        images = [f'generated/scene_{i:02d}.png' for i in range(1, 7)]
        for image in images:
            (self.folder / image).write_bytes(b'image')
        self.job.update(generated_images=images, scene_prompts=['scene']*6, scene_narrations=['story']*6,
                        status='error', voice_path='audio/kept.mp3', flow_settings={'model':'Veo 3.1 - Fast','duration':'4s'})
        self.manager._save(self.job)

    def test_manual_prompt_and_all_models_reach_package_without_changing_other_scenes(self):
        for model in ['', 'Omni 1.1 Flash','Veo 3.1 - Lite','Veo 3.1 - Fast','Veo 3.1 - Quality','Veo 3.1 - Lite [Lower Priority]']:
            current=self.manager.get(self.job['id'])
            saved=save(self.manager,current['id'],2,'Slow camera push-in, vertical 9:16.',model,current['revision'])
            package=self.manager.flow_package(current['id'],2)
            self.assertTrue(package['motion_prompt_ready'])
            self.assertIn('Slow camera push-in',package['video_prompt'])
            self.assertEqual(package['flow_settings'].get('model',''),model)
            self.assertEqual(package['flow_settings']['duration'],'4s')
            self.assertEqual(self.manager.flow_package(current['id'],1)['flow_settings']['model'],'Veo 3.1 - Fast')
            self.assertEqual(saved['voice_path'],'audio/kept.mp3')
            self.assertEqual(saved['scene_prompts'],['scene']*6)

    def test_review_allows_flow_edit_after_voice_but_not_active_or_completed_scene(self):
        self.assertTrue(story_review(self.folder,self.job)['scenes'][0]['flow_editable'])
        self.assertFalse(story_review(self.folder,self.job,True)['scenes'][0]['flow_editable'])
        self.job['flow_clips']={'1':'videos/kept.mp4'}
        self.manager._save(self.job)
        with self.assertRaises(ValueError):
            save(self.manager,self.job['id'],1,'Motion','',self.job['revision'])

    def test_revision_and_image_identity(self):
        saved=save(self.manager,self.job['id'],2,'Motion','',self.job['revision'])
        with self.assertRaises(ValueError):
            save(self.manager,self.job['id'],2,'Other','',self.job['revision'])
        (self.folder/'generated/scene_02.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'ภาพหรือบท'):
            self.manager.flow_package(saved['id'],2)
