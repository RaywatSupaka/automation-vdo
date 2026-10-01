"""Historical reply recovery runs against isolated actual Extension code."""
import json
import subprocess
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs

ROOT = Path(__file__).resolve().parents[1]


class AIAnswerRecovery439Tests(unittest.TestCase):
    def test_classification_completed_recovery_and_helper_identity(self):
        run = subprocess.run(
            ['node', str(ROOT / 'tests/ai_answer_recovery_439.cjs')],
            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=30,
            **hidden_process_kwargs(),
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        evidence = json.loads(run.stdout)
        self.assertTrue(evidence['ok'])
        self.assertGreaterEqual(evidence['cases'], 40)
        self.assertEqual(evidence['networkRequests'], 0)
        self.assertEqual(evidence['liveStateWrites'], 0)
