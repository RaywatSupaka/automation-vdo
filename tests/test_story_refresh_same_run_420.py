"""A Story refresh attaches to its exact active run without another AI Send."""
import json
import subprocess
import unittest
from pathlib import Path


class StoryRefreshSameRunTests(unittest.TestCase):
    def test_exact_run_is_idempotent_and_other_run_is_not_adopted(self):
        result = subprocess.run(
            ['node', str(Path(__file__).with_name('story_refresh_same_run_420.cjs'))],
            capture_output=True, text=True, encoding='utf-8', timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'ok': True, 'cases': 2})


if __name__ == '__main__':
    unittest.main()
