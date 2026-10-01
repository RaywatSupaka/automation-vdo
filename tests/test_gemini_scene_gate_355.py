import subprocess
import unittest
from pathlib import Path

class GeminiSceneGate355Tests(unittest.TestCase):
    def test_real_content_gate_and_background_both_providers(self):
        result=subprocess.run(['node','tests/gemini_scene_gate_355.js'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('"cases":10',result.stdout)
