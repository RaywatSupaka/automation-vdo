import json
import tempfile
import unittest
from pathlib import Path

from core.story_manager import StoryManager


class StoryManualImageReplayTests(unittest.TestCase):
    def test_authorization_is_exact_and_once_only(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            folder = Path(temp) / 'workspace' / 'stories' / 'STORY-TEST'
            (folder / 'generated').mkdir(parents=True)
            (folder / 'generated' / 'scene_01.png').write_bytes(b'saved')
            job = {'id': 'STORY-TEST', 'status': 'error', 'revision': 7,
                   'scene_count': 3, 'image_ai_provider': 'chatgpt',
                   'last_error': 'CHATGPT_IMAGE_PRIOR_RUN_UNCONFIRMED_DRAFT_PRESENT'}
            (folder / 'job.json').write_text(json.dumps(job), encoding='utf-8')
            with self.assertRaises(ValueError):
                manager.authorize_uncertain_image_replay('STORY-TEST', 2, 6)
            with self.assertRaises(ValueError):
                manager.authorize_uncertain_image_replay('STORY-TEST', 3, 7)
            claim = manager.authorize_uncertain_image_replay('STORY-TEST', 2, 7)
            self.assertEqual(claim['max_sends'], 1)
            self.assertEqual(manager.get('STORY-TEST')['revision'], 8)
            with self.assertRaises(ValueError):
                manager.authorize_uncertain_image_replay('STORY-TEST', 2, 8)
            self.assertEqual((folder / 'generated' / 'scene_01.png').read_bytes(), b'saved')


if __name__ == '__main__':
    unittest.main()
