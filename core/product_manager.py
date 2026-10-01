import json
from core.flow_settings import flow_settings
from core.media_audio import flow_audio_instruction
import base64
import binascii
import functools
import html
import hashlib
import mimetypes
import os
import re
import socket
import shutil
import threading
import time
import urllib.request
import urllib.error
import uuid
import unicodedata
from datetime import datetime
from ipaddress import ip_address
from pathlib import Path

from core.workspace_cleaner import working_video_folder
from core.clip_cover import COVER_PROMPT, normalize_cover, ensure_cover
from core.ai_web_models import normalize_ai_web_model
from core.product_source_images import canonical_source_image_paths, select_source_images, verified_source_image_paths
from core.atomic_json import AtomicJsonFile, JsonPersistenceError, runtime_backup_path
from core.flow_fallback import (
    FLOW_ATTACHMENT_UNCONFIRMED, FLOW_LOCAL_FALLBACK_CODES,
    validated_attachment_failure_evidence,
)
from urllib.parse import urlparse, urlunparse

from PIL import Image

try:
    from pythainlp.tokenize import syllable_tokenize as thai_syllable_tokenize
    from pythainlp.tokenize import word_tokenize as thai_word_tokenize
except Exception:  # Optional fallback keeps the app usable before dependencies are installed.
    thai_syllable_tokenize = None
    thai_word_tokenize = None

from core.thai_tts import prepare_thai_tts_script
from core.smartsub_online import SmartSubOnlineClient


_PRODUCT_MANIFEST_LOCK = threading.RLock()


def _serialized_manifest_operation(method):
    """Keep every job.json read/modify/write transaction inside one process lock."""
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._manifest_lock:
            return method(self, *args, **kwargs)
    return wrapped


