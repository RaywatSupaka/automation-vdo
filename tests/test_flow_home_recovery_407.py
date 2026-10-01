"""Home promotional media is not an owned scene result; preserve ready recovery."""
from pathlib import Path
import subprocess
import unittest
from core.cancellable_process import hidden_process_kwargs


class FlowHomeRecovery407Tests(unittest.TestCase):
    def test_native_dom_content_worker_and_resume(self):
        result = subprocess.run(
            ['node', 'tests/flow_home_recovery_407.cjs'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, encoding='utf-8', timeout=90, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
