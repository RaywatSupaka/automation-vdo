import re
import shutil
import ctypes
from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont


SUPPORTED_FONT_EXTENSIONS = {".ttf", ".otf"}


@dataclass(frozen=True)
class FontRecord:
    label: str
    family: str
    style: str
    path: Path
    source: str


class FontManager:
    """Discover bundled fonts and safely import fonts selected by the user."""

    def __init__(self, project_root):
        self.root = Path(project_root).resolve()
        self.bundled_dir = self.root / "assets" / "fonts" / "smartsubai"
        self.user_dir = self.root / "assets" / "fonts" / "user"
        self.bundled_dir.mkdir(parents=True, exist_ok=True)
        self.user_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def inspect(path):
        path = Path(path).resolve()
        if path.suffix.lower() not in SUPPORTED_FONT_EXTENSIONS:
            raise ValueError("รองรับเฉพาะไฟล์ฟอนต์ TTF และ OTF")
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("ไม่พบไฟล์ฟอนต์ที่เลือก")
        if path.stat().st_size > 50 * 1024 * 1024:
            raise ValueError("ไฟล์ฟอนต์ต้องมีขนาดไม่เกิน 50 MB")
        try:
            family, style = ImageFont.truetype(str(path), 24).getname()
        except Exception as exc:
            raise ValueError("ไฟล์นี้ไม่ใช่ฟอนต์ที่โปรแกรมอ่านได้") from exc
        return str(family or path.stem), str(style or "Regular")

    def scan(self):
        records = []
        seen = set()
        for source, folder in (("SmartSubAI", self.bundled_dir), ("อัปโหลดเอง", self.user_dir)):
            for path in sorted(folder.iterdir(), key=lambda item: item.name.lower()):
                if not path.is_file() or path.suffix.lower() not in SUPPORTED_FONT_EXTENSIONS:
                    continue
                try:
                    family, style = self.inspect(path)
                except ValueError:
                    continue
                self._register_private_font(path)
                key = str(path.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                label = f"{family} {style} • {source}"
                records.append(FontRecord(label, family, style, path.resolve(), source))
        return records

    @staticmethod
    def _register_private_font(path):
        """Make bundled/uploaded fonts available to Tk preview without installing globally."""
        try:
            ctypes.windll.gdi32.AddFontResourceExW(str(Path(path).resolve()), 0x10, 0)
        except Exception:
            pass

    def upload(self, source_path):
        source_path = Path(source_path).resolve()
        family, style = self.inspect(source_path)
        safe_stem = re.sub(r"[^A-Za-z0-9ก-๙._-]+", "-", source_path.stem).strip("-._") or "custom-font"
        destination = self.user_dir / f"{safe_stem}{source_path.suffix.lower()}"
        index = 2
        while destination.exists() and destination.read_bytes() != source_path.read_bytes():
            destination = self.user_dir / f"{safe_stem}-{index}{source_path.suffix.lower()}"
            index += 1
        if not destination.exists():
            shutil.copy2(source_path, destination)
        return FontRecord(f"{family} {style} • อัปโหลดเอง", family, style, destination.resolve(), "อัปโหลดเอง")

    def portable_path(self, path):
        value = Path(path).resolve()
        try:
            return value.relative_to(self.root).as_posix()
        except ValueError:
            return str(value)

    def resolve(self, value):
        if not value:
            return None
        path = Path(value)
        return path.resolve() if path.is_absolute() else (self.root / path).resolve()
