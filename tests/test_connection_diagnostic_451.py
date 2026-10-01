import subprocess
import unittest
from pathlib import Path


class ConnectionDiagnosticTests(unittest.TestCase):
    def test_background_heartbeat_states(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/connection_diagnostic_451.cjs'], cwd=root, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
