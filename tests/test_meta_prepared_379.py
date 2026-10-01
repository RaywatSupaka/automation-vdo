import subprocess
import unittest
from pathlib import Path


class MetaPreparedRegression(unittest.TestCase):
    def test_live_long_prompt_geometry_and_controller(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/meta_prepared_379.cjs'], cwd=root,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('16 cases passed', result.stdout)
