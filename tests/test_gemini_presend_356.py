import subprocess
import unittest
from pathlib import Path
class GeminiPresend356Tests(unittest.TestCase):
    def test_readiness_wait_and_identity(self):
        r=subprocess.run(['node','tests/gemini_presend_356.js'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
