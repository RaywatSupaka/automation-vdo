"""Actual Meta Stop-title regression, isolated browser with synthetic content only."""
import subprocess
import unittest
from pathlib import Path


class MetaStopTitleTests(unittest.TestCase):
    def test_conversation_title_does_not_hide_completed_video(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", str(root / "tests/meta_stop_title.cjs")], cwd=root,
            capture_output=True, text=True, encoding="utf-8", timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
