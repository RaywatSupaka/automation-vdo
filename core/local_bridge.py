import hashlib
import json
import mimetypes
import math
import os
import re
import secrets
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote
from core.product_image_recovery import ProductImageRecovery
from core.bridge_diagnostics import safe_ai_send_diagnostics, safe_ai_image_observation


class LocalBridge:
    REQUIRED_EXTENSION_VERSION = "0.15.498"
    COMMAND_LEASE_SECONDS = 180
    FLOW_RUN_ACTIONS = {
        "focus_flow_web", "debug_flow_dom", "open_flow", "inspect_flow",
        "resume_flow_workspace", "approve_flow_credit", "stop_flow_generation",
        "open_flow_result", "download_flow_result", "inspect_flow_result_dom",
    }
    AI_RUN_ACTIONS = {
        "open_chatgpt", "open_story_chatgpt", "cancel_story_chatgpt",
        "resume_chatgpt", "restart_chatgpt_images", "inspect_chatgpt",
        "focus_ai_web",
    }

    def __init__(
        self,
        host,
        port,
        products,
        logger,
        on_import=None,
        stories=None,
        on_story_ready=None,
        desktop_state=None,
        desktop_action=None,
        desktop_media=None,
        desktop_web_root=None,
        presenters=None,
        desktop_intro_library=None,
        desktop_green_library=None,
        membership=None,
        story_run_active=None,
    ):
        self.membership = membership
        self.host, self.port, self.products = host, int(port), products
        self.logger, self.on_import = logger, on_import
        self.stories = stories
        from core.meta_video import MetaVideoManager
        self.meta_video = MetaVideoManager(stories, products=products) if stories or products else None
        from core.ai_cover import AICovers
        self.ai_covers = AICovers(products, stories)
        self.presenters = presenters
        self.on_story_ready = on_story_ready
        self.desktop_state = desktop_state
        self.desktop_action = desktop_action
        self.story_run_active = story_run_active
        self.desktop_media = desktop_media
        self.desktop_intro_library = desktop_intro_library
        self.desktop_green_library = desktop_green_library
        self._intro_upload_lock = threading.Lock()
        self.desktop_web_root = Path(desktop_web_root).resolve() if desktop_web_root else None
        self.server = None
        # The serial Meta gate owns this fence while publishing its durable
        # command via the normal broker (which re-enters the same fence).
        self._extension_lock = threading.RLock()
        self._flow_diagnostic_lock = threading.Lock()
        self._extension_trace_lock = threading.Lock()
        self._extension_clients = {}
        self._extension_reload_requests = {}
        self._extension_commands = []
        self._extension_runs = {}
        self._extension_trace = []
        self._extension_trace_sequence = 0
        self._ai_result_lock = threading.Lock()
        self._ai_result_receipts = {}
        # Session-only capability used by browser-origin requests. It rotates
        # whenever the local engine restarts and is never exposed by status,
        # logs, URLs or persistent configuration.
        self._extension_token = secrets.token_urlsafe(32)
        from core.extension_identity import ExtensionIdentity
        project_root = getattr(products, 'project_root', None)
        if not isinstance(project_root, (str, os.PathLike)):
            project_root = Path(__file__).resolve().parents[1]
        self._extension_identity = ExtensionIdentity(project_root)
        self._extension_sessions = {}

    @staticmethod
    def flow_failure_reason(value):
        """Bounded plain provider text, never a coerced object or page dump."""
        if not isinstance(value, str):
            return ""
        return " ".join("".join(" " if ord(char) < 32 or 127 <= ord(char) <= 159 else char
                                for char in value[:2400]).split())[:600]

    def _append_flow_diagnostic(self, progress):
        """Persist meaningful Flow transitions beside the Job for later review."""
        job_id = str(progress.get("flow_job_id") or "")
        if not job_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in job_id):
            return
        owner = self.presenters if job_id.startswith("PRESENTER-") else self.stories if job_id.startswith("STORY-") and self.stories is not None else self.products
        root = getattr(owner, "root", None)
        if not root:
            return
        payload = {
            "at": str(progress.get("flow_updated_at") or time.strftime("%Y-%m-%dT%H:%M:%S")),
            "job_id": job_id,
            "shot_index": int(progress.get("flow_shot_index") or 0),
            "run_id": str(progress.get("flow_run_id") or ""),
            "step": str(progress.get("flow_step") or ""),
            "image_ready": bool(progress.get("flow_image_ready")),
            "prompt_ready": bool(progress.get("flow_prompt_ready")),
            "message": str(progress.get("flow_message") or "")[:1000],
            "page_url": str(progress.get("flow_page_url") or "")[:1000],
            "page_excerpt": str(progress.get("flow_page_excerpt") or "")[:3000],
            "button_labels": list(progress.get("flow_button_labels") or [])[:30],
            "failure_code": str(progress.get("flow_failure_code") or "")[:100],
            "policy_failure_category": str(progress.get("flow_policy_failure_category") or "")[:100],
            "failure_card_fingerprint": str(progress.get("flow_failure_card_fingerprint") or "")[:160],
            "failure_reason": self.flow_failure_reason(progress.get("flow_failure_reason")),
            "attachment_failure_evidence": dict(progress.get("flow_attachment_failure_evidence") or {}),
        }
        try:
            log_folder = Path(root) / job_id / "logs"
            log_folder.mkdir(parents=True, exist_ok=True)
            with self._flow_diagnostic_lock:
                with (log_folder / "flow_extension.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except OSError as exc:
            self.logger.warning(
                "job_id=%s state=FLOW_DIAGNOSTIC result=write_failed error=%s", job_id, exc
            )

    @staticmethod
    def _safe_ai_send_diagnostics(payload):
        return safe_ai_send_diagnostics(payload)

    @staticmethod
    def _safe_ai_image_observation(payload):
        return safe_ai_image_observation(payload)

    @staticmethod
    def validate_flow_attachment_failure(body):
        """Keep pre-submit attachment evidence distinct from Flow policy denial."""
        if body.get("failure_code") != "FLOW_ATTACHMENT_UNCONFIRMED":
            return {}
        evidence = body.get("attachment_failure_evidence")
        if not isinstance(evidence, dict):
            raise ValueError("Attachment terminal evidence missing")
        job_id = str(body.get("job_id") or "")
        run_id = str(body.get("run_id") or "")
        shot_index = int(body.get("shot_index") or 0)
        page = urlparse(str(body.get("page_url") or ""))
        segments = page.path.split("/")
        project_id = segments[segments.index("project") + 1] if "project" in segments and segments.index("project") + 1 < len(segments) else ""
        numeric_fields = ("attempt_started_at", "grace_started_at", "grace_elapsed_ms")
        if any(type(evidence.get(key)) not in (int, float) or not math.isfinite(evidence[key]) for key in numeric_fields):
            raise ValueError("Attachment terminal timing invalid")
        expected_attempt = f"{job_id}:{shot_index}:{project_id}"
        expected_fingerprint = f"attachment:{job_id}:{shot_index}:{run_id}:{project_id}:{int(evidence['attempt_started_at'])}"[:160]
        if (
            body.get("step") != "attachment_failed" or not job_id or not run_id or shot_index <= 0
            or int(body.get("tab_id") or 0) <= 0
            or page.scheme != "https" or page.hostname not in {"flow.google.com", "labs.google"} or not project_id
            or body.get("image_ready") is not False or body.get("prompt_ready") is not True
            or body.get("has_rights_dialog") or body.get("confirmation_kind") or body.get("download_path")
            or type(evidence.get("schema_version")) is not int or evidence.get("schema_version") != 1
            or evidence.get("phase") != "before_submit"
            or evidence.get("attempt_key") != expected_attempt or evidence.get("project_id") != project_id
            or evidence.get("run_id") != run_id or type(evidence.get("attachment_attempt_count")) is not int
            or evidence.get("attachment_attempt_count") != 1
            or evidence["attempt_started_at"] <= 0 or evidence["attempt_started_at"] > evidence["grace_started_at"]
            or evidence["grace_elapsed_ms"] < 30000
            or str(body.get("failure_card_fingerprint") or "") != expected_fingerprint
            or any(evidence.get(key) is not True for key in (
                "submission_absent", "generation_absent", "result_absent", "confirmation_absent", "terminal_latched"
            ))
        ):
            raise ValueError("Attachment terminal evidence inconsistent")
        validated = {key: evidence[key] for key in (
            "schema_version", "phase", "attempt_key", "attempt_started_at", "grace_started_at",
            "grace_elapsed_ms", "project_id", "run_id", "attachment_attempt_count",
            "submission_absent", "generation_absent", "result_absent", "confirmation_absent", "terminal_latched"
        )}
        if evidence.get("selection_recovery_available") is True:
            validated["selection_recovery_available"] = True
        return validated

    @staticmethod
    def _safe_story_image_request(payload, scene_count=15):
        """Explicit local prompt audit, separate from credential-free Send facts."""
        if type(scene_count) is not int or not 1 <= scene_count <= 50:
            raise ValueError("Story image request scene count invalid")
        value = payload.get("image_request")
        if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value.get("schema_version") != 1:
            raise ValueError("Story image request snapshot missing")
        result = {"schema_version": 1}
        for key in ("prompt", "composer_text"):
            text = value.get(key)
            if not isinstance(text, str) or not text.strip() or len(text) > 100000:
                raise ValueError(f"Story image request {key} invalid")
            result[key] = text
        for key, lower, upper in (("scene_index", 1, scene_count),
                                  ("source_count", 0, 3), ("source_attachment_count", 0, 100)):
            number = value.get(key)
            if type(number) is not int or not lower <= number <= upper:
                raise ValueError(f"Story image request {key} invalid")
            result[key] = number
        attempt = value.get("attempt")
        if type(attempt) is not int or attempt < 1:
            raise ValueError("Story image request attempt invalid")
        result["attempt"] = attempt
        expected = "reference_image" if result["source_count"] else "text_to_image"
        if value.get("input_kind") != expected:
            raise ValueError("Story image request input kind inconsistent")
        result["input_kind"] = expected
        for key, allowed in (("attachment_scope", {"composer", "page_upload_previews"}),
                             ("entry_mode", {"visible_labels", "not_exposed"})):
            if value.get(key) not in allowed:
                raise ValueError(f"Story image request {key} invalid")
            result[key] = value[key]
        for key in ("source_attachment_busy", "source_attachment_failed", "image_expansion_open", "send_button_enabled"):
            if type(value.get(key)) is not bool:
                raise ValueError(f"Story image request {key} invalid")
            result[key] = value[key]
        labels = value.get("visible_mode_labels")
        if not isinstance(labels, list) or len(labels) > 8 or any(not isinstance(label, str) for label in labels):
            raise ValueError("Story image request labels invalid")
        result["visible_mode_labels"] = [label[:160] for label in labels]
        result["prompt_length"] = len(result["prompt"])
        result["composer_length"] = len(result["composer_text"])
        result["prompt_sha256"] = hashlib.sha256(result["prompt"].encode("utf-8")).hexdigest()
        result["composer_sha256"] = hashlib.sha256(result["composer_text"].encode("utf-8")).hexdigest()
        result["composer_matches"] = " ".join(result["prompt"].split()) == " ".join(result["composer_text"].split())
        return result

    def _record_extension_trace(self, payload):
        """Keep a compact live trace and persist Job-scoped Extension actions."""
        job_id = str(payload.get("job_id") or "")[:100]
        detail = payload.get("detail")
        if payload.get("action") == "image_prompt_ready":
            if not self.stories:
                raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
            story_job = self.stories.get(job_id)
            scene_count = story_job.get("scene_count")
            upper = 50 if story_job.get("long_video") else 15
            if type(scene_count) is not int or not 1 <= scene_count <= upper:
                raise ValueError("Story image request scene count invalid")
            detail = self._safe_story_image_request({"image_request": detail}, scene_count=scene_count)
        if not isinstance(detail, (dict, list)):
            detail = None
        with self._extension_trace_lock:
            self._extension_trace_sequence += 1
            item = {
                "sequence": self._extension_trace_sequence,
                "at": str(payload.get("at") or time.strftime("%Y-%m-%dT%H:%M:%S")),
                "client_id": str(payload.get("client_id") or "")[:200],
                "version": str(payload.get("version") or "")[:50],
                "service": str(payload.get("service") or "extension")[:50],
                "job_id": job_id,
                "shot_index": max(0, int(payload.get("shot_index") or 0)),
                "run_id": self._normalise_run_id(payload.get("run_id")),
                "action": str(payload.get("action") or "progress")[:100],
                "message": str(payload.get("message") or "")[:2000],
                "level": str(payload.get("level") or "info")[:20],
                "tab_id": max(0, int(payload.get("tab_id") or 0)),
                "page_url": str(payload.get("page_url") or "")[:1000],
                "detail": detail,
            }
            fingerprint = tuple(item.get(key) for key in (
            "client_id", "service", "job_id", "shot_index", "run_id", "action", "message", "level", "detail"
            ))
            previous = self._extension_trace[-1] if self._extension_trace else {}
            previous_fingerprint = tuple(previous.get(key) for key in (
                "client_id", "service", "job_id", "shot_index", "run_id", "action", "message", "level", "detail"
            ))
            if fingerprint == previous_fingerprint and item["action"] != "image_prompt_ready":
                return dict(previous)
            self._extension_trace.append(item)
            self._extension_trace = self._extension_trace[-300:]
        self.logger.info(
            "job_id=%s state=EXTENSION_TRACE service=%s shot=%s action=%s level=%s message=%s",
            job_id or "-", item["service"], item["shot_index"], item["action"], item["level"],
            item["message"].replace("\n", " ")[:500] or "-",
        )
        if job_id and all(char in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in job_id):
            owner = self.presenters if job_id.startswith("PRESENTER-") else self.stories if job_id.startswith("STORY-") and self.stories is not None else self.products
            root = getattr(owner, "root", None)
            if item["action"] == "image_prompt_ready" and (
                not job_id.startswith("STORY-") or self.stories is None or not root
                or not (Path(root) / job_id / "job.json").is_file()
            ):
                raise ValueError("Story image request job missing")
            if root:
                try:
                    log_folder = Path(root) / job_id / "logs"
                    log_folder.mkdir(parents=True, exist_ok=True)
                    with self._extension_trace_lock:
                        with (log_folder / "extension_trace.jsonl").open("a", encoding="utf-8") as handle:
                            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
                            if item["action"] == "image_prompt_ready":
                                handle.flush()
                                os.fsync(handle.fileno())
                except OSError as exc:
                    self.logger.warning(
                        "job_id=%s state=EXTENSION_TRACE result=write_failed error=%s", job_id, exc
                    )
                    if item["action"] == "image_prompt_ready":
                        raise
        elif item["action"] == "image_prompt_ready":
            raise ValueError("Story image request job invalid")
        return dict(item)

    def request_extension_reload(self, client_id, target_version):
        """Ask one authenticated, recently seen worker to reload once."""
        with self._extension_lock:
            client = self._extension_clients.get(client_id) or {}
            if (client.get("origin") != f"chrome-extension://{client_id}"
                    or time.time() - client.get("last_seen_epoch", 0) > 70
                    or target_version != self.REQUIRED_EXTENSION_VERSION):
                raise ValueError("Extension ตัวเดิมยังไม่เชื่อมต่อ • โหลดซ้ำจาก Chrome ด้วยตนเองหนึ่งครั้ง")
            if client.get("extension_update_protocol") != 1:
                raise ValueError("Extension รุ่นที่ติดตั้งยังไม่รองรับปุ่ม Reload • กด Reload ใน Chrome อีกหนึ่งครั้ง")
            self._extension_reload_requests[client_id] = {
                "target_version": target_version,
                "nonce": secrets.token_hex(16),
                "expires_at": time.time() + 90,
            }

    def extension_status(self):
        now = time.time()
        with self._extension_lock:
            clients = [dict(item) for item in self._extension_clients.values() if now - item.get("last_seen_epoch", 0) <= 70]
        with self._extension_trace_lock:
            trace = [dict(item) for item in self._extension_trace[-200:]]
        if not clients:
            return {"connected": False, "clients": [], "trace": trace}
        clients.sort(key=lambda item: item.get("last_seen_epoch", 0), reverse=True)
        for item in clients:
            item.pop("last_seen_epoch", None)
        # Keep every fresh client visible, while the desktop's primary status
        # represents an available client paired with this engine.
        client = next((item for item in clients
                       if item.get("version") == self.REQUIRED_EXTENSION_VERSION), clients[0])
        return {"connected": True, "client": client, "clients": clients, "trace": trace}

    def clear_ai_progress(self, job_id):
        """Remove stale terminal AI state before a checkpoint resume command."""
        job_id = str(job_id or "")
        with self._extension_lock:
            for client in self._extension_clients.values():
                if str(client.get("ai_job_id") or "") != job_id:
                    continue
                for key in (
                    "ai_step", "ai_job_id", "ai_message", "ai_image_count", "ai_provider",
                    "ai_action_kind", "ai_service", "ai_resume_action", "ai_page_url",
                    "ai_page_excerpt", "ai_updated_at", "ai_send_diagnostics", "ai_image_observation",
                    "ai_response_active", "ai_response_signature", "ai_observation",
                ):
                    client.pop(key, None)

    def clear_flow_progress(self, job_id, shot_index=0):
        """Discard a stale Flow terminal state before opening a new project."""
        job_id = str(job_id or "")
        shot_index = int(shot_index or 0)
        with self._extension_lock:
            for client in self._extension_clients.values():
                if str(client.get("flow_job_id") or "") != job_id:
                    continue
                if shot_index and int(client.get("flow_shot_index") or 0) != shot_index:
                    continue
                for key in tuple(client):
                    if key.startswith("flow_"):
                        client.pop(key, None)

    def _validated_scene_video_flow_progress(self, body):
        """Bind planned Flow observations/download bytes to their original claim."""
        job_id, index = str(body.get('job_id') or ''), int(body.get('shot_index') or 0)
        if not self.stories or not job_id.startswith('STORY-') or index < 1:
            return {}
        from core.scene_video_plan import enabled, assert_binding
        from core.scene_video_worker import flow_download_path
        with self.stories._manifest_lock:
            job = self.stories.get(job_id)
            if not enabled(job):
                if body.get('scene_video_plan'):
                    raise ValueError('ผลฉากอ้างแผนที่ไม่มีในงานนี้')
                return {}
            binding = body.get('scene_video_plan')
            assert_binding(job, index, binding, allow_legacy_active=True)
            if binding and (binding.get('provider') != 'google_flow'
                            or body.get('video_provider') not in {None, '', 'google_flow'}):
                raise ValueError('ผลฉากไม่ตรงผู้สร้าง Google Flow ที่บันทึกไว้')
            result = {'flow_scene_video_plan': dict(binding) if binding else None,
                      'flow_video_provider': 'google_flow', 'flow_download_sha256': ''}
            observed = body.get('observed_flow_settings')
            if isinstance(observed, dict):
                from core.flow_settings import flow_settings, FIELDS
                result['flow_observed_settings'] = flow_settings({key: observed[key] for key in FIELDS if key in observed})
            download = str(body.get('download_path') or '')
            if download:
                expected = flow_download_path(job_id, index, binding).resolve()
                target = Path(download).resolve()
                if target != expected or not target.is_file() or target.stat().st_size < 1024:
                    raise ValueError('ไฟล์ดาวน์โหลดไม่ตรง attempt ของฉาก • ไม่รับไฟล์เก่าทับ')
                before = target.stat()
                digest = hashlib.sha256()
                with target.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(chunk)
                after = target.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('ไฟล์ดาวน์โหลดยังเปลี่ยนอยู่ • รอผลเดิม')
                result['flow_download_sha256'] = digest.hexdigest()
            return result

    def _resolve_product_flow_shot(self, job_id):
        """Return the active or first unfinished 1-based Flow shot."""
        from core.product_manager import ProductManager
        job_id = str(job_id or "")
        if not job_id or job_id.startswith("STORY-"):
            return 0
        job = next((item for item in self.products.list_jobs() if str(item.get("id") or "") == job_id), None)
        if not job:
            return 0
        images = list(job.get("generated_images") or job.get("source_images") or [])
        prompts = list(job.get("flow_shot_prompts") or [])
        shot_count = min(len(images), len(prompts)) if prompts else len(images)
        if shot_count <= 0:
            return 0
        folder = Path(self.products.root) / job_id
        clips = dict(job.get("flow_clips") or {})
        local_clips = dict(job.get("flow_local_motion_clips") or {})
        unfinished = []
        completed_remote = []
        for index in range(1, min(15, shot_count) + 1):
            # A terminal slot remains local even if its render has not finished
            # or was cleaned up. Only the desktop local-motion worker may
            # repair it; a default Flow command must never resubmit its image.
            fallback = ProductManager.flow_local_fallback_checkpoint(job, index)
            local_relative = str(local_clips.get(str(index)) or "")
            if fallback or (
                local_relative and (folder / local_relative).is_file()
            ):
                continue
            relative = str(clips.get(str(index)) or "")
            if not relative or not (folder / relative).is_file():
                unfinished.append(index)
            else:
                completed_remote.append(index)
        now = time.time()
        with self._extension_lock:
            live_clients = sorted((
                client for client in self._extension_clients.values()
                if str(client.get("flow_job_id") or "") == job_id
                and str(client.get("version") or "") == self.REQUIRED_EXTENSION_VERSION
                and now - float(client.get("last_seen_epoch") or 0) <= 70
                and int(client.get("flow_shot_index") or 0) in unfinished
            ), key=lambda client: float(client.get("last_seen_epoch") or 0), reverse=True)
            if live_clients:
                return int(live_clients[0]["flow_shot_index"])
        if unfinished:
            return unfinished[0]
        # Keep result/focus commands usable for a fully imported Flow job,
        # without ever selecting a terminal local-motion slot.
        return completed_remote[-1] if completed_remote else 0

    def _accept_product_ai_result(self, body):
        """Commit one result and its handoff once, unless the user cancelled."""
        body = dict(body)
        body.setdefault("provider", "chatgpt_web_extension")
        body.setdefault("image_generation_provider", "chatgpt_web")
        body.setdefault("image_generation_via_chatgpt_web", True)
        job_id = str(body.get("job_id") or "")
        fingerprint = hashlib.sha256(json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        with self._ai_result_lock:
            current = self.products.get_job(job_id)
            if str(current.get("automation_status") or "") == "cancelled":
                self.logger.info("job_id=%s state=AI_RESULT result=ignored_cancelled", job_id)
                return {
                    "ok": True, "ignored": True, "reason": "job_cancelled",
                    "job": current, "flow_command": None,
                }
            receipt = self._ai_result_receipts.get(job_id) or {}
            generated_images = list(current.get("generated_images") or [])
            duplicate = bool(
                receipt.get("fingerprint") == fingerprint
                and current.get("ai_status") == "ready"
                and generated_images == receipt.get("generated_images")
                and all((Path(self.products.root) / job_id / relative).is_file() for relative in generated_images)
            )
            if duplicate and receipt.get("handoff_complete"):
                self.logger.info("job_id=%s state=AI_RESULT result=duplicate", job_id)
                return {"ok": True, "duplicate": True, "job": current, "flow_command": None}
            if not duplicate:
                recovery = ProductImageRecovery(self.products, job_id)
                provenance = recovery.validate_result(body)
                if provenance and current.get("image_recovery_result_digest") == fingerprint:
                    self.logger.info("job_id=%s state=AI_RESULT result=durable_duplicate", job_id)
                    return {"ok": True, "duplicate": True, "job": current, "flow_command": None}
                if provenance:
                    provenance["image_recovery_result_digest"] = fingerprint
                    job = self.products.apply_ai_result(body, image_provenance=provenance)
                else:
                    job = self.products.apply_ai_result(body)
                # Remember only successfully committed results. A retry after
                # a lost response must not reset Flow clips or start it twice.
                receipt = {
                    "fingerprint": fingerprint, "handoff_complete": False,
                    "generated_images": list(job.get("generated_images") or []),
                }
                self._ai_result_receipts[job_id] = receipt
                if len(self._ai_result_receipts) > 100:
                    self._ai_result_receipts.pop(next(iter(self._ai_result_receipts)))
                self.logger.info("job_id=%s state=AI_RESULT result=success", job_id)
                if self.on_import:
                    self.on_import(job, False)
            flow_command = None
            # A callback may have cancelled the job or taken ownership of the
            # pipeline. Read the current state before scheduling browser work.
            job = self.products.get_job(job_id)
            automation_status = str(job.get("automation_status") or "")
            if automation_status in {"", "idle"}:
                flow_command = self.queue_extension_command(
                    "open_flow", job_id, 1 if len(job.get("generated_images") or []) >= 3 else 0
                )
                self.logger.info(
                    "job_id=%s state=AUTO_FLOW command_id=%s result=queued", job_id, flow_command["id"]
                )
            else:
                self.logger.info(
                    "job_id=%s state=AUTO_FLOW result=no_handoff automation_status=%s",
                    job_id, automation_status,
                )
            # Queue failure leaves this false, so a delivery retry can finish
            # that handoff without applying the successful result again.
            receipt["handoff_complete"] = True
            return {"ok": True, "duplicate": duplicate, "job": job, "flow_command": flow_command}

    def _validate_story_ai_run_locked(self, body):
        job_id = str(body.get("job_id") or "")
        incoming = self._normalise_run_id(body.get("run_id"))
        expected = str((self._extension_runs.get(("ai", job_id, 0)) or {}).get("run_id") or "")
        if (expected or incoming) and expected != incoming:
            raise ValueError("Checkpoint Story เป็นของรอบเก่าหรือยังไม่มีคำสั่งรอบนี้ • ไม่เขียนทับงานเดิม")

    def _claim_callback_files(self, path, body):
        """Fence provider callbacks before result/Extension/manifest locks.

        A callback may already be reading media when Delete is clicked. Its
        claim makes deletion report busy; a durable deletion intent denies a
        delayed callback even after the deleting worker/engine has exited.
        """
        paths = {
            '/api/products/import', '/api/ai/result', '/api/jobs/partial-image',
            '/api/jobs/image-recovery', '/api/stories/result', '/api/stories/partial-image',
            '/api/stories/image-fallback', '/api/stories/analysis-checkpoint',
            '/api/stories/editorial-sending',
            '/api/stories/long-video-plan', '/api/stories/scene-gate',
            '/api/meta-video/event', '/api/meta-video/redesign',
            '/api/extension/progress', '/api/extension/flow-recovery',
            '/api/extension/flow-motion-plan', '/api/extension/queue',
        }
        if path not in paths or not isinstance(body, dict):
            return None
        root = getattr(self.products, 'project_root', None)
        if not isinstance(root, (str, os.PathLike)):
            products_root = getattr(self.products, 'root', None)
            if not isinstance(products_root, (str, os.PathLike)):
                return None  # Isolated legacy adapters without a filesystem.
            root = Path(products_root).parent.parent
        from core.job_file_guard import guard_for
        from core.product_job_deletion import assert_job_available
        guard = guard_for(root)
        targets = guard.references((body.get('job_id'), body.get('target_job_id')))
        if not targets:
            return None
        for job_id in targets:
            assert_job_available(root, job_id)
        claim = guard.start(references=targets)
        try:
            # Delete can finish between the first journal read and start().
            for job_id in targets:
                assert_job_available(root, job_id)
            return claim
        except BaseException:
            claim.release()
            raise

    def _accept_story_checkpoint(self, body, analysis=False):
        if not self.stories:
            raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
        with self._extension_lock:
            self._validate_story_ai_run_locked(body)
            if analysis:
                if body.get('editorial_request_id'):
                    return self.stories.save_analysis_checkpoint(str(body.get("job_id") or ""), body.get("result"),
                                                                body['editorial_request_id'])
                return self.stories.save_analysis_checkpoint(str(body.get("job_id") or ""), body.get("result"))
            return self.stories.save_partial_image(body.get("job_id"), body.get("index"), body.get("image"))

    def _accept_story_image_fallback(self, body):
        if not self.stories:
            raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
        if not body.get("run_id") or body.get("reason") != "STORY_IMAGE_REFUSED" or body.get("policy") != "reuse_saved_local_v1":
            raise ValueError("STORY_IMAGE_FALLBACK_REVIEW • ต้องมีหลักฐานการปฏิเสธของรอบงานปัจจุบัน")
        index, source_index = body.get("index"), body.get("source_index")
        if type(index) is not int or type(source_index) is not int or not 1 <= source_index < index <= 50:
            raise ValueError("STORY_IMAGE_FALLBACK_REVIEW • ลำดับภาพประกอบเดิมไม่ถูกต้อง")
        proof = body.get("receipt_proof")
        if not isinstance(proof, dict) or set(proof) != {"original_run_id", "review_revision", "created_at"}:
            raise ValueError("STORY_IMAGE_FALLBACK_REVIEW • หลักฐานรอบที่ถูกปฏิเสธไม่ครบ")
        if not self._normalise_run_id(proof.get("original_run_id")) or type(proof.get("review_revision")) is not int or proof["review_revision"] < 0:
            raise ValueError("STORY_IMAGE_FALLBACK_REVIEW • หลักฐานรอบที่ถูกปฏิเสธไม่ถูกต้อง")
        if type(proof.get("created_at")) not in {int, float} or not 0 < proof["created_at"] <= time.time() * 1000 + 60000:
            raise ValueError("STORY_IMAGE_FALLBACK_REVIEW • เวลาหลักฐานการปฏิเสธไม่ถูกต้อง")
        with self._extension_lock:
            self._validate_story_ai_run_locked(body)
            job_id = str(body.get("job_id") or "")
            job = self.stories.get(job_id)
            scene_count = job.get("scene_count")
            upper = 50 if job.get("long_video") else 15
            if type(scene_count) is not int or not 1 <= scene_count <= upper or index > scene_count:
                raise ValueError("STORY_IMAGE_FALLBACK_REVIEW • ลำดับภาพเกินจำนวนฉากของงาน")
            provider = str(body.get("provider") or "")
            if provider not in {"chatgpt", "gemini"} or provider != str(job.get("image_ai_provider") or "chatgpt"):
                raise ValueError("STORY_IMAGE_FALLBACK_REVIEW • ผู้ให้บริการไม่ตรงกับงานเดิม")
            return self.stories.save_refused_image_fallback(job_id, index, source_index,
                                                          str(body.get("response_excerpt") or "")[:1200], receipt_proof=dict(proof))

    @staticmethod
    def _normalise_run_id(value):
        run_id = str(value or "").strip()
        if not run_id:
            return ""
        if len(run_id) > 100 or not run_id.startswith("RUN-"):
            raise ValueError("Run ID ไม่ถูกต้อง")
        if any(not (character.isalnum() or character in "-_") for character in run_id):
            raise ValueError("Run ID ไม่ถูกต้อง")
        return run_id

    def _extension_run_key(self, action, job_id, shot_index):
        if action == 'open_meta_video':
            return ('meta_ai', str(job_id or ''), int(shot_index or 0))
        if action in self.FLOW_RUN_ACTIONS:
            return ("flow", str(job_id or ""), int(shot_index or 0))
        if action in self.AI_RUN_ACTIONS:
            return ("ai", str(job_id or ""), 0)
        return ("job", str(job_id or ""), 0)

    def _resolve_extension_run_id(self, action, job_id, shot_index, requested=""):
        requested = self._normalise_run_id(requested)
        key = self._extension_run_key(action, job_id, shot_index)
        now = time.time()
        with self._extension_lock:
            current = self._extension_runs.get(key) or {}
            run_id = requested or str(current.get("run_id") or "")
            if not run_id and job_id:
                candidates = [
                    item for item_key, item in self._extension_runs.items()
                    if item_key[1] == str(job_id)
                ]
                if candidates:
                    run_id = str(max(candidates, key=lambda item: item.get("updated_at", 0)).get("run_id") or "")
            if not run_id:
                run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
            self._extension_runs[key] = {"run_id": run_id, "updated_at": now}
        return run_id

    def queue_extension_command(self, action, job_id="", shot_index=0, provider_hint="", run_id="", preserve_checkpoint=False, _meta_sequence=None):
        if _meta_sequence is not None:
            if (action != 'open_meta_video' or not job_id.startswith('STORY-')
                    or not re.fullmatch(r'CMD-[A-F0-9]{10}', str(_meta_sequence.get('id') or ''))
                    or _meta_sequence.get('run_id') != run_id):
                raise ValueError('META_SEQUENCE_REVIEW • คำสั่งรายฉากไม่ตรงงาน')
            with self._extension_lock:
                existing = next((row for row in self._extension_commands if row['id'] == _meta_sequence['id']), None)
                if existing:
                    if (existing['job_id'], existing['shot_index'], existing['run_id']) != (job_id, shot_index, run_id):
                        raise ValueError('META_SEQUENCE_REVIEW • รหัสคำสั่งซ้ำกับงานอื่น')
                    return dict(existing)
        if action == 'focus_browser' and job_id:
            raise ValueError('คำสั่งเปิดหน้าต่างไม่เปลี่ยนงาน')
        allowed_actions = {"read_flow_settings", "capture_shopee_product", "open_chatgpt", "open_story_chatgpt", "cancel_story_chatgpt", "resume_chatgpt", "restart_chatgpt_images", "inspect_chatgpt", "focus_ai_web", "focus_flow_web", "debug_flow_dom", "open_flow", "inspect_flow", "resume_flow_workspace", "approve_flow_credit", "stop_flow_generation", "open_flow_result", "download_flow_result", "inspect_flow_result_dom", "close_automation_browser"}
        allowed_actions.add('focus_browser')
        allowed_actions.add('open_meta_video')
        if action not in allowed_actions:
            raise ValueError("คำสั่ง Extension ไม่ถูกต้อง")
        shot_index = int(shot_index or 0)
        if shot_index < 0 or shot_index > 50:
            raise ValueError("ลำดับช็อตไม่ถูกต้อง")
        flow_shot_actions = {
            "focus_flow_web", "open_flow", "inspect_flow", "resume_flow_workspace",
            "approve_flow_credit", "stop_flow_generation", "open_flow_result",
            "download_flow_result", "inspect_flow_result_dom",
        }
        if job_id and not shot_index and action in flow_shot_actions:
            shot_index = self._resolve_product_flow_shot(job_id)
            if not shot_index:
                raise ValueError("ไม่พบลำดับช็อต Google Flow ที่พร้อมทำงาน")
        requested_provider = str(provider_hint or "").strip().lower()
        ai_provider = requested_provider or "chatgpt"
        if ai_provider not in {"chatgpt", "gemini"}:
            raise ValueError("ผู้ให้บริการ AI Web ไม่ถูกต้อง")
        if job_id and action in {"open_chatgpt", "open_story_chatgpt", "cancel_story_chatgpt", "resume_chatgpt", "restart_chatgpt_images", "inspect_chatgpt", "focus_ai_web"}:
            if job_id.startswith("PRESENTER-"):
                if not self.presenters: raise ValueError("ยังไม่ได้เปิดคลังตัวละคร")
                ai_package = self.presenters.plugin_request(job_id)
            elif job_id.startswith("STORY-"):
                if not self.stories:
                    raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
                ai_package = self.stories.plugin_request(job_id)
            else:
                ai_package = self.products.plugin_request(job_id)
            job_provider = str(ai_package.get("job", {}).get("image_ai_provider") or "chatgpt").strip().lower()
            if job_provider not in {"chatgpt", "gemini"}:
                raise ValueError("ผู้ให้บริการสร้างภาพของ Job ไม่ถูกต้อง")
            if requested_provider and requested_provider != job_provider:
                raise ValueError("คำสั่ง Extension พยายามเปิด AI Web ไม่ตรงกับ Provider ที่ล็อกไว้ใน Job")
            ai_provider = job_provider
        elif job_id and action in {"close_automation_browser", "inspect_flow", "resume_flow_workspace", "approve_flow_credit", "stop_flow_generation", "open_flow_result", "download_flow_result", "inspect_flow_result_dom", "focus_flow_web"}:
            if job_id.startswith("PRESENTER-"):
                if not self.presenters: raise ValueError("ยังไม่ได้เปิดคลังตัวละคร")
                self.presenters.get(job_id)
            elif job_id.startswith("STORY-"):
                if not self.stories:
                    raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
                self.stories.get(job_id)
            elif not any(job.get("id") == job_id for job in self.products.list_jobs()):
                raise ValueError("ไม่พบ Job")
        elif action == 'open_meta_video':
            if not self.meta_video:
                raise ValueError('Meta AI ยังไม่พร้อม')
            if job_id.startswith('STORY-'):
                if not self.stories:
                    raise ValueError('ยังไม่ได้เปิดโหมดเรื่องเล่า')
            elif job_id.startswith('JOB-') and self.products:
                self.products.get_job(job_id)
            else:
                raise ValueError('Meta AI ต้องใช้งานกับงานคลิปที่รองรับ')
            self.meta_video.begin(job_id, shot_index, resume=_meta_sequence is None)
        elif job_id and action != "capture_shopee_product":
            if job_id.startswith("PRESENTER-"):
                if not self.presenters: raise ValueError("ยังไม่ได้เปิดคลังตัวละคร")
                self.presenters.flow_package(job_id, shot_index=shot_index)
            elif job_id.startswith("STORY-"):
                if not self.stories:
                    raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
                self.stories.flow_package(job_id, shot_index=shot_index)
            else:
                self.products.flow_package(job_id, shot_index=shot_index)
        elif job_id and not any(job.get("id") == job_id for job in self.products.list_jobs()):
            raise ValueError("ไม่พบ Job")
        if action == 'close_automation_browser' and shot_index:
            manager = self.stories if str(job_id).startswith('STORY-') else self.products
            saved_job = manager.get(job_id) if str(job_id).startswith('STORY-') else manager.get_job(job_id)
            relative = str((saved_job.get('flow_clips') or {}).get(str(shot_index)) or '')
            folder = (manager.root / job_id).resolve()
            saved = (folder / relative).resolve()
            if not relative or not saved.is_relative_to(folder) or not saved.is_file() or saved.stat().st_size <= 0:
                raise ValueError('ยังไม่ได้บันทึกวิดีโอฉากนี้ • ไม่ปิดแท็บ')
            with self._extension_lock:
                run_id = str((self._extension_runs.get(('flow', str(job_id), shot_index)) or {}).get('run_id') or '')
            if not run_id:
                raise ValueError('ไม่พบรอบงานของแท็บฉากนี้ • เก็บแท็บไว้')
        resolved_run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}" if action == 'focus_browser' else self._resolve_extension_run_id(
            action, job_id, shot_index, requested=run_id
        )
        command = {
            "id": _meta_sequence['id'] if _meta_sequence else f"CMD-{uuid.uuid4().hex[:10].upper()}",
            "action": action,
            "job_id": str(job_id or ""),
            "shot_index": shot_index,
            "created_at": time.time(),
            "status": "pending",
            "min_version": self.REQUIRED_EXTENSION_VERSION,
            "provider": 'meta_ai' if action == 'open_meta_video' else ai_provider,
            "run_id": resolved_run_id,
        }
        if job_id.startswith('STORY-') and shot_index and (action in flow_shot_actions or action == 'open_meta_video'):
            from core.scene_video_plan import enabled, package_binding, assert_binding
            with self.stories._manifest_lock:
                scene_job = self.stories.get(job_id)
                if enabled(scene_job):
                    binding = package_binding(scene_job, shot_index)
                    assert_binding(scene_job, shot_index, binding, allow_legacy_active=True)
                    if binding:
                        expected_provider = 'meta_ai' if action == 'open_meta_video' else 'google_flow'
                        if binding['provider'] != expected_provider:
                            raise ValueError('คำสั่งวิดีโอไม่ตรงผู้สร้างในแผนรายฉาก')
                        command['scene_video_plan'] = binding
        if preserve_checkpoint:
            if action != "stop_flow_generation" or not job_id.startswith("PRESENTER-"):
                raise ValueError("เก็บจุดทำต่อได้เฉพาะคำสั่งหยุดคลิปผู้บรรยาย")
            command["preserve_checkpoint"] = True
        with self._extension_lock:
            if action == "open_story_chatgpt" and job_id.startswith("STORY-"):
                # The desktop may observe a missing/late heartbeat while the
                # first worker is still running. Reuse its command even after
                # its ACK: ACK only means the worker accepted the command,
                # not that analysis or image generation has finished.
                existing = next((row for row in reversed(self._extension_commands)
                                 if row.get("action") == action
                                 and row.get("job_id") == job_id
                                 and row.get("run_id") == resolved_run_id
                                 and row.get("status") in {"pending", "delivered", "completed"}), None)
                if existing:
                    return dict(existing)
                # An engine restart loses the in-memory command list, while
                # the accepted ChatGPT turn remains on disk. Never start a
                # fresh master analysis around that uncertain result.
                if re.fullmatch(r"STORY-[A-Za-z0-9_-]+", job_id):
                    folder = Path(self.stories.root) / job_id
                    if not (folder / "prompts" / "ai_analysis_checkpoint.json").is_file():
                        trace_path = folder / "logs" / "extension_trace.jsonl"
                        try:
                            with trace_path.open("r", encoding="utf-8") as handle:
                                accepted_before_checkpoint = any(
                                    (row.get("action") == "ai_send_accepted"
                                     and row.get("service") == "chatgpt")
                                    for line in handle if line.strip()
                                    for row in (json.loads(line),) if isinstance(row, dict)
                                )
                        except FileNotFoundError:
                            accepted_before_checkpoint = False
                        except (OSError, ValueError, UnicodeError):
                            raise ValueError("AI_WEB_WAIT_REVIEW • อ่านหลักฐานคำขอเดิมไม่ได้ • เก็บแท็บไว้และไม่ส่งซ้ำ")
                        if accepted_before_checkpoint:
                            raise ValueError("AI_WEB_WAIT_REVIEW • เว็บรับคำขอวิเคราะห์เดิมแล้ว แต่ยังไม่มี Checkpoint • เก็บแท็บไว้และไม่เปิดแชตใหม่")
            if action == 'close_automation_browser' and shot_index:
                command['cleanup_shot_index'] = shot_index
                command['cleanup_runs'] = [resolved_run_id]
            elif action == "close_automation_browser" and job_id:
                # Freeze every currently known run for this Job, including its
                # AI and per-shot Flow runs. A later resume must not join this
                # cleanup transaction merely because it reuses the same Job.
                command["cleanup_runs"] = sorted({resolved_run_id} | {
                    str(value.get("run_id")) for key, value in self._extension_runs.items()
                    if key[1] == str(job_id) and value.get("run_id")
                })
            self._extension_commands.append(command)
            self._extension_commands = self._extension_commands[-100:]
        return dict(command)

    def cancel_presenter_pending_commands(self, job_id):
        if not self.presenters:
            raise ValueError("ยังไม่ได้เปิดคลังตัวละคร")
        self.presenters.get(job_id)
        with self._extension_lock:
            for command in self._extension_commands:
                if command.get("job_id") == job_id and command.get("status") == "pending":
                    command.update(status="cancelled", cancelled_at=time.time())

    def extension_command_status(self, command_id):
        """Return a safe snapshot used by the desktop queue as an execution barrier."""
        with self._extension_lock:
            command = next((item for item in self._extension_commands if item.get("id") == str(command_id or "")), None)
            return dict(command) if command else None

    def pending_job_commands(self, job_ids):
        """Read-only deletion barrier; include commands leased but not ACKed."""
        with self._extension_lock:
            return [str(item.get('job_id')) for item in self._extension_commands
                    if item.get('job_id') in job_ids and item.get('status') in {'pending', 'delivered'}]

    def start(self):
        self.ai_covers.recover_startup()
        bridge = self
        class Handler(BaseHTTPRequestHandler):
            def _headers(self, status=200, content_type="application/json; charset=utf-8"):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                origin = self.headers.get("Origin", "")
                if origin.startswith("chrome-extension://") and bridge._extension_identity.allowed(origin):
                    self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Content-Type, X-SmartFlow-Token, X-SmartFlow-Profile",
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            def _send(self, payload, status=200):
                try:
                    self._headers(status)
                    self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                    return True
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    # Browsers cancel superseded state/media requests during
                    # navigation. That is a normal client disconnect, not a
                    # Bridge failure and must not produce a socketserver trace.
                    return False
            def _send_file(self, target):
                target = Path(target).resolve()
                size = target.stat().st_size
                start, end = 0, max(0, size - 1)
                status = 200
                range_header = str(self.headers.get("Range") or "").strip()
                if range_header.startswith("bytes=") and size:
                    requested = range_header[6:].split(",", 1)[0].strip()
                    left, _, right = requested.partition("-")
                    try:
                        if left:
                            start = max(0, min(int(left), size - 1))
                            end = max(start, min(int(right), size - 1)) if right else size - 1
                        elif right:
                            length = max(1, min(int(right), size))
                            start, end = size - length, size - 1
                        status = 206
                    except ValueError:
                        start, end, status = 0, size - 1, 200
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(max(0, end - start + 1)))
                    if status == 206:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    origin = self.headers.get("Origin", "")
                    if origin.startswith("chrome-extension://") and bridge._extension_identity.allowed(origin):
                        self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    remaining = max(0, end - start + 1)
                    with target.open("rb") as source:
                        source.seek(start)
                        while remaining:
                            chunk = source.read(min(1024 * 1024, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                    return True
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    return False
            def _desktop_origin_allowed(self):
                origin = str(self.headers.get("Origin") or "").strip()
                fetch_site = str(self.headers.get("Sec-Fetch-Site") or "").strip().lower()
                if fetch_site == "cross-site":
                    return False
                if not origin:
                    return fetch_site in {'', 'same-origin'}
                try:
                    parsed_origin = urlparse(origin)
                    server_port = int(bridge.server.server_address[1])
                    return (
                        parsed_origin.scheme == "http"
                        and parsed_origin.hostname in {"127.0.0.1", "localhost", "::1"}
                        and int(parsed_origin.port or 80) == server_port
                    )
                except (TypeError, ValueError):
                    return False
            def _extension_request_allowed(self):
                """Authenticate browser-origin Extension traffic.

                Local Python/CLI callers intentionally remain compatible when
                they send no Origin header. Browser callers must be this Chrome
                Extension and know the engine's current session capability.
                """
                origin = str(self.headers.get("Origin") or "").strip()
                supplied = str(self.headers.get("X-SmartFlow-Token") or "")
                profile = str(self.headers.get('X-SmartFlow-Profile') or '')[:48]
                if not origin:
                    site = str(self.headers.get('Sec-Fetch-Site') or '').lower()
                    if not site:
                        return True  # Native local clients, not browser traffic.
                    # Chrome omits Origin on extension GETs with host permission;
                    # native downloads additionally use Sec-Fetch-Site cross-site.
                    # The unguessable session capability still binds the request
                    # to the verified extension and exact profile from bootstrap.
                    if site not in {'none', 'cross-site'} or not supplied:
                        return False
                    with bridge._extension_lock:
                        sessions = list(bridge._extension_sessions.items())
                    return any(saved_profile == profile and expected
                               and secrets.compare_digest(supplied, expected)
                               and bridge._extension_identity.allowed(saved_origin)
                               for (saved_origin, saved_profile), expected in sessions)
                if not bridge._extension_identity.allowed(origin):
                    return False
                with bridge._extension_lock:
                    expected=bridge._extension_sessions.get((origin,profile),'')
                return bool(supplied and expected) and secrets.compare_digest(supplied,expected)
            def _require_extension_request(self):
                if self._extension_request_allowed():
                    return True
                self._send(
                    {"ok": False, "error": "Extension session authentication required"},
                    403,
                )
                return False
            @staticmethod
            def _protected_extension_get(path):
                return (
                    path.startswith('/api/meta-video/')
                    or
                    path.startswith("/api/ai-covers/")
                    or path == "/api/products"
                    or path == "/api/extension/commands"
                    or path == "/api/extension/run-owner"
                    or path.startswith("/api/extension/command/")
                    or path == "/api/ai/requests"
                    or (path.startswith("/api/jobs/") and path.endswith("/chatgpt-package"))
                    or (path.startswith("/api/stories/") and path.endswith("/chatgpt-package"))
                    or path.startswith("/api/presenters/")
                    or (path.startswith("/api/jobs/") and path.endswith("/flow-package"))
                )
            @staticmethod
            def _protected_extension_post(path):
                return path in {
                    '/api/meta-video/event',
                    '/api/meta-video/redesign',
                    "/api/ai-covers/event",
                    "/api/products/import",
                    "/api/ai/result",
                    "/api/jobs/partial-image",
                    "/api/jobs/image-recovery",
                    "/api/stories/result",
                    "/api/stories/partial-image",
                    "/api/stories/image-fallback",
                    "/api/stories/analysis-checkpoint",
                    "/api/stories/editorial-sending",
                    "/api/stories/long-video-plan",
                    "/api/presenters/image",
                    "/api/extension/disconnect",
                    "/api/extension/command-ack",
                    "/api/extension/progress",
                    "/api/extension/flow-recovery",
                    "/api/extension/flow-motion-plan",
                    "/api/extension/queue",
                }
            def do_OPTIONS(self): self._headers(204)
            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                if path.startswith('/api/') and not (self._desktop_origin_allowed() or self._extension_request_allowed()):
                    self._send({'ok':False,'error':'Local application or paired Extension required'},403);return
                if path == '/api/membership/status':
                    if not self._desktop_origin_allowed() or not bridge.membership:
                        self._send({'ok': False}, 403); return
                    self._send(bridge.membership.status()); return
                if path == '/api/desktop/music-preview':
                    try:
                        from core.music_library import resolve_track
                        if not bridge.desktop_web_root:
                            raise ValueError('ไม่พบคลังเพลง')
                        name = (parse_qs(parsed.query).get('file') or [''])[0]
                        self._send_file(resolve_track(bridge.desktop_web_root.parent / 'assets' / 'audio' / 'background', name))
                    except Exception:
                        self._send({'ok': False, 'error': 'ไม่พบไฟล์เพลง'}, 404)
                    return
                if path == '/api/desktop/green-asset':
                    try:
                        file = str((parse_qs(parsed.query).get('file') or [''])[0])
                        if not bridge.desktop_green_library:
                            raise ValueError('ไม่พบไฟล์')
                        self._send_file(bridge.desktop_green_library.resolve(file, verify=False))
                    except Exception:
                        self._send({'ok':False,'error':'ไม่พบไฟล์กรีนสกรีน'},404)
                    return
                if path == '/api/desktop/green-preview':
                    try:
                        token = str((parse_qs(parsed.query).get('token') or [''])[0])
                        if not bridge.desktop_green_library or len(token)!=32 or any(c not in '0123456789abcdef' for c in token):
                            raise ValueError('ไม่พบตัวอย่าง')
                        self._send_file(bridge.desktop_green_library.root/'workspace'/'preview'/'screenfx'/(token+'.mp4'))
                    except Exception:
                        self._send({'ok':False,'error':'ไม่พบตัวอย่างกรีนสกรีน'},404)
                    return
                if self._protected_extension_get(path) and not self._require_extension_request():
                    return
                if path == '/api/meta-video/package':
                    try:
                        query = parse_qs(parsed.query)
                        if not bridge.meta_video:
                            raise ValueError('Meta ยังไม่พร้อม')
                        self._send({'ok': True, 'package': bridge.meta_video.begin(
                            str((query.get('job_id') or [''])[0]), int((query.get('index') or [0])[0]))})
                    except Exception as exc:
                        self._send({'ok': False, 'error': str(exc)}, 400)
                elif path.startswith("/api/ai-covers/"):
                    try:
                        key = path.rsplit('/', 1)[-1]
                        if key == 'pending':
                            self._send({'ok': True, 'requests': bridge.ai_covers.pending()})
                        elif path.startswith('/api/ai-covers/status/'):
                            self._send({'ok': True, 'request': bridge.ai_covers.get(key)})
                        else:
                            self._send({'ok': True, 'request': bridge.ai_covers.package(key)})
                    except Exception as exc:
                        self._send({'ok': False, 'error': str(exc)}, 400)
                elif path == "/desktop":
                    self.send_response(302)
                    self.send_header("Location", "/desktop/")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                elif path == "/desktop/" or path.startswith("/desktop/"):
                    try:
                        if not bridge.desktop_web_root:
                            raise FileNotFoundError("ยังไม่ได้ติดตั้งหน้าจอ Hybrid")
                        relative = "index.html" if path == "/desktop/" else path[len("/desktop/"):]
                        if not relative or "\\" in relative or ".." in relative:
                            raise ValueError("path ไม่ถูกต้อง")
                        target = (bridge.desktop_web_root / relative).resolve()
                        if bridge.desktop_web_root != target.parent and bridge.desktop_web_root not in target.parents:
                            raise ValueError("path ไม่ถูกต้อง")
                        if not target.is_file():
                            target = bridge.desktop_web_root / "index.html"
                        self._send_file(target)
                    except Exception as exc:
                        self._send({"ok": False, "error": str(exc)}, 404)
                elif path == "/api/desktop/state":
                    try:
                        if not bridge.desktop_state:
                            raise RuntimeError("Hybrid engine ยังไม่พร้อม")
                        query = parse_qs(parsed.query)
                        mode = str((query.get("mode") or ["full"])[0]).strip().lower()
                        payload = bridge.desktop_state(mode) if mode in {"compact", "subtitle_preview", "logs"} else bridge.desktop_state()
                        self._send({"ok": True, **(payload if isinstance(payload, dict) else {"state": payload})})
                    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                        return
                    except Exception as exc:
                        try:
                            self._send({"ok": False, "error": str(exc)}, 503)
                        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                            return
                elif path == "/api/desktop/media":
                    try:
                        if not bridge.desktop_media:
                            raise FileNotFoundError("ไม่พบตัวอ่านไฟล์พรีวิว")
                        query = parse_qs(parsed.query)
                        item_id = str((query.get("item_id") or [""])[0])[:200]
                        kind = str((query.get("kind") or ["preview"])[0])[:30]
                        target = bridge.desktop_media(item_id, kind)
                        if not target or not Path(target).is_file():
                            raise FileNotFoundError("ไม่พบไฟล์พรีวิว")
                        self._send_file(target)
                    except Exception as exc:
                        self._send({"ok": False, "error": str(exc)}, 404)
                elif path == "/health":
                    from core.app_updates import customer_version
                    self._send({"ok": True, "service": "Shopee AutoPost Local Bridge", "ai_provider": "browser_extension", "ai_providers": ["chatgpt_web", "gemini_web"], "requires_api_key": False, "extension_version_required": bridge.REQUIRED_EXTENSION_VERSION, "desktop_ui": "hybrid" if bridge.desktop_web_root else "legacy", "engine_pid": os.getpid(), "release_version": customer_version()})
                elif path == "/api/products": self._send({"ok": True, "jobs": bridge.products.list_jobs()})
                elif path == "/api/extension/status": self._send({"ok": True, **bridge.extension_status()})
                elif path == "/api/extension/run-owner":
                    query = parse_qs(parsed.query)
                    job_id = str((query.get("job_id") or [""])[0])
                    run_id = str((query.get("run_id") or [""])[0])
                    active = False
                    if job_id.startswith("STORY-") and 0 < len(job_id) <= 100 and run_id:
                        with bridge._extension_lock:
                            registered = str((bridge._extension_runs.get(("ai", job_id, 0)) or {}).get("run_id") or "") == run_id
                        if registered and callable(bridge.story_run_active):
                            try:
                                active = bridge.story_run_active(job_id) is True
                            except Exception:
                                active = False
                    # The response deliberately exposes no run ID, prompt, or session token.
                    self._send({"ok": True, "active": active})
                elif path == "/api/extension/commands":
                    client_id = str((parse_qs(parsed.query).get("client_id") or [""])[0])[:200]
                    if not client_id:
                        self._send({"ok": False, "error": "client_id ไม่ถูกต้อง"}, 400); return
                    now = time.time()
                    with bridge._extension_lock:
                        client_version = (bridge._extension_clients.get(client_id) or {}).get("version", "")
                        ready = [
                            item for item in bridge._extension_commands
                            if client_version == item.get("min_version", bridge.REQUIRED_EXTENSION_VERSION)
                            and (
                                item.get("status") == "pending"
                                or (
                                    item.get("status") == "delivered"
                                    and float(item.get("lease_expires_at") or 0) <= now
                                )
                            )
                        ]
                        commands = []
                        for item in ready:
                            lease_token = f"LEASE-{uuid.uuid4().hex[:16].upper()}"
                            item.update({
                                "status": "delivered",
                                "client_id": client_id,
                                "delivered_at": now,
                                "lease_token": lease_token,
                                "lease_expires_at": now + bridge.COMMAND_LEASE_SECONDS,
                            })
                            commands.append(dict(item))
                    self._send({"ok": True, "commands": commands, "extension_version_required": bridge.REQUIRED_EXTENSION_VERSION, "update_required": client_version != bridge.REQUIRED_EXTENSION_VERSION})
                elif path.startswith("/api/extension/command/"):
                    command_id = path.rsplit("/", 1)[-1]
                    with bridge._extension_lock:
                        command = next((dict(item) for item in bridge._extension_commands if item.get("id") == command_id), None)
                    if command: self._send({"ok": True, "command": command})
                    else: self._send({"ok": False, "error": "ไม่พบคำสั่ง"}, 404)
                elif path == "/api/ai/requests":
                    base_url = f"http://{bridge.host}:{bridge.server.server_address[1]}"
                    requests = []
                    for job in bridge.products.list_jobs():
                        if job.get("ai_status") != "request_ready": continue
                        package = bridge.products.plugin_request(job["id"])
                        package["provider"] = "chatgpt_plugin"
                        package["requires_api_key"] = False
                        package["image_urls"] = [f"{base_url}/api/jobs/{job['id']}/files/{path.replace(chr(92), '/')}" for path in package.get("request", {}).get("image_files", job.get("source_images", []))]
                        package["product_prompt_repair"] = {"enabled": True, "service_continuous": True, "contract_version": 2, "policy_redesign_limit": 1}
                        requests.append(package)
                    self._send({"ok": True, "provider": "chatgpt_plugin", "requires_api_key": False, "requests": requests})
                elif path.startswith("/api/jobs/") and path.endswith("/chatgpt-package"):
                    try:
                        job_id = path[len("/api/jobs/"):-len("/chatgpt-package")].strip("/")
                        package = bridge.products.plugin_request(job_id)
                        base_url = f"http://{bridge.host}:{bridge.server.server_address[1]}"
                        ai_provider = str(package["job"].get("image_ai_provider") or "chatgpt")
                        package["provider"] = f"{ai_provider}_web_extension"
                        package["image_ai_provider"] = ai_provider
                        package["requires_api_key"] = False
                        package["product_prompt_repair"] = {"enabled": True, "service_continuous": True, "contract_version": 2, "policy_redesign_limit": 1}
                        package["image_urls"] = [
                            f"{base_url}/api/jobs/{job_id}/files/{item.replace(chr(92), '/')}"
                            for item in package["request"].get("image_files", package["job"].get("source_images", []))
                        ]
                        checkpoint_items = package.pop("checkpoint_images", [])
                        package["checkpoint_images"] = [
                            {
                                "index": int(item.replace(chr(92), "/").rsplit("/", 1)[-1].split("selling_image_", 1)[-1].split(".", 1)[0]),
                                "url": f"{base_url}/api/jobs/{job_id}/files/{item.replace(chr(92), '/')}",
                            }
                            for item in checkpoint_items
                        ]
                        self._send({"ok": True, "package": package})
                    except Exception as exc:
                        self._send({"ok": False, "error": str(exc)}, 404)
                elif path.startswith("/api/presenters/"):
                    try:
                        if not bridge.presenters: raise ValueError("ยังไม่ได้เปิดคลังตัวละคร")
                        parts = path.split("/")
                        job_id = parts[3]
                        folder = bridge.presenters.folder(job_id).resolve()
                        if path.endswith("/chatgpt-package"):
                            package = bridge.presenters.plugin_request(job_id)
                            base_url = f"http://{bridge.host}:{bridge.server.server_address[1]}"
                            provider = package["job"]["image_ai_provider"]
                            package.update(provider=f"{provider}_web_extension", image_ai_provider=provider, requires_api_key=False)
                            package["image_urls"] = [f"{base_url}/api/presenters/{job_id}/files/{item}" for item in package["job"]["source_images"]]
                            self._send({"ok": True, "package": package})
                        elif len(parts) >= 6 and parts[4] == "files":
                            target = (folder / "/".join(parts[5:])).resolve()
                            if folder not in target.parents or not target.is_file(): raise ValueError("ไฟล์ไม่ถูกต้อง")
                            self._send_file(target)
                        else: raise ValueError("ไม่พบเส้นทางตัวละคร")
                    except Exception as exc: self._send({"ok": False, "error": str(exc)}, 404)
                elif path.startswith("/api/stories/") and path.endswith("/chatgpt-package"):
                    try:
                        if not bridge.stories: raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
                        job_id = path[len("/api/stories/"):-len("/chatgpt-package")].strip("/")
                        package = bridge.stories.plugin_request(job_id)
                        base_url = f"http://{bridge.host}:{bridge.server.server_address[1]}"
                        ai_provider = str(package["job"].get("image_ai_provider") or "chatgpt")
                        package["provider"] = f"{ai_provider}_web_extension"
                        package["image_ai_provider"] = ai_provider
                        package["requires_api_key"] = False
                        package["image_urls"] = [f"{base_url}/api/stories/{job_id}/files/{item.replace(chr(92), '/')}" for item in package["job"].get("source_images", [])]
                        checkpoint_items = package.pop("checkpoint_images", [])
                        package["checkpoint_images"] = [
                            {
                                "index": int(item.replace(chr(92), "/").rsplit("/", 1)[-1].split("scene_", 1)[-1].split(".", 1)[0]),
                                "url": f"{base_url}/api/stories/{job_id}/files/{item.replace(chr(92), '/')}",
                            }
                            for item in checkpoint_items
                        ]
                        self._send({"ok": True, "package": package})
                    except Exception as exc:
                        self._send({"ok": False, "error": str(exc)}, 404)
                elif path.startswith("/api/jobs/") and path.endswith("/flow-package"):
                    try:
                        job_id = path[len("/api/jobs/"):-len("/flow-package")].strip("/")
                        shot_index = int((parse_qs(parsed.query).get("shot_index") or [0])[0] or 0)
                        is_story = job_id.startswith("STORY-")
                        is_presenter = job_id.startswith("PRESENTER-")
                        if is_presenter:
                            if not bridge.presenters: raise ValueError("ยังไม่ได้เปิดคลังตัวละคร")
                            package = bridge.presenters.flow_package(job_id, shot_index=shot_index)
                        elif is_story:
                            if not bridge.stories: raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
                            package = bridge.stories.flow_package(job_id, shot_index=shot_index)
                        else:
                            package = bridge.products.flow_package(job_id, shot_index=shot_index)
                        if not is_presenter:
                            from core.flow_replacement import apply_replacement
                            manager = bridge.stories if is_story else bridge.products
                            job = manager.get(job_id) if is_story else manager.get_job(job_id)
                            apply_replacement(manager.root / job_id, job, shot_index, package)
                            if is_story and package.get('speech_retry_id'):
                                from core.flow_speech_quality import retry_prompt
                                package['video_prompt'] = retry_prompt(package.get('video_prompt'))
                        base_url = f"http://{bridge.host}:{bridge.server.server_address[1]}"
                        file_scope = "presenters" if is_presenter else "stories" if is_story else "jobs"
                        package["image_urls"] = [
                            f"{base_url}/api/{file_scope}/{job_id}/files/{path.replace(chr(92), '/')}"
                            for path in package.pop("image_files", [])
                        ]
                        if is_story and not package.get('speech_retry_id'):
                            from core.atomic_json import AtomicJsonFile
                            restart = AtomicJsonFile(bridge.stories.root / job_id / 'prompts' / 'flow_manual_resume.json').read({})
                            if restart.get('index') == shot_index and restart.get('job_id') == job_id:
                                ledger = AtomicJsonFile(bridge.stories.root / job_id / 'prompts' / 'flow_recovery.json').read({'scenes': {}})
                                events = ledger.get('scenes', {}).get(str(shot_index), [])
                                last = events[-1] if events else {}
                                if last.get('phase') == 'needs_review' and last.get('digest') == restart.get('event_digest') and last.get('request_id') == restart.get('request_id'):
                                    package['manual_flow_repair'] = {**restart, 'review_checkpoint': last}
                                    from core.flow_review import ready_home_replacement
                                    ready = ready_home_replacement(bridge.stories.root / job_id, job, shot_index, restart)
                                    if ready:
                                        package['ready_home_replacement'] = {**ready,
                                            'image_url': f"{base_url}/api/stories/{job_id}/files/{ready['image_file']}"}
                                else:
                                    package['manual_flow_repair'] = restart
                        self._send({"ok": True, "package": package})
                    except Exception as exc:
                        self._send({"ok": False, "error": str(exc)}, 404)
                elif path.startswith("/api/jobs/") and "/files/" in path:
                    try:
                        prefix, relative = path.split("/files/", 1)
                        job_id = prefix.rsplit("/", 1)[-1]
                        if not job_id.startswith("JOB-") or "\\" in relative or ".." in relative: raise ValueError("path ไม่ถูกต้อง")
                        job_folder = (bridge.products.root / job_id).resolve()
                        target = (job_folder / relative).resolve()
                        if target.parent != job_folder and job_folder not in target.parents: raise ValueError("path ไม่ถูกต้อง")
                        if not target.is_file(): raise FileNotFoundError("ไม่พบไฟล์")
                        self._send_file(target)
                    except Exception as exc: self._send({"ok": False, "error": str(exc)}, 404)
                elif path.startswith("/api/stories/") and "/files/" in path:
                    try:
                        if not bridge.stories: raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
                        prefix, relative = path.split("/files/", 1)
                        job_id = prefix.rsplit("/", 1)[-1]
                        if not job_id.startswith("STORY-") or "\\" in relative or ".." in relative: raise ValueError("path ไม่ถูกต้อง")
                        job_folder = (bridge.stories.root / job_id).resolve()
                        target = (job_folder / relative).resolve()
                        if target.parent != job_folder and job_folder not in target.parents: raise ValueError("path ไม่ถูกต้อง")
                        if not target.is_file(): raise FileNotFoundError("ไม่พบไฟล์")
                        self._send_file(target)
                    except Exception as exc: self._send({"ok": False, "error": str(exc)}, 404)
                else: self._send({"ok": False, "error": "not_found"}, 404)
            def do_POST(self):
                callback_claim = None
                try:
                    path = urlparse(self.path).path
                    if path.startswith('/api/membership/'):
                        self._membership_request(path)
                        return
                    if path in {'/api/desktop/intro-upload','/api/desktop/green-upload'}:
                        media_library = bridge.desktop_green_library if path.endswith('green-upload') else bridge.desktop_intro_library
                        if not self._desktop_origin_allowed():
                            self._send({'ok': False, 'error': 'ปฏิเสธไฟล์จากหน้าเว็บภายนอก'}, 403)
                            return
                        if not media_library:
                            self._send({'ok': False, 'error': 'กรุณาเปิดโปรแกรมรุ่นใหม่เพื่อใช้นำเข้าวิดีโอ'}, 503)
                            return
                        if self.headers.get('Content-Type', '').split(';')[0] != 'application/octet-stream' or self.headers.get('Transfer-Encoding'):
                            raise ValueError('รูปแบบอัปโหลดวิดีโอไม่ถูกต้อง')
                        if not bridge._intro_upload_lock.acquire(blocking=False):
                            self._send({'ok': False, 'error': 'กำลังนำเข้าวิดีโออีกไฟล์ กรุณารอสักครู่'}, 409)
                            return
                        old_timeout = self.connection.gettimeout()
                        try:
                            self.connection.settimeout(30)
                            result = media_library.import_stream(
                                self.rfile, int(self.headers.get('Content-Length', '0')),
                                unquote(self.headers.get('X-File-Name', '')))
                            self._send({'ok': True, **result})
                        finally:
                            self.connection.settimeout(old_timeout)
                            bridge._intro_upload_lock.release()
                        return
                    if self._protected_extension_post(path) and not self._require_extension_request():
                        return
                    size = int(self.headers.get("Content-Length", "0"))
                    if path in {"/api/meta-video/redesign", "/api/ai-covers/event", "/api/ai/result", "/api/jobs/partial-image", "/api/jobs/image-recovery", "/api/stories/result", "/api/stories/partial-image", "/api/presenters/image"}:
                        max_size = 160 * 1024 * 1024
                    elif path in {"/api/desktop/action", "/api/extension/flow-recovery"}:
                        max_size = 20 * 1024 * 1024
                    else:
                        max_size = 2 * 1024 * 1024
                    if size <= 0 or size > max_size: raise ValueError("ขนาดข้อมูลไม่ถูกต้อง")
                    body = json.loads(self.rfile.read(size).decode("utf-8"))
                    callback_claim = bridge._claim_callback_files(path, body)
                    if path == '/api/meta-video/redesign':
                        if body.get('version') != bridge.REQUIRED_EXTENSION_VERSION or not bridge.meta_video:
                            raise ValueError('รุ่น Extension ไม่ตรงหรือ Meta ยังไม่พร้อม')
                        self._send({'ok':True,'receipt':bridge.meta_video.redesign_event(body)})
                    elif path == '/api/meta-video/event':
                        if body.get('version') != bridge.REQUIRED_EXTENSION_VERSION or not bridge.meta_video:
                            raise ValueError('รุ่น Extension ไม่ตรงหรือ Meta ยังไม่พร้อม')
                        self._send({'ok': True, 'receipt': bridge.meta_video.event(body)})
                    elif path == '/api/ai-covers/event':
                        if body.get('version') != bridge.REQUIRED_EXTENSION_VERSION:
                            raise ValueError('รุ่น Extension ไม่ตรงกับโปรแกรม')
                        self._send({'ok': True, 'request': bridge.ai_covers.event(str(body.get('request_id') or ''), body)})
                    elif path == "/api/desktop/action":
                        if not self._desktop_origin_allowed():
                            self._send({"ok": False, "error": "ปฏิเสธคำสั่งจากหน้าเว็บภายนอก"}, 403); return
                        if not bridge.desktop_action:
                            raise RuntimeError("Hybrid engine ยังไม่พร้อม")
                        action = str(body.get("action") or "")[:100]
                        payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
                        from core.membership import guard_action
                        guard_action(bridge, action)
                        result = bridge.desktop_action(action, payload)
                        self._send(result if isinstance(result, dict) else {"ok": True, "result": result})
                    elif path == "/api/presenters/image":
                        if not bridge.presenters: raise ValueError("ยังไม่ได้เปิดคลังตัวละคร")
                        job_id, run_id = str(body.get("job_id") or ""), str(body.get("run_id") or "")
                        with bridge._extension_lock:
                            expected = (bridge._extension_runs.get(("ai", job_id, 0)) or {}).get("run_id")
                        if not run_id or expected != run_id: raise ValueError("ผลตัวละครไม่ตรง Run ปัจจุบัน")
                        if body.get("action") == "claim":
                            bridge.presenters.claim_image(job_id, run_id)
                        elif body.get("action") == "save":
                            bridge.presenters.save_image(job_id, run_id, body.get("image"))
                        else: raise ValueError("คำสั่งตัวละครไม่ถูกต้อง")
                        self._send({"ok": True})
                    elif path == "/api/products/import":
                        target_job_id = str(body.pop("target_job_id", "") or "")
                        target_capture_command_id = str(body.pop("target_capture_command_id", "") or "")
                        job, created = bridge.products.import_product(
                            body,
                            target_job_id=target_job_id,
                            target_capture_command_id=target_capture_command_id,
                        )
                        bridge.logger.info("job_id=%s state=IMPORT_PRODUCT result=%s", job["id"], "created" if created else "duplicate")
                        if bridge.on_import: bridge.on_import(job, created)
                        capture_ready = False
                        verified_count = 0
                        if job.get("story_source_only"):
                            from core.product_source_images import verified_source_image_paths
                            from core.product_pipeline import real_product_data
                            verified = verified_source_image_paths(
                                bridge.products.root / job["id"], job.get("source_images") or []
                            )
                            verified_count = len(verified)
                            capture_ready = bool(real_product_data(job) and verified)
                        self._send({"ok": True, "created": created, "job": job,
                                    "capture_ready": capture_ready,
                                    "verified_source_image_count": verified_count,
                                    "capture_command_id": target_capture_command_id})
                    elif path == "/api/ai/result":
                        self._send(bridge._accept_product_ai_result(body))
                    elif path == "/api/jobs/partial-image":
                        job = bridge.products.save_partial_image(body.get("job_id"), body.get("index"), body.get("image"))
                        bridge.logger.info("job_id=%s state=PRODUCT_IMAGE_CHECKPOINT index=%s result=success", job["id"], int(body.get("index") or 0))
                        self._send({"ok": True, "job_id": job["id"], "image_count": job.get("partial_image_count", 0)})
                    elif path == "/api/jobs/image-recovery":
                        job_id = str(body.get("job_id") or "")
                        recovery = ProductImageRecovery(bridge.products, job_id)
                        payload = recovery.request(body)
                        bridge.logger.info("job_id=%s state=PRODUCT_IMAGE_RECOVERY operation=%s index=%s outcome=%s", job_id,
                                           str(body.get("operation") or "")[:20], body.get("index", 0), str(body.get("outcome") or "")[:30])
                        self._send({"ok": True, **payload})
                    elif path == "/api/stories/scene-gate":
                        from core.scene_pipeline import ScenePipeline
                        with bridge._extension_lock:
                            bridge._validate_story_ai_run_locked(body)
                            from core.meta_scene_sequence import enabled as serial_meta, gate as meta_scene_gate
                            if serial_meta(bridge.stories.get(str(body.get('job_id') or ''))):
                                self._send(meta_scene_gate(bridge, body))
                                return
                            job_id, index = str(body.get('job_id') or ''), body.get('index')
                            job = (bridge.stories.get(job_id) if body.get('action') == 'status'
                                   else bridge.stories.prepare_scene_pipeline(job_id, index))
                            folder = bridge.stories.root / job_id
                            pipeline = ScenePipeline(folder)
                            if body.get('action') == 'prepare':
                                payload = {'ok': True, 'phase': 'prepared'}
                            elif body.get('action') == 'status':
                                row = pipeline.get(index)
                                payload = {'ok': True, **row}
                                handler = getattr(bridge, 'on_story_scene_ready', None)
                                if handler and row.get('phase') in {'requested','video','voice'}:
                                    handler({'job_id':job_id,'index':index,'revision':row['revision'],'run_id':body['run_id']})
                            elif body.get('action') == 'ready':
                                handler = getattr(bridge, 'on_story_scene_ready', None)
                                if not handler:
                                    raise ValueError('โปรแกรมยังไม่รองรับการทำงานรายฉาก')
                                image = folder / job['generated_images'][index-1]
                                from core.scene_video_plan import enabled as planned_video, apply_at_safe_boundary
                                if planned_video(job):
                                    # Claim the next scene before creating its local busy
                                    # marker; an earlier active attempt remains held.
                                    job = apply_at_safe_boundary(bridge.stories, job_id, index)['job']
                                row = pipeline.request(index, int(job['scene_count']), {
                                    'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                                    'narration': job['scene_narrations'][index-1],
                                    'audio_choices': job.get('audio_choices'),
                                    **({'actor_dialogue': True, 'scene_dialogue_turns': job['scene_dialogue_turns'][index-1],
                                        'character_bible': job['character_bible']} if job.get('actor_dialogue') else {}),
                                }, run_id=body['run_id'])
                                payload = {'ok': True, **row}
                                if row['phase'] in {'requested', 'video', 'voice'}:
                                    handler({'job_id': job_id, 'index': index, 'revision': row['revision'], 'run_id': body['run_id']})
                            else:
                                raise ValueError('คำสั่งรายฉากไม่ถูกต้อง')
                        self._send(payload)
                    elif path == "/api/stories/result":
                        if not bridge.stories: raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
                        body = dict(body)
                        body.setdefault("provider", "chatgpt_web_extension")
                        with bridge._extension_lock:
                            bridge._validate_story_ai_run_locked(body)
                            from core.meta_scene_sequence import assert_all_ready
                            assert_all_ready(bridge.stories, bridge.stories.get(str(body.get('job_id') or '')))
                            job = bridge.stories.apply_ai_result(body)
                        bridge.logger.info("job_id=%s state=STORY_AI_RESULT result=success", job["id"])
                        if bridge.on_story_ready: bridge.on_story_ready(job)
                        self._send({"ok": True, "job": job})
                    elif path == "/api/extension/flow-motion-plan":
                        from core.flow_motion_plan import motion_plan_action
                        job_id = str(body.get("job_id") or "")
                        with bridge._extension_lock:
                            expected = bridge._extension_runs.get(("ai", job_id, 0)) or {}
                            if not body.get("run_id") or expected.get("run_id") != body["run_id"]:
                                raise ValueError("FLOW_PLAN_REVIEW • AI run mismatch")
                            if job_id.startswith("STORY-"):
                                job, folder, route = bridge.stories.get(job_id), bridge.stories.root / job_id, "stories"
                            elif job_id.startswith("JOB-"):
                                job, folder, route = bridge.products.get_job(job_id), bridge.products.root / job_id, "jobs"
                            else:
                                raise ValueError("FLOW_PLAN_REVIEW • invalid job")
                            payload = motion_plan_action(folder, job, body)
                            payload["context"]["image_url"] = f"http://127.0.0.1:{bridge.server.server_address[1]}/api/{route}/{job_id}/files/{payload['context']['image_file']}"
                            repair = (payload.get('record') or {}).get('story_visual_repair')
                            if repair and repair.get('image_file'):
                                repair['image_url'] = f"http://127.0.0.1:{bridge.server.server_address[1]}/api/{route}/{job_id}/files/{repair['image_file']}"
                        self._send(payload)
                    elif path == "/api/extension/flow-recovery":
                        from core.story_prompt_recovery import record_recovery
                        job_id = str(body.get('job_id') or '')
                        index = body.get('index')
                        if type(index) is not int or not 1 <= index <= 50:
                            raise ValueError('Flow recovery scene invalid')
                        with bridge._extension_lock:
                            expected = bridge._extension_runs.get(('flow', job_id, index)) or {}
                            if not expected.get('run_id') or expected['run_id'] != body.get('run_id'):
                                raise ValueError('Flow recovery run mismatch')
                            if job_id.startswith('STORY-'):
                                job = bridge.stories.get(job_id)
                                folder = bridge.stories.root / job_id
                            elif job_id.startswith('JOB-'):
                                job = bridge.products.get_job(job_id)
                                folder = bridge.products.root / job_id
                                job = {**job, 'scene_count': len(job.get('generated_images') or [])}
                            else:
                                raise ValueError('Flow recovery job invalid')
                            if body.get('replacement_action'):
                                from core.flow_replacement import replacement_action
                                payload = replacement_action(folder, job, body)
                                row = payload['replacement']
                                if row.get('image_file'):
                                    route = 'stories' if job_id.startswith('STORY-') else 'jobs'
                                    row['image_url'] = f"http://127.0.0.1:{bridge.server.server_address[1]}/api/{route}/{job_id}/files/{row['image_file']}"
                            else:
                                payload = record_recovery(folder, job, body, flow=True)
                        self._send(payload)
                    elif path == "/api/stories/scene-recovery":
                        if not bridge.stories: raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
                        with bridge._extension_lock:
                            bridge._validate_story_ai_run_locked(body)
                            payload = bridge.stories.record_scene_recovery(body)
                        self._send(payload)
                    elif path == "/api/stories/partial-image":
                        if not bridge.stories: raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
                        job = bridge._accept_story_checkpoint(body)
                        bridge.logger.info("job_id=%s state=STORY_IMAGE_CHECKPOINT index=%s result=success", job["id"], int(body.get("index") or 0))
                        self._send({"ok": True, "job_id": job["id"], "image_count": job.get("partial_image_count", 0)})
                    elif path == "/api/stories/image-fallback":
                        payload = bridge._accept_story_image_fallback(body)
                        bridge.logger.info("job_id=%s state=STORY_IMAGE_REFUSAL_FALLBACK index=%s source_index=%s result=checkpointed_local_only",
                                           str(body.get("job_id") or ""), body.get("index"), body.get("source_index"))
                        self._send(payload)
                    elif path == "/api/stories/editorial-sending":
                        with bridge._extension_lock:
                            bridge._validate_story_ai_run_locked(body)
                            state = bridge.stories.mark_editorial_sending(str(body.get('job_id') or ''),
                                body.get('request_id'), body.get('provider'), body.get('conversation_url'))
                        self._send({'ok': True, 'editorial': state})
                    elif path == "/api/stories/analysis-checkpoint":
                        if not bridge.stories: raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
                        job_id = str(body.get("job_id") or "")
                        job = bridge._accept_story_checkpoint(body, analysis=True)
                        bridge.logger.info("job_id=%s state=STORY_ANALYSIS_CHECKPOINT result=success", job["id"])
                        from core.product_editorial import enabled as editorial_enabled, response as editorial_response
                        payload = {"ok": True, "job_id": job["id"], "analysis_status": job.get("analysis_status")}
                        if editorial_enabled(job):
                            payload['editorial'] = editorial_response(job)
                        self._send(payload)
                    elif path == "/api/stories/long-video-plan":
                        if not bridge.stories: raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
                        with bridge._extension_lock:
                            bridge._validate_story_ai_run_locked(body)
                            plan = bridge.stories.save_long_video_plan_step(
                                str(body.get('job_id') or ''), outline=body.get('outline'),
                                chapter=body.get('chapter'), chapter_index=body.get('chapter_index') or 0,
                                pending_request=body.get('pending_request'),
                                clear_pending=body.get('clear_pending') is True)
                        self._send({'ok': True, 'job_id': plan['job_id'],
                                    'chapter_count': len(plan['chapters']),
                                    'outline_saved': plan.get('outline') is not None})
                    elif path == "/api/extension/heartbeat":
                        origin = str(self.headers.get('Origin') or '')
                        expected = {f'127.0.0.1:{bridge.server.server_address[1]}', f'localhost:{bridge.server.server_address[1]}'}
                        # Bootstrap issues only the local session capability. It is
                        # never proof of desktop login and cannot be read by web pages.
                        if (self.headers.get('Host') not in expected
                                or (origin and not bridge._extension_identity.allowed(origin))
                                or (not origin and not self._desktop_origin_allowed())):
                            # Public version diagnostics are not identity proof. Never
                            # issue a capability or register an unpaired old worker.
                            mismatch = str(body.get('version') or '') != bridge.REQUIRED_EXTENSION_VERSION
                            self._send({'ok': False, 'paired': False,
                                'extension_version_required': bridge.REQUIRED_EXTENSION_VERSION,
                                'reload_required': mismatch,
                                'error': ('ต้องอัปเดตไฟล์ Extension เป็น ' + bridge.REQUIRED_EXTENSION_VERSION
                                    + ' แล้วกดโหลดซ้ำที่ตัวเดิม • ยังไม่จับคู่กับโปรแกรม' if mismatch
                                    else 'Extension origin required • ตรวจโฟลเดอร์ Extension แล้วกดโหลดซ้ำที่ตัวเดิม')}, 403); return
                        client_id = str(body.get("client_id") or "")[:200]
                        if not client_id: raise ValueError("client_id ไม่ถูกต้อง")
                        if origin and client_id != origin.removeprefix('chrome-extension://'):
                            self._send({'ok':False,'error':'Extension identity mismatch'},403);return
                        client = {
                            "client_id": client_id,
                            "version": str(body.get("version") or "")[:50],
                            "browser": str(body.get("browser") or "Chrome")[:50],
                            "page": str(body.get("page") or "other")[:50],
                            "last_seen": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "last_seen_epoch": time.time(),
                            "profile_id": str(body.get('profile_id') or '')[:48],
                            "speech_retry_protocol": 1 if body.get('speech_retry_protocol') == 1 else 0,
                            "extension_update_protocol": 1 if body.get('extension_update_protocol') == 1 else 0,
                            "origin": origin,
                        }
                        with bridge._extension_lock:
                            session_key=(origin,client['profile_id'])
                            capability=bridge._extension_sessions.setdefault(session_key,secrets.token_urlsafe(32))
                            previous = bridge._extension_clients.get(client_id) or {}
                            client.update({key: value for key, value in previous.items() if key.startswith("flow_") or key.startswith("ai_")})
                            bridge._extension_clients[client_id] = client
                            reload_request = bridge._extension_reload_requests.pop(client_id, None)
                            if (reload_request and (reload_request["expires_at"] < time.time()
                                    or client["version"] == reload_request["target_version"])):
                                reload_request = None
                        self._send({
                            "ok": True,
                            "connected": True,
                            "extension_version_required": bridge.REQUIRED_EXTENSION_VERSION,
                            "reload_required": client["version"] != bridge.REQUIRED_EXTENSION_VERSION,
                            "extension_token": capability,
                            "extension_reload_request": ({"target_version": reload_request["target_version"],
                                "nonce": reload_request["nonce"]} if reload_request else None),
                        })
                    elif path == "/api/extension/disconnect":
                        client_id = str(body.get("client_id") or "")[:200]
                        with bridge._extension_lock:
                            bridge._extension_clients.pop(client_id, None)
                        self._send({"ok": True, "connected": False})
                    elif path == "/api/extension/command-ack":
                        command_id = str(body.get("command_id") or "")
                        client_id = str(body.get("client_id") or "")[:200]
                        run_id = bridge._normalise_run_id(body.get("run_id"))
                        lease_token = str(body.get("lease_token") or "")[:100]
                        duplicate = False
                        with bridge._extension_lock:
                            command = next((item for item in bridge._extension_commands if item.get("id") == command_id), None)
                            if not command:
                                raise ValueError("ไม่พบคำสั่ง")
                            if command.get("status") in {"completed", "failed"}:
                                duplicate = (
                                    command.get("ack_client_id") == client_id
                                    and command.get("ack_run_id") == run_id
                                    and command.get("ack_lease_token") == lease_token
                                    and command.get("status") == ("completed" if body.get("ok") else "failed")
                                )
                                if not duplicate:
                                    raise ValueError("ACK ซ้ำไม่ตรงกับผลลัพธ์เดิม")
                            else:
                                if command.get("status") != "delivered":
                                    raise ValueError("คำสั่งไม่ได้อยู่ระหว่างรับผล หรือถูกยกเลิกแล้ว")
                                if not client_id or client_id != str(command.get("client_id") or ""):
                                    raise ValueError("Client ID ของ ACK ไม่ตรงกับผู้รับคำสั่ง")
                                if not run_id or run_id != str(command.get("run_id") or ""):
                                    raise ValueError("Run ID ของ ACK ไม่ตรงกับคำสั่ง")
                                if not lease_token or lease_token != str(command.get("lease_token") or ""):
                                    raise ValueError("Lease token ของ ACK ไม่ตรงกับคำสั่ง")
                                if float(command.get("lease_expires_at") or 0) < time.time():
                                    raise ValueError("Lease ของคำสั่งหมดอายุแล้ว")
                                command["status"] = "completed" if body.get("ok") else "failed"
                                if command.get("action") == "read_flow_settings" and body.get("ok"):
                                    from core.flow_settings import flow_capabilities
                                    command["flow_capabilities"] = flow_capabilities(body.get("flow_capabilities"))
                                command["error"] = str(body.get("error") or "")[:1000]
                                command["completed_at"] = time.time()
                                command["ack_client_id"] = client_id
                                command["ack_run_id"] = run_id
                                command["ack_lease_token"] = lease_token
                                if body.get("ok") and command.get("action") == "close_automation_browser":
                                    closed_job_id = str(command.get("job_id") or "")
                                    closed_shot = int(command.get('cleanup_shot_index') or 0)
                                    cleanup_runs = set(command.get("cleanup_runs") or [run_id])
                                    for run_key in tuple(bridge._extension_runs):
                                        if (run_key[1] == closed_job_id
                                                and (not closed_shot or run_key == ('flow', closed_job_id, closed_shot))
                                                and bridge._extension_runs[run_key].get("run_id") in cleanup_runs):
                                            bridge._extension_runs.pop(run_key, None)
                                    for extension_client in bridge._extension_clients.values():
                                        if (str(extension_client.get("flow_job_id") or "") == closed_job_id
                                                and (not closed_shot or int(extension_client.get('flow_shot_index') or 0) == closed_shot)
                                                and extension_client.get("flow_run_id") in cleanup_runs):
                                            for key in tuple(extension_client):
                                                if key.startswith("flow_"):
                                                    extension_client.pop(key, None)
                                        if (not closed_shot and str(extension_client.get("ai_job_id") or "") == closed_job_id
                                                and extension_client.get("ai_run_id") in cleanup_runs):
                                            for key in tuple(extension_client):
                                                if key.startswith("ai_"):
                                                    extension_client.pop(key, None)
                        if not duplicate:
                            bridge.logger.info(
                                "state=EXT_COMMAND action=%s command_id=%s run_id=%s result=%s error=%s",
                                command.get("action"), command_id, command.get("run_id"),
                                command.get("status"), command.get("error") or "-",
                            )
                        self._send({"ok": True, "duplicate": duplicate})
                    elif path == "/api/extension/progress":
                        client_id = str(body.get("client_id") or "")[:200]
                        if not client_id: raise ValueError("client_id ไม่ถูกต้อง")
                        incoming_run_id = bridge._normalise_run_id(body.get("run_id"))
                        sender_tab_id = max(0, int(body.get("tab_id") or 0))
                        scope = str(body.get("scope") or "").lower()
                        if scope == 'observation':
                            # Side-channel only. Never dispatch pipeline callbacks from helper/cover status.
                            from core.automation_observation import attach_observation
                            channel=str(body.get('channel') or '')
                            if channel not in {'repair','cover'}:
                                raise ValueError('Unknown observation channel')
                            with bridge._extension_lock:
                                client=bridge._extension_clients.get(client_id)
                                if not client or client.get('version') != bridge.REQUIRED_EXTENSION_VERSION:
                                    raise ValueError('Extension version/heartbeat mismatch')
                                rows=client.setdefault('aux_observations', {})
                                old=rows.get(channel) or {}
                                p={'ai_job_id':str(body.get('job_id') or '')[:100], 'ai_run_id':incoming_run_id,
                                   'ai_tab_id':sender_tab_id, 'ai_step':str(body.get('step') or '')[:100]}
                                ok=attach_observation({'ai_observation':old},p,body,'ai')
                                if ok:
                                    p['ai_observation']['acknowledged'] = True
                                    rows[channel]={**p['ai_observation'],'job_id':p['ai_job_id'],
                                        'provider':str(body.get('provider') or 'AI Web')[:50], 'channel':channel,
                                        'message':str(body.get('message') or '')[:500]}
                            self._send({'ok':True,'ignored':not ok})
                            return
                        if scope == "trace":
                            with bridge._extension_lock:
                                trace_client = bridge._extension_clients.get(client_id)
                                if not trace_client:
                                    raise ValueError("Extension heartbeat missing")
                                trace_version = str(trace_client.get("version") or "")
                            if trace_version != bridge.REQUIRED_EXTENSION_VERSION:
                                self._send({
                                    "ok": True, "ignored": True, "reason": "version_mismatch",
                                    "extension_version_required": bridge.REQUIRED_EXTENSION_VERSION,
                                })
                                return
                            trace_item = bridge._record_extension_trace({
                                "client_id": client_id,
                                "version": trace_version,
                                "service": str(body.get("service") or "extension"),
                                "job_id": str(body.get("job_id") or ""),
                                "shot_index": int(body.get("shot_index") or 0),
                                "run_id": incoming_run_id,
                                "action": str(body.get("action") or body.get("step") or "progress"),
                                "message": str(body.get("message") or ""),
                                "level": str(body.get("level") or "info"),
                                "tab_id": sender_tab_id,
                                "page_url": str(body.get("page_url") or ""),
                                "detail": body.get("detail"),
                            })
                            self._send({"ok": True, "trace": trace_item})
                            return
                        progress = {
                            "flow_step": str(body.get("step") or "")[:100],
                            "flow_job_id": str(body.get("job_id") or "")[:100],
                            "flow_shot_index": int(body.get("shot_index") or 0),
                            "flow_run_id": incoming_run_id,
                            "flow_inspection_command_id": str(body.get("inspection_command_id") or "")[:100],
                            "flow_tab_id": sender_tab_id,
                            "flow_message": str(body.get("message") or "")[:1000],
                            "flow_image_ready": bool(body.get("image_ready")),
                            "flow_prompt_ready": bool(body.get("prompt_ready")),
                            "flow_has_rights_dialog": bool(body.get("has_rights_dialog")),
                            "flow_confirmation_kind": str(body.get("confirmation_kind") or "")[:50],
                            "flow_page_url": str(body.get("page_url") or "")[:1000],
                            "flow_repair_request_id": str(body.get("repair_request_id") or "")[:100],
                            "flow_repair_handoff": body.get("repair_handoff") is True,
                            "flow_continuous_wait": body.get("continuous_wait") is True,
                            "flow_button_labels": [str(item)[:100] for item in (body.get("button_labels") or [])[:30]],
                            "flow_page_excerpt": str(body.get("page_excerpt") or "")[:3000],
                            "flow_download_path": str(body.get("download_path") or "")[:1000],
                            "flow_failure_code": str(body.get("failure_code") or "")[:100],
                            "flow_policy_failure_category": str(body.get("policy_failure_category") or "")[:100],
                            "flow_failure_card_fingerprint": str(body.get("failure_card_fingerprint") or "")[:160],
                            "flow_failure_reason": bridge.flow_failure_reason(body.get("failure_reason"))
                                if body.get("failure_code") == "FLOW_POLICY_BLOCKED" else "",
                            "flow_attachment_failure_evidence": bridge.validate_flow_attachment_failure(body),
                            "flow_action_kind": str(body.get("action_kind") or "")[:50],
                            "flow_service": str(body.get("service") or "")[:50],
                            "flow_resume_action": str(body.get("resume_action") or "")[:100],
                            "flow_updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        }
                        if scope == "chatgpt":
                            progress = {
                                "ai_step": str(body.get("step") or "")[:100],
                                "ai_job_id": str(body.get("job_id") or "")[:100],
                                "ai_run_id": incoming_run_id,
                                "ai_tab_id": sender_tab_id,
                                "ai_message": str(body.get("message") or "")[:10000],
                                "ai_image_count": max(0, min(50, int(body.get("image_count") or 0))),
                                "ai_provider": str(body.get("provider") or "")[:50],
                                "ai_action_kind": str(body.get("action_kind") or "")[:50],
                                "ai_service": str(body.get("service") or "")[:50],
                                "ai_resume_action": str(body.get("resume_action") or "")[:100],
                                "ai_page_url": str(body.get("page_url") or "")[:1000],
                                "ai_page_excerpt": str(body.get("page_excerpt") or "")[:3000],
                                "ai_send_diagnostics": bridge._safe_ai_send_diagnostics(body),
                                "ai_image_observation": bridge._safe_ai_image_observation(body),
                                "ai_response_active": body.get("response_active") is True,
                                "ai_response_signature": str(body.get("response_signature") or "")[:64],
                                "ai_updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            }
                        elif scope == "chatgpt_inspect":
                            progress = {
                                "ai_inspect_message": str(body.get("message") or "")[:10000],
                                "ai_inspected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            }
                        flow_transition = None
                        ai_transition = None
                        ignored_reason = ""
                        with bridge._extension_lock:
                            client = bridge._extension_clients.get(client_id)
                            if not client:
                                raise ValueError("Extension heartbeat missing")
                            if str(client.get("version") or "") != bridge.REQUIRED_EXTENSION_VERSION:
                                ignored_reason = "version_mismatch"
                            elif scope == "chatgpt":
                                incoming_job = str(progress.get("ai_job_id") or "")
                                expected_run = str((bridge._extension_runs.get(("ai", incoming_job, 0)) or {}).get("run_id") or "")
                                if expected_run and incoming_run_id and incoming_run_id != expected_run:
                                    ignored_reason = "stale_ai_run"
                                else:
                                    if expected_run and not incoming_run_id:
                                        progress["ai_run_id"] = expected_run
                                    # A recovery/helper report may omit the count (older
                                    # clients send zero). Completed images cannot disappear
                                    # within the same job/run just because its browser phase
                                    # changed from image generation to response recovery.
                                    if (progress.get("ai_run_id")
                                            and incoming_job == str(client.get("ai_job_id") or "")
                                            and str(progress.get("ai_run_id") or "") == str(client.get("ai_run_id") or "")):
                                        progress["ai_image_count"] = max(
                                            int(progress.get("ai_image_count") or 0),
                                            int(client.get("ai_image_count") or 0),
                                        )
                                    from core.automation_observation import attach_observation
                                    if not attach_observation(client, progress, body, 'ai'):
                                        self._send({'ok': True, 'ignored': True, 'reason': 'stale_observation'})
                                        return
                                    previous_signature = (
                                        str(client.get("ai_job_id") or ""),
                                        str(client.get("ai_step") or ""),
                                        str(client.get("ai_message") or ""),
                                        int(client.get("ai_image_count") or 0),
                                        client.get("ai_send_diagnostics") or {},
                                        client.get("ai_image_observation") or {},
                                    )
                                    next_signature = (
                                        str(progress.get("ai_job_id") or ""),
                                        str(progress.get("ai_step") or ""),
                                        str(progress.get("ai_message") or ""),
                                        int(progress.get("ai_image_count") or 0),
                                        progress.get("ai_send_diagnostics") or {},
                                        progress.get("ai_image_observation") or {},
                                    )
                                    if (next_signature != previous_signature or progress.get("ai_step") == "image_prompt_ready"
                                            or (client.get('ai_observation') or {}).get('acknowledged') is False):
                                        ai_transition = dict(progress)
                                    client.update(progress)
                            elif scope == "chatgpt_inspect":
                                client.update(progress)
                            else:
                                incoming_job = str(progress.get("flow_job_id") or "")
                                incoming_shot = int(progress.get("flow_shot_index") or 0)
                                expected_run = str((bridge._extension_runs.get(("flow", incoming_job, incoming_shot)) or {}).get("run_id") or "")
                                if expected_run and incoming_run_id and incoming_run_id != expected_run:
                                    ignored_reason = "stale_flow_run"
                                else:
                                    if expected_run and not incoming_run_id:
                                        progress["flow_run_id"] = expected_run
                                    progress.update(bridge._validated_scene_video_flow_progress(body))
                                    from core.automation_observation import attach_observation
                                    if not attach_observation(client, progress, body, 'flow'):
                                        self._send({'ok': True, 'ignored': True, 'reason': 'stale_observation'})
                                        return
                                    incoming_step = str(progress.get("flow_step") or "")
                                    previous_job = str(client.get("flow_job_id") or "")
                                    previous_shot = int(client.get("flow_shot_index") or 0)
                                    previous_step = str(client.get("flow_step") or "")
                                    passive_steps = {"package_loaded", "package_ready"}
                                    preserve_previous = bool(
                                        incoming_job and incoming_job == previous_job and (
                                            # The landing helper reports shot 0 while the real
                                            # project tab reports a numbered shot. Never let the
                                            # auxiliary tab hide live progress.
                                            (incoming_shot == 0 and previous_shot > 0)
                                            or (
                                                incoming_shot == previous_shot
                                                and previous_step in {"generation_complete", "attachment_failed"}
                                                and incoming_step in passive_steps
                                                and (previous_step != "attachment_failed"
                                                     or str(client.get("flow_run_id") or "") == str(progress.get("flow_run_id") or ""))
                                            )
                                        )
                                    )
                                    if preserve_previous:
                                        progress = {
                                            key: value for key, value in client.items()
                                            if key.startswith("flow_")
                                        }
                                    previous_signature = (
                                        str(client.get("flow_job_id") or ""),
                                        int(client.get("flow_shot_index") or 0),
                                        str(client.get("flow_step") or ""),
                                        str(client.get("flow_message") or ""),
                                        str(client.get("flow_failure_card_fingerprint") or ""),
                                        str(client.get("flow_failure_reason") or ""),
                                    )
                                    next_signature = (
                                        str(progress.get("flow_job_id") or ""),
                                        int(progress.get("flow_shot_index") or 0),
                                        str(progress.get("flow_step") or ""),
                                        str(progress.get("flow_message") or ""),
                                        str(progress.get("flow_failure_card_fingerprint") or ""),
                                        str(progress.get("flow_failure_reason") or ""),
                                    )
                                    if (next_signature != previous_signature
                                            or (client.get('flow_observation') or {}).get('acknowledged') is False):
                                        flow_transition = dict(progress)
                                    client.update(progress)
                        if ignored_reason:
                            self._send({
                                "ok": True, "ignored": True, "reason": ignored_reason,
                                "extension_version_required": bridge.REQUIRED_EXTENSION_VERSION,
                            })
                            return
                        if flow_transition:
                            bridge.logger.info(
                                "job_id=%s state=FLOW_EXTENSION shot=%s step=%s image=%s prompt=%s message=%s",
                                flow_transition.get("flow_job_id") or "-",
                                flow_transition.get("flow_shot_index") or 0,
                                flow_transition.get("flow_step") or "-",
                                int(bool(flow_transition.get("flow_image_ready"))),
                                int(bool(flow_transition.get("flow_prompt_ready"))),
                                str(flow_transition.get("flow_message") or "-").replace("\n", " ")[:500],
                            )
                            bridge._append_flow_diagnostic(flow_transition)
                            bridge._record_extension_trace({
                                "client_id": client_id,
                                "version": bridge.REQUIRED_EXTENSION_VERSION,
                                "service": "flow",
                                "job_id": flow_transition.get("flow_job_id"),
                                "shot_index": flow_transition.get("flow_shot_index"),
                                "run_id": flow_transition.get("flow_run_id"),
                                "action": flow_transition.get("flow_step"),
                                "message": flow_transition.get("flow_message"),
                                "level": "error" if flow_transition.get("flow_step") == "error" else "info",
                                "tab_id": flow_transition.get("flow_tab_id"),
                                "page_url": flow_transition.get("flow_page_url"),
                            })
                        if ai_transition:
                            story_image_detail = None
                            if ai_transition.get("ai_step") == "image_prompt_ready":
                                if not bridge.stories:
                                    raise ValueError("ยังไม่ได้เปิดโหมดเรื่องเล่า")
                                story_job = bridge.stories.get(ai_transition.get("ai_job_id"))
                                scene_count = story_job.get("scene_count")
                                upper = 50 if story_job.get("long_video") else 15
                                if type(scene_count) is not int or not 1 <= scene_count <= upper:
                                    raise ValueError("Story image request scene count invalid")
                                story_image_detail = bridge._safe_story_image_request(body, scene_count=scene_count)
                            bridge._record_extension_trace({
                                "client_id": client_id,
                                "version": bridge.REQUIRED_EXTENSION_VERSION,
                                "service": ai_transition.get("ai_provider") or "ai_web",
                                "job_id": ai_transition.get("ai_job_id"),
                                "run_id": ai_transition.get("ai_run_id"),
                                "action": ai_transition.get("ai_step"),
                                "message": ai_transition.get("ai_message"),
                                "level": "error" if ai_transition.get("ai_step") == "error" else "info",
                                "tab_id": ai_transition.get("ai_tab_id"),
                                "page_url": ai_transition.get("ai_page_url"),
                                "detail": story_image_detail if story_image_detail is not None
                                    else ai_transition.get("ai_image_observation")
                                    or ai_transition.get("ai_send_diagnostics") or None,
                            })
                        # A failed durable trace must not turn the outbox retry into
                        # a successful duplicate ACK. Commit only after trace writes.
                        prefix = 'ai' if scope == 'chatgpt' else 'flow'
                        observation = progress.get(prefix + '_observation')
                        if observation:
                            with bridge._extension_lock:
                                current = (bridge._extension_clients.get(client_id) or {}).get(prefix + '_observation')
                                if current is observation:
                                    current['acknowledged'] = True
                        self._send({"ok": True, "progress": progress})
                    elif path == "/api/extension/queue":
                        command = bridge.queue_extension_command(
                            str(body.get("action") or ""),
                            str(body.get("job_id") or ""),
                            int(body.get("shot_index") or 0),
                            provider_hint=str(body.get("provider") or ""),
                            run_id=str(body.get("run_id") or ""),
                        )
                        self._send({"ok": True, "command": command})
                    else:
                        self._send({"ok": False, "error": "not_found"}, 404)
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    # Browser polling may be cancelled during navigation or
                    # app shutdown. It is not an import/pipeline failure and
                    # must not flood the recovery log with a false traceback.
                    return
                except ValueError as exc:
                    if path == '/api/extension/progress' and getattr(exc, 'code', '') == 'PRODUCT_JOB_DELETED':
                        # A status-only late report is terminally ignored. The
                        # existing Extension outbox can ACK it and stop retrying;
                        # image/media save routes still fail, never fake success.
                        self._send({'ok': True, 'ignored': True, 'reason': 'job_permanently_deleted'})
                        return
                    # Invalid client data is an expected HTTP 400 response, not
                    # an application crash. Keep one concise audit line without
                    # burying real server failures under validation tracebacks.
                    bridge.logger.warning(
                        "state=BRIDGE_REQUEST path=%s result=rejected error=%s", path, exc
                    )
                    self._send({"ok": False, "error": str(exc)}, 400)
                except Exception as exc:
                    bridge.logger.exception("state=BRIDGE_REQUEST path=%s result=error error=%s", path, exc)
                    self._send({"ok": False, "error": str(exc)}, 500)
                finally:
                    if callback_claim is not None:
                        callback_claim.release()
            def _membership_request(self, path):
                from core.membership import MembershipError
                # Extension licensing was removed in391. Never accept a Token
                # or consult desktop/cloud membership on a browser request.
                if path.startswith('/api/membership/extension/'):
                    self._send({'ok': False, 'code': 'EXTENSION_MEMBERSHIP_REMOVED'}, 410); return
                # This broker owns all server credentials; pages never receive
                # activation/renewal/session secrets. DNS rebinding is rejected.
                expected = {f'127.0.0.1:{bridge.server.server_address[1]}', f'localhost:{bridge.server.server_address[1]}'}
                if self.headers.get('Host') not in expected or not bridge.membership:
                    self._send({'ok': False}, 403); return
                if not self._desktop_origin_allowed():
                    self._send({'ok': False}, 403); return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 2048:
                        raise MembershipError('INVALID_REQUEST')
                    data = json.loads(self.rfile.read(size))
                    if not isinstance(data, dict):
                        raise MembershipError('INVALID_REQUEST')
                    if path == '/api/membership/desktop/login':
                        result = bridge.membership.login(data.get('token'), 'desktop', '', str(data.get('version') or ''))
                    elif path == '/api/membership/desktop/logout':
                        result = bridge.membership.logout('desktop')
                    else:
                        self._send({'ok': False}, 404); return
                    self._send(result)
                except MembershipError as error:
                    self._send({'ok': False, 'code': error.code, 'error': str(error)}, 403)
                except Exception:
                    self._send({'ok': False, 'code': 'INVALID_REQUEST', 'error': 'ตรวจสิทธิ์ไม่สำเร็จ กรุณาลองใหม่'}, 400)

            def log_message(self, format, *args): return
        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, name="local-bridge", daemon=True).start()
        return self

    def stop(self):
        if self.server: self.server.shutdown(); self.server.server_close(); self.server = None
