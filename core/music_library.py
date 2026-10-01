"""Explicit music pool; None preserves legacy jobs, [] never means all."""
from pathlib import Path

EXTENSIONS = {'.mp3', '.wav', '.m4a', '.aac', '.ogg'}


def resolve_track(folder, name):
    folder = Path(folder).resolve()
    if not isinstance(name, str) or not name or '/' in name or '\\' in name:
        raise ValueError('ชื่อไฟล์เพลงไม่ถูกต้อง')
    path = (folder / name).resolve()
    if path.parent != folder or path.suffix.lower() not in EXTENSIONS or not path.is_file():
        raise ValueError('ไม่พบไฟล์เพลงที่เลือก: ' + name)
    return path


def validate_selection(folder, names, count):
    if not isinstance(names, list) or any(not isinstance(x, str) for x in names):
        raise ValueError('กรุณาเลือกรายการเพลง')
    names = list(dict.fromkeys(names))
    for name in names:
        resolve_track(folder, name)
    if type(count) is not int or count < 1 or count > max(1, len(names)):
        raise ValueError('จำนวนเพลงต้องอยู่ระหว่าง 1 ถึงจำนวนเพลงที่เลือก')
    return names, count


def selected_paths(files, names):
    if names is None:
        return files
    by_name = {p.name: p for p in files}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise ValueError('ไม่พบเพลงที่บันทึกไว้: ' + ', '.join(missing))
    return [by_name[n] for n in names]
