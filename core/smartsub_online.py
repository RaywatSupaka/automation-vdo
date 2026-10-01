import json
import mimetypes
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

from core.cancellable_process import check_cancelled, hidden_process_kwargs, run_cancellable
from core.video_logo import locate_ffmpeg


class SmartSubOnlineError(RuntimeError):
    pass


class SmartSubOnlineClient:
    """Dependency-free client for SmartSub Online device and subtitle jobs."""

    ALLOWED_HOST = "www.catfufu.com"
    SOURCE_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".mp4", ".webm", ".mov"}
    TERMINAL_STATUSES = {"done", "error", "cancelled", "canceled"}

    def __init__(self, device_credential="", base_url="https://www.catfufu.com/api/smartsub-online/v2", timeout=60, allow_localhost=False):
        parsed = urlparse(str(base_url or "").rstrip("/"))
        is_local_test = allow_localhost and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
        if not is_local_test and (parsed.scheme != "https" or parsed.hostname != self.ALLOWED_HOST):
            raise ValueError("Subtitle API ต้องเชื่อมต่อผ่าน https://www.catfufu.com เท่านั้น")
        if not parsed.path.rstrip("/").endswith("/api/smartsub-online/v2"):
            raise ValueError("Subtitle API base URL ไม่ถูกต้อง")
        self.base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
        self._device_credential = str(device_credential or "").strip()
        self.timeout = max(5, int(timeout))

    def __repr__(self):
        return f"SmartSubOnlineClient(base_url={self.base_url!r}, device_credential='***')"

    def redeem(self, client_id, token):
        client_id = self._safe_client_id(client_id)
        token = str(token or "").strip()
        if not token:
            raise ValueError("กรุณาใส่ Token สำหรับเชื่อมต่อ Subtitle")
        result = self._json_request(
            "POST",
            "/devices/redeem",
            json.dumps({"clientId": client_id, "token": token}, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "SmartPost-AI/0.5"},
        )
        credential = str(result.get("deviceCredential") or result.get("device_credential") or "").strip()
        if not credential:
            raise SmartSubOnlineError("เชื่อมต่อสำเร็จแต่ระบบไม่ส่งรหัสอุปกรณ์กลับมา")
        self._device_credential = credential
        return result, credential

    def create_job(self, audio_path, language="th", idempotency_key=None):
        self._require_credential()
        source = Path(audio_path)
        if not source.is_file() or source.suffix.lower() != ".wav":
            raise ValueError("Subtitle API รับเฉพาะ WAV กรุณาเตรียมไฟล์ด้วย prepare_wav ก่อน")
        if source.stat().st_size <= 0:
            raise ValueError("ไฟล์เสียงว่างเปล่า")
        if source.stat().st_size > 1024 * 1024 * 1024:
            raise ValueError("ไฟล์เสียงมีขนาดเกิน 1 GB")
        language = str(language or "th").strip().lower()
        if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})?", language):
            raise ValueError("รหัสภาษา Subtitle ไม่ถูกต้อง")
        key = str(idempotency_key or uuid.uuid4())
        result = self._multipart("/jobs", {"language": language}, {"audio": source}, key)
        job_id = str(result.get("jobId") or result.get("job_id") or "").strip()
        if not job_id:
            raise SmartSubOnlineError("ระบบไม่ส่ง jobId กลับมา")
        return result

    @classmethod
    def prepare_wav(cls, source_path, target_path, ffmpeg_path="", cancel_event=None):
        source, target = Path(source_path), Path(target_path)
        if not source.is_file() or source.suffix.lower() not in cls.SOURCE_AUDIO_EXTENSIONS:
            raise ValueError("ไม่พบไฟล์เสียงต้นฉบับที่รองรับ")
        if source.stat().st_size <= 0:
            raise ValueError("ไฟล์เสียงต้นฉบับว่างเปล่า")
        ffmpeg = locate_ffmpeg(ffmpeg_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.stem}.{uuid.uuid4().hex}.tmp.wav")
        command = [str(ffmpeg), "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(temporary)]
        try:
            result = run_cancellable(command, cancel_event=cancel_event, timeout=900)
            if result.returncode or not temporary.is_file() or temporary.stat().st_size <= 44:
                raise SmartSubOnlineError("แปลงเสียงเป็น WAV ไม่สำเร็จ: " + result.stderr.strip()[-700:])
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def get_job(self, job_id):
        self._require_credential()
        job_id = self._safe_id(job_id, "jobId")
        return self._json_request("GET", f"/jobs/{quote(job_id)}", headers=self._auth_headers())

    def get_status(self):
        """Return normalized subtitle credit status for the connected device."""
        self._require_credential()
        result = self._json_request("GET", "/status", headers=self._auth_headers(), timeout=30)

        def as_non_negative_int(key, default=0):
            try:
                return max(0, int(result.get(key, default) or 0))
            except (TypeError, ValueError):
                raise SmartSubOnlineError(f"Subtitle API ส่งค่า {key} ไม่ถูกต้อง") from None

        return {
            "connected": bool(result.get("ok", True)),
            "credits": as_non_negative_int("creditBalance"),
            "trial_remaining": as_non_negative_int("trialRemaining"),
            "job_credit_cost": as_non_negative_int("jobCreditCost", 1),
            "credit_unit_seconds": as_non_negative_int("creditUnitSeconds"),
            "expires_at": str(result.get("creditExpiresAt") or ""),
            "requires_token": bool(result.get("requiresToken", False)),
        }

    def wait_until_done(self, job_id, timeout=1800, poll_interval=2, on_status=None, cancel_event=None):
        deadline = time.monotonic() + max(1, float(timeout))
        last_status = ""
        while time.monotonic() < deadline:
            check_cancelled(cancel_event)
            result = self.get_job(job_id)
            status = str(result.get("status") or result.get("state") or "").strip().lower()
            if on_status and status != last_status:
                on_status(status or "processing", result)
            last_status = status
            if status == "done":
                return result
            if status in {"error", "cancelled", "canceled", "failed"}:
                detail = result.get("error") or result.get("message") or status
                raise SmartSubOnlineError(f"สร้างคำบรรยายไม่สำเร็จ: {detail}")
            wait_seconds = max(0.2, float(poll_interval))
            if cancel_event is not None:
                if cancel_event.wait(wait_seconds):
                    check_cancelled(cancel_event)
            else:
                time.sleep(wait_seconds)
        raise SmartSubOnlineError("หมดเวลารอ Subtitle กรุณาตรวจสถานะงานอีกครั้ง")

    @staticmethod
    def extract_artifacts(result):
        """Return normalized transcript/SRT/VTT when the API embeds them in a job response."""
        containers = [result]
        for key in ("result", "output", "data"):
            value = result.get(key)
            if isinstance(value, dict):
                containers.append(value)
        found = {"transcript": "", "srt": "", "vtt": ""}
        aliases = {
            "transcript": ("transcript", "text", "transcription"),
            "srt": ("srt", "srtText", "srt_text", "subtitleSrt"),
            "vtt": ("vtt", "vttText", "vtt_text", "subtitleVtt"),
        }
        for container in containers:
            for target, keys in aliases.items():
                if found[target]:
                    continue
                for key in keys:
                    value = container.get(key)
                    if isinstance(value, str) and value.strip():
                        found[target] = value.strip()
                        break
        segments = next((item.get("segments") for item in containers if isinstance(item.get("segments"), list)), None)
        if not found["transcript"] and segments:
            found["transcript"] = "\n".join(str(item.get("text") or "").strip() for item in segments if isinstance(item, dict) and str(item.get("text") or "").strip())
        found["segments"] = segments or []
        return found

    def _multipart(self, path, fields, files, idempotency_key):
        boundary = f"----SmartPostSubtitle{uuid.uuid4().hex}"
        body = bytearray()
        for name, value in fields.items():
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))
        for name, file_path in files.items():
            source = Path(file_path)
            content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            safe_name = source.name.replace('"', "")
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{safe_name}"\r\nContent-Type: {content_type}\r\n\r\n'.encode("utf-8"))
            body.extend(source.read_bytes())
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("ascii"))
        headers = self._auth_headers()
        headers.update({"Content-Type": f"multipart/form-data; boundary={boundary}", "Idempotency-Key": str(idempotency_key)})
        return self._json_request("POST", path, bytes(body), headers, timeout=max(self.timeout, 300))

    def _json_request(self, method, path, body=None, headers=None, timeout=None):
        request = urllib.request.Request(f"{self.base_url}{path}", data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(request, timeout=max(5, int(timeout or self.timeout))) as response:
                raw = response.read(8 * 1024 * 1024)
            result = json.loads(raw.decode("utf-8"))
            if not isinstance(result, dict):
                raise SmartSubOnlineError("รูปแบบคำตอบจาก Subtitle API ไม่ถูกต้อง")
            return result
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from None
        except urllib.error.URLError as exc:
            raise SmartSubOnlineError(f"เชื่อมต่อ Subtitle API ไม่สำเร็จ: {exc.reason}") from None
        except json.JSONDecodeError:
            raise SmartSubOnlineError("Subtitle API ส่งข้อมูลที่อ่านไม่ได้") from None

    def _auth_headers(self):
        self._require_credential()
        return {"Authorization": f"Bearer {self._device_credential}", "Accept": "application/json", "User-Agent": "SmartPost-AI/0.5"}

    def _require_credential(self):
        if not self._device_credential:
            raise ValueError("ยังไม่ได้เชื่อมต่อ Subtitle Token กับเครื่องนี้")

    @staticmethod
    def _safe_client_id(value):
        value = str(value or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{3,120}", value):
            raise ValueError("clientId ไม่ถูกต้อง")
        return value

    @staticmethod
    def _safe_id(value, label):
        value = str(value or "").strip()
        if not value or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,240}", value):
            raise ValueError(f"{label} ไม่ถูกต้อง")
        return value

    @staticmethod
    def _http_error(exc):
        try:
            payload = json.loads(exc.read(256 * 1024).decode("utf-8", errors="replace"))
            detail = payload.get("detail") or payload.get("error") or payload.get("message")
            if isinstance(detail, dict):
                detail = detail.get("message") or json.dumps(detail, ensure_ascii=False)
        except Exception:
            detail = None
        if exc.code in {401, 403}:
            detail = "รหัสอุปกรณ์ไม่ถูกต้อง หมดอายุ หรือไม่มีสิทธิ์ใช้งาน"
        elif exc.code == 409:
            detail = detail or "Token นี้ถูกแลกแล้ว หรือคำขอซ้ำ"
        elif exc.code == 402:
            detail = "เครดิต Subtitle ไม่เพียงพอ"
        elif exc.code == 429:
            detail = "เรียก Subtitle API ถี่เกินไป กรุณารอสักครู่"
        return SmartSubOnlineError(f"Subtitle API HTTP {exc.code}: {detail or exc.reason}")
