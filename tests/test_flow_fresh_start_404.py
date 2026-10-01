import subprocess
import unittest
from pathlib import Path


class FlowFreshStart404Tests(unittest.TestCase):
    def test_authorized_new_scene_does_not_reopen_old_project(self):
        result = subprocess.run(['node', 'tests/flow_fresh_start_404.js'],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, encoding='utf-8', timeout=40)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
