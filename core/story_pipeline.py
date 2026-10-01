STORY_STAGES = (
    ("chatgpt", "ChatGPT Web", 0, 60),
    ("voice", "สร้างเสียง AI", 60, 80),
    ("video", "ประกอบฉากวิดีโอ", 80, 88),
    ("finishing", "ซับ โลโก้ และเสียงประกอบ", 88, 100),
)

STORY_AUTO_RECOVERY_LIMIT = 2

_MANUAL_RECOVERY_MARKERS = (
    "ผู้ใช้ยกเลิก", "user_cancel", "api key", "เครดิต", "แพ็กเกจ",
    "เข้าสู่ระบบ", "login", "captcha", "ยืนยันตัวตน", "reload extension",
    "เวอร์ชัน", "permission", "สิทธิ์", "บทพากย์ยังไม่พร้อม",
    # Submission was already accepted. Reopening analysis would send it again,
    # even when the first answer is still available in the owned conversation.
    "ai_analysis_timeout", "ai_analysis_format_review", "ai_analysis_json_ambiguous",
    "gemini_text_send_review", "gemini_text_request_review",
    "ai_web_resume_review", "ai_web_wait_review", "ใช้เวลาตอบนานเกิน 6 นาที",
)

_CONTENT_RECOVERY_STOP_CODES = (
    "meta_sequence_review",
    "flow_scene_count_invalid", "story google flow ต้องมีอย่างน้อย 2 ฉาก",
    "story_content_mismatch", "story_image_refused", "story_scene_prompt_stale", "story_reference_required",
    "story_image_response_review", "flow_plan_review", "flow_video_settings_review",
    "story_image_audit_unconfirmed", "story_image_context_conflict",
    "story_analysis_checkpoint_review", "story_image_checkpoint_unreadable",
    "story_image_receipt_review", "story_image_download_pending", "story_image_fallback_review",
)


def story_recovery_action(job, message):
    """Return the safe checkpoint action for a failed story stage.

    ChatGPT/image work can resume by exact missing scene index. Rendering can be
    repeated only after a voice file exists, so an uncertain TTS request is
    never submitted twice and cannot consume credit twice.
    """
    job = dict(job or {})
    error = str(message or "").strip().lower()
    if not error or any(marker in error for marker in _MANUAL_RECOVERY_MARKERS):
        return ""
    # These errors preserve the original story and saved images for review.
    # Automatically reopening the image stage would resend a refused request
    # or repair the story into different content, even with the same Job id.
    # A provider explicitly requesting a reference also needs user review;
    # repeating the same source-less request cannot supply the missing image.
    # A completed unexplained no-image response is not proof of a transient
    # failure either; preserve it for review instead of submitting again.
    if any(code in error for code in _CONTENT_RECOVERY_STOP_CODES):
        return ""
    if job.get("cancel_requested") or job.get("status") == "cancelled":
        return ""
    expected = max(1, int(job.get("scene_count") or 1))
    generated = list(job.get("generated_images") or [])
    partial = list(job.get("partial_generated_images") or [])
    ai_ready = job.get("ai_status") == "ready" and len(generated) == expected
    if not ai_ready:
        # The extension reloads saved scene_XX checkpoints and fills only gaps.
        return "resume_chatgpt"
    if (job.get("audio_choices") or {}).get("mode", "api") != "api":
        return "render"
    if job.get("voice_status") == "ready" and job.get("voice_path"):
        return "render"
    # A persisted TTS job id is a paid-request checkpoint.  Polling that same
    # queue again does not submit or charge for another voice request.
    if job.get("voice_job_id"):
        return "voice"
    # Legacy jobs created before voice checkpoints cannot be auto-retried
    # safely because the original paid request id was not persisted.
    return ""


def story_provider_failover_action(job, message):
    """Keep the provider selected for this Story Job until the user changes it."""
    return ""


