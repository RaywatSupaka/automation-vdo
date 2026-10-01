import json
import subprocess
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs


class GeminiStoryResultRecoveryTests(unittest.TestCase):
    def test_exact_owned_image_restore_and_technical_successor(self):
        harness = Path(__file__).with_name("gemini_story_result_recovery_439.cjs")
        result = subprocess.run(
            ["node", str(harness)], capture_output=True, text=True,
            encoding="utf-8", timeout=25, **hidden_process_kwargs()
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {"ok": True, "cases": 29})


if __name__ == "__main__":
    unittest.main()
