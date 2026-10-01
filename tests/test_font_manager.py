import tempfile
import unittest
from pathlib import Path

from core.font_manager import FontManager


class FontManagerTests(unittest.TestCase):
    def test_scans_and_imports_valid_font(self):
        system_font = Path("C:/Windows/Fonts/arial.ttf")
        if not system_font.exists():
            self.skipTest("ไม่มีฟอนต์ระบบสำหรับทดสอบ")
        with tempfile.TemporaryDirectory() as temp:
            manager = FontManager(temp)
            record = manager.upload(system_font)
            self.assertTrue(record.path.is_file())
            self.assertEqual(record.source, "อัปโหลดเอง")
            self.assertTrue(any(item.path == record.path for item in manager.scan()))
            self.assertTrue(manager.portable_path(record.path).startswith("assets/fonts/user/"))

    def test_rejects_non_font_file(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = FontManager(temp)
            fake = Path(temp) / "fake.ttf"
            fake.write_text("not-a-font", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ไม่ใช่ฟอนต์"):
                manager.upload(fake)


if __name__ == "__main__":
    unittest.main()