class ProductManager:
    def __init__(self, root: Path):
        self.project_root = Path(root).resolve()
        self.root = self.project_root / "workspace" / "products"
        self.root.mkdir(parents=True, exist_ok=True)
        # A process-wide re-entrant lock also protects callers that construct a
        # second ProductManager for the same workspace (bridge/tools/tests).
        self._manifest_lock = _PRODUCT_MANIFEST_LOCK

    @staticmethod
    def _migrate_retired_video_provider(job):
        """Move retired-provider jobs to Google Flow without exposing stale UI state."""
        changed = False
        if str(job.get("video_ai_provider") or "flow").strip().lower() == "meta":
            job["video_ai_provider"] = "flow"
            changed = True

        # Earlier migrations kept the retired provider name for diagnostics.
        # Desktop state includes Product Job details, so that internal marker
        # leaked back into the program even after every provider button and
        # Extension route had been removed.
        if str(job.get("legacy_video_ai_provider") or "").strip().lower() == "meta":
            job.pop("legacy_video_ai_provider", None)
            changed = True

        source_type = str(job.get("video_source_type") or "").strip().lower()
        source_migrations = {
            "meta_pending": "google_flow_pending",
            "meta_clips": "google_flow_clips",
            "meta_ai_vibes_clips": "google_flow_clips",
            "meta_ai_vibes_composite": "google_flow_composite",
        }
        if source_type in source_migrations:
            job["video_source_type"] = source_migrations[source_type]
            changed = True
        if source_type == "meta_pending":
            job["flow_video_status"] = "waiting_generation"
            job["video_status"] = "waiting_flow"

        retired_markers = ("meta ai", "meta.ai", "vibes")
        contains_retired_name = lambda value: any(
            marker in str(value or "").lower() for marker in retired_markers
        )
        if contains_retired_name(job.get("automation_error")):
            job["automation_error"] = ""
            if str(job.get("automation_status") or "") == "error":
                job["automation_status"] = "idle"
                job["automation_stage"] = "flow"
            changed = True
        if contains_retired_name(job.get("last_error")):
            job["last_error"] = ""
            changed = True
        if contains_retired_name(job.get("last_runtime_recovery_reason")):
            job["last_runtime_recovery_reason"] = "ย้ายงานเดิมมาทำต่อด้วย Google Flow จาก Checkpoint"
            changed = True

        history = list(job.get("automation_failure_history") or [])
        history_changed = False
        for item in history:
            if isinstance(item, dict) and contains_retired_name(item.get("error")):
                item["error"] = "ผู้สร้างวิดีโอเดิมทำงานไม่สำเร็จ • ย้ายไป Google Flow และเก็บ Checkpoint เดิมแล้ว"
                history_changed = True
        if history_changed:
            job["automation_failure_history"] = history
            changed = True

        if changed:
            job["video_provider_migrated_at"] = datetime.now().isoformat(timespec="seconds")
        return changed

    def _manifest_store(self, path):
        path = Path(path)
        return AtomicJsonFile(
            path,
            backup_path=runtime_backup_path(self.project_root, path),
        )

    def _load_manifest_file(self, path, *, read_only=False):
        from core.product_job_deletion import assert_path_available
        assert_path_available(path)
        store = self._manifest_store(path)
        value = store.peek() if read_only else store.read()
        if not isinstance(value, dict):
            raise ValueError("Product manifest ว่างเปล่าหรือเสียหาย")
        if isinstance(value.get("source_images"), list):
            value["source_images"] = canonical_source_image_paths(Path(path).parent, value["source_images"])
        return value

    def _save_manifest_file(self, path, manifest):
        """Atomically replace job.json so readers never observe half-written JSON."""
        from core.product_job_deletion import assert_path_available
        assert_path_available(path)
        if isinstance(manifest.get("source_images"), list):
            manifest["source_images"] = canonical_source_image_paths(Path(path).parent, manifest["source_images"])
        self._manifest_store(path).write(manifest)
        return manifest

    def list_jobs(self):
        jobs = []
        for path in sorted(self.root.glob("JOB-*"), reverse=True):
            manifest = path / "job.json"
            if manifest.is_file() or runtime_backup_path(self.project_root, manifest).is_file():
                try:
                    job = self._load_manifest_file(manifest, read_only=True)
                    changed = self._migrate_retired_video_provider(job)
                    shop_id, product_id = self.product_ids_from_url(job.get("posting_product_url") or job.get("product_url") or "")
                    if shop_id and not job.get("shop_id"): job["shop_id"] = shop_id; changed = True
                    if product_id and not job.get("product_id"): job["product_id"] = product_id; changed = True
                    if job.get("product_source") == "manual_link" and job.get("affiliate_url"):
                        current_url = job.get("product_url") or ""
                        parsed_url = urlparse(current_url)
                        canonical_url = urlunparse(parsed_url._replace(query="", fragment="")) if parsed_url.scheme else current_url
                        if current_url and not job.get("resolved_product_url"): job["resolved_product_url"] = current_url; changed = True
                        if canonical_url and job.get("product_url") != canonical_url: job["product_url"] = canonical_url; changed = True
                        if job.get("posting_product_url") != job.get("affiliate_url"): job["posting_product_url"] = job["affiliate_url"]; changed = True
                    if job.get("ai_status") == "ready" and not job.get("ai_review_status"):
                        job["ai_review_status"] = "needs_review"; changed = True
                    spoken_path = path / "captions" / "spoken_script.txt"
                    if spoken_path.exists() and not job.get("spoken_script"):
                        job["spoken_script"] = spoken_path.read_text(encoding="utf-8").strip(); changed = True
                    voice_files = list((path / "audio").glob("voiceover.*")) if (path / "audio").exists() else []
                    if voice_files and job.get("voice_status") != "ready":
                        job["voice_status"] = "ready"
                        job["voice_path"] = str(voice_files[0].relative_to(path)); changed = True
                    elif not job.get("voice_status"):
                        job["voice_status"] = "not_generated"; changed = True
                    subtitle_files = list((path / "captions").glob("subtitle.*")) if (path / "captions").exists() else []
                    if subtitle_files and job.get("subtitle_status") != "ready":
                        job["subtitle_status"] = "ready"; changed = True
                    elif not job.get("subtitle_status"):
                        job["subtitle_status"] = "not_generated"; changed = True
                    readiness = self._readiness(job)
                    if job.get("readiness") != readiness: job["readiness"] = readiness; changed = True
                    # A dashboard poll must not rewrite a saved prompt, receipt,
                    # timestamp or manifest. Explicit AI dispatch upgrades the
                    # request under its normal job transaction.
                    jobs.append(job)
                except (OSError, ValueError, JsonPersistenceError):
                    continue
        # The random suffix in JOB-YYYYMMDD-XXXXXX is not chronological.
        # Product history is ordered by creation time so housekeeping or a
        # settings edit cannot unexpectedly reshuffle old jobs to the top.
        return sorted(
            jobs,
            key=lambda item: (
                str(item.get("created_at") or item.get("updated_at") or ""),
                str(item.get("id") or ""),
            ),
            reverse=True,
        )

    @_serialized_manifest_operation
    def get_job(self, job_id):
        job_id = str(job_id or "")
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        path = self.root / job_id / "job.json"
        if not path.is_file() and not runtime_backup_path(self.project_root, path).is_file():
            raise ValueError("ไม่พบ Product Job")
        job = self._load_manifest_file(path)
        # Keep legacy presentation compatible without mutating the job merely
        # because a detail panel or bridge reader requested it.
        self._migrate_retired_video_provider(job)
        return job

    def set_automation_state(self, job_id, status, stage="", error=""):
        allowed = {"running", "completed", "cancelled", "error", "idle"}
        status = str(status or "idle").strip().lower()
        if status not in allowed:
            raise ValueError("สถานะ Automation ไม่ถูกต้อง")
        manifest = self.get_job(job_id)
        previous_stage = str(manifest.get("automation_stage") or "")
        if status == "error":
            failures = list(manifest.get("automation_failure_history") or [])
            failures.append({
                "at": datetime.now().isoformat(timespec="seconds"),
                "stage": previous_stage or str(stage or "stopped"),
                "error": str(error or "ไม่ทราบสาเหตุ")[:1500],
            })
            manifest["automation_failure_history"] = failures[-20:]
            manifest["automation_failure_total"] = int(manifest.get("automation_failure_total") or 0) + 1
        manifest.update({
            "automation_status": status,
            "automation_stage": str(stage or ""),
            "automation_error": str(error or "")[:3000],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        path = self.root / str(job_id) / "job.json"
        self._save_manifest_file(path, manifest)
        return manifest

    def mark_runtime_recovering(self, job_id, reason="โปรแกรมหยุดระหว่างทำงาน"):
        """Persist one bounded startup recovery without deleting checkpoints."""
        manifest = self.get_job(job_id)
        manifest.update({
            "automation_status": "running",
            "runtime_recovery_count": int(manifest.get("runtime_recovery_count") or 0) + 1,
            "last_runtime_recovery_reason": str(reason or "")[:1500],
            "last_runtime_recovery_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        path = self.root / str(job_id) / "job.json"
        self._save_manifest_file(path, manifest)
        return manifest

    def mark_ai_recovering(self, job_id, reason=""):
        manifest = self.get_job(job_id)
        attempts = int(manifest.get("ai_auto_recovery_attempts") or 0) + 1
        manifest.update({
            "status": "waiting_ai",
            "automation_status": "running",
            "automation_stage": "ai",
            "automation_error": "",
            "ai_auto_recovery_attempts": attempts,
            "ai_last_recovery_reason": str(reason or "")[:1500],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        path = self.root / str(job_id) / "job.json"
        self._save_manifest_file(path, manifest)
        return manifest

    @_serialized_manifest_operation
    def advance_flow_policy_prompt(self, job_id, shot_index, reason=""):
        """Move one failed Flow shot to the next, materially safer prompt."""
        manifest = self.get_job(job_id)
        shot_index = int(shot_index or 0)
        if not 1 <= shot_index <= 3:
            raise ValueError("ลำดับช็อต Google Flow ไม่ถูกต้อง")
        modes = dict(manifest.get("flow_prompt_retry_modes") or {})
        current = str(modes.get(str(shot_index)) or "")
        next_mode = "policy_safe_v1" if not current else "policy_minimal_v1"
        modes[str(shot_index)] = next_mode
        history = list(manifest.get("flow_policy_retry_history") or [])
        history.append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "shot_index": shot_index,
            "from": current or "product_specific_v1",
            "to": next_mode,
            "reason": str(reason or "")[:1000],
        })
        manifest.update({
            "flow_prompt_retry_modes": modes,
            "flow_policy_retry_history": history[-12:],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_manifest_file(self.root / str(job_id) / "job.json", manifest)
        return manifest, next_mode

    @staticmethod
    def _refresh_product_segment_state(manifest):
        """Keep per-provider Product segment totals truthful."""
        remote = dict(manifest.get("flow_clips") or {})
        local = dict(manifest.get("flow_local_motion_clips") or {})
        meta = dict(manifest.get("meta_clips") or {})
        target_count = int(
            manifest.get("flow_target_clip_count")
            or len(manifest.get("composition_images") or manifest.get("generated_images") or manifest.get("source_images") or [])
            or 3
        )
        flow_slots = {
            str(index) for index in range(1, target_count + 1)
            if remote.get(str(index)) or local.get(str(index))
        }
        meta_slots = {str(index) for index in range(1, target_count + 1) if meta.get(str(index))}
        selected_provider = str(manifest.get("video_ai_provider") or "flow").strip().lower()
        active_slots = meta_slots if selected_provider == "meta_ai" else flow_slots
        flow_ready = len(flow_slots) >= target_count
        ready = len(active_slots) >= target_count
        if selected_provider == "meta_ai":
            source_type = "meta_ai_clips" if meta_slots else "meta_ai_pending"
        elif local:
            source_type = "google_flow_hybrid_clips"
        elif remote:
            source_type = "google_flow_clips"
        else:
            source_type = "google_flow_pending"
        manifest.update({
            # ``flow_clip_count`` remains genuine Google Flow only for old UI
            # and API consumers. ``video_segment_count`` describes only the
            # currently-selected provider; clips from a former provider are
            # retained but must not make the active route look complete.
            "flow_clip_count": len(remote),
            "flow_remote_clip_count": len(remote),
            "flow_local_motion_clip_count": len(local),
            "meta_clip_count": len(meta),
            "flow_segment_count": len(flow_slots),
            "video_segment_count": len(active_slots),
            "flow_required_clip_count": target_count,
            "flow_video_status": "ready" if flow_ready else "waiting_downloads",
            "video_status": "clips_ready" if ready else "collecting_clips",
            "video_source_type": source_type,
        })
        return manifest

    def mark_flow_policy_fallback(
        self, job_id, shot_index, source_image_index, reason="",
        category="policy", fingerprint="", flow_run_id="",
    ):
        """Checkpoint an authenticated policy decision before local rendering."""
        return self._mark_flow_local_fallback(
            job_id, shot_index, source_image_index, reason, category,
            fingerprint, flow_run_id, failure_code="FLOW_POLICY_BLOCKED",
        )

    def mark_flow_attachment_fallback(
        self, job_id, shot_index, source_image_index, reason="",
        fingerprint="", flow_run_id="", evidence=None,
    ):
        """Checkpoint a latched attachment failure without calling it policy."""
        proof = validated_attachment_failure_evidence(evidence, flow_run_id, fingerprint)
        return self._mark_flow_local_fallback(
            job_id, shot_index, source_image_index, reason, "attachment_unconfirmed",
            fingerprint, flow_run_id, failure_code=FLOW_ATTACHMENT_UNCONFIRMED,
            evidence=proof,
        )

    @staticmethod
    def flow_local_fallback_checkpoint(manifest, shot_index):
        key = str(int(shot_index or 0))
        reused = dict((manifest.get("image_reuse_fallbacks") or {}).get(key) or {})
        if (reused.get("failure_code") == "USER_APPROVED_IMAGE_REUSE" and reused.get("user_approved") is True
                and reused.get("revision") == manifest.get("image_recovery_revision")
                and (manifest.get("image_slot_origins") or {}).get(key, {}).get("origin") == "reused_existing"
                and reused.get("source_sha256")):
            return reused
        for field, code in (
            ("flow_policy_fallbacks", "FLOW_POLICY_BLOCKED"),
            ("flow_attachment_fallbacks", FLOW_ATTACHMENT_UNCONFIRMED),
        ):
            checkpoint = dict((manifest.get(field) or {}).get(key) or {})
            if checkpoint.get("failure_code") == code:
                if code == FLOW_ATTACHMENT_UNCONFIRMED:
                    try:
                        validated_attachment_failure_evidence(
                            checkpoint.get("attachment_failure_evidence"),
                            checkpoint.get("flow_run_id"), checkpoint.get("failure_card_fingerprint"),
                        )
                    except ValueError:
                        continue
                return checkpoint
        return {}

    @_serialized_manifest_operation
    def _mark_flow_local_fallback(
        self, job_id, shot_index, source_image_index, reason="", category="policy",
        fingerprint="", flow_run_id="", failure_code="FLOW_POLICY_BLOCKED", evidence=None,
    ):
        """Checkpoint one terminal decision before local rendering.

        Persisting this first makes resume idempotent: a crash during FFmpeg
        rendering can only retry the local render, never upload/submit the
        rejected source image to Google Flow again.
        """
        job_id = str(job_id)
        shot_index = int(shot_index or 0)
        source_image_index = int(source_image_index or shot_index)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path = folder / "job.json"
        if not manifest_path.is_file():
            raise ValueError("ไม่พบ Job")
        manifest = self._load_manifest_file(manifest_path)
        image_files = list(manifest.get("composition_images") or manifest.get("generated_images") or manifest.get("source_images") or [])
        target_count = len(image_files) or int(manifest.get("flow_target_clip_count") or 3)
        if not 1 <= shot_index <= target_count or not 1 <= source_image_index <= len(image_files):
            raise ValueError("ลำดับรูปต้นทาง Google Flow ไม่ถูกต้อง")
        if failure_code == FLOW_ATTACHMENT_UNCONFIRMED and not (folder / str(image_files[source_image_index - 1])).is_file():
            raise ValueError("ไม่พบรูปต้นทางสำหรับคลิปเคลื่อนไหวในเครื่อง")
        if dict(manifest.get("flow_clips") or {}).get(str(shot_index)):
            return manifest
        if self.flow_local_fallback_checkpoint(manifest, shot_index):
            return manifest

        now = datetime.now().isoformat(timespec="seconds")
        key = str(shot_index)
        attachment = failure_code == FLOW_ATTACHMENT_UNCONFIRMED
        fallback_field = "flow_attachment_fallbacks" if attachment else "flow_policy_fallbacks"
        history_field = "flow_attachment_fallback_history" if attachment else "flow_policy_fallback_history"
        source_type = "product_local_motion_attachment_fallback" if attachment else "product_local_motion_policy_fallback"
        category_field = "failure_category" if attachment else "policy_category"
        fallback = dict((manifest.get(fallback_field) or {}).get(key) or {})
        fallback.update({
            "shot_index": shot_index,
            "source_image_index": source_image_index,
            "source_image": str(image_files[source_image_index - 1]),
            "failure_code": failure_code,
            category_field: str(category or "policy")[:100],
            "failure_card_fingerprint": str(fingerprint or fallback.get("failure_card_fingerprint") or "")[:160],
            "flow_run_id": str(flow_run_id or fallback.get("flow_run_id") or "")[:160],
            "reason": str(reason or fallback.get("reason") or "")[:1500],
            "status": "ready" if fallback.get("status") == "ready" else "render_pending",
            "first_seen_at": str(fallback.get("first_seen_at") or now),
            "updated_at": now,
        })
        if attachment:
            fallback["attachment_failure_evidence"] = dict(evidence or {})
        fallbacks = dict(manifest.get(fallback_field) or {})
        fallbacks[key] = fallback
        failed_sources = dict(manifest.get("flow_failed_source_images") or {})
        failed_sources[str(source_image_index)] = {
            "at": now,
            "category": str(category or "policy")[:100],
            "reason": str(reason or "")[:1000],
            "output_slot": shot_index,
            "failure_code": failure_code,
            "failure_card_fingerprint": str(fingerprint or "")[:160],
            "flow_run_id": str(flow_run_id or "")[:160],
            "fallback": source_type,
        }
        source_map = dict(manifest.get("flow_source_image_map") or {})
        variant_map = dict(manifest.get("flow_source_variant_map") or {})
        source_map[key] = source_image_index
        variant_map[key] = 1
        retry_modes = dict(manifest.get("flow_prompt_retry_modes") or {})
        retry_modes.pop(key, None)
        history = list(manifest.get(history_field) or [])
        history_key = (shot_index, str(fallback.get("failure_card_fingerprint") or ""))
        if not any(
            (int(item.get("shot_index") or 0), str(item.get("failure_card_fingerprint") or "")) == history_key
            for item in history if isinstance(item, dict)
        ):
            history.append({
                "at": now,
                "shot_index": shot_index,
                "source_image_index": source_image_index,
                "failure_code": failure_code,
                category_field: str(category or "policy")[:100],
                "failure_card_fingerprint": str(fingerprint or "")[:160],
                "flow_run_id": str(flow_run_id or "")[:160],
                "action": "local_motion_fallback",
            })
        manifest.update({
            fallback_field: fallbacks,
            "flow_failed_source_images": failed_sources,
            "flow_source_image_map": source_map,
            "flow_source_variant_map": variant_map,
            "flow_prompt_retry_modes": retry_modes,
            history_field: history[-20:],
            "flow_target_clip_count": target_count,
            "updated_at": now,
        })
        self._refresh_product_segment_state(manifest)
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    @_serialized_manifest_operation
    def ensure_product_flow_source_identity(self, job_id):
        """Retire legacy quota reallocation for every unfinished Product slot."""
        job_id = str(job_id)
        manifest_path = self.root / job_id / "job.json"
        if not manifest_path.is_file():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        image_files = list(manifest.get("composition_images") or manifest.get("generated_images") or manifest.get("source_images") or [])
        target_count = len(image_files) or int(manifest.get("flow_target_clip_count") or 3)
        remote = dict(manifest.get("flow_clips") or {})
        local = dict(manifest.get("flow_local_motion_clips") or {})
        fallbacks = {
            **dict(manifest.get("flow_policy_fallbacks") or {}),
            **dict(manifest.get("flow_attachment_fallbacks") or {}),
        }
        source_map = dict(manifest.get("flow_source_image_map") or {})
        variant_map = dict(manifest.get("flow_source_variant_map") or {})
        retry_modes = dict(manifest.get("flow_prompt_retry_modes") or {})
        changed = False
        for index in range(1, target_count + 1):
            key = str(index)
            if remote.get(key) or local.get(key) or fallbacks.get(key):
                continue
            if int(source_map.get(key) or index) != index or int(variant_map.get(key) or 1) != 1:
                changed = True
            source_map[key] = index
            variant_map[key] = 1
            if key in retry_modes:
                retry_modes.pop(key, None)
                changed = True
        if changed or source_map != dict(manifest.get("flow_source_image_map") or {}) or variant_map != dict(manifest.get("flow_source_variant_map") or {}):
            manifest.update({
                "flow_source_image_map": source_map,
                "flow_source_variant_map": variant_map,
                "flow_prompt_retry_modes": retry_modes,
                "flow_legacy_reallocation_retired_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            })
            self._save_manifest_file(manifest_path, manifest)
        return manifest

    @_serialized_manifest_operation
    def attach_flow_local_motion_clip(self, job_id, shot_index, source_path, render_plan=None):
        """Attach a local Product segment without mislabelling it as Flow."""
        job_id = str(job_id)
        shot_index = int(shot_index or 0)
        source = Path(source_path)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        if not source.is_file() or source.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi"}:
            raise ValueError("ไฟล์คลิปเคลื่อนไหวในเครื่องไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path = folder / "job.json"
        if not manifest_path.is_file():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        key = str(shot_index)
        fallback = self.flow_local_fallback_checkpoint(manifest, shot_index)
        if fallback.get("failure_code") not in (*FLOW_LOCAL_FALLBACK_CODES, "USER_APPROVED_IMAGE_REUSE"):
            raise ValueError("ยังไม่มี Checkpoint ยืนยันสำหรับคลิปเคลื่อนไหวในเครื่อง")
        attachment = fallback["failure_code"] == FLOW_ATTACHMENT_UNCONFIRMED
        reused_image = fallback["failure_code"] == "USER_APPROVED_IMAGE_REUSE"
        fallback_field = "image_reuse_fallbacks" if reused_image else "flow_attachment_fallbacks" if attachment else "flow_policy_fallbacks"
        if dict(manifest.get("flow_clips") or {}).get(key):
            raise ValueError(f"ช็อต {shot_index} มีคลิป Google Flow แล้ว จึงห้ามซ้อน Local Motion")
        target = working_video_folder(folder) / f"product_local_motion_shot_{shot_index:02d}{source.suffix.lower()}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        local = dict(manifest.get("flow_local_motion_clips") or {})
        local[key] = str(target.relative_to(folder))
        fallback.update({
            "status": "ready",
            "clip_path": str(target.relative_to(folder)),
            "render_plan": json.loads(json.dumps(dict(render_plan or {}), ensure_ascii=False, default=str)),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        fallbacks = dict(manifest.get(fallback_field) or {})
        fallbacks[key] = fallback
        provenance = dict(manifest.get("flow_segment_provenance") or {})
        provenance[key] = {
            "source_type": "product_local_motion_user_image_reuse" if reused_image else "product_local_motion_attachment_fallback" if attachment else "product_local_motion_policy_fallback",
            "source_image_index": int(fallback.get("source_image_index") or shot_index),
            "source_image": str(fallback.get("source_image") or ""),
            "clip_path": str(target.relative_to(folder)),
            "failure_code": fallback["failure_code"],
            "failure_category" if attachment or reused_image else "policy_category": (
                "user_approved_image_reuse" if reused_image else "attachment_unconfirmed" if attachment else str(fallback.get("policy_category") or "policy")
            ),
            "reason": str(fallback.get("reason") or ""),
            "failure_card_fingerprint": str(fallback.get("failure_card_fingerprint") or ""),
            "flow_run_id": str(fallback.get("flow_run_id") or ""),
        }
        manifest.update({
            "flow_local_motion_clips": local,
            fallback_field: fallbacks,
            "flow_segment_provenance": provenance,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._refresh_product_segment_state(manifest)
        manifest["readiness"] = self._readiness(manifest)
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    @_serialized_manifest_operation
    def reassign_flow_shot_source(self, job_id, shot_index, failed_source_index=0, reason="", category="policy"):
        """Move one output slot to another usable image without reducing the clip target."""
        manifest = self.get_job(job_id)
        shot_index = int(shot_index or 0)
        image_files = list(manifest.get("composition_images") or manifest.get("generated_images") or manifest.get("source_images") or [])
        target_count = len(image_files) or int(manifest.get("flow_target_clip_count") or 3)
        if not 1 <= shot_index <= target_count:
            raise ValueError("ลำดับช็อต Google Flow ไม่ถูกต้อง")
        clips = dict(manifest.get("flow_clips") or {})
        if clips.get(str(shot_index)):
            return manifest, 0

        source_map = {
            str(index): int((manifest.get("flow_source_image_map") or {}).get(str(index)) or index)
            for index in range(1, target_count + 1)
        }
        failed_source_index = int(failed_source_index or source_map.get(str(shot_index)) or shot_index)
        if not 1 <= failed_source_index <= target_count:
            raise ValueError("ลำดับรูปต้นทาง Google Flow ไม่ถูกต้อง")

        slot_attempts = dict(manifest.get("flow_slot_source_attempts") or {})
        attempted = []
        for value in list(slot_attempts.get(str(shot_index)) or []):
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
            if 1 <= value <= target_count and value not in attempted:
                attempted.append(value)
        if failed_source_index not in attempted:
            attempted.append(failed_source_index)
        slot_attempts[str(shot_index)] = attempted

        failed_sources = dict(manifest.get("flow_failed_source_images") or {})
        failed_sources[str(failed_source_index)] = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "category": str(category or "policy")[:80],
            "reason": str(reason or "")[:1000],
            "output_slot": shot_index,
        }
        blocked_sources = {int(key) for key in failed_sources if str(key).isdigit()}
        candidates = [*range(failed_source_index + 1, target_count + 1), *range(failed_source_index - 1, 0, -1)]
        replacement = next((index for index in candidates if index not in blocked_sources and index not in attempted), 0)
        if replacement:
            source_map[str(shot_index)] = replacement

        variant_map = {}
        source_counts = {}
        for output_slot in range(1, target_count + 1):
            source_index = int(source_map.get(str(output_slot)) or output_slot)
            source_counts[source_index] = source_counts.get(source_index, 0) + 1
            variant_map[str(output_slot)] = source_counts[source_index]

        retry_modes = dict(manifest.get("flow_prompt_retry_modes") or {})
        retry_modes.pop(str(shot_index), None)
        history = list(manifest.get("flow_reallocation_history") or [])
        history.append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "output_slot": shot_index,
            "failed_source_image": failed_source_index,
            "replacement_source_image": replacement,
            "reason": str(reason or "")[:1000],
        })
        manifest.update({
            "flow_source_image_map": source_map,
            "flow_source_variant_map": variant_map,
            "flow_slot_source_attempts": slot_attempts,
            "flow_failed_source_images": failed_sources,
            "flow_reallocation_history": history[-12:],
            "flow_prompt_retry_modes": retry_modes,
            "flow_skipped_shots": {},
            "flow_target_clip_count": target_count,
            "flow_required_clip_count": target_count,
            "flow_clip_count": len(clips),
            "flow_video_status": "ready" if len(clips) >= target_count else "waiting_downloads",
            "video_status": "clips_ready" if len(clips) >= target_count else "collecting_clips",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_manifest_file(self.root / str(job_id) / "job.json", manifest)
        return manifest, replacement

    def reset_ai_recovery_attempts(self, job_id):
        manifest = self.get_job(job_id)
        manifest.pop("ai_auto_recovery_attempts", None)
        manifest.pop("ai_last_recovery_reason", None)
        path = self.root / str(job_id) / "job.json"
        self._save_manifest_file(path, manifest)
        return manifest

    @staticmethod
    def validate_shopee_url(value):
        value = str(value or "").strip()
        if not value:
            raise ValueError("กรุณาวางลิงก์สินค้า")
        if "://" not in value:
            value = "https://" + value
        parsed = urlparse(value)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (hostname == "shopee.co.th" or hostname.endswith(".shopee.co.th")):
            raise ValueError("อนุญาตเฉพาะลิงก์ HTTPS ของ Shopee Thailand")
        return urlunparse(parsed._replace(fragment=""))

    @staticmethod
    def product_ids_from_url(url):
        for pattern in (r"[?&](?:itemId|item_id)=(\d+)", r"-i\.(\d+)\.(\d+)", r"/product/(\d+)/(\d+)", r"/opaanlp/(\d+)/(\d+)"):
            match = re.search(pattern, url, re.I)
            if match:
                return (match.group(1), match.group(2)) if len(match.groups()) == 2 else ("", match.group(1))
        return "", ""

    def import_link(self, value, force_new=False):
        original_url = self.validate_shopee_url(value)
        final_url, metadata = self._resolve_product_link(original_url)
        shop_id, product_id = self.product_ids_from_url(final_url)
        parsed_final = urlparse(final_url)
        canonical_url = urlunparse(parsed_final._replace(query="", fragment=""))
        name = metadata.get("title") or (f"สินค้า Shopee • ID {product_id}" if product_id else "สินค้า Shopee จากลิงก์")
        product = {
            "shop_id": shop_id,
            "product_id": product_id,
            "product_name": name,
            "product_url": canonical_url,
            "resolved_product_url": final_url,
            "posting_product_url": original_url,
            "affiliate_url": original_url,
            "description": metadata.get("description", ""),
            "images": [metadata["image"]] if metadata.get("image") else [],
            "product_source": "manual_link",
            "link_status": "verified",
            "captured_at": datetime.now().isoformat(timespec="seconds"),
        }
        return self.import_product(product, force_new=force_new)

    def create_story_source(self, value, request_id, options=None):
        """Create or recover one Product source job for an idempotent UI request."""
        request_id = str(request_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", request_id):
            raise ValueError("รหัสคำขอเตรียมสินค้าไม่ถูกต้อง")
        validated_url = self.validate_shopee_url(value)
        link_hash = hashlib.sha256(validated_url.encode("utf-8")).hexdigest()
        for existing in self.list_jobs():
            if str(existing.get("story_prepare_request_id") or "") != request_id:
                continue
            if existing.get("story_prepare_link_sha256") != link_hash:
                raise ValueError("รหัสคำขอเดิมถูกผูกกับลิงก์สินค้าอื่นแล้ว")
            return existing, False

        from core.product_prepare_options import freeze_product_options
        prepare_options = freeze_product_options(options)
        job, created = self.import_link(validated_url, force_new=True)
        self._manifest_store(self.root / job["id"] / "job.json").update(
            lambda row: {
                **row,
                "story_source_only": True,
                "story_prepare_request_id": request_id,
                "story_prepare_link_sha256": link_hash,
                "story_prepare_options": prepare_options,
            }
        )
        return self.get_job(job["id"]), created

    def story_source_preparations(self):
        """Return safe summary rows for pre-AI Shopee captures that can resume."""
        rows = []
        for job in self.list_jobs():
            if not job.get("story_source_only") or job.get("story_job_id") or job.get("story_queued_item_id"):
                continue
            verified = verified_source_image_paths(self.root / job["id"], job.get("source_images") or [])
            name = str(job.get("product_name") or "").strip()
            placeholder = name == "สินค้า Shopee จากลิงก์" or name.startswith("สินค้า Shopee • ID ")
            rows.append({
                "id": str(job["id"]),
                "request_id": str(job.get("story_prepare_request_id") or ""),
                "product_name": name,
                "created_at": str(job.get("created_at") or ""),
                "source_image_count": len(verified),
                "capture_ready": bool(not placeholder and verified),
                "capture_command_status": str(job.get("story_capture_status") or ""),
                "prepare_options": job.get("story_prepare_options") if isinstance(job.get("story_prepare_options"), dict) else {},
            })
        return rows

    def link_story_job(self, source_job_id, story_job_id):
        source_job_id, story_job_id = str(source_job_id or "").strip(), str(story_job_id or "").strip()
        if not source_job_id.startswith("JOB-") or not story_job_id.startswith("STORY-"):
            raise ValueError("รหัสงาน Product Story ไม่ถูกต้อง")
        path = self.root / source_job_id / "job.json"
        def update(row):
            if not row.get("story_source_only"):
                raise ValueError("Product Job นี้ไม่ใช่งานเตรียมคลิปสินค้า")
            previous = str(row.get("story_job_id") or "")
            if previous and previous != story_job_id:
                raise ValueError("งานเตรียมสินค้านี้ผูกกับ Story Job อื่นแล้ว")
            return {**row, "story_job_id": story_job_id, "story_dispatched_at": row.get("story_dispatched_at") or datetime.now().isoformat(timespec="seconds")}
        return self._manifest_store(path).update(update)

    def import_product(self, product, force_new=False, target_job_id="", target_capture_command_id=""):
        if not isinstance(product, dict):
            raise ValueError("ข้อมูลสินค้าต้องเป็น object")
        name = str(product.get("product_name") or "").strip()
        url = str(product.get("product_url") or "").strip()
        if not name or not url:
            raise ValueError("ไม่พบชื่อสินค้าหรือลิงก์สินค้า")
        incoming_product_id = str(product.get("product_id") or "")
        target_job_id = str(target_job_id or "").strip()
        existing = None
        if target_job_id:
            existing = self.get_job(target_job_id)
            expected_capture_command = str(existing.get("story_capture_command_id") or "")
            incoming_capture_command = str(target_capture_command_id or "").strip()
            if existing.get("story_source_only") and (
                not expected_capture_command or expected_capture_command != incoming_capture_command
            ):
                raise ValueError("ผลอ่านสินค้าไม่ตรงคำสั่งจับภาพปัจจุบัน • เก็บงานเตรียมสินค้าไว้")
            if expected_capture_command and incoming_capture_command and expected_capture_command != incoming_capture_command:
                raise ValueError("ผลอ่านสินค้าเป็นของคำสั่งเก่า • เก็บงานเตรียมสินค้าปัจจุบันไว้")
            target_product_id = str(existing.get("product_id") or "")
            if incoming_product_id and target_product_id and incoming_product_id != target_product_id:
                raise ValueError("ข้อมูลสินค้าจาก Chrome ไม่ตรงกับ Product Job เป้าหมาย")
        elif not force_new:
            existing = next((j for j in self.list_jobs() if (j.get("product_url") == url or (incoming_product_id and j.get("product_id") == incoming_product_id)) and j.get("status") not in {"failed", "posted"}), None)
        if existing:
            changed = False
            folder = self.root / existing["id"]
            for key in ("shop_id", "product_id", "posting_product_url", "affiliate_url", "link_status"):
                incoming = str(product.get(key) or "")
                if incoming and not existing.get(key): existing[key] = incoming; changed = True
            placeholder_name = re.fullmatch(r"สินค้า Shopee(?: จากลิงก์| • ID \d+)?", str(existing.get("product_name") or ""))
            if placeholder_name and name and not re.fullmatch(r"สินค้า Shopee(?: จากลิงก์| • ID \d+)?", name):
                existing["product_name"] = name; changed = True
            for key in ("price", "commission", "description"):
                incoming = str(product.get(key) or "").strip()
                if incoming and (not existing.get(key) or key == "description"):
                    existing[key] = incoming[:10000] if key == "description" else incoming
                    changed = True
            saved_images = list(existing.get("source_images") or [])
            verified_images = verified_source_image_paths(folder, saved_images)
            if verified_images != saved_images:
                saved_images = verified_images
                existing["source_images"] = saved_images
                changed = True
            if not saved_images:
                original_folder = folder / "original"
                old_indices = [int(match.group(1)) for path in original_folder.glob("product_*.*")
                               if (match := re.match(r"product_(\d+)\.", path.name))]
                offset = max(old_indices, default=0)
                saved_images, capture = self._download_product_images(product.get("images") or [], original_folder, offset)
                if capture != existing.get("source_image_capture"):
                    existing["source_image_capture"] = capture
                    changed = True
                if saved_images:
                    existing["source_images"] = saved_images
                    changed = True
            if changed:
                has_real_name = not re.fullmatch(r"สินค้า Shopee(?: จากลิงก์| • ID \d+)?", str(existing.get("product_name") or ""))
                saved_images = verified_source_image_paths(folder, existing.get("source_images") or saved_images)
                existing["source_images"] = saved_images
                ai_state = "request_ready" if saved_images and has_real_name else "needs_product_data"
                existing["ai_status"] = ai_state
                existing["status"] = "waiting_ai" if ai_state == "request_ready" else "needs_product_data"
                existing["ai_review_status"] = "not_generated"
                existing["readiness"] = self._readiness(existing)
                existing["updated_at"] = datetime.now().isoformat(timespec="seconds")
                self._save_manifest_file(self.root / existing["id"] / "job.json", existing)
                product_snapshot = dict(product)
                product_snapshot["merged_into_job"] = existing["id"]
                (folder / "product.json").write_text(json.dumps(product_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
                self._write_ai_request(folder, existing)
            return existing, False
        job_id = f"JOB-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        folder = self.root / job_id
        for child in ("original", "generated", "captions", "prompts", "videos", "audio", "assets", "screenshots", "ai_inbox"):
            (folder / child).mkdir(parents=True, exist_ok=True)
        saved_images, image_capture = self._download_product_images(product.get("images") or [], folder / "original")
        now = datetime.now().isoformat(timespec="seconds")
        manifest = {
            "id": job_id,
            "product_id": str(product.get("product_id") or ""),
            "shop_id": str(product.get("shop_id") or ""),
            "product_name": name,
            "product_url": url,
            "posting_product_url": str(product.get("posting_product_url") or url),
            "affiliate_url": str(product.get("affiliate_url") or ""),
            "resolved_product_url": str(product.get("resolved_product_url") or ""),
            "product_source": str(product.get("product_source") or "browser_extension"),
            "campaign_source_job": str(product.get("campaign_source_job") or ""),
            "link_status": str(product.get("link_status") or "verified"),
            "price": str(product.get("price") or ""),
            "commission": str(product.get("commission") or ""),
            "description": str(product.get("description") or "")[:10000],
            "source_images": saved_images,
            "source_image_capture": image_capture,
            "status": "waiting_ai" if saved_images and name != "สินค้า Shopee จากลิงก์" else "needs_product_data",
            "ai_status": "request_ready" if saved_images and name != "สินค้า Shopee จากลิงก์" else "needs_product_data",
            "ai_review_status": "not_generated",
            "video_status": "missing",
            "voice_status": "not_generated",
            "subtitle_status": "not_generated",
            "subtitle_requested": False,
            "phone_transfer_status": "pending",
            "post_status": "pending",
            "readiness": {"ready": False, "missing": ["caption", "video"]},
            "created_at": now,
            "updated_at": now,
        }
        (folder / "product.json").write_text(json.dumps(product, ensure_ascii=False, indent=2), encoding="utf-8")
        self._save_manifest_file(folder / "job.json", manifest)
        self._write_ai_request(folder, manifest)
        return manifest, True

    def apply_ai_result(self, result, *, image_provenance=None):
        if not isinstance(result, dict):
            raise ValueError("ผลลัพธ์ AI ต้องเป็น object")
        job_id = str(result.get("job_id") or "")
        if not job_id.startswith("JOB-") or any(char in job_id for char in "/\\.."):
            raise ValueError("job_id ไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path = folder / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        caption = str(result.get("caption_short") or "").strip()
        hashtags = result.get("hashtags") or []
        if isinstance(hashtags, str): hashtags = [hashtags]
        video_prompt = str(result.get("video_prompt") or "").strip()
        pronunciation_notes = result.get("pronunciation_notes") or {}
        if not isinstance(pronunciation_notes, dict):
            pronunciation_notes = {}
        spoken_script_raw = str(result.get("spoken_script") or "").strip()
        spoken_script, tts_issues = prepare_thai_tts_script(spoken_script_raw, pronunciation_notes)
        spoken_script_short_raw = str(result.get("spoken_script_short") or "").strip()
        spoken_script_short, short_tts_issues = prepare_thai_tts_script(spoken_script_short_raw, pronunciation_notes) if spoken_script_short_raw else ("", [])
        warnings = result.get("warnings") or []
        if isinstance(warnings, str):
            warnings = [warnings]
        warnings = list(warnings)
        warnings.extend(issue for issue in tts_issues + short_tts_issues if issue not in warnings)
        (folder / "captions" / "caption.txt").write_text(caption, encoding="utf-8")
        (folder / "captions" / "hashtags.txt").write_text(" ".join(map(str, hashtags)), encoding="utf-8")
        (folder / "captions" / "spoken_script_raw.txt").write_text(spoken_script_raw, encoding="utf-8")
        (folder / "captions" / "spoken_script.txt").write_text(spoken_script, encoding="utf-8")
        if spoken_script_short_raw:
            (folder / "captions" / "spoken_script_short_raw.txt").write_text(spoken_script_short_raw, encoding="utf-8")
            (folder / "captions" / "spoken_script_short.txt").write_text(spoken_script_short, encoding="utf-8")
        if pronunciation_notes:
            (folder / "captions" / "pronunciation_notes.json").write_text(json.dumps(pronunciation_notes, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "prompts" / "google_flow_prompt.txt").write_text(video_prompt, encoding="utf-8")
        caption_alternatives = result.get("caption_alternatives") or []
        if caption_alternatives:
            (folder / "captions" / "caption_alternatives.txt").write_text("\n\n".join(str(item) for item in caption_alternatives), encoding="utf-8")
        shot_list = result.get("shot_list") or []
        if shot_list:
            (folder / "prompts" / "shot_plan.json").write_text(json.dumps(shot_list, ensure_ascii=False, indent=2), encoding="utf-8")
        flow_shots = result.get("flow_shot_prompts") or []
        if flow_shots:
            (folder / "prompts" / "google_flow_shots.txt").write_text("\n\n".join(f"SHOT {index}\n{item}" for index, item in enumerate(flow_shots, 1)), encoding="utf-8")
            (folder / "prompts" / "google_flow_shots.json").write_text(json.dumps(flow_shots, ensure_ascii=False, indent=2), encoding="utf-8")
        image_prompts = result.get("image_prompts") or []
        if image_prompts:
            (folder / "prompts" / "image_prompts.json").write_text(json.dumps(image_prompts, ensure_ascii=False, indent=2), encoding="utf-8")
        editing_overlay_plan = result.get("editing_overlay_plan") or []
        if editing_overlay_plan:
            (folder / "prompts" / "editing_overlay_plan.json").write_text(json.dumps(editing_overlay_plan, ensure_ascii=False, indent=2), encoding="utf-8")
        flow_gui_design = result.get("flow_gui_design") or []
        if flow_gui_design:
            (folder / "prompts" / "flow_gui_design.json").write_text(json.dumps(flow_gui_design, ensure_ascii=False, indent=2), encoding="utf-8")
        spoken_segments_raw = result.get("spoken_script_segments") or []
        spoken_segments = []
        segment_issues = []
        for segment in spoken_segments_raw:
            prepared, issues = prepare_thai_tts_script(str(segment or "").strip(), pronunciation_notes)
            if prepared:
                spoken_segments.append(prepared)
            segment_issues.extend(issues)
        if spoken_segments:
            (folder / "captions" / "spoken_segments.json").write_text(json.dumps(spoken_segments, ensure_ascii=False, indent=2), encoding="utf-8")
        warnings.extend(issue for issue in segment_issues if issue not in warnings)
        (folder / "ai_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        generated = []
        for index, encoded in enumerate(result.get("generated_images") or [], 1):
            if not isinstance(encoded, str): continue
            raw = encoded.split(",", 1)[-1]
            data = base64.b64decode(raw, validate=True)
            if len(data) > 20 * 1024 * 1024: raise ValueError("รูป AI มีขนาดเกิน 20 MB")
            target = folder / "generated" / f"selling_image_{index:02d}.png"
            target.write_bytes(data); generated.append(str(target.relative_to(folder)))
        selected_provider = str(manifest.get("image_ai_provider") or "chatgpt").strip().lower()
        provider_text = str(result.get("image_generation_provider") or result.get("provider") or selected_provider).lower()
        if "gemini" in provider_text:
            selected_provider = "gemini"
        manifest.update({"status": "waiting_review", "ai_status": "ready", "ai_review_status": "needs_review", "ai_provider": str(result.get("provider") or f"{selected_provider}_web_extension"), "image_generation_provider": str(result.get("image_generation_provider") or f"{selected_provider}_web"), "image_generation_via_chatgpt_web": bool(result.get("image_generation_via_chatgpt_web", selected_provider == "chatgpt")), "image_generation_via_gemini_web": bool(result.get("image_generation_via_gemini_web", selected_provider == "gemini")), "generated_from_source_images": bool(manifest.get("source_images")), "generated_images": generated, "image_prompts": list(image_prompts), "flow_shot_prompts": list(flow_shots), "flow_gui_design": list(flow_gui_design), "editing_overlay_plan": list(editing_overlay_plan), "spoken_script_segments": spoken_segments, "caption": caption, "spoken_script_raw": spoken_script_raw, "spoken_script": spoken_script, "spoken_script_short": spoken_script_short, "pronunciation_notes": pronunciation_notes, "tts_script_issues": tts_issues + short_tts_issues + segment_issues, "warnings": warnings, "updated_at": datetime.now().isoformat(timespec="seconds")})
        if generated:
            previous_clips = dict(manifest.get("flow_clips") or {})
            previous_local_clips = dict(manifest.get("flow_local_motion_clips") or {})
            previous_meta_clips = dict(manifest.get("meta_clips") or {})
            previous_meta_receipts = dict(manifest.get("meta_clip_receipts") or {})
            # The receipt journal is keyed by scene, so a new image set must
            # archive its old owner before starting fresh Meta request IDs.
            # Keep the old evidence in-place rather than deleting it.
            meta_receipt_store = self._manifest_store(folder / "prompts" / "meta_video_receipts.json")
            with meta_receipt_store.locked():
                receipt_data = meta_receipt_store.read_unlocked(default={"scenes": {}})
                old_scenes = dict(receipt_data.get("scenes") or {})
                if old_scenes:
                    stale_receipts = list(receipt_data.get("stale_contexts") or [])
                    stale_receipts.append({"at": datetime.now().isoformat(timespec="seconds"), "scenes": old_scenes})
                    receipt_data["stale_contexts"] = stale_receipts[-10:]
                    receipt_data["scenes"] = {}
                    meta_receipt_store.write_unlocked(receipt_data)
            previous_video = str(manifest.get("video_path") or "")
            manifest.update({
                "stale_flow_clips": previous_clips,
                "stale_flow_local_motion_clips": previous_local_clips,
                "stale_meta_clips": previous_meta_clips,
                "stale_meta_clip_receipts": previous_meta_receipts,
                "stale_video_path": previous_video,
                "flow_clips": {},
                "flow_local_motion_clips": {},
                "meta_clips": {},
                "meta_clip_receipts": {},
                "meta_clip_count": 0,
                "flow_policy_fallbacks": {},
                "flow_policy_fallback_history": [],
                "flow_attachment_fallbacks": {},
                "flow_attachment_fallback_history": [],
                "flow_segment_provenance": {},
                "flow_prompt_retry_modes": {},
                "flow_policy_retry_history": [],
                "flow_skipped_shots": {},
                "flow_source_image_map": {str(index): index for index in range(1, len(generated) + 1)},
                "flow_source_variant_map": {str(index): 1 for index in range(1, len(generated) + 1)},
                "flow_failed_source_images": {},
                "flow_slot_source_attempts": {},
                "flow_reallocation_history": [],
                "flow_target_clip_count": len(generated),
                "flow_required_clip_count": len(generated),
                "flow_clip_count": 0,
                "flow_remote_clip_count": 0,
                "flow_local_motion_clip_count": 0,
                "flow_segment_count": 0,
                "video_segment_count": 0,
                "flow_video_status": "waiting_generation",
                "video_status": "waiting_flow",
                "video_path": "",
                "flow_video_path": "",
                "video_source_type": "meta_ai_pending" if str(manifest.get("video_ai_provider") or "flow") == "meta_ai" else "google_flow_pending",
            })
        manifest.pop("partial_generated_images", None)
        # A deliberately imported new image set invalidates old consent and
        # composition maps, but never deletes the underlying media files.
        if "generated_images" in result:
            for field in ("composition_images", "image_reuse_fallbacks", "image_slot_origins",
                          "image_recovery_revision", "image_recovery_result_digest", "recovered_image_count"):
                manifest.pop(field, None)
            manifest.update(ai_generated_image_count=len(generated), reused_image_count=0)
        if image_provenance:
            manifest.update(image_provenance)
        manifest.pop("partial_image_count", None)
        manifest.pop("ai_auto_recovery_attempts", None)
        manifest.pop("ai_last_recovery_reason", None)
        manifest["cover"] = normalize_cover(result.get("cover") or manifest.get("cover"))
        # Cover is optional for Product: a typography problem must not restart AI/Flow.
        if generated:
            try:
                manifest.update(ensure_cover(self.project_root, folder, manifest))
                manifest.pop("cover_error", None)
            except (OSError, ValueError) as exc:
                manifest["cover_error"] = str(exc)
        manifest["readiness"] = self._readiness(manifest)
        if manifest["readiness"]["ready"]: manifest["status"] = "ready_for_phone"
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def attach_video(self, job_id, source_path):
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        source = Path(source_path)
        if not source.is_file() or source.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi"}:
            raise ValueError("ไฟล์วิดีโอไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path = folder / "job.json"
        if not manifest_path.exists(): raise ValueError("ไม่พบ Job")
        target = folder / "videos" / f"final{source.suffix.lower()}"
        shutil.copy2(source, target)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({"video_status": "ready", "video_path": str(target.relative_to(folder)), "video_source_type": "manual_uploaded_video", "status": "waiting_caption", "updated_at": datetime.now().isoformat(timespec="seconds")})
        manifest["readiness"] = self._readiness(manifest)
        if manifest["readiness"]["ready"]: manifest["status"] = "ready_for_phone"
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def invalidate_stale_flow_outputs(self, job_id):
        """Detach old Flow clips after the reference images/prompts have changed; keep files recoverable."""
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        path = self.root / job_id / "job.json"
        if not path.is_file():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest.update({
            "stale_flow_clips": dict(manifest.get("flow_clips") or {}),
            "stale_flow_local_motion_clips": dict(manifest.get("flow_local_motion_clips") or {}),
            "stale_video_path": str(manifest.get("video_path") or ""),
            "flow_clips": {},
            "flow_local_motion_clips": {},
            "flow_policy_fallbacks": {},
            "flow_policy_fallback_history": [],
            "flow_attachment_fallbacks": {},
            "flow_attachment_fallback_history": [],
            "flow_segment_provenance": {},
            "flow_prompt_retry_modes": {},
            "flow_policy_retry_history": [],
            "flow_skipped_shots": {},
            "flow_source_image_map": {},
            "flow_source_variant_map": {},
            "flow_failed_source_images": {},
            "flow_slot_source_attempts": {},
            "flow_reallocation_history": [],
            "flow_target_clip_count": len(manifest.get("composition_images") or manifest.get("generated_images") or manifest.get("source_images") or []),
            "flow_required_clip_count": len(manifest.get("composition_images") or manifest.get("generated_images") or manifest.get("source_images") or []),
            "flow_clip_count": 0,
            "flow_remote_clip_count": 0,
            "flow_local_motion_clip_count": 0,
            "flow_segment_count": 0,
            "flow_video_status": "waiting_generation",
            "video_status": "waiting_flow",
            "video_path": "",
            "flow_video_path": "",
            "video_source_type": "google_flow_pending",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        manifest["readiness"] = self._readiness(manifest)
        self._save_manifest_file(path, manifest)
        return manifest

    @_serialized_manifest_operation
    def attach_flow_clip(self, job_id, shot_index, source_path, provider="flow"):
        job_id = str(job_id)
        shot_index = int(shot_index)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        if not 1 <= shot_index <= 9:
            raise ValueError("ลำดับช็อตไม่ถูกต้อง")
        provider = str(provider or "flow").strip().lower()
        if provider != "flow":
            raise ValueError("ผู้ให้บริการสร้างวิดีโอไม่ถูกต้อง")
        provider_name = "Google Flow"
        source = Path(source_path)
        if not source.is_file() or source.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi"}:
            raise ValueError("ไฟล์วิดีโอไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path = folder / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            self.flow_local_fallback_checkpoint(manifest, shot_index)
            or dict(manifest.get("flow_local_motion_clips") or {}).get(str(shot_index))
        ):
            raise ValueError(
                f"ช็อต {shot_index} มี Checkpoint คลิปเคลื่อนไหวในเครื่องแล้ว • "
                "ต้องใช้คลิปเคลื่อนไหวในเครื่องจากรูปเดิมและห้ามส่งซ้ำ"
            )

        def fingerprint(path):
            digest = hashlib.sha256()
            with Path(path).open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()

        source_hash = fingerprint(source)
        for existing_index, relative in dict(manifest.get("flow_clips") or {}).items():
            if str(existing_index) == str(shot_index):
                continue
            existing = folder / str(relative or "")
            if existing.is_file() and fingerprint(existing) == source_hash:
                raise ValueError(f"วิดีโอ {provider_name} ช็อต {shot_index} ซ้ำกับช็อต {existing_index}")
        target = working_video_folder(folder) / f"flow_shot_{shot_index:02d}{source.suffix.lower()}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        clips = dict(manifest.get("flow_clips") or {})
        clips[str(shot_index)] = str(target.relative_to(folder))
        target_count = int(manifest.get("flow_target_clip_count") or len(manifest.get("composition_images") or manifest.get("generated_images") or manifest.get("source_images") or []) or 3)
        source_index = int((manifest.get("flow_source_image_map") or {}).get(str(shot_index)) or shot_index)
        variant_index = int((manifest.get("flow_source_variant_map") or {}).get(str(shot_index)) or 1)
        provenance = dict(manifest.get("flow_segment_provenance") or {})
        provenance[str(shot_index)] = {
            "source_type": "google_flow",
            "source_image_index": source_index,
            "source_variant_index": variant_index,
            "clip_path": str(target.relative_to(folder)),
        }
        manifest.update({
            "video_ai_provider": provider,
            "flow_clips": clips,
            "flow_segment_provenance": provenance,
            "flow_skipped_shots": {},
            "flow_target_clip_count": target_count,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._refresh_product_segment_state(manifest)
        manifest["readiness"] = self._readiness(manifest)
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def save_video_qa(self, job_id, status, findings, artifact_paths=None):
        folder = self.root / str(job_id)
        manifest_path = folder / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        status = str(status or "needs_review")
        if status not in {"approved", "needs_review", "rejected"}:
            raise ValueError("สถานะตรวจวิดีโอไม่ถูกต้อง")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "video_qa_status": status,
            "video_qa_findings": [str(item) for item in (findings or [])],
            "video_qa_artifacts": [str(item) for item in (artifact_paths or [])],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def save_effect_video(self, job_id, output_path, source_path, settings):
        folder = (self.root / str(job_id)).resolve()
        manifest_path = folder / "job.json"
        output, source = Path(output_path).resolve(), Path(source_path).resolve()
        if not manifest_path.exists() or folder not in output.parents or folder not in source.parents:
            raise ValueError("ไฟล์เอฟเฟกต์ต้องอยู่ใน Product Job เดียวกัน")
        if not output.is_file() or not source.is_file():
            raise ValueError("ไม่พบวิดีโอก่อนหรือหลังใส่เอฟเฟกต์")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "video_status": "ready",
            "video_path": str(output.relative_to(folder)),
            "video_without_logo_path": str(output.relative_to(folder)),
            "video_before_effects_path": str(source.relative_to(folder)),
            "effect_status": "ready",
            "effect_preset": str(settings.get("preset", "neon_focus")),
            "effect_accent_color": str(settings.get("accent_color", "#2AD8F2")),
            "effect_target_x_percent": float(settings.get("target_x_percent", 50)),
            "effect_target_y_percent": float(settings.get("target_y_percent", 56)),
            "effect_intensity": int(settings.get("intensity", 2)),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        manifest["readiness"] = self._readiness(manifest)
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def promote_video(self, job_id, relative_path, flow_source_path="", source_provider="flow"):
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path = folder / "job.json"
        target = (folder / str(relative_path)).resolve()
        if not manifest_path.exists() or (target.parent != folder.resolve() and folder.resolve() not in target.parents):
            raise ValueError("ไม่พบ Job หรือ path ไม่ถูกต้อง")
        if not target.is_file() or target.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi"}:
            raise ValueError("ไม่พบไฟล์วิดีโอ Final")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_type = str(manifest.get("video_source_type") or "processed_video")
        if flow_source_path or source_provider == "meta_ai":
            video_provider = str(source_provider or manifest.get("video_ai_provider") or "flow").strip().lower()
            if video_provider == 'meta_ai':
                provider_name = 'Meta AI'
                clips = dict(manifest.get('meta_clips') or {})
                local_clips = {}
            else:
                provider_name = "Google Flow"
                clips = dict(manifest.get("flow_clips") or {})
                local_clips = dict(manifest.get("flow_local_motion_clips") or {})
            target_count = int(manifest.get("flow_target_clip_count") or len(manifest.get("composition_images") or manifest.get("generated_images") or manifest.get("source_images") or []) or 3)
            missing = [
                str(index) for index in range(1, target_count + 1)
                if not (
                    clips.get(str(index)) and (folder / clips[str(index)]).is_file()
                ) and not (
                    local_clips.get(str(index)) and (folder / local_clips[str(index)]).is_file()
                )
            ]
            if missing:
                raise ValueError(
                    f"ยังไม่มีช่วงวิดีโอจาก {provider_name} หรือ Local Motion สำหรับช็อต: "
                    + ", ".join(missing)
                )
            source_type = "meta_ai_composite" if video_provider == 'meta_ai' else "google_flow_hybrid_composite" if local_clips else "google_flow_composite"
        stale_processed = {
            "video_path": str(manifest.get("video_path") or ""),
            "subtitle_video_path": str(manifest.get("subtitle_video_path") or ""),
            "audio_mix_path": str(manifest.get("audio_mix_path") or ""),
        }
        manifest.update({
            "video_status": "ready",
            "video_path": str(target.relative_to(folder)),
            "flow_video_path": str(flow_source_path or manifest.get("flow_video_path") or "") if source_type != 'meta_ai_composite' else str(manifest.get("flow_video_path") or ""),
            "flow_video_status": "ready" if source_type in {"flow_composite", "google_flow_composite", "google_flow_hybrid_composite"} else manifest.get("flow_video_status", ""),
            "video_source_type": source_type,
            "stale_processed_outputs": stale_processed,
            "video_without_subtitle_path": "",
            "subtitle_video_path": "",
            "subtitle_video_status": "needs_render" if manifest.get("subtitle_status") == "ready" else manifest.get("subtitle_video_status", "pending"),
            "video_without_audio_mix_path": "",
            "audio_mix_path": "",
            "audio_mix_status": "needs_render" if manifest.get("audio_mix_status") not in {None, "", "not_generated"} else manifest.get("audio_mix_status", "not_generated"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        manifest["readiness"] = self._readiness(manifest)
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def save_logo_video(self, job_id, output_path, source_path, logo_path, settings):
        from core.logo_layout import normalize_logo_layout
        layout = normalize_logo_layout(settings.get('layout'))
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        folder = (self.root / job_id).resolve()
        manifest_path = folder / "job.json"
        output, source, logo = Path(output_path).resolve(), Path(source_path).resolve(), Path(logo_path).resolve()
        if not manifest_path.exists() or folder not in output.parents or folder not in source.parents:
            raise ValueError("ไฟล์วิดีโอต้องอยู่ใน Product Job เดียวกัน")
        if not output.is_file() or output.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi"}:
            raise ValueError("ไม่พบวิดีโอที่ใส่โลโก้แล้ว")
        if not source.is_file() or not logo.is_file():
            raise ValueError("ไม่พบวิดีโอต้นฉบับหรือไฟล์โลโก้")
        asset_folder = folder / "assets"
        asset_folder.mkdir(parents=True, exist_ok=True)
        saved_logo = asset_folder / f"video_logo{logo.suffix.lower()}"
        if logo != saved_logo.resolve():
            shutil.copy2(logo, saved_logo)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_relative = str(source.relative_to(folder))
        manifest.update({
            "video_status": "ready",
            "video_path": str(output.relative_to(folder)),
            "video_without_logo_path": source_relative,
            "logo_status": "ready",
            "logo_file": str(saved_logo.relative_to(folder)),
            "logo_opacity": float(settings.get("opacity", 0.8)),
            "logo_size_percent": float(settings.get("size_percent", 18)),
            "logo_position": str(settings.get("position", "bottom_right")),
            "logo_margin": int(settings.get("margin", 28)),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        if layout is not None:
            manifest['logo_layout'] = layout
        else:
            manifest.pop('logo_layout', None)
        manifest["readiness"] = self._readiness(manifest)
        if manifest["readiness"]["ready"]:
            manifest["status"] = "ready_for_phone"
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def save_voice_result(self, job_id, source_path, external_job_id, reference_id, output_id=""):
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        source = Path(source_path)
        if not source.is_file() or source.suffix.lower() not in {".wav", ".mp3", ".mp4"}:
            raise ValueError("ไฟล์เสียง AI ไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path = folder / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        audio_folder = folder / "audio"
        audio_folder.mkdir(parents=True, exist_ok=True)
        target = audio_folder / f"voiceover{source.suffix.lower()}"
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "voice_status": "ready",
            "voice_path": str(target.relative_to(folder)),
            "voice_job_id": str(external_job_id or ""),
            "voice_output_id": str(output_id or ""),
            "voice_reference_id": str(reference_id or ""),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def mark_voice_queued(self, job_id, external_job_id, reference_id):
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        manifest_path = self.root / job_id / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "voice_status": "queued",
            "voice_job_id": str(external_job_id or ""),
            "voice_reference_id": str(reference_id or ""),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def mark_subtitle_queued(self, job_id, external_job_id, language="th"):
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        manifest_path = self.root / job_id / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "subtitle_status": "queued",
            "subtitle_requested": True,
            "subtitle_job_id": str(external_job_id or ""),
            "subtitle_language": str(language or "th"),
            "subtitle_error": "",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def set_subtitle_requested(self, job_id, enabled):
        manifest_path = self.root / str(job_id) / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({"subtitle_requested": bool(enabled), "updated_at": datetime.now().isoformat(timespec="seconds")})
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def set_image_ai_provider(self, job_id, provider):
        provider = str(provider or "chatgpt").strip().lower()
        if provider not in {"chatgpt", "gemini"}:
            raise ValueError("รองรับผู้สร้างภาพเฉพาะ ChatGPT Web หรือ Gemini Web")
        manifest_path = self.root / str(job_id) / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "image_ai_provider": provider,
            "ai_web_model": normalize_ai_web_model(provider, manifest.get("ai_web_model")),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    @_serialized_manifest_operation
    def set_ai_web_model(self, job_id, provider, model):
        provider = str(provider or "chatgpt").strip().lower()
        if provider not in {"chatgpt", "gemini"}:
            raise ValueError("ผู้สร้างภาพไม่ถูกต้อง")
        model = normalize_ai_web_model(provider, model)
        manifest_path = self.root / str(job_id) / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "ai_web_model": model,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def set_video_ai_provider(self, job_id, provider):
        provider = str(provider or "flow").strip().lower()
        if provider not in {"flow", "meta_ai"}:
            raise ValueError("ผู้สร้างวิดีโอต้องเป็น Google Flow หรือ Meta AI")
        manifest_path = self.root / str(job_id) / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if provider == 'meta_ai':
            if manifest.get('long_video') or manifest.get('aspect_ratio') == '16:9':
                raise ValueError('Meta AI รุ่นทดลองรองรับวิดีโอแนวตั้งเท่านั้น')
            target_count = int(manifest.get('flow_target_clip_count') or len(manifest.get('composition_images') or manifest.get('generated_images') or manifest.get('source_images') or []) or 3)
            if target_count < 1 or target_count > 9:
                raise ValueError('จำนวนฉากนี้ยังไม่รองรับ Meta AI')
        manifest["video_ai_provider"] = provider
        self._refresh_product_segment_state(manifest)
        manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def save_subtitle_result(self, job_id, external_job_id, result, syllables_per_cue=3):
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path = folder / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        if not isinstance(result, dict):
            raise ValueError("ผล Subtitle ไม่ถูกต้อง")
        syllables_per_cue = int(syllables_per_cue)
        if not 1 <= syllables_per_cue <= 5:
            raise ValueError("จำนวนพยางค์ต่อช่วงต้องอยู่ระหว่าง 1-5")
        captions = folder / "captions"
        captions.mkdir(parents=True, exist_ok=True)
        (captions / "smartsub_job.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts = SmartSubOnlineClient.extract_artifacts(result)
        transcript = str(artifacts.get("transcript") or "").strip()
        srt = str(artifacts.get("srt") or "").strip()
        vtt = str(artifacts.get("vtt") or "").strip()
        segments = artifacts.get("segments") or []
        if segments:
            srt = self._segments_to_srt(segments, syllables_per_cue)
        saved = {}
        for name, text in (("transcript", transcript), ("subtitle.srt", srt), ("subtitle.vtt", vtt)):
            if text:
                target = captions / ("transcript.txt" if name == "transcript" else name)
                target.write_text(text.rstrip() + "\n", encoding="utf-8")
                saved[name] = str(target.relative_to(folder))
        if not saved:
            raise ValueError("งานเสร็จแล้วแต่ผลลัพธ์ไม่มีข้อความหรือไฟล์คำบรรยาย")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "subtitle_status": "ready",
            "subtitle_requested": True,
            "subtitle_job_id": str(external_job_id or ""),
            "subtitle_paths": saved,
            "subtitle_transcript": transcript,
            "subtitle_syllables_per_cue": syllables_per_cue,
            "subtitle_video_status": "needs_render" if manifest.get("video_status") == "ready" else manifest.get("subtitle_video_status", "pending"),
            "subtitle_error": "",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_manifest_file(manifest_path, manifest)

        # SmartSub supplies the timing, while the approved ChatGPT/TTS script is
        # the source of truth for the words.  Do this here (instead of only in
        # the command-line pipeline) so GUI, automatic, and rebuild flows all
        # receive the same correction behavior.
        subtitle_path = captions / "subtitle.srt"
        approved_script = str(manifest.get("spoken_script") or "").strip()
        if subtitle_path.is_file() and approved_script and (manifest.get("audio_choices") or {}).get("mode", "api") == "api":
            raw_path = captions / "subtitle_api_raw.srt"
            shutil.copy2(subtitle_path, raw_path)
            manifest, corrected_path = self.correct_subtitle_from_script(job_id)
            saved = dict(manifest.get("subtitle_paths") or saved)
            saved["subtitle.srt"] = str(corrected_path.relative_to(folder))
            return manifest, saved
        return manifest, saved

    def rebuild_subtitle_segments(self, job_id, syllables_per_cue):
        folder = self.root / str(job_id)
        manifest_path = folder / "job.json"
        result_path = folder / "captions" / "smartsub_job.json"
        if not manifest_path.exists() or not result_path.exists():
            raise ValueError("Job นี้ยังไม่มีผลจาก Subtitle API")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        return self.save_subtitle_result(job_id, manifest.get("subtitle_job_id"), result, syllables_per_cue)

    def correct_subtitle_from_script(self, job_id):
        """Keep API timing but replace recognition errors with the approved TTS script."""
        folder = self.root / str(job_id)
        manifest_path = folder / "job.json"
        subtitle_path = folder / "captions" / "subtitle.srt"
        if not manifest_path.exists() or not subtitle_path.exists():
            raise ValueError("Job นี้ยังไม่มี Subtitle สำหรับแก้คำ")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        spoken_script = str(manifest.get("spoken_script") or "")
        script = re.sub(r"\[(?:pause:[0-9.]+|laughter|sigh|surprise-ah|question-ah|dissatisfaction-hnn)\]", " ", spoken_script, flags=re.I)
        script = re.sub(r"\s+", " ", script).strip()
        if not script:
            raise ValueError("Job นี้ยังไม่มีบทพูดต้นฉบับสำหรับแก้ Subtitle")
        raw_path = folder / "captions" / "subtitle_api_raw.srt"
        timing_path = raw_path if raw_path.is_file() else subtitle_path
        source = timing_path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")
        cue_pattern = re.compile(
            r"(?:^|\n\s*\n)(?:\d+\s*\n)?"
            r"(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
            r"(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n(?P<text>.*?)(?=\n\s*\n|\Z)",
            re.S,
        )
        cues = list(cue_pattern.finditer(source.strip()))
        if not cues:
            raise ValueError("Subtitle API ไม่มีช่วงเวลาที่อ่านได้")

        def seconds(value):
            hours, minutes, rest = str(value).replace(",", ".").split(":")
            return int(hours) * 3600 + int(minutes) * 60 + float(rest)

        def stamp(value):
            milliseconds = max(0, round(float(value) * 1000))
            hours, milliseconds = divmod(milliseconds, 3600000)
            minutes, milliseconds = divmod(milliseconds, 60000)
            seconds_value, milliseconds = divmod(milliseconds, 1000)
            return f"{hours:02d}:{minutes:02d}:{seconds_value:02d},{milliseconds:03d}"

        maximum = int(manifest.get("subtitle_syllables_per_cue") or 3)
        # The old correction divided the whole narration by cue count.  That
        # erased every real silence reported by SmartSub and made the captions
        # drift ahead/behind the voice after the first [pause].  Keep the API
        # speech ranges, then fit the approved words only inside those ranges.
        speech_intervals = [
            (seconds(cue.group("start")), seconds(cue.group("end")))
            for cue in cues
            if seconds(cue.group("end")) > seconds(cue.group("start"))
        ]
        duration = max(end for _start, end in speech_intervals)
        sync_lead_ms = max(0, min(500, int(manifest.get("subtitle_sync_lead_ms") or 120)))
        pause_split = re.split(r"\[pause:([0-9.]+)\]", spoken_script, flags=re.I)
        authored_sections = [str(pause_split[index] or "").strip() for index in range(0, len(pause_split), 2)]
        authored_pauses = [max(0.2, min(3.0, float(pause_split[index]))) for index in range(1, len(pause_split), 2)]
        timed_words = []
        if authored_pauses and any(authored_sections):
            # TTS renders [pause:x] as a real silence. SmartSub can sometimes
            # hallucinate a word across that silence, so its cue may hide the
            # gap. Reconstruct the authored pause positions from the exact
            # script that was sent to VoiceClone, while retaining the API's
            # measured total speech duration.
            section_weights = [
                max(1, len(re.sub(r"[^A-Za-z0-9\u0e00-\u0e7f]+", "", section)))
                for section in authored_sections
            ]
            authored_pause_total = sum(authored_pauses)
            pause_total = min(authored_pause_total, max(0.0, duration - 0.25 * len(authored_sections)))
            pause_scale = pause_total / authored_pause_total if authored_pause_total else 0.0
            active_budget = max(0.1, duration - pause_total)
            weight_total = sum(section_weights) or 1
            cursor = 0.0
            for section_index, (section, weight) in enumerate(zip(authored_sections, section_weights)):
                if section:
                    section_duration = active_budget * weight / weight_total
                    section_end = min(duration, cursor + section_duration)
                    section_words = self._script_to_timed_words(
                        section,
                        duration,
                        speech_intervals=[(cursor, section_end)],
                        lead_seconds=sync_lead_ms / 1000.0,
                    )
                    for word in section_words:
                        word["source_chunk"] = section_index * 10000 + int(word.get("source_chunk") or 0)
                    timed_words.extend(section_words)
                    cursor = section_end
                if section_index < len(authored_pauses):
                    cursor = min(duration, cursor + authored_pauses[section_index] * pause_scale)
        else:
            timed_words = self._script_to_timed_words(
                spoken_script,
                duration,
                speech_intervals=speech_intervals,
                lead_seconds=sync_lead_ms / 1000.0,
            )
        corrected_srt = self._segments_to_srt([{"words": timed_words}], maximum)
        if not corrected_srt.strip():
            raise ValueError("ไม่สามารถจัดเวลา Subtitle จากบทพูดต้นฉบับได้")
        if not raw_path.exists():
            shutil.copy2(subtitle_path, raw_path)
        subtitle_path.write_text(corrected_srt.rstrip() + "\n", encoding="utf-8")
        manifest.update({
            "subtitle_paths": {**dict(manifest.get("subtitle_paths") or {}), "subtitle.srt": str(subtitle_path.relative_to(folder)), "subtitle_api_raw.srt": str(raw_path.relative_to(folder))},
            "subtitle_alignment_status": "corrected_from_approved_script",
            "subtitle_reference_source": "spoken_script",
            "subtitle_correction_enabled": True,
            "subtitle_timing_model": "api_speech_intervals_v2",
            "subtitle_timing_source": "smartsub_api_speech_intervals",
            "subtitle_sync_lead_ms": sync_lead_ms,
            "subtitle_transcript": script,
            "subtitle_cue_count": corrected_srt.count(" --> "),
            # Correcting recognised words invalidates every video that already
            # burned the previous SRT.  Keeping those statuses at ``ready``
            # made resumed jobs silently reuse captions with misspelled product
            # names even though the approved script was available.
            "subtitle_video_status": "needs_render",
            "audio_mix_status": (
                "needs_render"
                if manifest.get("audio_mix_status") not in {None, "", "not_generated"}
                else manifest.get("audio_mix_status", "not_generated")
            ),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_manifest_file(manifest_path, manifest)
        return manifest, subtitle_path

    def mark_subtitle_error(self, job_id, message):
        manifest_path = self.root / str(job_id) / "job.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({"subtitle_status": "error", "subtitle_error": str(message or ""), "updated_at": datetime.now().isoformat(timespec="seconds")})
        self._save_manifest_file(manifest_path, manifest)

    def mark_subtitle_video_needs_render(self, job_id):
        manifest_path = self.root / str(job_id) / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Product Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "subtitle_video_status": "needs_render",
            "subtitle_video_error": "",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def save_subtitled_video(self, job_id, output_path, source_path, subtitle_path, style_settings=None):
        folder = (self.root / str(job_id)).resolve()
        manifest_path = folder / "job.json"
        output, source, subtitle = Path(output_path).resolve(), Path(source_path).resolve(), Path(subtitle_path).resolve()
        if not manifest_path.exists() or folder not in output.parents or folder not in source.parents or folder not in subtitle.parents:
            raise ValueError("ไฟล์ Subtitle และวิดีโอต้องอยู่ใน Product Job เดียวกัน")
        if not output.is_file() or output.stat().st_size == 0:
            raise ValueError("ไฟล์วิดีโอที่ใส่ Subtitle ไม่ถูกต้อง")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "video_status": "ready",
            "video_path": str(output.relative_to(folder)),
            "video_without_subtitle_path": str(source.relative_to(folder)),
            "subtitle_video_status": "ready",
            "subtitle_video_path": str(output.relative_to(folder)),
            "subtitle_burn_source": str(subtitle.relative_to(folder)),
            "subtitle_style": dict(style_settings or {}),
            "video_without_audio_mix_path": str(output.relative_to(folder)),
            "audio_mix_status": "needs_render" if manifest.get("audio_mix_status") else manifest.get("audio_mix_status", "not_generated"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        manifest["readiness"] = self._readiness(manifest)
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def save_audio_mix_result(self, job_id, output_path, source_path, settings, plan):
        folder = (self.root / str(job_id)).resolve()
        manifest_path = folder / "job.json"
        output, source = Path(output_path).resolve(), Path(source_path).resolve()
        if not manifest_path.exists() or folder not in output.parents or folder not in source.parents:
            raise ValueError("ไฟล์เสียงผสมและวิดีโอต้องอยู่ใน Product Job เดียวกัน")
        if not output.is_file() or output.stat().st_size == 0:
            raise ValueError("วิดีโอที่ผสมเสียงไม่ถูกต้อง")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        safe_settings = json.loads(json.dumps(dict(settings or {}), ensure_ascii=False, default=str))
        safe_plan = json.loads(json.dumps(dict(plan or {}), ensure_ascii=False, default=str))
        manifest.update({
            "video_status": "ready",
            "video_path": str(output.relative_to(folder)),
            "video_without_audio_mix_path": str(source.relative_to(folder)),
            "audio_mix_status": "ready",
            "audio_mix_path": str(output.relative_to(folder)),
            "audio_mix_settings": safe_settings,
            "audio_mix_plan": safe_plan,
            "audio_mix_error": "",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        manifest["readiness"] = self._readiness(manifest)
        self._save_manifest_file(manifest_path, manifest)
        return manifest

    def mark_audio_mix_error(self, job_id, message):
        manifest_path = self.root / str(job_id) / "job.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({"audio_mix_status": "error", "audio_mix_error": str(message or ""), "updated_at": datetime.now().isoformat(timespec="seconds")})
        self._save_manifest_file(manifest_path, manifest)

    def mark_subtitle_video_error(self, job_id, message):
        manifest_path = self.root / str(job_id) / "job.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({"subtitle_video_status": "error", "subtitle_video_error": str(message or ""), "updated_at": datetime.now().isoformat(timespec="seconds")})
        self._save_manifest_file(manifest_path, manifest)

    @staticmethod
    def _segments_to_srt(segments, syllables_per_cue=3):
        def stamp(value):
            milliseconds = max(0, round(float(value or 0) * 1000))
            hours, milliseconds = divmod(milliseconds, 3600000)
            minutes, milliseconds = divmod(milliseconds, 60000)
            seconds, milliseconds = divmod(milliseconds, 1000)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
        syllables_per_cue = int(syllables_per_cue)
        if not 1 <= syllables_per_cue <= 5:
            raise ValueError("จำนวนพยางค์ต่อช่วงต้องอยู่ระหว่าง 1-5")
        timed_words = []
        for item in segments:
            if not isinstance(item, dict):
                continue
            words = item.get("words") if isinstance(item.get("words"), list) else []
            if words:
                for word in words:
                    if not isinstance(word, dict) or not str(word.get("text") or "").strip():
                        continue
                    start = word.get("start", word.get("startTime", word.get("start_time", item.get("start", 0))))
                    end = word.get("end", word.get("endTime", word.get("end_time", item.get("end", start))))
                    timed_word = {"text": str(word["text"]).strip(), "start": start, "end": end}
                    if "source_chunk" in word:
                        timed_word["source_chunk"] = word.get("source_chunk")
                    timed_words.append(timed_word)
            else:
                text = str(item.get("text") or "").strip()
                start = item.get("start", item.get("startTime", item.get("start_time", 0)))
                end = item.get("end", item.get("endTime", item.get("end_time", start)))
                if text:
                    timed_words.append({"text": text, "start": start, "end": end})
        timed_words = ProductManager._coalesce_subtitle_units(timed_words)
        timed_words = ProductManager._split_subtitle_syllable_units(timed_words)
        blocks = []
        previous_end = 0.0
        for group in ProductManager._group_subtitle_units(timed_words, syllables_per_cue):
            text = ProductManager._join_subtitle_tokens([word["text"] for word in group])
            start = max(float(group[0]["start"]), previous_end)
            end = max(start + 0.05, float(group[-1]["end"]))
            blocks.append(f"{len(blocks)+1}\n{stamp(start)} --> {stamp(end)}\n{text}")
            previous_end = end
        return "\n\n".join(blocks)

    @staticmethod
    def _split_subtitle_syllable_units(words):
        """Split Thai words into spoken syllables without detaching vowel/tone marks."""
        units = []
        thai_text = re.compile(r"[\u0e00-\u0e7f]")
        starts_with_mark = re.compile(r"^[\u0e31\u0e34-\u0e3a\u0e47-\u0e4e]")
        for word_index, word in enumerate(words):
            token = unicodedata.normalize("NFC", str(word.get("text") or "").strip())
            if not token:
                continue
            pieces = [token]
            if thai_syllable_tokenize and thai_text.search(token) and not re.search(r"[A-Za-z0-9]", token):
                try:
                    raw = thai_syllable_tokenize(token, engine="dict", keep_whitespace=False)
                    pieces = []
                    for value in raw:
                        piece = unicodedata.normalize("NFC", str(value or "").strip())
                        if not piece:
                            continue
                        if pieces and starts_with_mark.match(piece):
                            pieces[-1] += piece
                        else:
                            pieces.append(piece)
                    pieces = pieces or [token]
                except Exception:
                    pieces = [token]
            start = float(word.get("start") or 0)
            end = max(start, float(word.get("end", start) or start))
            duration = max(0.01, end - start)
            step = duration / max(1, len(pieces))
            for index, piece in enumerate(pieces):
                piece_start = start + step * index
                piece_end = end if index == len(pieces) - 1 else start + step * (index + 1)
                units.append({"text": piece, "start": piece_start, "end": max(piece_start + 0.01, piece_end), "word_group": word_index, "source_chunk": word.get("source_chunk")})
        return units

    @staticmethod
    def _group_subtitle_units(units, maximum):
        """Keep lexical words and authored phrase boundaries intact.

        The 1-5 syllable setting is a visual grouping target.  It must never cut
        a word, join two space-separated narration phrases, or leave a Thai
        prefix such as ``ไม่``/``จะ`` dangling at the end of a cue.
        """
        maximum = max(1, int(maximum))
        words, current_word = [], []
        previous_group = object()
        for unit in units:
            group_id = unit.get("word_group")
            if current_word and group_id != previous_group:
                words.append(current_word)
                current_word = []
            current_word.append(unit)
            previous_group = group_id
        if current_word:
            words.append(current_word)

        dangling_prefixes = {
            "ไม่", "จะ", "ยัง", "ต้อง", "กำลัง", "อยาก", "อาจ", "เคย", "ให้", "ถูก", "โดย",
            "กับ", "ของ", "ใน", "ที่", "ซึ่ง", "และ", "หรือ", "แต่", "เพราะ", "ขนาด",
            "ถ้า", "เมื่อ", "แม้", "ทุก", "บาง",
        }
        groups, current = [], []
        current_chunk = None
        for word_units in words:
            source_chunk = word_units[0].get("source_chunk")
            # Spaces in the approved ChatGPT narration are intentional phrase
            # boundaries.  Crossing one is what produced cues such as
            # "อยู่คุณตา" and "เลยทุก".
            if current and source_chunk is not None and current_chunk is not None and source_chunk != current_chunk:
                groups.append([unit for word in current for unit in word])
                current = []
            current_chunk = source_chunk
            current_size = sum(len(word) for word in current)
            if len(word_units) > maximum:
                if current:
                    groups.append([unit for word in current for unit in word]); current = []
                # A long word may exceed the selected 1-5 syllable target, but
                # splitting it across cues produces broken Thai such as
                # "สมา" / "ชิก".  Keep the complete word in one cue instead.
                groups.append(list(word_units))
            elif current_size + len(word_units) <= maximum:
                current.append(word_units)
            else:
                # Move a prefix/connector forward so the next cue reads as a
                # natural unit: "เจ้าทอง / ไม่อยู่", not "เจ้าทองไม่ / อยู่".
                if len(current) > 1:
                    last_text = ProductManager._join_subtitle_tokens(
                        [unit["text"] for unit in current[-1]]
                    )
                    if last_text in dangling_prefixes:
                        carry = [current.pop()]
                        while current:
                            previous_text = ProductManager._join_subtitle_tokens(
                                [unit["text"] for unit in current[-1]]
                            )
                            if previous_text not in dangling_prefixes:
                                break
                            carry.insert(0, current.pop())
                        if current:
                            groups.append([unit for word in current for unit in word])
                        current = [*carry, word_units]
                        continue
                if current:
                    groups.append([unit for word in current for unit in word])
                current = [word_units]
        if current:
            groups.append([unit for word in current for unit in word])
        return groups

    @staticmethod
    def _script_to_timed_words(script, duration, speech_intervals=None, lead_seconds=0.0, protected_terms=None):
        """Tokenize an approved script and optionally fit it to real speech ranges.

        ``speech_intervals`` lets Story Shorts keep the exact approved text while
        skipping real pauses in the generated narration.  Without it this keeps
        the original proportional behavior used by older jobs and tests.
        """
        script = re.sub(r"\[(?:pause:[0-9.]+|laughter|sigh|surprise-ah|question-ah|dissatisfaction-hnn)\]", " ", str(script or ""), flags=re.I)
        script = unicodedata.normalize("NFC", re.sub(r"\s+", " ", script).strip())
        if not script:
            return []
        protected_terms = {
            str(term or "").strip()
            for term in (protected_terms or [])
            if len(str(term or "").strip()) >= 2
        }
        stop_words = {"อาจ", "จะ", "เคย", "กำลัง", "ได้", "ไม่ได้", "ไม่", "เกิด", "ล้ม", "เดิน", "วิ่ง", "พูด", "บอก", "ขาย", "วาง", "เรียก", "นอน", "รีบ"}
        # Drama narration uses ``speaker: text`` records.  Thai tokenizers can
        # split an uncommon short name in running text (for example ``มิน`` in
        # ``ที่มินไม่คิด`` becomes ``มิ`` + ``น``).  Learn every explicit
        # speaker label before tokenizing so the same name remains one lexical
        # word everywhere in the subtitle stream.
        for speaker in re.findall(r"(?:^|\s)([\u0e00-\u0e7f]{2,20})\s*:", script):
            protected_terms.add(speaker.strip())
        for authored_chunk in script.split():
            called = re.search(r"(?:ชื่อ(?:ว่า)?|เรียก(?:มัน|เขา|เธอ)?ว่า)([\u0e00-\u0e7f]{2,16})$", authored_chunk)
            if called:
                protected_terms.add(called.group(1))
            titled = re.search(
                r"(?:คุณตา|คุณยาย|คุณปู่|คุณย่า|นาย|นาง|เด็กชาย|เด็กหญิง)([\u0e00-\u0e7f]{2,12}?)(?=อาจ|จะ|เคย|กำลัง|ได้|ไม่ได้|ไม่|เกิด|ล้ม|เดิน|วิ่ง|พูด|บอก|ขาย|วาง|เรียก|นอน|รีบ|$)",
                authored_chunk,
            )
            if titled and titled.group(1) not in stop_words:
                protected_terms.add(titled.group(1))

        def merge_protected(tokens):
            if not protected_terms:
                return tokens
            merged, index = [], 0
            ordered = sorted(protected_terms, key=len, reverse=True)
            while index < len(tokens):
                matched = None
                for term in ordered:
                    candidate = ""
                    for stop in range(index, len(tokens)):
                        candidate += tokens[stop]
                        if candidate == term:
                            matched = (term, stop + 1)
                            break
                        if not term.startswith(candidate):
                            break
                    if matched:
                        break
                if matched:
                    merged.append(matched[0])
                    index = matched[1]
                else:
                    merged.append(tokens[index])
                    index += 1
            return merged

        records = []
        punctuation = re.compile(r"^[,.;:!?ฯๆ]+$")
        for chunk_index, chunk in enumerate(script.split()):
            tokens = [chunk]
            if thai_word_tokenize and re.search(r"[\u0e00-\u0e7f]", chunk):
                try:
                    tokens = [str(item).strip() for item in thai_word_tokenize(chunk, engine="newmm", keep_whitespace=False) if str(item).strip()] or [chunk]
                except Exception:
                    tokens = [chunk]
            tokens = merge_protected(tokens)
            for token in tokens:
                syllable_count = 1
                if punctuation.fullmatch(token):
                    syllable_count = 0
                elif thai_syllable_tokenize and re.search(r"[\u0e00-\u0e7f]", token):
                    try:
                        syllable_count = max(1, len([item for item in thai_syllable_tokenize(token, engine="dict", keep_whitespace=False) if str(item).strip()]))
                    except Exception:
                        syllable_count = 1
                records.append({"text": token, "source_chunk": chunk_index, "weight": max(0.15, float(syllable_count))})
        total_weight = sum(item["weight"] for item in records) or 1.0
        cursor = 0.0
        total_duration = max(0.1, float(duration or 0))

        intervals = []
        for value in speech_intervals or []:
            if not isinstance(value, (tuple, list)) or len(value) < 2:
                continue
            start = max(0.0, min(total_duration, float(value[0])))
            end = max(start, min(total_duration, float(value[1])))
            if end - start >= 0.01:
                intervals.append((start, end))
        intervals.sort()
        active_duration = sum(end - start for start, end in intervals)

        def active_to_wall(value, prefer_next=False):
            value = max(0.0, min(active_duration, float(value)))
            elapsed = 0.0
            for interval_index, (start, end) in enumerate(intervals):
                span = end - start
                boundary = elapsed + span
                if value < boundary - 1e-7:
                    return start + (value - elapsed)
                if abs(value - boundary) <= 1e-7:
                    if prefer_next and interval_index + 1 < len(intervals):
                        return intervals[interval_index + 1][0]
                    return end
                elapsed = boundary
            return intervals[-1][1]

        lead = max(-0.5, min(0.5, float(lead_seconds or 0)))
        for index, item in enumerate(records):
            position_start = cursor / total_weight
            cursor += item["weight"]
            position_end = 1.0 if index == len(records) - 1 else cursor / total_weight
            if intervals and active_duration > 0.05:
                start = active_to_wall(active_duration * position_start, prefer_next=True) - lead
                end = active_to_wall(active_duration * position_end, prefer_next=False) - lead
                start = max(0.0, min(total_duration, start))
                end = max(start + 0.01, min(total_duration, end))
            else:
                start = total_duration * position_start
                end = total_duration * position_end
            item.update({"start": start, "end": max(start + 0.01, end)})
            item.pop("weight", None)
        return records

    @staticmethod
    def _coalesce_subtitle_units(words):
        combined = []
        for word in words:
            token = str(word.get("text") or "").strip()
            if not token:
                continue
            if combined:
                previous = combined[-1]
                previous_text = str(previous.get("text") or "")
                if re.fullmatch(r"[,.!?;:…ฯ]+", token):
                    previous["text"] = previous_text + token
                    previous["end"] = word.get("end", previous.get("end"))
                    continue
                if token == "ๆ":
                    previous["text"] = previous_text + token
                    previous["end"] = word.get("end", previous.get("end"))
                    continue
                numeric_chain = bool(re.fullmatch(r"\d+(?:[,.]\d*)?", previous_text))
                if token in {",", "."} and numeric_chain:
                    previous["text"] = previous_text + token
                    previous["end"] = word.get("end", previous.get("end"))
                    continue
                if token.isdigit() and numeric_chain and (previous_text[-1:].isdigit() or previous_text[-1:] in {",", "."}):
                    previous["text"] = previous_text + token
                    previous["end"] = word.get("end", previous.get("end"))
                    continue
            combined.append(dict(word, text=token))
        return combined

    @staticmethod
    def _join_subtitle_tokens(tokens):
        result, previous = "", ""
        punctuation = {",", ".", "!", "?", ":", ";", "%", "ฯ", "ๆ"}
        for raw in tokens:
            token = str(raw or "").strip()
            if not token:
                continue
            current_ascii = bool(re.search(r"[A-Za-z0-9]", token))
            previous_ascii = bool(re.search(r"[A-Za-z0-9]", previous))
            if not result:
                result = token
            elif token in punctuation:
                result += token
            elif token.isdigit() and (previous.isdigit() or previous in {",", "."}):
                result += token
            elif current_ascii or previous_ascii:
                result += " " + token
            else:
                result += token
            previous = token
        return result

    def attach_images(self, job_id, source_paths):
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id: raise ValueError("job_id ไม่ถูกต้อง")
        folder = self.root / job_id; manifest_path = folder / "job.json"
        if not manifest_path.exists(): raise ValueError("ไม่พบ Job")
        manifest = self._load_manifest_file(manifest_path)
        saved = list(manifest.get("source_images") or [])
        next_index = len(saved) + 1
        for source_value in source_paths:
            source = Path(source_value)
            if not source.is_file(): raise ValueError(f"ไม่พบรูป: {source}")
            try:
                with Image.open(source) as image: image.verify()
            except Exception as exc: raise ValueError(f"ไฟล์ไม่ใช่รูปภาพที่อ่านได้: {source.name}") from exc
            extension = source.suffix.lower() if source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else ".png"
            target = folder / "original" / f"product_{next_index:02d}{extension}"
            shutil.copy2(source, target); saved.append(str(target.relative_to(folder))); next_index += 1
        ai_state = "request_ready" if saved and manifest.get("product_name") != "สินค้า Shopee จากลิงก์" else "needs_product_data"
        manifest.update({"source_images": saved, "ai_status": ai_state, "ai_review_status": "not_generated", "status": "waiting_ai" if ai_state == "request_ready" else "needs_product_data", "partial_generated_images": [], "partial_image_count": 0, "updated_at": datetime.now().isoformat(timespec="seconds")})
        manifest.pop("ai_auto_recovery_attempts", None)
        manifest.pop("ai_last_recovery_reason", None)
        manifest["readiness"] = self._readiness(manifest)
        self._save_manifest_file(manifest_path, manifest)
        self._write_ai_request(folder, manifest)
        return manifest

    def curate_source_images(self, job_id, relative_paths):
        """Select only verified product photos without deleting the raw browser capture."""
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path = folder / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        selected = []
        original = (folder / "original").resolve()
        for value in relative_paths:
            candidate = (folder / str(value)).resolve()
            if candidate.parent != original or not candidate.is_file():
                raise ValueError("เลือกรูปได้เฉพาะไฟล์ในโฟลเดอร์ original ของ Job")
            if candidate.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                raise ValueError(f"ไม่รองรับไฟล์รูป: {candidate.name}")
            try:
                with Image.open(candidate) as image:
                    image.verify()
                with Image.open(candidate) as image:
                    width, height = image.size
            except Exception as exc:
                raise ValueError(f"ไฟล์รูปอ่านไม่ได้: {candidate.name}") from exc
            if width < 128 or height < 128:
                raise ValueError(f"รูปมีขนาดเล็กเกินไป: {candidate.name}")
            selected.append(str(candidate.relative_to(folder)))
        if not selected:
            raise ValueError("ต้องมีรูปสินค้าจริงอย่างน้อยหนึ่งรูป")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.update({
            "source_images": selected,
            "ai_status": "request_ready",
            "ai_review_status": "not_generated",
            "status": "waiting_ai",
            "partial_generated_images": [],
            "partial_image_count": 0,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        manifest.pop("ai_auto_recovery_attempts", None)
        manifest.pop("ai_last_recovery_reason", None)
        manifest["readiness"] = self._readiness(manifest)
        self._save_manifest_file(manifest_path, manifest)
        self._write_ai_request(folder, manifest)
        return manifest

    def update_product_info(self, job_id, name, price="", commission="", description=""):
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id: raise ValueError("job_id ไม่ถูกต้อง")
        name = str(name or "").strip()
        if not name: raise ValueError("กรุณาระบุชื่อสินค้า")
        folder = self.root / job_id; path = folder / "job.json"
        if not path.exists(): raise ValueError("ไม่พบ Job")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        ai_state = "request_ready" if manifest.get("source_images") and name != "สินค้า Shopee จากลิงก์" else "needs_product_data"
        manifest.update({"product_name": name, "price": str(price or "").strip(), "commission": str(commission or "").strip(), "description": str(description or "").strip()[:10000], "ai_status": ai_state, "ai_review_status": "not_generated", "status": "waiting_ai" if ai_state == "request_ready" else "needs_product_data", "partial_generated_images": [], "partial_image_count": 0, "updated_at": datetime.now().isoformat(timespec="seconds")})
        manifest.pop("ai_auto_recovery_attempts", None)
        manifest.pop("ai_last_recovery_reason", None)
        manifest["readiness"] = self._readiness(manifest)
        self._save_manifest_file(path, manifest)
        self._write_ai_request(folder, manifest)
        return manifest

    def approve_ai_result(self, job_id):
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id: raise ValueError("job_id ไม่ถูกต้อง")
        path = self.root / job_id / "job.json"
        if not path.exists(): raise ValueError("ไม่พบ Job")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("ai_status") != "ready" or not manifest.get("caption"): raise ValueError("ยังไม่มีผล AI ให้ตรวจ")
        manifest["ai_review_status"] = "approved"
        manifest["readiness"] = self._readiness(manifest)
        manifest["status"] = "ready_for_phone" if manifest["readiness"]["ready"] else "waiting_video"
        manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._save_manifest_file(path, manifest)
        return manifest

    def check_readiness(self, job_id):
        if not str(job_id).startswith("JOB-") or "/" in str(job_id) or "\\" in str(job_id) or ".." in str(job_id): raise ValueError("job_id ไม่ถูกต้อง")
        path = self.root / str(job_id) / "job.json"
        if not path.exists(): raise ValueError("ไม่พบ Job")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["readiness"] = self._readiness(manifest)
        if manifest["readiness"]["ready"] and manifest.get("post_status") != "posted": manifest["status"] = "ready_for_phone"
        self._save_manifest_file(path, manifest)
        return manifest["readiness"]

    def save_partial_image(self, job_id, index, encoded):
        """Atomically checkpoint each Product image before the browser continues."""
        manifest = self.get_job(job_id)
        index = int(index or 0)
        if index < 1 or index > 3:
            raise ValueError("ลำดับรูปสินค้าต้องอยู่ระหว่าง 1-3")
        raw = str(encoded or "")
        if raw.startswith("data:"):
            raw = raw.split(",", 1)[-1]
        try:
            payload = base64.b64decode(raw, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("ข้อมูลรูปสินค้า Checkpoint ไม่ถูกต้อง") from None
        if len(payload) < 100 or len(payload) > 20 * 1024 * 1024:
            raise ValueError("ขนาดรูปสินค้า Checkpoint ไม่ถูกต้อง")
        folder = self.root / str(job_id)
        target = folder / "generated" / f"selling_image_{index:02d}.png"
        temporary = target.with_suffix(".png.partial")
        try:
            temporary.write_bytes(payload)
            with Image.open(temporary) as image:
                image.verify()
            temporary.replace(target)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise ValueError("ไฟล์รูปสินค้า Checkpoint เปิดอ่านไม่ได้") from exc
        checkpoints = [
            str(path.relative_to(folder))
            for path in sorted((folder / "generated").glob("selling_image_*.png"))
            if path.is_file()
        ]
        manifest.update({
            "partial_generated_images": checkpoints,
            "partial_image_count": len(checkpoints),
            "ai_checkpoint_updated_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_manifest_file(folder / "job.json", manifest)
        return manifest

    def plugin_request(self, job_id):
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id: raise ValueError("job_id ไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path, request_path = folder / "job.json", folder / "ai_request.json"
        if not manifest_path.exists(): raise ValueError("ไม่พบ AI request ของ Job")
        manifest = self._load_manifest_file(manifest_path)
        # Select references without deleting originals or mutating an active
        # job's source list. Persist decisions for diagnostics only at this
        # explicit package boundary; completed generated/Flow files stay intact.
        from core.ai_web_resume import ai_web_resume_target
        resume_target = ai_web_resume_target(folder, manifest)
        selected, decisions = select_source_images(folder, manifest.get("source_images") or [])
        manifest["source_image_selection"] = decisions
        manifest["ai_reference_images"] = selected
        self._save_manifest_file(manifest_path, manifest)
        # Rebuild the request from the current prompt contract whenever the
        # extension asks for it. Old Jobs keep their image checkpoints, while
        # stale wording from an earlier app version cannot leak into a retry.
        request_manifest = dict(manifest, source_images=selected)
        if not (resume_target and resume_target.get('stage') == 'analysis' and request_path.is_file()):
            self._write_ai_request(folder, request_manifest)
        request = json.loads(request_path.read_text(encoding="utf-8"))
        prompt_path = folder / request["prompt_file"]
        checkpoints = [
            item for item in (manifest.get("partial_generated_images") or [])
            if (folder / str(item)).is_file()
        ]
        return {
            "job": manifest,
            "request": request,
            "prompt": prompt_path.read_text(encoding="utf-8"),
            "checkpoint_images": checkpoints,
            "ai_resume": resume_target,
        }

    def spoken_script(self, job_id):
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path = folder / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw_path = folder / "captions" / "spoken_script_raw.txt"
        script_path = folder / "captions" / "spoken_script.txt"
        raw_script = raw_path.read_text(encoding="utf-8") if raw_path.exists() else str(manifest.get("spoken_script_raw") or manifest.get("spoken_script") or "")
        script, issues = prepare_thai_tts_script(raw_script, manifest.get("pronunciation_notes") or {})
        stored_script = script_path.read_text(encoding="utf-8").strip() if script_path.exists() else ""
        if script and (script != stored_script or list(manifest.get("tts_script_issues") or []) != issues):
            script_path.write_text(script, encoding="utf-8")
            manifest.update({
                "spoken_script": script,
                "tts_script_issues": issues,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            })
            self._save_manifest_file(manifest_path, manifest)
        return manifest, script.strip()

    @_serialized_manifest_operation
    def save_spoken_script(self, job_id, raw_script):
        """Save a user-edited Product script and invalidate mismatched media."""
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path = folder / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw_script = str(raw_script or "").strip()
        script, issues = prepare_thai_tts_script(raw_script, manifest.get("pronunciation_notes") or {})
        if not script:
            raise ValueError("ยังไม่มีบทพูดสินค้าให้บันทึก")
        if issues:
            raise ValueError("บทพูดยังไม่พร้อมสำหรับสร้างเสียง: " + " • ".join(issues))
        previous = str(manifest.get("spoken_script") or "").strip()
        changed = script != previous
        captions = folder / "captions"
        captions.mkdir(parents=True, exist_ok=True)
        (captions / "spoken_script_raw.txt").write_text(raw_script, encoding="utf-8")
        (captions / "spoken_script.txt").write_text(script, encoding="utf-8")
        manifest.update({
            "spoken_script_raw": raw_script,
            "spoken_script": script,
            "tts_script_issues": [],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        })
        if changed and manifest.get("voice_status") == "ready":
            manifest["stale_voice_path"] = str(manifest.get("voice_path") or "")
            manifest["voice_status"] = "not_generated"
            manifest["subtitle_status"] = "not_generated"
            manifest.pop("voice_path", None)
            manifest.pop("voice_job_id", None)
            manifest.pop("voice_output_id", None)
            manifest.pop("subtitle_path", None)
            manifest.pop("subtitle_video_path", None)
        manifest["readiness"] = self._readiness(manifest)
        self._save_manifest_file(manifest_path, manifest)
        return manifest, script, changed

    def flow_package(self, job_id, shot_index=0, provider="google_flow"):
        """Return reviewed per-shot Product inputs for Google Flow or Meta AI."""
        job_id = str(job_id)
        if not job_id.startswith("JOB-") or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError("job_id ไม่ถูกต้อง")
        folder = self.root / job_id
        manifest_path = folder / "job.json"
        if not manifest_path.exists():
            raise ValueError("ไม่พบ Job")
        manifest = self._load_manifest_file(manifest_path)
        prompt_path = folder / "prompts" / "google_flow_prompt.txt"
        caption_path = folder / "captions" / "caption.txt"
        hashtags_path = folder / "captions" / "hashtags.txt"
        image_files = list(manifest.get("composition_images") or manifest.get("generated_images") or manifest.get("source_images") or [])
        flow_shots = list(manifest.get("flow_shot_prompts") or [])
        if not flow_shots:
            shots_path = folder / "prompts" / "google_flow_shots.json"
            if shots_path.exists():
                try:
                    flow_shots = list(json.loads(shots_path.read_text(encoding="utf-8")) or [])
                except (OSError, json.JSONDecodeError, TypeError):
                    flow_shots = []
        shot_index = int(shot_index or 0)
        provider = str(provider or "google_flow").strip().lower()
        if provider not in {"google_flow", "meta_ai"}:
            raise ValueError("ผู้สร้างวิดีโอไม่ถูกต้อง")
        if shot_index:
            target_count = len(image_files)
            if not 1 <= shot_index <= target_count:
                raise ValueError("ไม่พบรูปสำหรับช็อตที่เลือก")
            fallback = self.flow_local_fallback_checkpoint(manifest, shot_index)
            if provider == "google_flow" and fallback.get("failure_code") in (*FLOW_LOCAL_FALLBACK_CODES, "USER_APPROVED_IMAGE_REUSE"):
                checkpoint_code = (
                    "USER_APPROVED_IMAGE_REUSE_CHECKPOINT"
                    if fallback["failure_code"] == "USER_APPROVED_IMAGE_REUSE"
                    else
                    "FLOW_ATTACHMENT_LOCAL_FALLBACK_CHECKPOINT"
                    if fallback["failure_code"] == FLOW_ATTACHMENT_UNCONFIRMED
                    else "FLOW_POLICY_LOCAL_FALLBACK_CHECKPOINT"
                )
                raise ValueError(
                    f"{checkpoint_code} • ช็อต {shot_index} "
                    "จะสร้าง Local Motion จากรูปเดิม • ห้ามส่งเข้า Google Flow ซ้ำ"
                )
            # One output slot always belongs to the same-numbered source image.
            # Legacy quota reallocation/retry maps remain only as diagnostics;
            # no runtime path may turn another image into an alternate take.
            source_image_index = shot_index
            source_variant_index = 1
            selected_prompt = str(flow_shots[source_image_index - 1]).strip() if source_image_index <= len(flow_shots) else ""
            if not selected_prompt:
                selected_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
            retry_mode = ""
            selected_prompt = self._product_specific_cgi_prompt(
                selected_prompt, manifest, source_image_index,
            )
            selected_images = [image_files[source_image_index - 1]]
        else:
            retry_mode = ""
            source_image_index = 0
            source_variant_index = 1
            selected_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
            selected_prompt = self._product_specific_cgi_prompt(selected_prompt, manifest, 0)
            selected_images = image_files
        from core.flow_motion_plan import saved_motion_prompt, provider_for
        motion_prompt = saved_motion_prompt(folder, manifest, shot_index, selected_images[0]) if shot_index and provider == "google_flow" else ""
        from core.generated_music import apply_to_prompt
        if shot_index:
            video_prompt = apply_to_prompt(manifest, shot_index, motion_prompt or selected_prompt + flow_audio_instruction(manifest, shot_index))
        else:
            # Manual controls use index 0 only for metadata/readiness. The
            # bridge resolves an actual 1-based shot before dispatch; a summary
            # must neither require nor apply a scene's frozen music selection.
            from core.media_audio import _flow_audio_instruction
            video_prompt = selected_prompt + _flow_audio_instruction(manifest, 0)
        return {
            "image_ai_provider": provider_for(manifest),
            "motion_prompt_ready": bool(motion_prompt),
            "fictional_ai_characters_confirmed": manifest.get("fictional_ai_characters_confirmed") is True,
            "flow_settings": flow_settings(manifest.get("flow_settings")),
            "job_id": job_id,
            "product_name": manifest.get("product_name", ""),
            "product_id": manifest.get("product_id", ""),
            "posting_product_url": manifest.get("posting_product_url", ""),
            "ai_review_status": manifest.get("ai_review_status", "not_generated"),
            "video_status": manifest.get("video_status", "missing"),
            "shot_index": shot_index,
            "shot_count": len(image_files),
            "source_image_index": source_image_index,
            "source_variant_index": source_variant_index,
            "video_prompt": video_prompt,
            "caption": caption_path.read_text(encoding="utf-8") if caption_path.exists() else str(manifest.get("caption") or ""),
            "hashtags": hashtags_path.read_text(encoding="utf-8") if hashtags_path.exists() else "",
            "warnings": list(manifest.get("warnings") or []),
            "image_files": selected_images,
            "cgi_prompt_policy": retry_mode or "product_specific_v1",
        }

    @staticmethod
    def _flow_variant_direction(variant_index):
        variant_index = int(variant_index or 1)
        directions = {
            2: (
                "ALTERNATE TAKE 2: Create a clearly different second video from this same reference image. "
                "Use a gentle side-to-side camera move and a different natural product action while preserving "
                "the exact product identity and all verified details. Do not repeat the first take's motion."
            ),
            3: (
                "ALTERNATE TAKE 3: Create a clearly different third video from this same reference image. "
                "Use a slow close-detail reveal followed by a subtle pull-back while preserving the exact "
                "product identity and all verified details. Do not repeat either earlier take."
            ),
        }
        return directions.get(variant_index, directions[3])

    @staticmethod
    def _policy_safe_flow_prompt(manifest, shot_index, mode="policy_safe_v1"):
        """Create a concise neutral motion brief after an explicit policy denial."""
        shot_index = int(shot_index or 1)
        if str(mode or "") == "policy_minimal_v1":
            return (
                "Animate the uploaded reference image into exactly one short playable vertical 9:16 video. "
                "Keep the original image content and product completely unchanged. "
                "Add only one slow smooth camera move and subtle natural motion. "
                "No text, no added objects, no transformations and no special effects."
            )
        motions = {
            1: "Use a slow product reveal with a gentle forward camera move.",
            2: "Use a slow close-detail camera pan across only the visible product surface.",
            3: "Use a gentle camera arc that keeps the product fully visible in its existing setting.",
        }
        motion = motions.get(shot_index, motions[2])
        return (
            "Create exactly one short playable vertical 9:16 product showcase video from the uploaded reference image. "
            "Preserve every visible product, person, color, shape, material, logo, garment detail and accessory exactly as shown. "
            f"{motion} Add only natural parallax, realistic ambient light and subtle motion already implied by the image. "
            "Do not add or remove people, body parts, objects, text, claims, interfaces, particles, transformations or dramatic effects."
        )

    @staticmethod
    def _product_specific_cgi_prompt(original_prompt, manifest, shot_index=0):
        """Put verified product function ahead of any generic CGI brief returned by AI."""
        original = str(original_prompt or "").strip()
        name = " ".join(str(manifest.get("product_name") or "สินค้าจากภาพอ้างอิง").split())[:240]
        # Flow Agent accepts concise shot briefs more reliably. The old guard
        # copied up to 700 characters of the marketplace description and then
        # repeated the same restrictions around an already detailed creative
        # brief. Real Job JOB-20260902-CA57FF reached 3,003 characters and Flow
        # repeatedly cleared the composer into an empty session instead of
        # entering the render queue. Preserve verified identity and the exact
        # per-shot CGI direction, but keep this extra evidence summary bounded.
        description = " ".join(str(manifest.get("description") or "").split())[:360]
        apparel = bool(re.search(
            r"เสื้อ|กางเกง|กระโปรง|เดรส|คาร์ดิแกน|แจ็กเก็ต|ยีนส์|shirt|cardigan|jacket|pants|jeans|dress|skirt|garment|clothing",
            f"{name} {description}", flags=re.IGNORECASE,
        ))
        shot_roles = ({
            1: "reveal the real garment cut, silhouette, color and styling context",
            2: "show only visible collar, button, seam, ribbing, weave or construction details in close view",
            3: "show the existing garment in a realistic styling context without inventing a material claim or accessory",
        } if apparel else {
            1: "reveal the real form, scale, material and primary use context",
            2: "show one visible real feature, material, structure or working detail in close view",
            3: "show the realistic use result or benefit without inventing a claim or accessory",
        })
        role = shot_roles.get(int(shot_index or 0), "show only verified real features and realistic use")
        verified = f'Product: "{name}".' + (f" Verified description: {description}." if description else "")
        identity = (
            "exact garment identity, cut, silhouette, color, collar, buttons, seams, ribbing and visible styling"
            if apparel else
            "exact product identity, shape, color, logo, materials, construction and visible accessories"
        )
        emphasis = (
            "Use only subtle realistic light and camera focus that follow visible garment seams or texture"
            if apparel else
            "Any CGI must originate from and follow a verified product surface, movement or real use"
        )
        invention_guard = (
            "Do not invent fabric performance, sizing, fit, accessories, results, text, prices or claims."
            if apparel else
            "Do not invent specifications, mechanisms, accessories, results, text, prices or claims."
        )
        guard = f"""HIGHEST-PRIORITY PRODUCT-SPECIFIC CGI DIRECTION — SHOT {int(shot_index or 0) or 'ALL'}:
Preserve the {identity} from the reference. For this shot, {role}. {emphasis}; keep the product unobstructed and recognizable.
Every CGI element must explain a real visible feature, material, structure, movement or use of this exact product.
Do not use generic technology HUDs, dashboards, tracking brackets, floating data cards or circuit graphics. {invention_guard}
{verified}

ORIGINAL CREATIVE BRIEF (follow only where it does not conflict with the product-specific CGI direction):
{original}"""
        return guard.strip()

    @staticmethod
    def _readiness(manifest):
        missing = []
        if not manifest.get("posting_product_url"): missing.append("product_link")
        if not manifest.get("caption"): missing.append("caption")
        if manifest.get("ai_status") != "ready": missing.append("ai_result")
        elif manifest.get("ai_review_status") != "approved": missing.append("ai_approval")
        if manifest.get("video_status") != "ready" or not manifest.get("video_path"): missing.append("video")
        return {"ready": not missing, "missing": missing, "product_id_verified": bool(manifest.get("product_id"))}

    def _resolve_product_link(self, url):
        metadata = {}
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=15) as response:
                final_url = self.validate_shopee_url(response.geturl())
                raw = response.read(1024 * 1024).decode("utf-8", errors="ignore")
            for key, prop in (("title", "og:title"), ("description", "og:description"), ("image", "og:image")):
                match = re.search(rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)', raw, re.I)
                if not match:
                    match = re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}["\']', raw, re.I)
                if match: metadata[key] = html.unescape(match.group(1)).strip()
            return final_url, metadata
        except Exception:
            return url, metadata

    def _write_ai_request(self, folder, job):
        from core.analysis_json_transport import analysis_json_prompt
        prompt = f"""นี่เป็นงานเขียนข้อความและ JSON เท่านั้น ไม่ต้องสร้างรูป ไม่ต้องสร้างวิดีโอ และไม่ต้องเรียกใช้เครื่องมือของ Gemini
วิเคราะห์สินค้าจากชื่อ ข้อมูล และรูปอ้างอิงที่แนบมา โดยใช้เฉพาะข้อเท็จจริงที่ยืนยันได้ แล้วตอบเป็น JSON object อย่างเดียว

ชื่อสินค้า: {job['product_name']}
ราคา: {job['price']}
ค่าคอมมิชชัน: {job['commission']}
รายละเอียด: {job['description']}
ลิงก์สินค้าต้นทาง: {job.get('product_url', '')}
ลิงก์สำหรับติดกับโพสต์: {job.get('posting_product_url', '')}

สร้างผลลัพธ์ต่อไปนี้ใน JSON:
- caption_short, caption_alternatives, hashtags และ video_prompt ภาษาไทยแบบกระชับ
- image_prompts 3 รายการ: ภาพเปิดสินค้า, ภาพรายละเอียด, ภาพไลฟ์สไตล์ปิดการขาย แนวตั้ง 9:16 และคงรูปร่าง สี โลโก้กับบรรจุภัณฑ์เดิม
- flow_gui_design 3 รายการ จับคู่กับภาพ แต่ละรายการมี product_feature, cgi_purpose, visual_style, cgi_elements, animation, composition, accent_colors และ unsupported_elements_to_avoid
- flow_shot_prompts 3 รายการสำหรับ Google Flow ช็อตละ 8-10 วินาที: เปิดสินค้า, อธิบายจุดเด่นจริงหนึ่งเรื่อง, ปิดด้วยการใช้งานที่สมเหตุสมผล
- spoken_script 25-30 วินาที, spoken_script_short 8-10 วินาที และ spoken_script_segments 3 รายการ
- pronunciation_notes, shot_list และ warnings

แผนภาพหนึ่งฉากต้องเป็นชุดเดียวกัน: image_prompts[i], flow_gui_design[i] และ flow_shot_prompts[i] ต้องใช้สินค้า สถานที่ และองค์ประกอบเดียวกัน ให้ flow_shot_prompts กับ spoken_script_segments เป็น object มี scene_index เลข 1, 2, 3 ตามลำดับ
ภาพที่สองเป็นรายละเอียดสินค้า วิดีโอที่สองให้เคลื่อนกล้องตามรายละเอียดที่มีในภาพนั้น ห้ามสั่งตัดไปจอรถหรือสถานที่ใหม่ที่ไม่มีในภาพ หากต้องสาธิตการใช้งาน ให้เตรียมองค์ประกอบนั้นในภาพไลฟ์สไตล์ฉากที่สามตั้งแต่แรก
แยกข้อเท็จจริงสินค้าและบทพูดที่ต้องรักษาออกจากมุมกล้องที่เสนอเอง: บทพูดอธิบายคุณสมบัติที่ยืนยันแล้วได้โดยไม่ต้องสร้างภาพสาธิตทุกประโยค พรอมต์วิดีโอเป็นการเคลื่อนไหวจากภาพอ้างอิงหนึ่งภาพ ไม่ใช่รายการตัดต่อหลายสถานที่

ข้อห้าม: อย่าแต่งสเปก ราคา ส่วนลด สรรพคุณ อุปกรณ์ คน มือ โลโก้ หรือข้อความบนภาพที่ไม่มีหลักฐาน ห้ามใช้ HUD เทคโนโลยี วงแหวน เรดาร์ หรือการ์ดข้อมูลสำเร็จรูปหากไม่เกี่ยวกับสินค้า CGI ทุกชิ้นต้องสื่อคุณสมบัติจริง อธิบายส่วนจริงของสินค้า และไม่บังสินค้า
ถ้าข้อมูลยืนยันไม่ได้ ให้ใส่ข้อจำกัดของข้อมูลไว้ใน warnings เท่านั้น ห้ามพูดเรื่องสินค้ามือสองในข้อความขายหรือบทพูด
บทพูดต้องใช้น้ำเสียงผู้รีวิวมืออาชีพ เป็นภาษาไทยธรรมชาติ ห้ามอ้างว่าเคยใช้ ห้ามพูดถึงขั้นตอนเบื้องหลัง เขียนคำอังกฤษเป็นคำอ่านไทยและตัวเลขเป็นคำไทยทั้งหมด ไม่ใส่ URL อีโมจิ แฮชแท็ก เครื่องหมายสกุลเงิน เปอร์เซ็นต์ วงเล็บ หรืออักษรย่อในบทพูด ใช้ [pause:0.5] หรือ [pause:1.0] ได้เท่านั้น

ตอบด้วย JSON object หนึ่งชุดใน code block ชนิด json ไม่มีคำอธิบายก่อนและหลัง โดย image_prompts, spoken_script_segments, flow_gui_design และ flow_shot_prompts ต้องมีอย่างละ 3 รายการพอดี
"""
        (folder / "prompts" / "chatgpt_request.txt").write_text(analysis_json_prompt(prompt + "\n\n" + COVER_PROMPT), encoding="utf-8")
        # `warnings` is intentionally optional. Gemini commonly returns an
        # empty array when every product fact is sufficiently supported. The
        # result importer already normalizes a missing/empty value to [], so
        # rejecting an otherwise complete package here wastes the analysis and
        # all generated image checkpoints.
        request = {"schema_version": 7, "job_id": job["id"], "provider": "chatgpt_plugin", "product_url": job.get("product_url", ""), "posting_product_url": job.get("posting_product_url", ""), "prompt_file": "prompts/chatgpt_request.txt", "image_files": job["source_images"], "required_fields": ["caption_short", "hashtags", "image_prompts", "video_prompt", "flow_gui_design", "flow_shot_prompts", "spoken_script", "spoken_script_short", "spoken_script_segments", "pronunciation_notes"], "expected_result_folder": "ai_inbox"}
        (folder / "ai_request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")

    def _download_image(self, url, folder, index):
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("อนุญาตเฉพาะรูป HTTPS")
        try:
            resolved = socket.gethostbyname(parsed.hostname)
            if ip_address(resolved).is_private or ip_address(resolved).is_loopback:
                raise ValueError("ไม่อนุญาตที่อยู่ภายในเครื่อง")
        except ValueError:
            raise
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type()
            if not content_type.startswith("image/"):
                raise ValueError("URL ไม่ใช่รูปภาพ")
            if content_type == "image/svg+xml":
                raise ValueError("ไม่รับไฟล์ SVG เป็นรูปสินค้า")
            data = response.read(15 * 1024 * 1024 + 1)
        if len(data) > 15 * 1024 * 1024:
            raise ValueError("รูปมีขนาดเกิน 15 MB")
        extension = mimetypes.guess_extension(content_type) or ".jpg"
        target = folder / f"product_{index:02d}{extension}"
        folder.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        try:
            with Image.open(target) as image:
                image.verify()
            with Image.open(target) as image:
                width, height = image.size
            if width < 128 or height < 128:
                raise ValueError("รูปสินค้ามีขนาดเล็กเกินไป")
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return target

    @staticmethod
    def _source_image_failure(url, error):
        """Return a small safe diagnostic without persisting a signed image URL."""
        host = (urlparse(str(url)).hostname or "ไม่ทราบโดเมน")[:120]
        if isinstance(error, urllib.error.HTTPError):
            reason = f"HTTP {int(error.code)}"
        elif isinstance(error, urllib.error.URLError):
            cause = error.reason
            if isinstance(cause, (TimeoutError, socket.timeout)):
                reason = "หมดเวลาการเชื่อมต่อ"
            elif isinstance(cause, socket.gaierror):
                reason = "ค้นหาโดเมนรูปไม่สำเร็จ"
            else:
                reason = "เชื่อมต่อเซิร์ฟเวอร์รูปไม่ได้"
        elif isinstance(error, (TimeoutError, socket.timeout)):
            reason = "หมดเวลาการเชื่อมต่อ"
        elif isinstance(error, socket.gaierror):
            reason = "ค้นหาโดเมนรูปไม่สำเร็จ"
        elif isinstance(error, Image.UnidentifiedImageError):
            reason = "ข้อมูลที่ได้รับอ่านเป็นรูปภาพไม่ได้"
        elif isinstance(error, ValueError):
            # _download_image raises fixed validation messages here; do not
            # store arbitrary exception text that could contain a full URL.
            reason = str(error)[:120]
        elif isinstance(error, PermissionError):
            reason = "เขียนไฟล์รูปลงเครื่องไม่ได้"
        elif isinstance(error, OSError):
            reason = "อ่านหรือเขียนไฟล์รูปไม่สำเร็จ"
        else:
            reason = "ดาวน์โหลดรูปไม่สำเร็จ"
        return {"host": host, "reason": reason}

    def _download_product_images(self, image_urls, folder, index_offset=0):
        urls = [str(value or "").strip() for value in (image_urls or []) if str(value or "").strip()]
        saved, failures = [], []
        for index, image_url in enumerate(urls, int(index_offset or 0) + 1):
            try:
                path = self._download_image(image_url, folder, index)
                saved.append(path.relative_to(folder.parent).as_posix())
            except Exception as exc:
                failures.append(self._source_image_failure(image_url, exc))
        return saved, {
            "attempted": len(urls),
            "saved": len(saved),
            "failures": failures[:5],
            "additional_failures": max(0, len(failures) - 5),
        }


# Serialize complete read/modify/write transactions, not merely the final
# replace.  This prevents a background worker and a UI action from each
# reading an older manifest then overwriting the other's newer fields.
for _method_name in (
    "list_jobs",
    "get_job",
    "set_automation_state",
    "mark_ai_recovering",
    "reset_ai_recovery_attempts",
    "import_link",
    "create_story_source",
    "story_source_preparations",
    "link_story_job",
    "import_product",
    "apply_ai_result",
    "attach_video",
    "invalidate_stale_flow_outputs",
    "attach_flow_clip",
    "save_video_qa",
    "save_effect_video",
    "promote_video",
    "save_logo_video",
    "save_voice_result",
    "mark_voice_queued",
    "mark_subtitle_queued",
    "set_subtitle_requested",
    "set_image_ai_provider",
    "set_video_ai_provider",
    "save_subtitle_result",
    "rebuild_subtitle_segments",
    "correct_subtitle_from_script",
    "mark_subtitle_error",
    "mark_subtitle_video_needs_render",
    "save_subtitled_video",
    "save_audio_mix_result",
    "mark_audio_mix_error",
    "mark_subtitle_video_error",
    "attach_images",
    "curate_source_images",
    "update_product_info",
    "approve_ai_result",
    "check_readiness",
    "save_partial_image",
    "plugin_request",
    "spoken_script",
    "flow_package",
):
    setattr(ProductManager, _method_name, _serialized_manifest_operation(getattr(ProductManager, _method_name)))
