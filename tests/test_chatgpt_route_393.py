import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs


class ChatGPTRoute393Tests(unittest.TestCase):
    def test_real_source_provisional_route_transitions(self):
        result = subprocess.run(['node', 'tests/chatgpt_route_393.cjs'],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding='utf-8',
                                timeout=45, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
