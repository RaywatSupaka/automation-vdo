import subprocess
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs


class ChatGPTSemanticTurnsTests(unittest.TestCase):
    def test_observed_semantic_dom_actual_source(self):
        result = subprocess.run(
            ['node', 'tests/chatgpt_semantic_turns_435.cjs'],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, encoding='utf-8', timeout=60,
            **hidden_process_kwargs(),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
