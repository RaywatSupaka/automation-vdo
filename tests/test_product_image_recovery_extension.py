import json
from pathlib import Path
import shutil
import subprocess
import unittest


class RecoveryExtensionTests(unittest.TestCase):
    def test_real_extension_recovery_and_attachment_contract(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([shutil.which('node'), str(root / 'tests/product_image_recovery_harness.js')],
                                capture_output=True, text=True, encoding='utf-8', cwd=root, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])
