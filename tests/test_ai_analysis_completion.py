import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AIAnalysisCompletionTests(unittest.TestCase):
    def test_real_analysis_wait_tracks_response_content(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required for the executable Extension contract")
        result = subprocess.run(
            [node, str(ROOT / "tests/ai_analysis_completion_harness.js")],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
