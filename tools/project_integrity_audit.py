from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
REPORT_JSON = LOGS / "PROJECT_INTEGRITY_AUDIT.json"
REPORT_TXT = LOGS / "PROJECT_INTEGRITY_AUDIT.txt"
SOURCE_DIRS = [ROOT, ROOT / "core", ROOT / "ui", ROOT / "desktop", ROOT / "tools", ROOT / "tests"]
EXCLUDED_PARTS = {".git", "backups", "workspace", "deliverables", "assets", "logs", "__pycache__", ".pytest_cache"}
REFERENCE_LIST_KEYS = {
    "source_images", "source_footage", "generated_images", "partial_generated_images",
    "reference_images", "output_images",
}
REFERENCE_SINGLE_KEYS = {
    "video_path", "voice_path", "cover_path", "subtitle_path", "final_path", "audio_path",
    "rejected_fallback_video_path",
}


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def source_python_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*.py"):
        if any(part in EXCLUDED_PARTS for part in path.relative_to(ROOT).parts):
            continue
        files.append(path)
    return sorted(set(files))


def audit_python() -> dict:
    errors = []
    broad_excepts = []
    duplicate_defs = []
    function_sizes = []
    files = source_python_files()
    for path in files:
        try:
            source = path.read_text(encoding="utf-8-sig")
            tree = ast.parse(source, filename=str(path))
        except Exception as exc:
            errors.append({"file": rel(path), "error": str(exc)})
            continue
        scopes: list[tuple[str, list[ast.stmt]]] = [("<module>", tree.body)]
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                scopes.append((node.name, node.body))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = int(getattr(node, "end_lineno", node.lineno))
                size = end - node.lineno + 1
                if size >= 180:
                    function_sizes.append({"file": rel(path), "name": node.name, "line": node.lineno, "lines": size})
            if isinstance(node, ast.ExceptHandler):
                broad = node.type is None or (
                    isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}
                )
                body_is_silent = all(isinstance(item, ast.Pass) for item in node.body)
                if broad and body_is_silent:
                    broad_excepts.append({"file": rel(path), "line": node.lineno})
        for scope, body in scopes:
            names = [node.name for node in body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for name, count in Counter(names).items():
                if count > 1:
                    duplicate_defs.append({"file": rel(path), "scope": scope, "name": name, "count": count})
    return {
        "files": len(files),
        "parse_errors": errors,
        "silent_broad_excepts": broad_excepts,
        "duplicate_definitions": duplicate_defs,
        "large_functions": sorted(function_sizes, key=lambda item: item["lines"], reverse=True),
    }


def audit_manifest() -> dict:
    path = ROOT / "browser_extension" / "manifest.json"
    errors = []
    missing = []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"ok": False, "errors": [str(exc)], "missing_files": []}
    candidates = [
        manifest.get("background", {}).get("service_worker"),
        manifest.get("action", {}).get("default_popup"),
    ]
    for item in manifest.get("content_scripts", []):
        candidates.extend(item.get("js", []))
        candidates.extend(item.get("css", []))
    candidates.extend((manifest.get("icons") or {}).values())
    candidates.extend((manifest.get("action", {}).get("default_icon") or {}).values())
    for item in sorted(set(filter(None, candidates))):
        if not (ROOT / "browser_extension" / item).is_file():
            missing.append(item)
    version = str(manifest.get("version") or "")
    bridge = (ROOT / "core" / "local_bridge.py").read_text(encoding="utf-8-sig")
    version_match = f'REQUIRED_EXTENSION_VERSION = "{version}"' in bridge
    if not version_match:
        errors.append("Manifest version ไม่ตรงกับ LocalBridge")
    return {
        "ok": not errors and not missing,
        "version": version,
        "manifest_version": manifest.get("manifest_version"),
        "permissions": manifest.get("permissions", []),
        "host_permissions": manifest.get("host_permissions", []),
        "version_match": version_match,
        "errors": errors,
        "missing_files": missing,
    }


def safe_reference(base: Path, value: object) -> tuple[Path | None, str]:
    raw = str(value or "").strip()
    if not raw:
        return None, "empty"
    candidate = Path(raw)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError:
        return resolved, "outside_job"
    return resolved, "ok"


def iter_job_jsons() -> list[Path]:
    result = []
    for parent in [ROOT / "workspace" / "products", ROOT / "workspace" / "stories", ROOT / "workspace" / "drama_series"]:
        if not parent.is_dir():
            continue
        result.extend(path for path in parent.glob("*/job.json") if path.is_file())
    return sorted(result)


