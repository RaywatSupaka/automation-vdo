"""Install a verified unpacked Extension into its existing stable directory."""
import json
import os
import re
import secrets
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def installed_extension_id(folder, chrome_root, selected_profile=""):
    """Find exactly one enabled SmartFlow install loaded from this exact path."""
    folder = Path(folder).resolve()
    matches = []
    root = Path(chrome_root)
    if not root.is_dir():
        raise ValueError("ไม่พบข้อมูลโปรไฟล์ Chrome")
    for profile in root.iterdir():
        if not profile.is_dir() or not re.fullmatch(r"Default|Profile \d+", profile.name):
            continue
        if selected_profile and profile.name != selected_profile:
            continue
        settings = {}
        for name in ("Preferences", "Secure Preferences"):
            try:
                data = json.loads((profile / name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            settings.update(data.get("extensions", {}).get("settings", {}))
        for ident, entry in settings.items():
            if (not re.fullmatch(r"[a-p]{32}", ident) or entry.get("state") not in (None, 1)
                    or entry.get("disable_reasons")):
                continue
            loaded = entry.get("path")
            if not loaded:
                continue
            loaded_path = Path(loaded)
            if not loaded_path.is_absolute():
                loaded_path = profile / "Extensions" / loaded_path
            if loaded_path.resolve() != folder:
                continue
            manifest = entry.get("manifest") or {}
            if not manifest:
                try:
                    manifest = json.loads((loaded_path / "manifest.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
            if manifest.get("name") not in ("SmartFlow AI", "SmartPost AI"):
                continue
            matches.append(ident)
    if len(matches) != 1:
        raise ValueError("ไม่พบ Extension ตัวเดิมในโฟลเดอร์ถาวรเพียงตัวเดียว • ตรวจโปรไฟล์และโฟลเดอร์ที่ Chrome โหลดอยู่")
    return matches[0]


def verify_bundled_package(archive, source_folder):
    """The downloaded package must be the exact Extension paired with this app."""
    source_folder = Path(source_folder)
    if not source_folder.is_dir():
        raise ValueError("โปรแกรมไม่มีไฟล์ Extension รุ่นที่เข้าคู่กัน")
    source = {path.relative_to(source_folder).as_posix(): path
              for path in source_folder.rglob("*") if path.is_file()}
    with zipfile.ZipFile(archive) as packed:
        files = [item for item in packed.infolist() if not item.is_dir()]
        names = [item.filename for item in files]
        if len(names) != len(set(names)) or set(names) != set(source):
            raise ValueError("ไฟล์ Extension ที่ดาวน์โหลดไม่ตรงกับชุดโปรแกรม")
        if any(item.file_size != source[item.filename].stat().st_size for item in files):
            raise ValueError("ขนาดไฟล์ Extension ที่ดาวน์โหลดไม่ตรงกับชุดโปรแกรม")
        for name, path in source.items():
            if packed.read(name) != path.read_bytes():
                raise ValueError("ไฟล์ Extension ที่ดาวน์โหลดไม่ตรงกับชุดโปรแกรม")


def install_archive(archive, folder, expected_version):
    """Stage and swap an Extension ZIP; retain the previous folder for recovery."""
    archive, folder = Path(archive), Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("ไม่พบโฟลเดอร์ Extension ถาวร")
    if json.loads((folder / "manifest.json").read_text(encoding="utf-8")).get("name") != "SmartFlow AI":
        raise ValueError("โฟลเดอร์ที่ติดตั้งไม่ใช่ SmartFlow AI")
    parent = folder.parent.resolve()
    stage = Path(tempfile.mkdtemp(prefix=".browser_extension-update-", dir=parent))
    backup = parent / (".browser_extension-backup-" + secrets.token_hex(8))
    if stage.parent.resolve() != parent or backup.parent.resolve() != parent:
        raise ValueError("ตำแหน่งอัปเดตไม่ถูกต้อง")
    try:
        with zipfile.ZipFile(archive) as packed:
            files = [item for item in packed.infolist() if not item.is_dir()]
            if not files or len(files) > 1000 or sum(item.file_size for item in files) > 200 * 1024 * 1024:
                raise ValueError("จำนวนหรือขนาดไฟล์ Extension ไม่ถูกต้อง")
            names = set()
            for item in files:
                name = item.filename
                parts = PurePosixPath(name).parts
                if (not parts or name.startswith("/") or "\\" in name or ":" in name
                        or any(part in ("", ".", "..") or part.rstrip(" .") != part for part in parts)
                        or (item.external_attr >> 16) & 0o170000 == 0o120000):
                    raise ValueError("ZIP มีเส้นทางไฟล์ไม่ปลอดภัย")
                key = name.casefold()
                if key in names:
                    raise ValueError("ZIP มีชื่อไฟล์ซ้ำ")
                names.add(key)
                destination = stage.joinpath(*parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with packed.open(item) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output)
        manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
        if (manifest.get("manifest_version") != 3 or manifest.get("name") != "SmartFlow AI"
                or manifest.get("version") != expected_version or not (stage / "background.js").is_file()):
            raise ValueError("ZIP ไม่ใช่ SmartFlow Extension รุ่นที่ประกาศ")
        os.replace(folder, backup)
        try:
            os.replace(stage, folder)
        except Exception:
            os.replace(backup, folder)
            raise
        return backup
    finally:
        if stage.exists() and stage.parent.resolve() == parent and stage.name.startswith(".browser_extension-update-"):
            shutil.rmtree(stage)
