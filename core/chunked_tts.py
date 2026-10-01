"""Sequential, resumable narration batches; never send >2,000 characters."""

import hashlib
import json
import re
import shutil
import unicodedata
import uuid
from pathlib import Path

from core.atomic_json import AtomicJsonFile
from core.cancellable_process import check_cancelled, run_cancellable
from core.external_tts import ExternalTtsError, MAX_TTS_REQUEST_CHARS


def split_tts_text(text):
    text = str(text or "").strip()
    if not text:
        raise ValueError("ยังไม่มีบทพูดสำหรับสร้างเสียง")
    chunks = []
    while len(text) > MAX_TTS_REQUEST_CHARS:
        end = MAX_TTS_REQUEST_CHARS
        # Prefer complete sentences/words. Keep pause directives and combining
        # marks attached even in unusually long text without spaces.
        boundaries = [m.end() for m in re.finditer(r"\[pause:[^\]]+\]|[.!?。！？\n]+|\s+", text[:end])]
        useful = [n for n in boundaries if n >= end // 2]
        if useful:
            end = useful[-1]
        for match in re.finditer(r"\[pause:[^\]]+\]", text):
            if match.start() < end < match.end():
                end = match.start()
                break
            if match.start() >= end:
                break
        while end > 0 and (unicodedata.category(text[end]).startswith("M") or text[end - 1] in "เแโใไ"):
            end -= 1
        if end <= 0:
            raise ValueError("ไม่สามารถแบ่งบทพากย์ภายใน 2,000 ตัวอักษรโดยรักษาข้อความได้")
        if text[:end].strip():
            chunks.append(text[:end])
        text = text[end:]
    if text.strip():
        chunks.append(text)
    return chunks


def merge_voice_chunks(paths, target, ffmpeg_path, *, cancel_event=None):
    """Normalize audio in order, then atomically publish only a complete file."""
    target = Path(target)
    ffmpeg = str(ffmpeg_path or "")
    if not Path(ffmpeg).is_file():
        ffmpeg = shutil.which("ffmpeg") or ""
    if not ffmpeg:
        raise FileNotFoundError("ไม่พบ FFmpeg สำหรับรวมเสียงพากย์ที่แบ่งช่วง")
    if target.suffix.lower() not in {".mp3", ".wav", ".mp4"}:
        raise ValueError("รูปแบบเสียงไม่รองรับ")
    target.parent.mkdir(parents=True, exist_ok=True)
    nonce = uuid.uuid4().hex
    playlist = target.parent / f".voice-{nonce}.txt"
    temporary = target.with_name(f".{target.stem}-{nonce}{target.suffix}")
    try:
        playlist.write_text("\n".join("file '" + Path(p).resolve().as_posix().replace("'", "'\\''") + "'" for p in paths), encoding="utf-8")
        codec = {".mp3": ["-c:a", "libmp3lame", "-q:a", "2"], ".wav": ["-c:a", "pcm_s16le"], ".mp4": ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]}[target.suffix.lower()]
        result = run_cancellable([ffmpeg, "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", str(playlist), "-vn", "-ar", "48000", "-ac", "2", *codec, str(temporary)], cancel_event=cancel_event, timeout=1800)
        check_cancelled(cancel_event)
        if result.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
            raise ExternalTtsError("รวมเสียงพากย์ไม่สำเร็จ • เก็บเสียงแต่ละช่วงไว้เพื่อทำต่อ")
        temporary.replace(target)
    finally:
        playlist.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)


