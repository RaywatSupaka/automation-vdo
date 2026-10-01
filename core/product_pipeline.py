"""Checkpoint and bounded recovery rules for the affiliate product pipeline."""

from datetime import datetime
from pathlib import Path


PRODUCT_STAGES = (
    ("product", "ตรวจข้อมูลสินค้า", 0, 12),
    ("ai", "สร้างภาพ บทพูด และแคปชั่น", 12, 38),
    ("voice", "สร้างเสียงพากย์ AI", 38, 52),
    ("flow", "สร้างวิดีโอด้วย AI 3 ช็อต", 52, 78),
    ("edit", "รวมคลิป เอฟเฟกต์ และโลโก้", 78, 86),
    ("subtitle", "ทำ Subtitle", 86, 94),
    ("audio", "ใส่เสียงประกอบและตรวจไฟล์", 94, 100),
)

PRODUCT_AI_AUTO_RECOVERY_LIMIT = 2
PRODUCT_RUNTIME_RECOVERY_LIMIT = 2


def interrupted_product_candidate(
    jobs,
    now=None,
    max_age_seconds=30 * 60,
    recovery_limit=PRODUCT_RUNTIME_RECOVERY_LIMIT,
):
    """Return the newest recently-running Job left behind by an app crash.

    A normal cancel is persisted as ``cancelled`` and is never resumed.  The
    time bound prevents an old historical ``running`` flag from unexpectedly
    spending browser/API credits days later.
    """
    now = now or datetime.now()
    valid_stages = {key for key, _label, _start, _end in PRODUCT_STAGES}
    candidates = []
    for row in jobs or []:
        job = dict(row or {})
        if str(job.get("automation_status") or "").lower() != "running":
            continue
        if recovery_limit is not None and int(job.get("runtime_recovery_count") or 0) >= int(recovery_limit):
            continue
        stage = str(job.get("automation_stage") or "").lower()
        if stage not in valid_stages:
            continue
        try:
            updated = datetime.fromisoformat(str(job.get("updated_at") or ""))
            age = (now - updated).total_seconds()
        except (TypeError, ValueError):
            continue
        if -300 <= age <= max(20, int(max_age_seconds)):
            candidates.append((updated, job))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1] if candidates else None


def recoverable_product_candidate(
    jobs,
    now=None,
    max_age_seconds=30 * 60,
    recovery_limit=PRODUCT_RUNTIME_RECOVERY_LIMIT,
):
    """Return a recent terminal browser/Flow error that is safe to resume.

    The engine can exit after its worker persisted ``automation_status=error``
    but before the UI event schedules the same-process retry. Startup recovery
    must therefore consider a bounded, classified error in addition to an
    orphaned ``running`` state.
    """
    now = now or datetime.now()
    candidates = []
    for row in jobs or []:
        job = dict(row or {})
        if str(job.get("automation_status") or "").lower() != "error":
            continue
        error = str(job.get("automation_error") or job.get("last_error") or "")
        if product_runtime_recovery_action(job, error, recovery_limit=recovery_limit) != "resume_pipeline":
            continue
        try:
            updated = datetime.fromisoformat(str(job.get("updated_at") or ""))
            age = (now - updated).total_seconds()
        except (TypeError, ValueError):
            continue
        if -300 <= age <= max(20, int(max_age_seconds)):
            candidates.append((updated, job))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1] if candidates else None

_PRODUCT_MANUAL_RECOVERY_MARKERS = (
    "ai_image_repair_review", "ai_image_policy_review",
    "flow_send_review", "flow_repair_review", "flow_attachment_unconfirmed", "flow_video_settings_review",
    "gemini_image_send_review", "gemini_text_send_review", "gemini_text_request_review", "ai_web_resume_review",
    # An accepted analysis timeout is not permission to re-send the prompt.
    "ai_analysis_timeout", "ai_analysis_format_review", "ai_analysis_json_ambiguous",
    "ai_web_wait_review", "ใช้เวลาตอบนานเกิน 6 นาที",
    "ผู้ใช้ยกเลิก", "user_cancel", "api key", "เครดิต", "แพ็กเกจ",
    "เข้าสู่ระบบ", "login", "captcha", "ยืนยันตัวตน", "reload extension",
    "เวอร์ชัน", "permission", "สิทธิ์", "policy", "ละเมิด",
    # An attachment safe-stop is an explicit at-most-once boundary. Automatic
    # runtime recovery would re-enter the same Flow media transaction and can
    # create duplicate local references or repeated card-menu clicks.
    "หยุดอย่างปลอดภัย", "ไม่อัปโหลดรูปซ้ำ", "หยุดเพื่อป้องกันการอัปโหลดรูปซ้ำ",
    "flow_attach_safe_target_missing", "flow_attach_proof_missing_after_single_action",
)

