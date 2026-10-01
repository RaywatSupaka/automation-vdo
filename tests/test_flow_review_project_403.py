import subprocess
import unittest
from pathlib import Path


class FlowReviewProject403Tests(unittest.TestCase):
    def test_actual_home_and_vanished_failure_card_recovery(self):
        result = subprocess.run(['node', 'tests/flow_review_project_403.js'],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, encoding='utf-8', timeout=40)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
