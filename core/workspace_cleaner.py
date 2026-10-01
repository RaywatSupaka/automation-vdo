import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs
from core.video_logo import locate_ffmpeg


def working_video_folder(job_folder):
    """Return the private render/checkpoint area used before a Final is accepted."""
    folder = Path(job_folder).resolve() / "videos" / ".working"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class FinalVideoValidator:
    """Validate the actual media streams and duration before cleanup is allowed."""

    def __init__(self, ffmpeg_path="", runner=None):
        ffmpeg = locate_ffmpeg(ffmpeg_path)
        probe_name = "ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe"
        self.ffprobe = ffmpeg.with_name(probe_name)
        self._runner = runner or subprocess.run

    @staticmethod
    def expected_duration(manifest):
        for container_key in ("audio_mix_plan", "render_plan", "video_plan"):
            container = manifest.get(container_key) or {}
            if not isinstance(container, dict):
                continue
            try:
                value = float(container.get("duration") or 0)
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                return value
        return 0.0

    def validate(self, path, manifest=None):
        path = Path(path).resolve()
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError("ไม่พบไฟล์ Final หรือไฟล์ว่าง")
        command = [
            str(self.ffprobe), "-v", "error", "-show_entries",
            "format=duration:stream=index,codec_type,codec_name,width,height,duration",
            "-of", "json", str(path),
        ]
        result = self._runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            **hidden_process_kwargs(),
        )
        if result.returncode:
            raise ValueError("เปิดอ่านวิดีโอ Final ไม่สำเร็จ: " + str(result.stderr or "")[-400:])
        try:
            data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("FFprobe อ่านข้อมูล Final ไม่สมบูรณ์") from exc
        streams = list(data.get("streams") or [])
        video = next((row for row in streams if row.get("codec_type") == "video"), None)
        audio = next((row for row in streams if row.get("codec_type") == "audio"), None)
        try:
            duration = float((data.get("format") or {}).get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0.0
        width = int((video or {}).get("width") or 0)
        height = int((video or {}).get("height") or 0)
        if not video or width <= 0 or height <= 0:
            raise ValueError("Final ไม่มีภาพวิดีโอที่อ่านได้")
        if not audio:
            raise ValueError("Final ไม่มีเสียงประกอบ/เสียงพากย์")
        if duration < 1 or duration > 4 * 60 * 60:
            raise ValueError(f"ความยาว Final ผิดปกติ ({duration:.2f} วินาที)")
        expected = self.expected_duration(manifest or {})
        tolerance = max(2.0, expected * 0.06) if expected else 0.0
        if expected and abs(duration - expected) > tolerance:
            raise ValueError(
                f"ความยาว Final ไม่ตรงแผน ({duration:.2f} / {expected:.2f} วินาที)"
            )
        return {
            "valid": True,
            "path": str(path),
            "size_bytes": int(path.stat().st_size),
            "duration": round(duration, 3),
            "expected_duration": round(expected, 3),
            "width": width,
            "height": height,
            "video_codec": str(video.get("codec_name") or ""),
            "audio_codec": str(audio.get("codec_name") or ""),
            "has_video": True,
            "has_audio": True,
            "validated_at": datetime.now().isoformat(timespec="seconds"),
        }


class WorkspaceCleaner:
    """Find and recycle regenerable SmartFlow files without touching source assets."""

    VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
    CACHE_FOLDERS = {
        "cache": "แคชของโปรแกรม",
        "preview": "ไฟล์พรีวิว",
        "diagnostics": "ไฟล์ตรวจสอบระบบ",
        "qa": "ผลทดสอบชั่วคราว",
        "qa_media_features": "ผลทดสอบสื่อ",
        "test_assets": "ไฟล์ทดสอบ",
    }
    CATEGORY_LABELS = {
        "intermediate_videos": "วิดีโอขั้นกลาง (เก็บ Final ไว้)",
        "cache": "แคชและพรีวิว",
        "diagnostics": "ไฟล์ตรวจสอบและทดสอบ",
        "temporary": "ไฟล์ดาวน์โหลด/เรนเดอร์ที่ไม่สมบูรณ์",
        "old_logs": "Log เก่าเกิน 7 วัน",
    }
    TEMP_SUFFIXES = {".tmp", ".part", ".crdownload", ".download"}

    def __init__(self, root, recycler, logger=None, now=None, validator=None, existing_job_min_age_sec=0):
        self.root = Path(root).resolve()
        self.workspace = (self.root / "workspace").resolve()
        self.logs = (self.root / "logs").resolve()
        self._recycler = recycler
        self._logger = logger
        self._now = now or time.time
        self._validator = validator
        self._existing_job_min_age_sec = max(0, int(existing_job_min_age_sec or 0))

    @classmethod
    def empty_summary(cls):
        return {
            "scan_id": "",
            "scanned_at": "",
            "file_count": 0,
            "size_bytes": 0,
            "job_count": 0,
            "protected_final_count": 0,
            "skipped_active_jobs": 0,
            "invalid_final_jobs": 0,
            "recent_jobs": 0,
            "categories": [
                {"key": key, "label": label, "file_count": 0, "size_bytes": 0}
                for key, label in cls.CATEGORY_LABELS.items()
            ],
            "busy": False,
            "error": "",
            "last_result": {},
            "auto_cleanup_enabled": True,
        }

    def scan(self, active_job_ids=None):
        records, meta = self._collect(active_job_ids or set())
        return self._summary(records, meta)

    def clean(self, scan_id, active_job_ids=None):
        expected = str(scan_id or "").strip()
        if not expected:
            raise ValueError("กรุณาสแกนไฟล์ขยะก่อนยืนยันลบ")
        records, meta = self._collect(active_job_ids or set())
        current = self._summary(records, meta)
        if current["scan_id"] != expected:
            raise ValueError("รายการไฟล์มีการเปลี่ยนแปลง กรุณาสแกนใหม่แล้วกดยืนยันอีกครั้ง")
        if not records:
            return {
                "deleted_count": 0,
                "failed_count": 0,
                "reclaimed_bytes": 0,
                "remaining": current,
            }

        deleted, failed = self._recycle_records(records)
        self._prune_empty_working_dirs(deleted)
        removed_by_manifest = {}
        for record in deleted:
            if record.get("manifest_path"):
                removed_by_manifest.setdefault(record["manifest_path"], []).append(record)

        manifest_failures = []
        for manifest_value, removed in removed_by_manifest.items():
            try:
                self._update_manifest(
                    Path(manifest_value),
                    removed,
                    validation_report=removed[0].get("validation_report") if removed else None,
                )
            except Exception as exc:
                manifest_failures.append({"path": manifest_value, "error": str(exc) or type(exc).__name__})

        remaining = self.scan(active_job_ids or set())
        reclaimed = sum(int(record.get("size_bytes") or 0) for record in deleted)
        if self._logger:
            self._logger.info(
                "state=WORKSPACE_CLEANUP result=%s deleted=%s failed=%s reclaimed_bytes=%s",
                "completed" if not failed and not manifest_failures else "partial",
                len(deleted),
                len(failed) + len(manifest_failures),
                reclaimed,
            )
        return {
            "deleted_count": len(deleted),
            "failed_count": len(failed) + len(manifest_failures),
            "reclaimed_bytes": reclaimed,
            "failed": (failed + manifest_failures)[:20],
            "remaining": remaining,
        }

    def _recycle_records(self, records):
        deleted = []
        failed = []
        for record in records:
            path = Path(record["path"]).resolve()
            if not self._deletion_allowed(path) or not path.is_file():
                failed.append({"path": str(path), "error": "พาธไม่อยู่ในพื้นที่ที่อนุญาต"})
                continue
            try:
                self._recycler(path)
                if path.exists():
                    raise OSError("Windows ยังไม่ได้ย้ายไฟล์ลงถังขยะ")
                deleted.append(record)
            except Exception as exc:
                failed.append({"path": str(path), "error": str(exc) or type(exc).__name__})
        return deleted, failed

    @staticmethod
    def _prune_empty_working_dirs(records):
        candidates = set()
        for record in records:
            path = Path(record.get("path") or "")
            for parent in path.parents:
                if parent.name == ".working" and parent.parent.name == "videos":
                    candidates.add(parent)
                    break
        for folder in sorted(candidates, key=lambda item: len(item.parts), reverse=True):
            try:
                for child in sorted(folder.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                    if child.is_dir():
                        child.rmdir()
                folder.rmdir()
            except OSError:
                # A retained/locked checkpoint keeps the folder intact.
                continue

    def cleanup_completed_job(self, job_id):
        """Clean one newly completed Job after media validation, without touching project assets."""
        job_id = str(job_id or "").strip()
        if not job_id or any(value in job_id for value in ("/", "\\", "..")):
            raise ValueError("Job ID สำหรับล้างไฟล์ไม่ถูกต้อง")
        kind = "product" if job_id.startswith("JOB-") else "story" if job_id.startswith("STORY-") else ""
        if not kind:
            raise ValueError("รองรับเฉพาะ Product และ Story Job")
        section = "products" if kind == "product" else "stories"
        manifest_path = (self.workspace / section / job_id / "job.json").resolve()
        expected_root = (self.workspace / section).resolve()
        if manifest_path.parent.parent != expected_root or not manifest_path.is_file():
            raise ValueError("ไม่พบข้อมูล Job ที่ต้องการเคลียร์")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not self._job_completed(kind, manifest):
            raise ValueError("Job ยังไม่สำเร็จ จึงเก็บไฟล์ Checkpoint ไว้ทั้งหมด")
        videos = (manifest_path.parent / "videos").resolve()
        final_path, final_relative = self._final_video(kind, manifest_path.parent, videos, manifest)
        if not final_path:
            raise ValueError("ไม่พบ Final ที่ตรงกับประเภทงาน")
        validation = self._validate_final(final_path, manifest)
        records = self._job_intermediate_records(
            manifest_path, manifest, kind, final_path, final_relative
        )
        deleted, failed = self._recycle_records(records)
        self._prune_empty_working_dirs(deleted)
        self._update_manifest(
            manifest_path,
            deleted,
            final_relative=final_relative,
            validation_report=validation,
        )
        reclaimed = sum(int(row.get("size_bytes") or 0) for row in deleted)
        if self._logger:
            self._logger.info(
                "job_id=%s state=AUTO_FINAL_CLEANUP result=%s deleted=%s failed=%s reclaimed_bytes=%s final=%s",
                job_id,
                "completed" if not failed else "partial",
                len(deleted),
                len(failed),
                reclaimed,
                final_path.name,
            )
        return {
            "job_id": job_id,
            "final_path": str(final_path),
            "validation": validation,
            "deleted_count": len(deleted),
            "failed_count": len(failed),
            "reclaimed_bytes": reclaimed,
            "failed": failed[:20],
        }

    def _collect(self, active_job_ids):
        active = {str(value or "").strip() for value in active_job_ids if str(value or "").strip()}
        records = {}
        meta = {
            "job_ids": set(),
            "protected_final_count": 0,
            "skipped_active_jobs": 0,
            "invalid_final_jobs": 0,
            "recent_jobs": 0,
        }

        for section in ("products", "stories"):
            root = self.workspace / section
            if not root.is_dir():
                continue
            for manifest_path in root.glob("*/job.json"):
                try:
                    manifest_path = manifest_path.resolve()
                    job_folder = manifest_path.parent.resolve()
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(manifest, dict):
                    continue
                job_id = str(manifest.get("id") or job_folder.name)
                if job_id in active:
                    meta["skipped_active_jobs"] += 1
                    continue
                kind = "product" if section == "products" else "story"
                if not self._job_completed(kind, manifest):
                    continue
                videos = (job_folder / "videos").resolve()
                final_path, final_relative = self._final_video(kind, job_folder, videos, manifest)
                if not final_path:
                    meta["invalid_final_jobs"] += 1
                    continue
                meta["protected_final_count"] += 1
                intermediates = self._job_intermediate_records(
                    manifest_path, manifest, kind, final_path, final_relative
                )
                if not intermediates:
                    continue
                age = max(0.0, float(self._now()) - manifest_path.stat().st_mtime)
                if age < self._existing_job_min_age_sec:
                    meta["recent_jobs"] += 1
                    continue
                try:
                    validation = self._validate_final(final_path, manifest)
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    meta["invalid_final_jobs"] += 1
                    if self._logger:
                        self._logger.warning(
                            "job_id=%s state=FINAL_CLEANUP_SCAN result=protected error=%s",
                            job_id,
                            exc,
                        )
                    continue
                for record in intermediates:
                    record.update({
                        "validation_report": dict(validation),
                        "final_duration": str(validation.get("duration") or 0),
                        "final_width": str(validation.get("width") or 0),
                        "final_height": str(validation.get("height") or 0),
                        "final_video_codec": str(validation.get("video_codec") or ""),
                        "final_audio_codec": str(validation.get("audio_codec") or ""),
                        "final_validated_at": str(validation.get("validated_at") or ""),
                    })
                    records[str(record["path"]).casefold()] = record
                if intermediates:
                    meta["job_ids"].add(job_id)

        for folder_name, label in self.CACHE_FOLDERS.items():
            folder = (self.workspace / folder_name).resolve()
            if not folder.is_dir():
                continue
            category = "cache" if folder_name in {"cache", "preview"} else "diagnostics"
            for candidate in folder.rglob("*"):
                try:
                    path = candidate.resolve()
                    if candidate.is_file() and folder in path.parents:
                        records[str(path).casefold()] = self._record(path, category, source_label=label)
                except OSError:
                    continue

        protected_imports = (self.workspace / "imports").resolve()
        cutoff = float(self._now()) - 24 * 60 * 60
        if self.workspace.is_dir():
            for candidate in self.workspace.rglob("*"):
                try:
                    path = candidate.resolve()
                    if not candidate.is_file() or protected_imports == path or protected_imports in path.parents:
                        continue
                    job_id = self._job_id_for_path(path)
                    if job_id and job_id in active:
                        continue
                    name = path.name.lower()
                    is_temp = path.suffix.lower() in self.TEMP_SUFFIXES or ".rendering." in name
                    if is_temp and candidate.stat().st_mtime < cutoff and str(path).casefold() not in records:
                        records[str(path).casefold()] = self._record(path, "temporary")
                except OSError:
                    continue

        log_cutoff = float(self._now()) - 7 * 24 * 60 * 60
        if self.logs.is_dir():
            for candidate in self.logs.rglob("*"):
                try:
                    path = candidate.resolve()
                    if candidate.is_file() and self.logs in path.parents and candidate.stat().st_mtime < log_cutoff:
                        records[str(path).casefold()] = self._record(path, "old_logs")
                except OSError:
                    continue

        return sorted(records.values(), key=lambda item: str(item["path"]).casefold()), meta

    @staticmethod
    def _job_completed(kind, manifest):
        status = str(manifest.get("status") or "").strip().lower()
        if str(manifest.get("video_status") or "").strip().lower() != "ready":
            return False
        if status in {"error", "failed", "cancelled", "canceled", "deleted", "processing", "running"}:
            return False
        if kind == "story":
            return status == "ready" and str(manifest.get("pipeline_stage") or "").lower() == "complete"
        automation = str(manifest.get("automation_status") or "").strip().lower()
        readiness = manifest.get("readiness") or {}
        if isinstance(readiness, dict) and readiness.get("ready") is False:
            return False
        return automation == "completed" or status in {"ready", "ready_for_phone", "posted", "completed"}

    def _final_video(self, kind, job_folder, videos_folder, manifest):
        relative = str(manifest.get("video_path") or "").strip()
        if not relative:
            return None, ""
        try:
            path = (job_folder / relative).resolve()
            if (
                videos_folder not in path.parents
                or path.suffix.lower() not in self.VIDEO_EXTENSIONS
                or not path.is_file()
                or path.stat().st_size <= 0
            ):
                return None, ""
            if kind == "story" and not re.fullmatch(
                r"story_short_complete(?:_windows(?:_\d+)?)?\.mp4", path.name, re.IGNORECASE
            ):
                return None, ""
            return path, str(path.relative_to(job_folder))
        except (OSError, ValueError):
            return None, ""

    def _validate_final(self, final_path, manifest):
        if self._validator is None:
            raise ValueError("ยังไม่ได้เชื่อมระบบตรวจสอบ Final จึงไม่อนุญาตให้ลบไฟล์")
        report = dict(self._validator.validate(final_path, manifest) or {})
        if not report.get("valid") or not report.get("has_video") or not report.get("has_audio"):
            raise ValueError("Final ยังตรวจภาพและเสียงไม่ผ่าน")
        return report

    def _job_intermediate_records(self, manifest_path, manifest, kind, final_path, final_relative):
        job_folder = manifest_path.parent.resolve()
        videos = (job_folder / "videos").resolve()
        if not videos.is_dir():
            return []
        records = []
        for candidate in videos.rglob("*"):
            try:
                path = candidate.resolve()
                if (
                    not candidate.is_file()
                    or videos not in path.parents
                    or path == final_path
                    or path.suffix.lower() not in self.VIDEO_EXTENSIONS
                ):
                    continue
                records.append(self._record(
                    path,
                    "intermediate_videos",
                    job_id=str(manifest.get("id") or job_folder.name),
                    manifest_path=str(manifest_path),
                    final_relative=final_relative,
                    job_kind=kind,
                ))
            except OSError:
                continue
        return records

    @staticmethod
    def _job_id_for_path(path):
        for parent in path.parents:
            if parent.name.startswith(("JOB-", "STORY-")):
                return parent.name
        return ""

    @staticmethod
    def _record(path, category, **extra):
        stat = path.stat()
        return {
            "path": str(path),
            "category": category,
            "size_bytes": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
            **{key: str(value) for key, value in extra.items()},
        }

    def _summary(self, records, meta):
        digest = hashlib.sha256()
        grouped = {key: {"key": key, "label": label, "file_count": 0, "size_bytes": 0}
                   for key, label in self.CATEGORY_LABELS.items()}
        for record in records:
            digest.update(
                f"{record['path'].casefold()}|{record['size_bytes']}|{record['mtime_ns']}|{record['category']}\n".encode("utf-8")
            )
            group = grouped[record["category"]]
            group["file_count"] += 1
            group["size_bytes"] += int(record["size_bytes"])
        return {
            "scan_id": digest.hexdigest(),
            "scanned_at": datetime.now().isoformat(timespec="seconds"),
            "file_count": len(records),
            "size_bytes": sum(int(record["size_bytes"]) for record in records),
            "job_count": len(meta["job_ids"]),
            "protected_final_count": int(meta["protected_final_count"]),
            "skipped_active_jobs": int(meta["skipped_active_jobs"]),
            "invalid_final_jobs": int(meta.get("invalid_final_jobs") or 0),
            "recent_jobs": int(meta.get("recent_jobs") or 0),
            "categories": list(grouped.values()),
        }

    def _deletion_allowed(self, path):
        path = Path(path).resolve()
        if self.workspace == path or self.logs == path:
            return False
        return self.workspace in path.parents or self.logs in path.parents

    @staticmethod
    def _update_manifest(manifest_path, removed_records, final_relative="", validation_report=None):
        manifest_path = Path(manifest_path).resolve()
        job_folder = manifest_path.parent.resolve()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        removed = {str(Path(record["path"]).resolve()).casefold() for record in removed_records}
        final_relative = str(
            final_relative
            or (removed_records[0].get("final_relative") if removed_records else "")
            or manifest.get("video_path")
            or ""
        )

        def was_removed(value):
            value = str(value or "").strip()
            if not value:
                return False
            try:
                return str((job_folder / value).resolve()).casefold() in removed
            except OSError:
                return False

        cleared_keys = set()
        for key, value in list(manifest.items()):
            if key.endswith("_path") and was_removed(value):
                manifest[key] = ""
                cleared_keys.add(key)
        for path_key, status_key in (
            ("audio_mix_path", "audio_mix_status"),
            ("subtitle_video_path", "subtitle_video_status"),
            ("flow_video_path", "flow_video_status"),
            ("logo_video_path", "logo_status"),
        ):
            if path_key in cleared_keys and str(manifest.get(status_key) or "").lower() == "ready":
                manifest[path_key] = final_relative
        # A validated Final can safely replace its regenerable source clips,
        # but the manifest must retain truthful historical provenance.  Keep
        # the accepted real/local counters while removing only paths to files
        # that were actually recycled.  This also prevents the library from
        # relabelling a hybrid Final as if every segment came from Flow.
        flow_clips = dict(manifest.get("flow_clips") or {})
        removed_remote_slots = {
            str(key) for key, value in flow_clips.items() if was_removed(value)
        }
        remote_total = max(
            len(flow_clips),
            int(manifest.get("flow_remote_clip_count") or 0),
            int(manifest.get("flow_clip_count") or 0),
        )
        manifest["flow_clips"] = {
            str(key): value for key, value in flow_clips.items() if not was_removed(value)
        }

        is_story = job_folder.parent.name.casefold() == "stories"
        if is_story:
            fallback_clips = dict(manifest.get("flow_fallback_clips") or {})
            removed_local_slots = {
                str(key) for key, value in fallback_clips.items() if was_removed(value)
            }
            local_total = max(
                len(fallback_clips), int(manifest.get("flow_fallback_count") or 0)
            )
            manifest["flow_fallback_clips"] = {
                str(key): value for key, value in fallback_clips.items() if not was_removed(value)
            }
            metadata = dict(manifest.get("flow_fallback_metadata") or {})
            for key in removed_local_slots:
                item = metadata.get(key)
                if isinstance(item, dict):
                    item = dict(item)
                    item.pop("clip_path", None)
                    item["retained_in_final"] = final_relative
                    metadata[key] = item
            manifest["flow_fallback_metadata"] = metadata

            prompt_retries = dict(manifest.get("flow_prompt_retries") or {})
            for key in removed_local_slots:
                item = prompt_retries.get(key)
                if not isinstance(item, dict):
                    continue
                item = dict(item)
                item.pop("fallback_clip_path", None)
                item.pop("fallback_saved_at", None)
                item.update({"status": "finalized", "retained_in_final": final_relative})
                prompt_retries[key] = item
            if "flow_prompt_retries" in manifest or prompt_retries:
                manifest["flow_prompt_retries"] = prompt_retries

            superseded = dict(manifest.get("superseded_flow_fallback_clips") or {})
            manifest["superseded_flow_fallback_clips"] = {
                str(key): value for key, value in superseded.items() if not was_removed(value)
            }
            manifest["flow_clip_count"] = remote_total
            manifest["flow_fallback_count"] = local_total
            manifest["flow_scene_count"] = max(
                int(manifest.get("flow_scene_count") or 0), remote_total + local_total
            )
        else:
            local_clips = dict(manifest.get("flow_local_motion_clips") or {})
            removed_local_slots = {
                str(key) for key, value in local_clips.items() if was_removed(value)
            }
            local_total = max(
                len(local_clips), int(manifest.get("flow_local_motion_clip_count") or 0)
            )
            manifest["flow_local_motion_clips"] = {
                str(key): value for key, value in local_clips.items() if not was_removed(value)
            }

            # Preserve the authenticated policy decision/history.  The Final
            # remains usable, so the local render is recorded as finalized;
            # if that Final is deleted later the Video Library cleanup route
            # resets this same checkpoint to render_pending for safe resume.
            fallbacks = dict(manifest.get("flow_policy_fallbacks") or {})
            for key, item in list(fallbacks.items()):
                if not isinstance(item, dict):
                    continue
                if str(key) not in removed_local_slots and not was_removed(item.get("clip_path")):
                    continue
                item = dict(item)
                item.pop("clip_path", None)
                item.pop("render_plan", None)
                item.update({"status": "finalized", "retained_in_final": final_relative})
                fallbacks[str(key)] = item
            manifest["flow_policy_fallbacks"] = fallbacks

            provenance = dict(manifest.get("flow_segment_provenance") or {})
            for key, item in list(provenance.items()):
                if not isinstance(item, dict):
                    continue
                if str(key) not in (removed_remote_slots | removed_local_slots) and not was_removed(item.get("clip_path")):
                    continue
                item = dict(item)
                item.pop("clip_path", None)
                item["retained_in_final"] = final_relative
                provenance[str(key)] = item
            manifest["flow_segment_provenance"] = provenance
            manifest["flow_clip_count"] = remote_total
            manifest["flow_remote_clip_count"] = remote_total
            manifest["flow_local_motion_clip_count"] = local_total
            manifest["flow_segment_count"] = max(
                int(manifest.get("flow_segment_count") or 0), remote_total + local_total
            )
        stale = dict(manifest.get("stale_processed_outputs") or {})
        manifest["stale_processed_outputs"] = {key: value for key, value in stale.items() if not was_removed(value)}
        manifest.update({
            "video_status": "ready",
            "video_path": final_relative,
            "cleanup_status": "final_only",
            "cleanup_removed_count": int(manifest.get("cleanup_removed_count") or 0) + len(removed_records),
            "cleanup_reclaimed_bytes": int(manifest.get("cleanup_reclaimed_bytes") or 0)
                + sum(int(record.get("size_bytes") or 0) for record in removed_records),
            "cleanup_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        if validation_report:
            manifest["final_validation"] = dict(validation_report)
            manifest["final_validation_status"] = "passed"
        temporary = manifest_path.with_name(f".{manifest_path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, manifest_path)
