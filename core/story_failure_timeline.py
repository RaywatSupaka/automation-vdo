"""Readable, job-owned Story extension timeline for the local error report."""

import json
import re
from pathlib import Path


_JOB_ID = re.compile(r"^STORY-[A-Za-z0-9_-]+$")


def story_failure_timeline(story_root, job_id, *, max_events=200):
    """Read the durable trace without changing a job or guessing policy causes."""
    if not _JOB_ID.fullmatch(str(job_id or "")):
        return ""
    job_dir = Path(story_root) / job_id
    if not (job_dir / "job.json").is_file():
        return ""
    try:
        job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        job = {}
    trace_file = job_dir / "logs" / "extension_trace.jsonl"
    try:
        with trace_file.open("r", encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    except (OSError, ValueError, UnicodeError):
        return ""
    rows = [row for row in rows if isinstance(row, dict) and row.get("job_id") == job_id]
    if not rows:
        return ""
    omitted = max(0, len(rows) - max_events)
    rows = rows[-max_events:]
    lines = ["--- ลำดับเหตุการณ์ของงานนี้ (Extension trace) ---"]
    if isinstance(job, dict):
        from core.story_recovery_summary import story_recovery_summary
        summary = story_recovery_summary(job, job_dir)
        saved = summary["saved_image_scenes"]
        lines.append("ภาพที่บันทึกในเครื่องแล้ว: " + (", ".join(map(str, saved)) if saved else "ยังไม่มี"))
        if summary["analysis_ready"]:
            lines.append("บทและรายละเอียด: บันทึกแล้ว")
        failed_scene = summary["failed_image_scene"]
        if failed_scene:
            lines.append(f"จุดที่หยุด: ภาพฉาก {failed_scene}" +
                         (" • ยังไม่ส่งคำขอ" if summary["send_not_started"] else ""))
            if summary["send_not_started"]:
                ready = next((event for event in reversed(rows)
                              if event.get("action") == "image_prompt_ready"
                              and isinstance(event.get("detail"), dict)
                              and event["detail"].get("scene_index") == failed_scene), None)
                if ready:
                    lines.append("ก่อนส่ง: ช่องพิมพ์ตรงกับคำสั่งที่เตรียมไว้" if ready["detail"].get("composer_matches")
                                 else "ก่อนส่ง: trace ยังไม่ยืนยันว่าช่องพิมพ์ตรงกับคำสั่ง")
                lines.append("การตรวจครั้งสุดท้ายหยุดก่อนกดส่ง; trace ไม่บันทึกเนื้อหาช่องพิมพ์ ณ จุดที่หยุด จึงยังระบุสาเหตุที่ข้อความเปลี่ยนไม่ได้")
    if omitted:
        lines.append(f"มีเหตุการณ์ก่อนหน้านี้อีก {omitted} รายการในไฟล์ extension_trace.jsonl")
    for index, row in enumerate(rows):
        at = str(row.get("at") or "-")
        action = str(row.get("action") or "progress")
        message = " ".join(str(row.get("message") or "").split())
        lines.append(f"{at}  [{action}] {message}")
        if action != "image_prompt_ready":
            continue
        detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
        prompt = str(detail.get("prompt") or "")
        run_id = str(row.get("run_id") or "")
        later = []
        for event in rows[index + 1:]:
            if event.get("action") in {"image_prompt_ready", "image_attempt_result"}:
                break
            later.append(event)
        confirmed = next((event for event in later
                          if str(event.get("run_id") or "") == run_id
                          and event.get("action") == "ai_send_accepted"), None)
        if prompt:
            status = "ยืนยันว่าเว็บรับแล้ว" if confirmed else "เตรียมไว้ แต่ยังไม่พบหลักฐานว่าเว็บรับ"
            scene = detail.get("scene_index") or "?"
            lines.extend((f"  พรอมต์ภาพฉาก {scene} ({status}):", prompt, "  --- จบพรอมต์ ---"))
    master_prompt = job_dir / "prompts" / "chatgpt_request.txt"
    try:
        saved_request = master_prompt.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        saved_request = ""
    if saved_request:
        lines.extend(("", "--- คำขอวิเคราะห์ที่โปรแกรมบันทึกไว้ ---",
                      "ไฟล์นี้เป็นต้นทางของคำขอ; trace ยืนยันการรับคำขอ แต่ไม่ได้เก็บข้อความบนเว็บแบบครบถ้วน",
                      saved_request[:20000], "--- จบคำขอวิเคราะห์ ---"))
    lines.append("หมายเหตุ: policy_refusal เป็นคำตอบจากเว็บ; ถ้าเว็บไม่ระบุข้อห้ามเฉพาะ รายงานนี้ระบุสาเหตุเฉพาะไม่ได้")
    return "\n".join(lines)
