"""Cross-layer Story refresh/receipt regressions; isolated storage and virtual time."""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StoryImageRefreshOwner459Tests(unittest.TestCase):
    def test_late_image_after_deferred_refresh_preserves_exact_receipt(self):
        result = subprocess.run(
            ["node", "tests/story_image_refresh_owner_459.cjs"], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        outcome = json.loads(result.stdout)
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["mode"], "current")
        self.assertGreaterEqual(outcome["checks"], 90)
        self.assertEqual(outcome["providerSubmissions"], 0)
        self.assertEqual(outcome["liveStateWrites"], 0)


if __name__ == "__main__":
    unittest.main()