_PRODUCT_AI_RECOVERY_MARKERS = (
    "ไม่ส่งรูปใหม่ภายใน", "ใช้เวลาตอบนานเกิน", "ไม่ได้สร้างไฟล์ภาพใหม่",
    "ไม่ส่งภาพ", "หมดเวลา", "network", "timeout", "timed out", "ขาดการเชื่อมต่อ",
    "หน้าเว็บโหลดช้า", "ไม่พบแท็บ", "receiving end does not exist",
    "หน้าตรวจสอบของ google", "เปิดไปหน้าอื่น", "สร้างภาพค้าง", "โหลดหน้า chatgpt เดิมใหม่",
    "json ขาดข้อมูล", "อ่าน json ไม่ได้", "จัดรูปแบบอัตโนมัติ",
    "ปฏิเสธการวิเคราะห์", "นอกเหนือขอบเขตโปรแกรม", "แนบรูปเข้า",
)

_PRODUCT_RUNTIME_RECOVERY_MARKERS = (
    "google flow", "flow ช็อต", "chrome/extension", "extension ออนไลน์",
    "ไม่พบแท็บ google flow", "รูปหรือ prompt ยังไม่พร้อม", "prompt ยังโหลดไม่ครบ",
    "ไม่รับคำสั่ง", "ไม่เริ่มสร้าง", "generation_status_unknown",
    "generation failed", "failed to generate", "ค้างที่", "หมดเวลารอ google flow",
)


def product_ai_recovery_action(job, message):
    """Return a safe second-layer action for incomplete Product AI work."""
    job = dict(job or {})
    error = str(message or "").strip().lower()
    if "flow_plan_review" in error:
        return ""
    if any(code in error for code in ("ai_image_recovery_stop", "ai_image_policy_blocked", "source_images_need_review", "ai_image_revision_changed")):
        return ""
    if not error or any(marker in error for marker in _PRODUCT_MANUAL_RECOVERY_MARKERS):
        return ""
    if job.get("automation_status") == "cancelled" or job.get("status") == "cancelled":
        return ""
    if job.get("ai_status") == "ready" and len(job.get("generated_images") or []) >= 3:
        return ""
    if any(marker in error for marker in _PRODUCT_AI_RECOVERY_MARKERS):
        return "resume_chatgpt"
    if job.get("partial_generated_images"):
        return "resume_chatgpt"
    return ""


def product_provider_failover_action(job, message):
    """Never change the image provider without an explicit user selection.

    Recovery may reload or resume the provider stored on the Job, but a Gemini
    failure must not silently open ChatGPT (or the reverse). Changing provider
    mid-Job loses the browser checkpoint and surprises the user.
    """
    return ""


def product_runtime_recovery_action(job, message, recovery_limit=PRODUCT_RUNTIME_RECOVERY_LIMIT):
    """Return a safe same-process resume action for transient browser/Flow failures.

    This is deliberately narrower than a generic retry.  It is only allowed
    when the Product Job already owns a real checkpoint and the failure belongs
    to Chrome/Extension/Google Flow.  Login, credit, policy and user-cancel
    states always remain manual so an automatic loop cannot spend credits or
    bypass a user decision.
    """
    job = dict(job or {})
    error = str(message or "").strip().lower()
    if "flow_plan_review" in error:
        return ""
    if any(code in error for code in ("ai_image_recovery_stop", "ai_image_policy_blocked", "source_images_need_review", "ai_image_revision_changed")):
        return ""
    if not error or any(marker in error for marker in _PRODUCT_MANUAL_RECOVERY_MARKERS):
        return ""
    if str(job.get("automation_status") or "").lower() in {"cancelled", "completed"}:
        return ""
    if str(job.get("status") or "").lower() == "cancelled" or bool(job.get("ready")):
        return ""
    if int(job.get("runtime_recovery_count") or 0) >= int(recovery_limit):
        return ""
    has_checkpoint = bool(
        job.get("ai_status") == "ready"
        or job.get("voice_status") == "ready"
        or job.get("generated_images")
        or job.get("partial_generated_images")
        or job.get("flow_clips")
        or job.get("flow_local_motion_clips")
        or job.get("flow_policy_fallbacks")
    )
    if has_checkpoint and any(marker in error for marker in _PRODUCT_RUNTIME_RECOVERY_MARKERS):
        return "resume_pipeline"
    return ""


