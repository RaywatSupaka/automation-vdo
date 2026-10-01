import subprocess
import unittest
from pathlib import Path


class StoryImageWaitTests(unittest.TestCase):
    def test_actual_source_wait_monitor(self):
        result = subprocess.run(['node', 'tests/story_image_wait_342_harness.js'],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS: Story342', result.stdout)
