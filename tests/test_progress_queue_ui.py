import shutil
import subprocess
import unittest
from pathlib import Path


class ProgressQueueUiTests(unittest.TestCase):
    def test_completed_dialog_closes_in_real_dom(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/progress_autoclose_dom.js'], cwd=root,
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"cases":8', result.stdout)

    def test_actual_javascript_popup_and_queue_controls(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node.js is required for the UI contract harness')
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([node, str(root / 'tests' / 'progress_queue_ui_harness.js')],
                                cwd=root, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