def product_ai_recovery_command(job, attempt):
    """Choose recovery without assuming browser-side analysis was persisted."""
    job = dict(job or {})
    has_checkpoint = bool(
        job.get("ai_status") == "ready"
        or job.get("generated_images")
        or job.get("partial_generated_images")
    )
    if not has_checkpoint:
        # A timeout can happen after ChatGPT rendered JSON but before the
        # content script parsed/stored it. Resume would then reload the tab and
        # fail with "ไม่พบผลวิเคราะห์เดิม". Re-run analysis in the same Job.
        return "open_chatgpt"
    return "restart_chatgpt_images" if int(attempt or 0) >= 2 else "resume_chatgpt"


def real_product_data(job):
    name = str((job or {}).get("product_name") or "").strip()
    placeholder = name == "สินค้า Shopee จากลิงก์" or name.startswith("สินค้า Shopee • ID ")
    return bool(name and not placeholder and (job or {}).get("source_images"))


def source_image_capture_detail(job):
    capture = (job or {}).get("source_image_capture") or {}
    attempted = int(capture.get("attempted") or 0)
    saved = int(capture.get("saved") or 0)
    failures = capture.get("failures") if isinstance(capture.get("failures"), list) else []
    details = []
    for item in failures[:3]:
        if not isinstance(item, dict):
            continue
        host = str(item.get("host") or "เซิร์ฟเวอร์รูป")[:80]
        reason = str(item.get("reason") or "ดาวน์โหลดไม่สำเร็จ")[:120]
        details.append(f"{host}: {reason}")
    if attempted:
        result = f"ดาวน์โหลดรูปได้ {saved}/{attempted}"
        if details:
            result += " • " + " ; ".join(details)
        extra = int(capture.get("additional_failures") or 0)
        if extra:
            result += f" • และอีก {extra} รายการ"
        return result[:500]
    return "หน้า Shopee ไม่พบ URL รูปที่นำมาดาวน์โหลดได้" if capture else ""


def ai_package_complete(job, folder):
    job = job or {}
    folder = Path(folder)
    images = list(job.get("composition_images") or job.get("generated_images") or [])
    prompts = list(job.get("flow_shot_prompts") or [])
    return (
        job.get("ai_status") == "ready"
        and len(images) >= 3
        and len(prompts) >= 3
        and bool(str(job.get("caption") or "").strip())
        and bool(str(job.get("spoken_script") or "").strip())
        and all((folder / item).is_file() for item in images[:3])
    )


def completed_flow_clips(job, folder):
    folder = Path(folder)
    clips = dict((job or {}).get("flow_clips") or {})
    return [index for index in (1, 2, 3) if clips.get(str(index)) and (folder / clips[str(index)]).is_file()]


def completed_product_segments(job, folder):
    """Return ordered Product slots backed by either Flow or local motion."""
    folder = Path(folder)
    remote = dict((job or {}).get("flow_clips") or {})
    local = dict((job or {}).get("flow_local_motion_clips") or {})
    target_count = int(
        (job or {}).get("flow_target_clip_count")
        or len((job or {}).get("generated_images") or (job or {}).get("source_images") or [])
        or 3
    )
    return [
        index for index in range(1, target_count + 1)
        if (
            remote.get(str(index)) and (folder / remote[str(index)]).is_file()
        ) or (
            local.get(str(index)) and (folder / local[str(index)]).is_file()
        )
    ]


def product_progress(job, folder, subtitle_enabled=True, audio_enabled=True):
    """Return monotonic progress based only on files/statuses already completed."""
    job = job or {}
    folder = Path(folder)
    if not real_product_data(job):
        return 5
    if not ai_package_complete(job, folder):
        return 12
    if (job.get("audio_choices") or {}).get("mode", "api") == "api" and (job.get("voice_status") != "ready" or not (folder / str(job.get("voice_path") or "")).is_file()):
        return 38
    segments = completed_product_segments(job, folder)
    target_count = int(job.get("flow_target_clip_count") or 3)
    if len(segments) < target_count:
        return 52 + round(24 * len(segments) / max(1, target_count))
    if job.get("video_status") != "ready" or not (folder / str(job.get("video_path") or "")).is_file():
        return 78
    if subtitle_enabled:
        if job.get("subtitle_status") != "ready":
            return 86
        if job.get("subtitle_video_status") != "ready":
            return 90
    if audio_enabled and job.get("audio_mix_status") != "ready":
        return 94
    return 100
