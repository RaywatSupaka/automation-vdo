"""Offline actual-source gate for reviewed prompt checkpoint priority."""
import subprocess
import unittest
from pathlib import Path


class StoryOverrideReuseTests(unittest.TestCase):
    def test_reviewed_prompt_checkpoint_priority(self):
        result = subprocess.run(
            ["node", "tests/story_override_reuse_harness.js"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
