"""Shared actual-source refresh handoff, offline Chrome documents only."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SharedRefreshHandoff439Tests(unittest.TestCase):
    def test_document_handoff_and_unknown_ack_liveness(self):
        result = subprocess.run(
            ["node", "tests/shared_refresh_handoff_439.cjs"], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        outcome = json.loads(result.stdout)
        self.assertTrue(outcome["ok"])
        self.assertGreaterEqual(outcome["cases"], 20)
        self.assertEqual(outcome["providerSubmissions"], 0)


if __name__ == "__main__":
    unittest.main()
