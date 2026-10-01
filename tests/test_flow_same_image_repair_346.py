import subprocess
import unittest
from pathlib import Path


class FlowSameImageRepair346Tests(unittest.TestCase):
    def test_actual_source_same_image_fresh_project(self):
        result = subprocess.run(['node', 'tests/flow_same_image_repair_346_harness.js'],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