def audit_jobs() -> dict:
    parse_errors = []
    duplicate_ids = []
    outside_references = []
    missing_ready_references = []
    missing_incomplete_references = []
    ids: defaultdict[str, list[str]] = defaultdict(list)
    jobs = iter_job_jsons()
    for path in jobs:
        try:
            job = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            parse_errors.append({"file": rel(path), "error": str(exc)})
            continue
        job_id = str(job.get("id") or "")
        ids[job_id].append(rel(path))
        base = path.parent
        references: list[tuple[str, object]] = []
        for key in REFERENCE_LIST_KEYS:
            for value in job.get(key) or []:
                references.append((key, value))
        for key in REFERENCE_SINGLE_KEYS:
            if job.get(key):
                references.append((key, job.get(key)))
        for key, value in (job.get("flow_clips") or {}).items():
            references.append((f"flow_clips.{key}", value))
        for key, value in references:
            target, state = safe_reference(base, value)
            if state == "outside_job":
                outside_references.append({"job": job_id, "key": key, "value": str(value), "file": rel(path)})
                continue
            if target is None or target.exists():
                continue
            status_text = " ".join(str(job.get(name) or "").lower() for name in (
                "status", "ai_status", "video_status", "voice_status", "cover_status", "flow_video_status"
            ))
            item = {"job": job_id, "key": key, "value": str(value), "file": rel(path)}
            if any(token in status_text for token in ("ready", "complete", "completed")):
                missing_ready_references.append(item)
            else:
                missing_incomplete_references.append(item)
    for job_id, paths in ids.items():
        if job_id and len(paths) > 1:
            duplicate_ids.append({"job": job_id, "files": paths})
    return {
        "jobs": len(jobs),
        "parse_errors": parse_errors,
        "duplicate_ids": duplicate_ids,
        "outside_job_references": outside_references,
        "missing_ready_references": missing_ready_references,
        "missing_incomplete_references": missing_incomplete_references,
    }


def audit_json_files() -> dict:
    targets = [ROOT / "config.json", ROOT / "workspace" / "story_batch_queue.json"]
    errors = []
    checked = []
    for path in targets:
        if not path.is_file():
            continue
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
            checked.append(rel(path))
        except Exception as exc:
            errors.append({"file": rel(path), "error": str(exc)})
    return {"checked": checked, "errors": errors}


def audit_nested_workspace() -> dict:
    suspicious = []
    for path in [
        ROOT / "workspace" / "workspace",
        ROOT / "workspace" / "products" / "workspace",
        ROOT / "workspace" / "stories" / "workspace",
    ]:
        if not path.exists():
            continue
        file_count = sum(1 for item in path.rglob("*") if item.is_file())
        total_bytes = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        suspicious.append({"path": rel(path), "files": file_count, "bytes": total_bytes})
    return {"suspicious_nested_workspace": suspicious}


def audit_runtime_files() -> dict:
    paths = [ROOT / "app.py", ROOT / "RUN.bat", ROOT / "SmartFlow AI.exe", ROOT / "CREATE_SMARTFLOW_SHORTCUT.ps1"]
    return {
        rel(path): {
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
            "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(path.stat().st_mtime)) if path.exists() else "",
        }
        for path in paths
    }


def main() -> int:
    python = audit_python()
    manifest = audit_manifest()
    jobs = audit_jobs()
    json_files = audit_json_files()
    nested = audit_nested_workspace()
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "root": str(ROOT),
        "python": python,
        "extension": manifest,
        "jobs": jobs,
        "json": json_files,
        "workspace": nested,
        "runtime_files": audit_runtime_files(),
    }
    fatal = (
        python["parse_errors"]
        or python["duplicate_definitions"]
        or not manifest["ok"]
        or jobs["parse_errors"]
        or jobs["duplicate_ids"]
        or jobs["outside_job_references"]
        or json_files["errors"]
    )
    report["ok"] = not bool(fatal)
    report["warning_count"] = (
        len(python["silent_broad_excepts"])
        + len(python["large_functions"])
        + len(jobs["missing_ready_references"])
        + len(jobs["missing_incomplete_references"])
        + len(nested["suspicious_nested_workspace"])
    )
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"PROJECT INTEGRITY: {'PASS' if report['ok'] else 'FAIL'}",
        f"Python files: {python['files']}",
        f"Jobs: {jobs['jobs']}",
        f"Warnings: {report['warning_count']}",
        f"Python parse errors: {len(python['parse_errors'])}",
        f"Duplicate definitions: {len(python['duplicate_definitions'])}",
        f"Job JSON errors: {len(jobs['parse_errors'])}",
        f"Duplicate job IDs: {len(jobs['duplicate_ids'])}",
        f"Outside-job references: {len(jobs['outside_job_references'])}",
        f"Missing ready references: {len(jobs['missing_ready_references'])}",
        f"Suspicious nested workspaces: {len(nested['suspicious_nested_workspace'])}",
    ]
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
