import subprocess
import unittest
from pathlib import Path


class ExtensionTransportLifecycleTests(unittest.TestCase):
    def test_real_background_transport_with_isolated_browser_stubs(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", str(root / "tests" / "extension_transport_lifecycle_harness.js")],
            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("extension_transport_lifecycle: PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
