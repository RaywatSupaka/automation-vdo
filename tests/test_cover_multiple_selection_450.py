import json
from pathlib import Path
import shutil
import subprocess
import unittest


class CoverMultipleSelectionNative450(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node required')
    def test_owned_multiple_cover_selection_in_native_chromium(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ['node', 'tests/cover_multiple_selection_450.cjs'], cwd=root,
            capture_output=True, text=True, encoding='utf-8', timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        proof = json.loads(result.stdout)
        self.assertTrue(proof['ok'])
        self.assertTrue(proof['nativeDom'])
        self.assertGreaterEqual(proof['checks'], 60)
        self.assertEqual(proof['scenarios'], 12)
        self.assertEqual(proof['providerNetworkRequests'], 0)
        self.assertEqual(proof['providerActions'], 0)
