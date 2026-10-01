import pathlib
import subprocess
import unittest


class StoryRefreshRedo437Tests(unittest.TestCase):
    def test_actual_content_and_background_recovery_contract(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", "tests/story_refresh_redo_437.cjs"], cwd=root,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"ok":true', result.stdout)
