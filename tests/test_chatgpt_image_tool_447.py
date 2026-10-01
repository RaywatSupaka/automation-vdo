import json
import subprocess
import unittest
from pathlib import Path


class ChatGPTImageTool447Tests(unittest.TestCase):
    def test_actual_image_tool_send_and_wait_contract(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/chatgpt_image_tool_447.cjs'], cwd=root,
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreaterEqual(json.loads(result.stdout)['cases'], 50)

