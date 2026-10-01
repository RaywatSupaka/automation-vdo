import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AISendAcceptanceTests(unittest.TestCase):
    def test_real_dispatch_capture_and_passive_acceptance_races(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the executable Extension contract")
        result = subprocess.run(
            [node, str(ROOT / "tests/ai_send_acceptance_harness.js")],
            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
