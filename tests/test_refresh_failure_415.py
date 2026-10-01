import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RefreshFailure415Tests(unittest.TestCase):
    def test_confirmed_failure_survives_refresh_and_fresh_handoff(self):
        result = subprocess.run(['node', 'tests/refresh_failure_415.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_dom_and_terminal_observation(self):
        result = subprocess.run(['node', 'tests/refresh_failure_dom_415.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
