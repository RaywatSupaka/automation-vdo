"""Malformed completed Flow helper replies are repairable, not new media attempts."""
import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs


class FlowFormatRecovery410Tests(unittest.TestCase):
    def test_actual_parser_and_owned_helper_recovery(self):
        result = subprocess.run(['node', 'tests/flow_format_recovery_410.cjs'],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding='utf-8', timeout=45,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
