import json
import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs


class FlowRestartCheckpointTests(unittest.TestCase):
    def test_restart_uses_owned_result_without_generation(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('flow_restart_checkpoint_harness.js'))],
                                capture_output=True, text=True, encoding='utf-8', timeout=25,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'ok': True, 'cases': 19})
