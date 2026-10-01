"""Background refresh-cycle regressions use only isolated Chrome fixtures."""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StoryRefreshLoopBackground456Tests(unittest.TestCase):
    def test_accepted_owner_cycles_and_redo_guards(self):
        result = subprocess.run(
            ["node", "tests/story_refresh_loop_background_456.cjs"], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        outcome = json.loads(result.stdout)
        self.assertTrue(outcome["ok"])
        self.assertGreaterEqual(outcome["cases"], 35)


if __name__ == "__main__":
    unittest.main()
