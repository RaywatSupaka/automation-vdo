"""Meta clean-Home recovery exercises the production adapter without live browser access."""
import subprocess
import unittest
from pathlib import Path


class MetaTabRecovery454Tests(unittest.TestCase):
    def test_production_adapter_tab_loss_and_restart_boundaries(self):
        result = subprocess.run(
            ['node', 'tests/meta_tab_recovery_454.cjs'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
