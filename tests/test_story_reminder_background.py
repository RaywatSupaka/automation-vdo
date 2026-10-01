import json
import shutil
import subprocess
import unittest
from pathlib import Path


class StoryReminderBackgroundTests(unittest.TestCase):
    def test_actual_trusted_send_and_durable_child_guards(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js unavailable')
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([node, 'tests/story_reminder_background.cjs'], cwd=root,
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
        self.assertGreaterEqual(json.loads(result.stdout)['cases'], 40)
