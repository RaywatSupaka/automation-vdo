import json
import subprocess
import unittest
from pathlib import Path


class CompletedResponseRefreshTests(unittest.TestCase):
    def test_completed_dom_and_durable_reload_guards(self):
        result = subprocess.run(['node', 'tests/completed_response_refresh_366.js'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, encoding='utf-8', timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreaterEqual(json.loads(result.stdout)['cases'], 23)
