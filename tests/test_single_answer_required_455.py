import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RequiredSingleAnswerTests(unittest.TestCase):
    def test_missing_helper_recovers_before_write_or_preserves_draft(self):
        result = subprocess.run(['node', 'tests/single_answer_required_455.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
