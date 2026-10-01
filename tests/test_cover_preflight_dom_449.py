import json
from pathlib import Path
import shutil
import subprocess
import unittest


class CoverPreflightNativeDom449(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_actual_preparation_helpers_against_native_home_dom(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ['node', 'tests/cover_preflight_dom_449.cjs'], cwd=root,
            capture_output=True, text=True, encoding='utf-8', timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        proof = json.loads(result.stdout)
        self.assertTrue(proof['nativeDom'])
        self.assertTrue(proof['ok'])
        self.assertGreaterEqual(proof['checks'], 60)
        self.assertEqual(proof['networkRequests'], 0)
