import subprocess
import unittest
from core.cancellable_process import hidden_process_kwargs

class GeminiDownloadTests(unittest.TestCase):
    def test_same_image_download_recovery(self):
        result=subprocess.run(['node','tests/gemini_download_harness.js'],capture_output=True,text=True,encoding='utf-8',timeout=30,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
