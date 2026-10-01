import subprocess
import unittest
from pathlib import Path


class MetaSendActiveGeometry453(unittest.TestCase):
    def test_native_active_animation_preserves_original_send_target(self):
        result = subprocess.run(
            ['node', 'tests/meta_send_active_geometry_453.cjs'],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, encoding='utf-8', timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
