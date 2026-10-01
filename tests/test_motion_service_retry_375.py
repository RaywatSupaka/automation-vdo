import json
import subprocess
import unittest
from pathlib import Path


class MotionServiceRetryTests(unittest.TestCase):
    def test_owned_native_retry_dom_and_durable_background(self):
        result = subprocess.run(['node', 'tests/motion_service_retry_375.js'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreaterEqual(json.loads(result.stdout)['cases'], 45)
