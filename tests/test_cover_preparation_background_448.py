import json
import subprocess
import unittest
from pathlib import Path


class CoverPreparationBackground448Tests(unittest.TestCase):
    def test_actual_cover_preparation_owner_and_refresh_fences(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ['node', 'tests/cover_preparation_background_448.cjs'], cwd=root,
            capture_output=True, text=True, encoding='utf-8', timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreaterEqual(json.loads(result.stdout)['cases'], 40)


if __name__ == '__main__':
    unittest.main()
