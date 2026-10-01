import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SingleAnswer412Tests(unittest.TestCase):
    def test_actual_prompt_writer_and_receipt_compatibility(self):
        result = subprocess.run(['node', 'tests/single_answer_412.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
