import subprocess
import unittest


class FlowServiceTerminalTests(unittest.TestCase):
    def test_owned_service_failure_uses_same_image_repair(self):
        result = subprocess.run(['node', 'tests/flow_service_terminal_385.js'],
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"cases":31', result.stdout)

    def test_service_repair_lifecycle_and_late_result_guards(self):
        result = subprocess.run(['node', 'tests/flow_service_repair_385.js'],
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"cases":21', result.stdout)


if __name__ == '__main__':
    unittest.main()
