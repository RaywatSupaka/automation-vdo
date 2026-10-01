"""Native isolated Chrome serialization + actual helper/background regression."""
import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs


class ReviewStorage419Tests(unittest.TestCase):
    def test_native_storage_and_continuous_helper_rounds(self):
        result = subprocess.run(['node', 'tests/review_storage_419.cjs'],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding='utf-8', timeout=60,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
