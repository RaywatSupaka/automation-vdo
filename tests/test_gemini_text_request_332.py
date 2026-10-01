import json
import subprocess
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs


class GeminiTextRequest332Tests(unittest.TestCase):
    def test_real_send_acceptance_and_pinned_response_owner(self):
        result = subprocess.run(
            ['node', str(Path(__file__).with_name('gemini_text_request_332_harness.js'))],
            capture_output=True, text=True, encoding='utf-8', timeout=25,
            **hidden_process_kwargs(),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'ok': True, 'cases': 25})


if __name__ == '__main__':
    unittest.main()
