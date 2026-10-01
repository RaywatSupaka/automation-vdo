import json
import pathlib
import subprocess
import unittest


class StorySameChatReminderTests(unittest.TestCase):
    def test_actual_content_receipt_and_reminder_contract(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/story_same_chat_reminder.cjs'], cwd=root,
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data['ok'])
        self.assertGreaterEqual(data['cases'], 60)
        self.assertEqual(data['providerSubmissions'], 0)
