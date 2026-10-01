import subprocess
import unittest


class FlowTerminalHandoffTests(unittest.TestCase):
    def test_owned_failed_card_enters_existing_repair(self):
        result = subprocess.run(['node', 'tests/flow_terminal_367.js'],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"cases":20', result.stdout)
