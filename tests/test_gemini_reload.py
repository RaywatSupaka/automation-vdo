import subprocess
import unittest
from core.cancellable_process import hidden_process_kwargs

class GeminiReloadTests(unittest.TestCase):
    def test_reload_budget_cancel_and_exact_acceptance(self):
        result=subprocess.run(['node','tests/gemini_reload_harness.js'],capture_output=True,text=True,encoding='utf-8',timeout=25,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
