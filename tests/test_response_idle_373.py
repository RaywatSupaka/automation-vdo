import json
import subprocess
import unittest
from pathlib import Path


class ResponseIdleScopeTests(unittest.TestCase):
    def test_real_wait_call_chain_and_saved_scene_refresh(self):
        result = subprocess.run(['node', 'tests/response_idle_373.js'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, encoding='utf-8', timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreaterEqual(json.loads(result.stdout)['cases'], 35)
