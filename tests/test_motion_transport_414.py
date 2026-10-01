import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MotionTransport414Tests(unittest.TestCase):
    def test_real_writer_submitted_dom_motion_wait_and_resume(self):
        result = subprocess.run(['node', 'tests/motion_transport_414.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
