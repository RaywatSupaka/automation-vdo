import subprocess
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs


class CoverDownloadBackground450Tests(unittest.TestCase):
    def test_actual_event_handler_keeps_parent_owner_and_reports_replacement_not_error(self):
        result = subprocess.run(
            ['node', str(Path(__file__).with_name('cover_download_replacement_450.cjs'))],
            capture_output=True, text=True, encoding='utf-8', timeout=20, **hidden_process_kwargs(),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
