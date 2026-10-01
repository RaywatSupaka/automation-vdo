"""Actual-source VM regressions; no browser, provider requests or user files."""
import json
import subprocess
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs


class FlowResumeLifecycleTests(unittest.TestCase):
    def test_extension_preserved_cancel_owned_inspection_and_resume(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('flow_resume_lifecycle_harness.js'))],
                                capture_output=True, text=True, encoding='utf-8', timeout=25,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'ok': True, 'cases': 37})


if __name__ == '__main__':
    unittest.main()
