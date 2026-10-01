import subprocess
import unittest
from pathlib import Path


class MetaSendFence451(unittest.TestCase):
    def test_production_gesture_boundaries(self):
        result = subprocess.run(['node', 'tests/meta_send_fence_451.cjs'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_dom_and_input_boundaries(self):
        result = subprocess.run(['node', 'tests/meta_send_native_451.cjs'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
