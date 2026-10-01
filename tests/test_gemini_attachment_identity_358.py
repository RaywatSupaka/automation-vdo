import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs

class GeminiAttachmentIdentity358Tests(unittest.TestCase):
    def test_real_decoded_blobs_presend_and_watch(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('gemini_attachment_identity_358.js'))],
            capture_output=True, text=True, timeout=40, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
