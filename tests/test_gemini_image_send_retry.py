import json
import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs


class GeminiImageSendRetryTests(unittest.TestCase):
    def test_actual_gesture_retry_and_late_acceptance_safety(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('gemini_image_send_retry_harness.js'))],
                                capture_output=True, text=True, encoding='utf-8', timeout=25,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'ok': True, 'cases': 60})


if __name__ == '__main__':
    unittest.main()
