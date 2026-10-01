"""Actual service-worker recovery regressions; no browser/provider operations."""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StoryPostRefreshBackground437Tests(unittest.TestCase):
    def test_missing_result_refresh_single_successor_and_restart_guards(self):
        result = subprocess.run(
            ["node", "tests/story_post_refresh_background_437.cjs"], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        outcome = json.loads(result.stdout)
        self.assertTrue(outcome["ok"])
        self.assertGreaterEqual(outcome["cases"], 38)


if __name__ == "__main__":
    unittest.main()
