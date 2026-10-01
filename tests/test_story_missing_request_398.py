import os
import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs


class StoryMissingRequestRefresh398(unittest.TestCase):
    def test_actual_source_missing_request_recovery_and_dom(self):
        result = subprocess.run(
            ['node', 'tests/story_missing_request_398.cjs'],
            cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(),
            capture_output=True, text=True, encoding='utf-8', timeout=90,
            **hidden_process_kwargs(),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"ok":true', result.stdout)
