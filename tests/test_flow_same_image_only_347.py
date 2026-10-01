import subprocess
import unittest
from pathlib import Path


class SameImageOnly347Tests(unittest.TestCase):
    def test_recovery_routes(self):
        result = subprocess.run(['node', 'tests/flow_same_image_only_347_harness.js'],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
