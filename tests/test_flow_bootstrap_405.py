import subprocess
import unittest
from pathlib import Path


class FlowBootstrap405Tests(unittest.TestCase):
    def test_content_script_reentry_during_new_controller_bootstrap(self):
        result = subprocess.run(['node', 'tests/flow_bootstrap_405.js'],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
