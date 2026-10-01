import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

from core.cancellable_process import check_cancelled


# Audio-quality invariant for every SmartFlow clip.  Keeping this at the API
# boundary prevents stale UI/config/job values from reintroducing distorted
# emotion or speed settings in Product, Story, or Drama pipelines.
CLIP_VOICE_EMOTION = "normal"
CLIP_VOICE_SPEED = 1.0
MAX_TTS_REQUEST_CHARS = 2000


class ExternalTtsError(RuntimeError):
    def __init__(self, message, *, retryable=False, payload=None):
        super().__init__(message)
        self.retryable = bool(retryable)
        self.payload = dict(payload or {})


def _origin(url):
    parsed = urlparse(url)
    if parsed.username or parsed.password:
        raise ValueError("credentials in URL")
    return parsed.scheme, parsed.hostname, parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)


class _TtsRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward credentials across origins or replay a paid POST."""
    def __init__(self, origin):
        self.origin = origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            allowed = _origin(newurl) == self.origin and req.get_method() in {"GET", "HEAD"}
        except ValueError:
            allowed = False
        if not allowed:
            raise ExternalTtsError("AI Voice ส่งต่อคำขอไปปลายทางที่ไม่อนุญาต • ไม่ส่ง Key หรือสร้างเสียงซ้ำ")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ExternalTtsClient:
    """Small, dependency-free client for the catfufu external TTS API."""

    ALLOWED_HOST = "www.catfufu.com"
    AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac", ".mp4"}
    OUTPUT_FORMATS = {"wav", "mp3", "mp4"}

    def __init__(self, api_key, base_url="https://www.catfufu.com", timeout=60, allow_localhost=False):
        self._api_key = str(api_key or "").strip()
        if not self._api_key:
            raise ValueError("กรุณาใส่ API Key ของ AI Voice")
        parsed = urlparse(str(base_url or "").rstrip("/"))
        is_local_test = allow_localhost and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
        origin = _origin(str(base_url))
        if parsed.username or parsed.password or (not is_local_test and origin != ("https", self.ALLOWED_HOST, 443)):
            raise ValueError("AI Voice API ต้องเชื่อมต่อผ่าน https://www.catfufu.com เท่านั้น")
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        self.timeout = max(5, int(timeout))
        self._opener = urllib.request.build_opener(_TtsRedirectHandler(origin))

    def __repr__(self):
        return f"ExternalTtsClient(base_url={self.base_url!r}, api_key='***')"

    def upload_reference(self, file_path):
        source = Path(file_path)
        if not source.is_file() or source.suffix.lower() not in self.AUDIO_EXTENSIONS:
            raise ValueError("กรุณาเลือกไฟล์เสียงอ้างอิงที่รองรับ")
        if source.stat().st_size > 100 * 1024 * 1024:
            raise ValueError("ไฟล์เสียงอ้างอิงมีขนาดเกิน 100 MB")
        upload_timeout = 300 if source.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mpeg", ".mpg"} else 120
        result = self._multipart("/api/tts/external/upload-reference", {}, {"file": source}, timeout=upload_timeout)
        reference_id = str(result.get("reference_id") or "").strip()
        if not reference_id:
            raise ExternalTtsError("ระบบไม่ส่ง reference_id กลับมา")
        return result

    def list_voices(self):
        """Return preset voices plus custom voices owned by this API key."""
        result = self._json_request("GET", "/api/tts/external/voices", timeout=30)
        raw_voices = result.get("voices")
        if not isinstance(raw_voices, list):
            raise ExternalTtsError("ระบบไม่ส่งรายการเสียงกลับมา")
        voices = []
        for item in raw_voices:
            if not isinstance(item, dict):
                continue
            reference_id = str(item.get("reference_id") or "").strip()
            if not reference_id or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", reference_id):
                continue
            source = str(item.get("source") or "preset").strip().lower()
            if source not in {"preset", "custom"}:
                source = "custom" if bool(item.get("custom")) else "preset"
            emotions = [
                str(value).strip().lower()
                for value in (item.get("allowed_emotions") or ["normal"])
                if str(value).strip()
            ]
            voices.append({
                "id": str(item.get("id") or reference_id).strip(),
                "reference_id": reference_id,
                "source": source,
                "custom": source == "custom",
                "name": str(item.get("name") or reference_id).strip(),
                "description": str(item.get("description") or "").strip(),
                "note": str(item.get("note") or "").strip(),
                "tags": [str(value) for value in (item.get("tags") or []) if str(value).strip()],
                "allowed_emotions": emotions or ["normal"],
                "normal_only": bool(item.get("normal_only")),
                "duration_sec": item.get("duration_sec"),
            })
        return {
            "voices": voices,
            "count": len(voices),
            "preset_count": sum(item["source"] == "preset" for item in voices),
            "custom_count": sum(item["source"] == "custom" for item in voices),
        }

    def get_status(self):
        """Return account connection and remaining credit without exposing the API key."""
        result = self._json_request("GET", "/api/tts/external/status", timeout=30)
        raw_credits = result.get("creditsRemaining")
        try:
            credits = None if raw_credits is None else max(0, int(raw_credits))
        except (TypeError, ValueError):
            raise ExternalTtsError("AI Voice ส่งจำนวนเครดิตไม่ถูกต้อง") from None
        return {
            "connected": bool(result.get("connected", result.get("ok", True))),
            "credits": credits,
            "unlimited": bool(result.get("unlimited")) or credits is None,
            "expires_at": str(result.get("creditPeriodEnd") or ""),
            "plan_code": str(result.get("planCode") or ""),
            "plan_name": str(result.get("planName") or ""),
        }

    def synthesize(
        self,
        text,
        reference_id,
        language="th",
        emotion_id=CLIP_VOICE_EMOTION,
        engine="auto",
        speed=CLIP_VOICE_SPEED,
        silence_sec=0.3,
        idempotency_key="",
    ):
        text = str(text or "").strip()
        reference_id = self._safe_id(reference_id, "reference_id")
        if not text:
            raise ValueError("ยังไม่มีบทพูดสำหรับสร้างเสียง")
        if len(text) > MAX_TTS_REQUEST_CHARS:
            raise ValueError("คำขอเสียงต้องไม่เกิน 2,000 ตัวอักษร • กรุณาใช้ระบบแบ่งบทพากย์")
        # These two values are deliberately fixed for clip generation.  Keep
        # the arguments for backward compatibility with callers and plugins,
        # but never forward stale/custom values to the Voice API.
        emotion_value = CLIP_VOICE_EMOTION
        speed_value = CLIP_VOICE_SPEED
        silence_value = float(silence_sec)
        if not 0.5 <= speed_value <= 2.0:
            raise ValueError("speed ต้องอยู่ระหว่าง 0.5-2.0")
        if not 0 <= silence_value <= 3:
            raise ValueError("silence_sec ต้องอยู่ระหว่าง 0-3 วินาที")
        idempotency_key = str(idempotency_key or "").strip()
        if idempotency_key:
            idempotency_key = self._safe_id(idempotency_key, "idempotency_key")
        fields = {
            "text": text,
            "language": str(language or "th"),
            "reference_id": reference_id,
            "emotion_id": emotion_value,
            "engine": str(engine or "auto"),
            "speed": str(speed_value),
            "silence_sec": str(silence_value),
        }
        if idempotency_key:
            fields["idempotency_key"] = idempotency_key
        result = self._form(
            "/api/tts/external/synthesize",
            fields,
            extra_headers={"Idempotency-Key": idempotency_key} if idempotency_key else None,
        )
        if not result.get("job_id"):
            raise ExternalTtsError("ระบบไม่ส่ง job_id กลับมา")
        return result

    def get_job(self, job_id):
        job_id = self._safe_id(job_id, "job_id")
        return self._json_request("GET", f"/api/tts/external/job/{quote(job_id)}", timeout=30)

    def wait_until_done(self, job_id, timeout=1800, poll_interval=15, on_status=None, cancel_event=None):
        deadline = time.monotonic() + max(1, float(timeout))
        transient_poll_failures = 0
        while time.monotonic() < deadline:
            check_cancelled(cancel_event)
            try:
                result = self.get_job(job_id)
                transient_poll_failures = 0
            except ExternalTtsError as exc:
                if not exc.retryable:
                    raise
                transient_poll_failures += 1
                if on_status:
                    on_status("connection_retry", {
                        "job_id": str(job_id),
                        "status": "connection_retry",
                        "detail": str(exc),
                        "retry_count": transient_poll_failures,
                    })
                wait_seconds = min(30.0, max(1.0, float(poll_interval)))
                if cancel_event is not None:
                    if cancel_event.wait(wait_seconds):
                        check_cancelled(cancel_event)
                else:
                    time.sleep(wait_seconds)
                continue
            status = str(result.get("status") or result.get("state") or "").lower()
            if on_status:
                on_status(status or "processing", result)
            if status in {"done", "completed", "succeeded", "success"}:
                output_id = self._find_output_id(result)
                if not output_id:
                    raise ExternalTtsError("งานเสร็จแล้วแต่ไม่พบ output_id")
                return result, output_id
            if status in {"failed", "error", "cancelled", "canceled"}:
                detail = str(
                    result.get("detail")
                    or result.get("error")
                    or result.get("message")
                    or result.get("stage")
                    or status
                ).strip()
                retryable = status in {"failed", "error"} and bool(re.search(
                    r"error opening|system error|no such file(?: or directory)?|errno\s*2|resource temporarily unavailable|resource busy|sharing violation|temporar",
                    detail,
                    re.IGNORECASE,
                ))
                raise ExternalTtsError(
                    f"สร้างเสียงไม่สำเร็จ: {detail}",
                    retryable=retryable,
                    payload=result,
                )
            wait_seconds = max(0.1, float(poll_interval))
            if cancel_event is not None:
                if cancel_event.wait(wait_seconds):
                    check_cancelled(cancel_event)
            else:
                time.sleep(wait_seconds)
        raise ExternalTtsError(
            "หมดเวลารอสร้างเสียง กรุณาตรวจสถานะอีกครั้ง",
            retryable=True,
            payload={"job_id": str(job_id), "status": "poll_timeout"},
        )

    def download(self, output_id, target_path, output_format="mp3", cancel_event=None):
        check_cancelled(cancel_event)
        output_id = self._safe_id(output_id, "output_id")
        output_format = str(output_format or "mp3").lower()
        if output_format not in self.OUTPUT_FORMATS:
            raise ValueError("รองรับไฟล์เสียงเฉพาะ wav, mp3 หรือ mp4")
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            f"{self.base_url}/api/tts/external/download/{quote(output_id)}?format={output_format}",
            headers=self._headers(),
            method="GET",
        )
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        download_timeout = 660 if output_format == "mp4" else 180
        try:
            with self._opener.open(request, timeout=max(self.timeout, download_timeout)) as response:
                content_type = response.headers.get_content_type().lower()
                expected_prefix = "video/" if output_format == "mp4" else "audio/"
                if not content_type.startswith(expected_prefix):
                    preview = response.read(4096).decode("utf-8", errors="replace")
                    raise ExternalTtsError(f"ชนิดไฟล์ที่ดาวน์โหลดไม่ถูกต้อง ({content_type}): {preview[:200]}")
                with temporary.open("wb") as handle:
                    while True:
                        check_cancelled(cancel_event)
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
            if not temporary.exists() or temporary.stat().st_size == 0:
                raise ExternalTtsError("ไฟล์เสียงที่ดาวน์โหลดว่างเปล่า")
            os.replace(temporary, target)
            return target
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from None
        except urllib.error.URLError as exc:
            raise ExternalTtsError(f"เชื่อมต่อ AI Voice ไม่สำเร็จ: {exc.reason}") from None
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)

    def _multipart(self, path, fields, files=None, timeout=None):
        boundary = f"----SmartPost{uuid.uuid4().hex}"
        body = bytearray()
        for name, value in fields.items():
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8"))
        for name, file_path in (files or {}).items():
            source = Path(file_path)
            content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            safe_name = source.name.replace('"', "")
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{safe_name}\"\r\nContent-Type: {content_type}\r\n\r\n".encode("utf-8"))
            body.extend(source.read_bytes())
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("ascii"))
        headers = self._headers()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        return self._json_request("POST", path, bytes(body), headers, timeout=timeout)

    def _form(self, path, fields, extra_headers=None):
        body = urlencode(fields).encode("utf-8")
        headers = self._headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=utf-8"
        headers.update(dict(extra_headers or {}))
        return self._json_request("POST", path, body, headers, timeout=60)

    def _json_request(self, method, path, body=None, headers=None, timeout=None):
        request = urllib.request.Request(f"{self.base_url}{path}", data=body, headers=headers or self._headers(), method=method)
        try:
            with self._opener.open(request, timeout=max(5, int(timeout or self.timeout))) as response:
                raw = response.read(2 * 1024 * 1024)
            result = json.loads(raw.decode("utf-8"))
            if not isinstance(result, dict):
                raise ExternalTtsError("รูปแบบคำตอบจาก AI Voice ไม่ถูกต้อง")
            return result
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from None
        except urllib.error.URLError as exc:
            raise ExternalTtsError(
                f"เชื่อมต่อ AI Voice ไม่สำเร็จชั่วคราว: {exc.reason}",
                retryable=True,
            ) from None
        except TimeoutError:
            raise ExternalTtsError(
                "AI Voice ตอบสถานะช้ากว่ากำหนด ระบบจะลองอ่านคิวเดิมอีกครั้ง",
                retryable=True,
            ) from None
        except json.JSONDecodeError:
            raise ExternalTtsError("AI Voice ส่งข้อมูลที่อ่านไม่ได้") from None

    def _headers(self):
        return {"X-API-Key": self._api_key, "Accept": "application/json", "User-Agent": "SmartPost-AI/0.4"}

    @staticmethod
    def _safe_id(value, label):
        value = str(value or "").strip()
        if not value or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", value):
            raise ValueError(f"{label} ไม่ถูกต้อง")
        return value

    @staticmethod
    def _find_output_id(result):
        direct = result.get("output_id")
        if direct:
            return str(direct)
        nested = result.get("result") or result.get("output") or {}
        return str(nested.get("output_id") or nested.get("id") or "") if isinstance(nested, dict) else ""

    @staticmethod
    def _http_error(exc):
        try:
            payload = json.loads(exc.read(64 * 1024).decode("utf-8", errors="replace"))
            detail = payload.get("detail") or payload.get("error") or payload.get("message")
        except Exception:
            detail = None
        if exc.code in {401, 403}:
            detail = "API Key ไม่ถูกต้อง ไม่มีสิทธิ์ หรือแพ็กเกจไม่รองรับ API"
        elif exc.code == 402:
            detail = "เครดิตไม่เพียงพอ"
        elif exc.code == 429:
            detail = "เรียกใช้งานถี่เกินไป กรุณารอสักครู่"
        return ExternalTtsError(f"AI Voice HTTP {exc.code}: {detail or exc.reason}")