def render_chunked_voice(client, text, reference_id, target, *, scope, options,
                         ffmpeg_path="", cancel_event=None, on_progress=None,
                         on_checkpoint=None, repair_reference=None,
                         legacy_job_id="", legacy_output_id=""):
    """Return (chunked job marker, chunked output marker, active reference id).

    All remote ids (not just the last) live in batch.json. A timed-out poll or
    download never advances to the next chunk. Idempotent submits survive a
    process crash after the server accepts but before we receive its job id.
    """
    target = Path(target)
    chunks = split_tts_text(text)
    options = dict(options)
    options.pop("idempotency_key", None)
    folder = target.parent / ".tts_chunks" / target.stem
    ledger = AtomicJsonFile(folder / "batch.json")
    # Separate lock from ledger IO. OS releases it even if the engine crashes.
    worker_lock = AtomicJsonFile(folder / "worker.lock", lock_timeout=0.5)
    identity = hashlib.sha256(json.dumps([scope, chunks, options], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def report(index, state):
        check_cancelled(cancel_event)
        if on_progress:
            on_progress(f"เสียงช่วง {index}/{len(chunks)} • {len(chunks[index - 1])} ตัวอักษร • {state}")

    with worker_lock.locked():
        check_cancelled(cancel_event)
        data = ledger.read(default=None)
        if data is None and str(legacy_job_id).startswith("chunked:"):
            raise ExternalTtsError("ไม่พบจุดบันทึกเสียงแบ่งช่วง • หยุดเพื่อไม่ใช้เสียงช่วงเดียวแทนทั้งบท")
        if data is None and legacy_job_id:
            # Already-paid, pre-upgrade whole-script job: finish it, never
            # submit the same narration again merely to adopt chunking.
            output_id = legacy_output_id
            if not output_id:
                _, output_id = client.wait_until_done(legacy_job_id, cancel_event=cancel_event,
                    on_status=lambda state, _: report(1, "ทำต่อคิวเดิม • " + state))
            client.download(output_id, target, target.suffix.lstrip("."), cancel_event=cancel_event)
            return legacy_job_id, output_id, reference_id
        if data is None:
            data = {"schema": 1, "identity": identity, "initial_reference_id": reference_id,
                    "reference_id": reference_id, "reference_repaired": False,
                    "chunks": [{"chars": len(chunk), "attempt": 1} for chunk in chunks]}
            ledger.write(data)
        if data.get("identity") != identity or reference_id not in {data.get("initial_reference_id"), data.get("reference_id")}:
            raise ExternalTtsError("บทหรือการตั้งค่าเสียงเปลี่ยนจากคิวที่บันทึกไว้ • หยุดเพื่อไม่สร้างเสียงซ้ำ")
        paths = []
        for index, (chunk, entry) in enumerate(zip(chunks, data["chunks"]), 1):
            check_cancelled(cancel_event)
            path = folder / f"part-{index:04d}.wav"
            paths.append(path)
            if entry.get("downloaded") and path.is_file() and path.stat().st_size == entry.get("size"):
                report(index, "ใช้เสียงช่วงเดิม")
                continue
            while not entry.get("output_id"):
                check_cancelled(cancel_event)
                if not entry.get("job_id"):
                    report(index, "กำลังส่งข้อความ")
                    ref_hash = hashlib.sha256(data["reference_id"].encode("utf-8")).hexdigest()[:16]
                    key = f"tts-chunk:{identity}:{ref_hash}:{index}:v{entry['attempt']}"
                    entry["idempotency_key"] = key
                    ledger.write(data)  # intent/key durable before any POST
                    try:
                        queued = client.synthesize(chunk, data["reference_id"], **options, idempotency_key=key)
                    except ExternalTtsError as exc:
                        missing = "HTTP 404" in str(exc) or "ไม่พบไฟล์เสียงต้นแบบ" in str(exc)
                        if not missing or not repair_reference or data["reference_repaired"] or index != 1:
                            raise
                        data["reference_id"] = str(repair_reference(data["reference_id"]))
                        data["reference_repaired"] = True
                        ledger.write(data)
                        continue
                    entry["job_id"] = str(queued["job_id"])
                    ledger.write(data)  # before cancellation callback or poll
                    if on_checkpoint:
                        on_checkpoint("chunked:" + entry["job_id"], data["reference_id"])
                report(index, "รอเซิร์ฟเวอร์ประมวลผล")
                try:
                    _, output_id = client.wait_until_done(entry["job_id"], cancel_event=cancel_event,
                        on_status=lambda state, _: report(index, state))
                except ExternalTtsError as exc:
                    terminal = str(exc.payload.get("status") or "").lower() in {"failed", "error"}
                    if not exc.retryable or not terminal or entry["attempt"] >= 2:
                        raise
                    entry.update(replaced_job_id=entry["job_id"], job_id="", attempt=2)
                    ledger.write(data)
                    report(index, "คิวเดิมล้มเหลวชั่วคราว • สร้างทดแทนได้หนึ่งครั้ง")
                    continue
                entry["output_id"] = str(output_id)
                ledger.write(data)
            report(index, "กำลังดาวน์โหลด")
            client.download(entry["output_id"], path, "wav", cancel_event=cancel_event)
            if not path.is_file() or path.stat().st_size == 0:
                raise ExternalTtsError("ดาวน์โหลดเสียงช่วงนี้ไม่ครบ • ยังไม่ส่งช่วงถัดไป")
            entry.update(downloaded=True, size=path.stat().st_size)
            ledger.write(data)
        report(len(chunks), "รวมเสียงตามลำดับ")
        merge_voice_chunks(paths, target, ffmpeg_path, cancel_event=cancel_event)
        data["complete"] = True
        ledger.write(data)
        last = data["chunks"][-1]
        return "chunked:" + last["job_id"], "chunked:" + last["output_id"], data["reference_id"]
