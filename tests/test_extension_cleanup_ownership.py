import subprocess
import unittest
from pathlib import Path


class ExtensionCleanupOwnershipTests(unittest.TestCase):
    def test_actual_cleanup_and_command_handlers_preserve_other_work(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", str(root / "tests" / "extension_cleanup_ownership_harness.js")],
            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"kind":"real_command_handler_failure","pass":true', result.stdout)


if __name__ == "__main__":
    unittest.main()
