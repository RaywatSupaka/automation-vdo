"""Gated exact-failure Gemini successor transaction; no live provider actions."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GeminiCleanSuccessor439Tests(unittest.TestCase):
    def test_one_durable_successor_with_exact_proof_and_live_veto(self):
        result = subprocess.run(["node", "tests/gemini_clean_successor_439.cjs"], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        outcome = json.loads(result.stdout)
        self.assertTrue(outcome["ok"])
        self.assertGreaterEqual(outcome["cases"], 27)
        self.assertEqual(outcome["providerSubmissions"], 0)


if __name__ == "__main__":
    unittest.main()
