import os
import subprocess
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs


class RefreshSafety399Tests(unittest.TestCase):
    def test_busy_dom_and_cancelled_flow_reload(self):
        result = subprocess.run(
            ["node", "tests/refresh_safety_399.cjs"],
            cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(),
            capture_output=True, text=True, encoding="utf-8", timeout=90,
            **hidden_process_kwargs(),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"ok":true', result.stdout)
