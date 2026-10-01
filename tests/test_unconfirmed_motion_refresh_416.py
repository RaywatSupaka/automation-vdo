import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class UnconfirmedMotionRefreshTests(unittest.TestCase):
    def test_actual_content_reload_proofs(self):
        result = subprocess.run([shutil.which('node'), str(ROOT / 'tests/unconfirmed_motion_refresh_416.cjs')],
                                cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['cases'], 28)
