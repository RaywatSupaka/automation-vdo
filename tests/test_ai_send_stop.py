import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AISendStopTests(unittest.TestCase):
    def test_trusted_send_rejects_stop_before_any_press(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the executable Extension contract")
        result = subprocess.run(
            [node, str(ROOT / "tests/ai_send_stop_harness.js")],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {"ok": True, "cases": 22})
