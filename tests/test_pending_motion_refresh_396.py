import json
import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs


class PendingMotionRefresh396Tests(unittest.TestCase):
    def test_owned_empty_refresh_and_read_only_resume(self):
        result = subprocess.run(['node', 'tests/pending_motion_refresh_396.cjs'],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding='utf-8',
                                timeout=45, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreaterEqual(json.loads(result.stdout)['cases'], 40)
