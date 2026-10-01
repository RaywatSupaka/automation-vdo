import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.clip_cover import ensure_cover


class AICoverNoLocalTests(unittest.TestCase):
    def test_story_and_drama_save_video_defer_cover(self):
        from core.story_manager import StoryManager
        for kind in ['story_short','drama_episode']:
            with tempfile.TemporaryDirectory() as tmp, patch('core.clip_cover.compose_cover') as render:
                manager=StoryManager(Path(tmp))
                job=manager.create('ทดสอบปก AI',scene_count=6,job_type=kind)
                job['ai_cover_options']={'enabled':True}
                manager._save(job)
                folder=manager.root/job['id']
                video=folder/'videos'/'final.mp4';video.write_bytes(b'keep video')
                saved=manager.save_video(job['id'],video,{'source_type':'story_image_sequence'})
                self.assertEqual(saved['video_status'],'ready')
                self.assertEqual(saved['cover_status'],'pending_ai')
                self.assertFalse(saved.get('cover_path'))
                self.assertEqual(video.read_bytes(),b'keep video')
                render.assert_not_called()

    def test_ai_selected_never_composes_local_cover(self):
        with tempfile.TemporaryDirectory() as tmp, patch('core.clip_cover.compose_cover') as render:
            folder=Path(tmp)
            for kind in ['product','story_short','drama_episode']:
                result=ensure_cover(folder,folder,{'job_type':kind,'ai_cover_options':{'enabled':True}})
                self.assertEqual(result,{'cover_status':'pending_ai'})
            render.assert_not_called()

    def test_existing_cover_preserved(self):
        with tempfile.TemporaryDirectory() as tmp, patch('core.clip_cover.compose_cover') as render:
            folder=Path(tmp); (folder/'old.jpg').write_bytes(b'keep')
            self.assertEqual(ensure_cover(folder,folder,{'cover_path':'old.jpg','ai_cover_options':{'enabled':True}}),{})
            self.assertEqual((folder/'old.jpg').read_bytes(),b'keep')
            render.assert_not_called()

    def test_disabled_and_legacy_keep_local_behavior(self):
        with tempfile.TemporaryDirectory() as tmp, patch('core.clip_cover.compose_cover',return_value={'cover_status':'ready'}) as render:
            for options in [None,{}, {'enabled':False}]:
                self.assertEqual(ensure_cover(tmp,tmp,{'ai_cover_options':options}),{'cover_status':'ready'})
            self.assertEqual(render.call_count,3)
