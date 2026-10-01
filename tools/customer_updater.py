"""External updater: signed full code patch, exact-file backup and rollback."""
import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.app_updates import safe_patch_name, verify_release, version


def validate_archive(archive):
    seen, total = set(), 0
    entries = []
    for item in archive.infolist():
        if item.is_dir():
            continue
        name = safe_patch_name(item.filename)
        normalized = str(name).lower()
        if normalized in seen or (item.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError("Duplicate/link in patch")
        seen.add(normalized)
        total += item.file_size
        if total > 2 * 1024**3 or len(seen) > 25000:
            raise ValueError("Patch exceeds extraction limit")
        entries.append((item, name))
    if not {"smartflow ai.exe", "customer-release.json"}.issubset(seen):
        raise ValueError("Patch missing application identity")
    return entries


def apply_patch(root, patch, release, backup):
    root, backup = Path(root).resolve(), Path(backup).resolve()
    local = json.loads((root / "customer-release.json").read_text(encoding="utf-8"))
    if local.get("app_id") != "smartflow" or version(release["version"]) <= version(local["version"]):
        raise ValueError("Wrong app or downgrade rejected")
    if local["version"] not in release.get("supported_from", []):
        raise ValueError("รุ่นนี้ต้องติดตั้งด้วยตัวติดตั้งเต็ม")
    patch = Path(patch)
    with patch.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if patch.stat().st_size != release["patch"]["size"] or digest != release["patch"]["sha256"]:
        raise ValueError("Patch checksum mismatch")
    backup.mkdir(parents=True, exist_ok=False)
    journal = []
    with zipfile.ZipFile(patch) as archive:
        entries = validate_archive(archive)
        packaged = json.loads(archive.read("customer-release.json"))
        if packaged.get("app_id") != "smartflow" or packaged.get("version") != release["version"] or packaged.get("extension_version") != release["extension_version"]:
            raise ValueError("Packaged identity differs from signed release")
        # Stage all content and verify CRC before changing any installed file.
        stage = backup / "stage"
        for item, name in entries:
            target = stage.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
        try:
            for item, name in entries:
                target = root.joinpath(*name.parts)
                if not target.resolve().is_relative_to(root):
                    raise ValueError("Installed path escapes application")
                existed = target.is_file()
                saved = backup / "original" / str(name)
                if existed:
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, saved)
                journal.append({"name": str(name), "existed": existed})
                (backup / "journal.json").write_text(json.dumps(journal), encoding="utf-8")
                target.parent.mkdir(parents=True, exist_ok=True)
                staged = stage.joinpath(*name.parts)
                shutil.copy2(staged, target)
        except Exception:
            rollback(root, backup)
            raise
    return backup


def rollback(root, backup):
    root, backup = Path(root).resolve(), Path(backup)
    for entry in reversed(json.loads((backup / "journal.json").read_text(encoding="utf-8"))):
        name = safe_patch_name(entry["name"])
        target = root.joinpath(*name.parts)
        if not target.resolve().is_relative_to(root):
            raise ValueError("Rollback target escapes application")
        if entry["existed"]:
            shutil.copy2(backup / "original" / str(name), target)
        else:
            target.unlink(missing_ok=True)


def process_alive(pid):
    if pid <= 0:
        return False
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def launch_verified(root, release_version):
    config = Path(os.environ["LOCALAPPDATA"]) / "SmartFlowAI/data/config.json"
    try:
        port = int(json.loads(config.read_text(encoding="utf-8")).get("bridge_port", 8765))
        if not 1 <= port <= 65535:
            raise ValueError("invalid port")
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError):
        raise ValueError("อ่าน config.json สำหรับตรวจการเปิดโปรแกรมไม่ได้ • ยังไม่ได้เปิดโปรแกรมรุ่นใหม่") from None
    marker = config.parent / "logs/desktop-ready.json"
    marker.unlink(missing_ok=True)
    process = subprocess.Popen([str(root / "SmartFlow AI.exe")], cwd=root)
    deadline = time.monotonic() + 50
    while time.monotonic() < deadline and process.poll() is None:
        try:
            with urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                health = json.load(response)
            ready = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else {}
            if health.get("release_version") == release_version and health.get("desktop_ui") == "hybrid" and ready.get("pid") == process.pid and ready.get("engine_pid") == health.get("engine_pid"):
                return
        except Exception:
            pass
        time.sleep(0.5)
    # Only the just-started application is terminated; its job object owns its engine.
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=10)
    raise RuntimeError("โปรแกรมรุ่นใหม่เปิดไม่สำเร็จ คืนไฟล์รุ่นเดิมแล้ว")


def main():
    parser = argparse.ArgumentParser()
    for name in ("root", "release", "patch"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--wait-pid", type=int, default=0)
    parser.add_argument("--engine-pid", type=int, default=0)
    args = parser.parse_args()
    try:
        release = verify_release(json.loads(args.release.read_text(encoding="utf-8")))
        deadline = time.monotonic() + 90
        while process_alive(args.wait_pid) or process_alive(args.engine_pid):
            if time.monotonic() >= deadline:
                raise ValueError("โปรแกรมยังไม่ปิด จึงยังไม่เปลี่ยนไฟล์ กรุณาลองใหม่")
            time.sleep(0.5)
        backup = args.release.parent.parent / "backups" / (release["version"] + "-" + str(time.time_ns()))
        apply_patch(args.root, args.patch, release, backup)
        try:
            launch_verified(args.root, release["version"])
        except Exception:
            rollback(args.root, backup)
            subprocess.Popen([str(args.root / "SmartFlow AI.exe")], cwd=args.root)
            raise
        (backup / "complete.json").write_text(json.dumps({"version": release["version"], "health": "passed"}), encoding="utf-8")
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(0, "อัปเดตไม่สำเร็จ: " + str(exc), "SmartFlow AI", 0x10)


if __name__ == "__main__":
    main()
