"""Actual document-fenced reload/collector handoff, without provider actions."""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StoryRefreshDocument438Tests(unittest.TestCase):
    def test_reload_waits_for_new_document_and_pins_resume(self):
        result = subprocess.run(
            ["node", "tests/story_refresh_document_438.cjs"], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        outcome = json.loads(result.stdout)
        self.assertTrue(outcome["ok"])
        self.assertGreaterEqual(outcome["cases"], 18)
        self.assertEqual(outcome["providerSubmissions"], 0)


if __name__ == "__main__":
    unittest.main()