def browser_progress(client, job_id, scene_count):
    """Map extension facts to workflow percent; never estimate from elapsed time."""
    client = dict(client or {})
    if str(client.get("ai_job_id") or "") != str(job_id or ""):
        return None
    count = max(0, min(int(scene_count or 1), int(client.get("ai_image_count") or 0)))
    total = max(1, int(scene_count or 1))
    step = str(client.get("ai_step") or "preparing")
    message = str(client.get("ai_message") or "กำลังเชื่อมต่อ ChatGPT Web")
    if step == "preparing":
        percent = 5
    elif step in {"repairing_analysis", "repairing_story_names", "story_names_repaired"}:
        percent = 12
    elif step in {"analysis_ready", "analysis_saved"}:
        percent = 15
    elif step in {"generating_images", "recovering_images", "retrying_image", "recovering_stalled_image", "checking_stalled_image", "uploading_source", "source_images_ready", "waiting_for_image", "downloading_image", "image_attempt_result", "image_prompt_ready", "recovering_result", "recovering_response", "image_refresh_check", "image_restart_pending", "image_restart_started", "image_result_verified"}:
        percent = 15 + round(40 * count / total)
    elif step in {"preparing_flow_prompt", "flow_prompt_saved"}:
        percent = 55
    elif step == 'waiting_scene_assets':
        percent = 15 + round(70 * count / total)
    elif step == "waiting_for_analysis":
        percent = 8
    elif step == "submitting":
        percent = 58
    elif step == "complete":
        percent = 60
    elif step == "user_action_required":
        percent = 5 + round(50 * count / total)
    elif step in {"cancelled", "error"}:
        percent = 0
    else:
        percent = 5
    action_kind = str(client.get("ai_action_kind") or "")
    if step == "user_action_required":
        detail = ("ระบบหยุดรออย่างปลอดภัย • กรุณา Login ใน Chrome แล้วระบบจะทำต่อจาก Checkpoint เดิม"
                  if action_kind == "login_required"
                  else "ระบบหยุดรออย่างปลอดภัย • กรุณาไปที่ Chrome แล้วติ๊ก ‘ฉันไม่ใช่โปรแกรมอัตโนมัติ’")
    elif step == "image_prompt_ready":
        detail = f"บันทึกพรอมต์ก่อนส่ง • ภาพเสร็จจริง {count}/{total}"
    elif step == "image_attempt_result":
        detail = f"ตรวจคำตอบภาพก่อนตัดสินใจ • ภาพเสร็จจริง {count}/{total}"
    elif step == "image_result_verified":
        detail = f"พบภาพแล้ว กำลังบันทึก • ภาพเสร็จจริง {count}/{total}"
    elif step in {"recovering_result", "recovering_response", "image_refresh_check", "image_restart_pending", "image_restart_started"}:
        detail = f"กำลังกู้ฉากที่ค้างอัตโนมัติ • ภาพเสร็จจริง {count}/{total} • เก็บภาพที่สำเร็จแล้วไว้"
    elif step in {"generating_images", "recovering_images", "retrying_image", "recovering_stalled_image", "checking_stalled_image", "uploading_source", "source_images_ready", "waiting_for_image", "downloading_image", "submitting", "complete"}:
        detail = f"ภาพเสร็จจริง {count}/{total}"
    elif step == "waiting_for_analysis":
        detail = "ส่ง Prompt สำเร็จแล้ว • หน้าเว็บกำลังวิเคราะห์ข้อมูล"
    elif step == "analysis_saved":
        detail = "บันทึกชื่อคลิป บทพากย์ และแผนทุกฉากลง Job แล้ว"
    elif step == "repairing_analysis":
        detail = "กำลังซ่อมรูปแบบคำตอบอัตโนมัติ โดยยังไม่เริ่มสร้างภาพ"
    elif step == "repairing_story_names":
        detail = "ตรวจการอ้างชื่อเฉพาะจุดในแผนเดิมหนึ่งครั้ง • ยังไม่เริ่มสร้างภาพ"
    elif step == "story_names_repaired":
        detail = "เติมชื่อกำกับคำบรรยายเดิมแล้ว • รอยืนยันบันทึก Checkpoint ก่อนสร้างภาพ"
    else:
        detail = "กำลังรอผลจากหน้าเว็บ"
    return {"percent": percent, "stage": "chatgpt", "message": message, "detail": detail, "step": step, "action_kind": action_kind, "service": str(client.get("ai_service") or client.get("ai_provider") or "")}
