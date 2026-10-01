"""Production-source fault injection without provider requests or customer state."""
from pathlib import Path
import subprocess
import unittest
from core.cancellable_process import hidden_process_kwargs


class AutomationLiveness406Tests(unittest.TestCase):
    def test_actual_source_liveness_and_ownership(self):
        result = subprocess.run(
            ['node', 'tests/automation_liveness_406.js'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, encoding='utf-8', timeout=30, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
