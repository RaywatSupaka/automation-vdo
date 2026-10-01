"""Quoted Product Story JSON uses the real Extension parser and repair loop."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs


ROOT = Path(__file__).resolve().parents[1]


class AnalysisJsonTransport428Tests(unittest.TestCase):
    def run_harness(self, *arguments):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the executable Extension contract")
        result = subprocess.run(
            [node, str(ROOT / "tests/analysis_json_transport_428.cjs"), *arguments],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
            **hidden_process_kwargs(),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["ok"])
        self.assertEqual(evidence["networkRequests"], 0)
        self.assertEqual(evidence["liveStateWrites"], 0)
        return evidence

    def test_actual_parser_and_owned_completed_format_recovery(self):
        evidence = self.run_harness()
        self.assertGreaterEqual(evidence["checks"], 30)

    def test_native_markdown_paragraph_and_fenced_code_transport(self):
        evidence = self.run_harness("--native")
        self.assertTrue(evidence["native"])
        self.assertTrue(evidence["browserClosed"])


if __name__ == "__main__":
    unittest.main()
