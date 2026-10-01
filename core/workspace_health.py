"""Read-only inventory of jobs hidden by unreadable workspace manifests."""

from __future__ import annotations

import re
import time
from pathlib import Path

from core.atomic_json import AtomicJsonFile, JsonPersistenceError, runtime_backup_path


_KINDS = (
    ("product", "products", "JOB-", "job.json", "สินค้า"),
    ("story", "stories", "STORY-", "job.json", "เรื่องเล่า"),
    ("drama", "drama_series", "SERIES-", "series.json", "ละครสั้น"),
)


def scan_workspace_issues(project_root: Path, *, max_items=20, new_folder_grace_seconds=60):
    """Report missing/unreadable manifests without repairing or changing jobs."""
    root = Path(project_root).resolve()
    issues = []
    for kind, relative, prefix, filename, label in _KINDS:
        base = root / "workspace" / relative
        for folder in sorted(base.glob(f"{prefix}*")):
            if not folder.is_dir() or folder.resolve().parent != base.resolve():
                continue
            manifest = folder / filename
            backup = runtime_backup_path(root, manifest)
            if not manifest.is_file() and not backup.is_file():
                try:
                    if all(child.name.lower() in {"logs", "tmp", "temp"} for child in folder.iterdir()):
                        continue  # A probe/log folder is not a saved job.
                except OSError:
                    pass
                try:
                    if time.time() - folder.stat().st_mtime < new_folder_grace_seconds:
                        continue  # Creation may be in progress.
                except OSError:
                    pass
                reason = "ไม่พบไฟล์สถานะงานหรือไฟล์สำรอง"
            else:
                try:
                    value = AtomicJsonFile(manifest, backup_path=backup).peek()
                    if isinstance(value, dict):
                        continue
                    reason = "ไฟล์สถานะงานไม่ใช่ข้อมูลที่โปรแกรมอ่านได้"
                except (OSError, UnicodeError, ValueError, JsonPersistenceError):
                    reason = "อ่านไฟล์สถานะงานและไฟล์สำรองไม่ได้"
            issues.append({"kind": kind, "label": label, "id": folder.name, "reason": reason})
    return {"count": len(issues), "items": issues[:max(0, int(max_items))]}


def resolve_workspace_issue_folder(project_root: Path, kind: str, item_id: str) -> Path:
    """Resolve only an existing direct child of a known SmartFlow workspace."""
    selected = next((row for row in _KINDS if row[0] == kind), None)
    if selected is None or not re.fullmatch(re.escape(selected[2]) + r"[A-Za-z0-9-]+", str(item_id or "")):
        raise ValueError("รหัสงานไม่ถูกต้อง")
    base = (Path(project_root).resolve() / "workspace" / selected[1]).resolve()
    target = (base / item_id).resolve()
    if target.parent != base or not target.is_dir():
        raise ValueError("ไม่พบโฟลเดอร์งาน")
    return target
