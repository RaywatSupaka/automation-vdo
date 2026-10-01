import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs

class GeminiMotionRestart359Tests(unittest.TestCase):
    def test_owned_restart_json_and_state_based_resume(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('gemini_motion_restart_359.js'))],
            capture_output=True, text=True, timeout=30, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
