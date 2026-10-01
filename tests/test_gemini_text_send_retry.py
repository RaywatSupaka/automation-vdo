import json
import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs


class GeminiTextSendRetryTests(unittest.TestCase):
    def test_observed_composer_dom_and_historical_thumbnail_race(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('gemini_text_send_dom_harness.js'))],
                                capture_output=True, text=True, encoding='utf-8', timeout=25,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'ok': True, 'cases': 6})

    def test_real_gesture_and_two_prompt_workflow(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('gemini_text_send_retry_harness.js'))],
                                capture_output=True, text=True, encoding='utf-8', timeout=25,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'ok': True, 'cases': 47})


if __name__ == '__main__':
    unittest.main()
