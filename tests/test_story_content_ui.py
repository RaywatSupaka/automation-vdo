import subprocess
import unittest
from pathlib import Path


class StoryContentUiTests(unittest.TestCase):
    def test_review_markup_preserves_identity_and_escapes_untrusted_text(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(["node", "tests/story_content_ui_harness.js"], cwd=root,
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_all_style_pickers_explain_medium_only(self):
        source = (Path(__file__).resolve().parents[1] / "web_ui/app.js").read_text(encoding="utf-8")
        self.assertIn("['story', 'story-batch', 'drama']", source)
        self.assertIn("เปลี่ยนเฉพาะวิธีวาด ไม่เปลี่ยนตัวละครหรือเนื้อเรื่อง", source)


if __name__ == "__main__":
    unittest.main()
