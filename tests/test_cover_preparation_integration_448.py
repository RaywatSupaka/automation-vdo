import json
from pathlib import Path
import shutil
import subprocess
import unittest


class CoverPreparationIntegration448(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_actual_cover_and_image_tool(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/cover_preparation_integration_448.cjs'], cwd=root,
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr[-5000:])
        self.assertEqual(json.loads(result.stdout)['cases'], 10)
