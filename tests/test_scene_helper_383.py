import json
from pathlib import Path
import subprocess
import unittest


class SceneHelper383Tests(unittest.TestCase):
    def test_actual_source_reference_and_candidate_recovery(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/scene_helper_383.js'], cwd=root,
                                capture_output=True, text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads(result.stdout)
        self.assertTrue(summary['ok'])
        self.assertGreaterEqual(summary['cases'], 30)
