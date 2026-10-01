"""Run exact background guards with a fake browser; no live provider requests."""
import json
import subprocess
import unittest
from pathlib import Path


class StoryImageRefreshBackgroundTests(unittest.TestCase):
    def test_same_receipt_single_refresh_and_same_tab_resume(self):
        result = subprocess.run(
            ["node", str(Path(__file__).with_name("story_image_refresh_background_harness.js"))],
            capture_output=True, text=True, encoding="utf-8", timeout=25,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        outcome = json.loads(result.stdout)
        self.assertTrue(outcome["ok"])
        self.assertGreaterEqual(outcome["cases"], 40)


if __name__ == "__main__":
    unittest.main()
