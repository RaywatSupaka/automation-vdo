import json
from pathlib import Path
import subprocess
import unittest
import os

from core.story_pipeline import story_recovery_action


class StoryImageReceiptTests(unittest.TestCase):
    def test_saved_previous_reference_before_new_or_prepared_send(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', str(root / 'tests/story_prepared_reference_435.cjs')],
                                cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreaterEqual(json.loads(result.stdout)['cases'], 28)

    def test_story_send_to_image_ownership(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('story_send_329_harness.js'))],
                                capture_output=True, text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_observed_chatgpt_story_scope_and_full_wait_loop(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        env.setdefault('NODE_PATH', str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result = subprocess.run(['node', str(root/'tests/story_image_scope_328_harness.js')],
                                capture_output=True, text=True, encoding='utf-8', env=env, timeout=40)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_actual_extension_receipt_and_resume_harness(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', str(root / 'tests/story_image_receipt_harness.js')],
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertTrue(summary['ok'])
        self.assertGreaterEqual(summary['cases'], 20)

    def test_unreadable_or_pending_media_does_not_trigger_automatic_generation(self):
        job = {'scene_count': 3, 'partial_generated_images': ['generated/scene_01.png']}
        for code in ('STORY_IMAGE_CHECKPOINT_UNREADABLE', 'STORY_IMAGE_RECEIPT_REVIEW',
                     'STORY_IMAGE_DOWNLOAD_PENDING', 'STORY_ANALYSIS_CHECKPOINT_REVIEW'):
            with self.subTest(code=code):
                self.assertEqual(story_recovery_action(job, code + ' scene 2'), '')


if __name__ == '__main__':
    unittest.main()
