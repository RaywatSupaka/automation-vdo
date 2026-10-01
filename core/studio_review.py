"""Small on-demand Story/Drama review models, never browser automation."""
import re
from pathlib import Path
from urllib.parse import quote

from core.story_script import spoken_script_for_job
from core.story_content import story_content_review
from core.story_image_result_recovery import story_image_result_review
from core.long_video import meta_landscape_available
from core.thai_tts import prepare_thai_tts_script


def pronunciation_notes(job):
    base = job.get("pronunciation_notes")
    user = job.get("user_pronunciation_notes")
    return {**(base if isinstance(base, dict) else {}), **(user if isinstance(user, dict) else {})}


def validate_user_notes(notes):
    if not isinstance(notes, dict) or len(notes) > 100:
        raise ValueError("คำอ่านต้องเป็นคู่คำต้นฉบับกับคำอ่าน ไม่เกิน 100 คำ")
    clean = {}
    for original, reading in notes.items():
        if not isinstance(original, str) or not isinstance(reading, str):
            raise ValueError("คำต้นฉบับและคำอ่านต้องเป็นข้อความ")
        original, reading = original.strip(), reading.strip()
        if not original or len(original) > 100 or not reading or len(reading) > 160:
            raise ValueError("กรอกคำต้นฉบับ 1–100 ตัวอักษร และคำอ่าน 1–160 ตัวอักษร")
        # Latin is allowed in the original, not the pronunciation.
        if (not re.search(r"[ก-๙]", reading) or re.search(r"[A-Za-z<>\[\]\r\n]", reading)
                or re.search(r"[<>\[\]\r\n]", original)):
            raise ValueError("ใช้คำอ่านภาษาไทย ไม่มีแท็กหรือขึ้นบรรทัดใหม่")
        clean[original] = reading
    return clean


def voice_review(job):
    from core.speech_delivery import enabled as speech_enabled, effective_script
    script, issues = (effective_script(job, include_pauses=True) if speech_enabled(job)
                     else prepare_thai_tts_script(spoken_script_for_job(job, include_pauses=True), pronunciation_notes(job)))
    return {"script": script, "issues": issues, "ready": bool(script) and not issues}


def voice_locked(job):
    return bool(job.get("voice_job_id") or job.get("voice_path") or job.get("dialogue_voice_checkpoints")
                or str(job.get("voice_status") or "") == "ready")


def safe_asset(folder, relative, suffixes):
    if not relative or not isinstance(relative, str):
        return None
    root = Path(folder).resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or target.suffix.lower() not in suffixes or not target.is_file():
        return None
    return target


def scene_asset(folder, job, index, kind="image"):
    if not 1 <= index <= int(job.get("scene_count") or 0):
        raise ValueError("ลำดับฉากไม่ถูกต้อง")
    if kind == "image":
        # Filenames carry the slot identity. Never index the compact partial list.
        candidates = [f"generated/scene_{index:02d}.png"]
        for relative in (job.get("generated_images") or []) + (job.get("partial_generated_images") or []):
            if re.fullmatch(rf"scene_0*{index}\.(png|jpg|jpeg|webp)", Path(str(relative)).name, re.I):
                candidates.append(relative)
        return next((path for candidate in candidates if (path := safe_asset(folder, candidate, {".png", ".jpg", ".jpeg", ".webp"}))), None)
    if kind not in {"flow", "meta", "local"}:
        raise ValueError("ประเภทไฟล์ฉากไม่ถูกต้อง")
    # The durable frozen source remains previewable even if an unrelated
    # legacy progress snapshot carried an older provider-specific clip map.
    from core.scene_video_plan import enabled, verified_asset
    if enabled(job):
        try:
            asset = verified_asset(folder, job, index)
        except ValueError:
            return None
        if asset and asset['provider'] == {'flow': 'google_flow', 'meta': 'meta_ai', 'local': 'local'}[kind]:
            return safe_asset(folder, asset['path'], {'.mp4', '.webm', '.mov', '.mkv'})
    field = {"flow": "flow_clips", "meta": "meta_clips", "local": "flow_fallback_clips"}[kind]
    return safe_asset(folder, dict(job.get(field) or {}).get(str(index)), {".mp4", ".webm", ".mov", ".mkv"})


def story_review(folder, job, active=False):
    from core.flow_scene_edit import editable
    from core.scene_video_plan import enabled as has_video_plan, effective_job, provider_for, settings_for, summary, verified_asset
    from core.flow_motion_plan import saved_motion_prompt
    from core.media_audio import flow_audio_instruction
    def url(index, kind):
        return "/api/desktop/media?item_id=" + quote(f"story-scene:{job['id']}:{index}:{kind}", safe="") + "&kind=preview"

    scenes = []
    video_plan = summary(folder, job, active)
    narrations = list(job.get("scene_narrations") or [])
    prompts = list(job.get("scene_prompts") or [])
    stored_remote = stored_meta = stored_local = 0
    prompt_editable = (not active and not voice_locked(job) and not job.get("cancel_requested")
                       and job.get("status") not in {"active", "running", "recovering", "cancelled", "canceled", "deleted"}
                       and not any(job.get(key) for key in ("video_path", "final_path", "final_video_path"))
                       and job.get("video_status") not in {"ready", "complete", "completed"}
                       and len(prompts) == int(job.get("scene_count") or 0))
    for index in range(1, min(80, int(job.get("scene_count") or 0)) + 1):
        image = scene_asset(folder, job, index)
        remote = scene_asset(folder, job, index, "flow")
        meta = scene_asset(folder, job, index, "meta")
        local = scene_asset(folder, job, index, "local")
        stored_remote += bool(remote)
        stored_meta += bool(meta)
        stored_local += bool(local)
        if has_video_plan(job):
            try:
                kept = verified_asset(folder, job, index)
            except ValueError:
                kept = None
            source = {'google_flow': 'flow', 'meta_ai': 'meta', 'local': 'local'}.get((kept or {}).get('provider'), 'pending')
        elif job.get('video_generation_mode') == 'meta_ai':
            source = "meta" if meta else "pending"
        elif job.get('video_generation_mode') == 'google_flow':
            source = "flow" if remote else "local" if local else "pending"
        else:
            source = "local" if local else "pending"
        flow_prompt = ''
        manual = (job.get('flow_scene_edits') or {}).get(str(index)) or {}
        if image and provider_for(job, index) == 'google_flow':
            try:
                view = effective_job(job, index)
                flow_prompt = manual.get('prompt') or saved_motion_prompt(folder, view, index, image.relative_to(Path(folder).resolve()).as_posix()).removesuffix(flow_audio_instruction(view, index))
            except ValueError:
                pass
        scenes.append({"index": index, "image_url": url(index, "image") if image else "",
                       "video_url": url(index, source) if source in {"flow", "meta", "local"} else "", "source": source,
                       "narration": str(narrations[index-1]) if index <= len(narrations) else "",
                       "prompt": str(prompts[index-1]) if index <= len(prompts) else "",
                       "prompt_editable": bool(prompt_editable and not image and not remote and not meta and not local),
                       "prompt_revised": str(index) in dict(job.get("scene_prompt_overrides") or {}),
                       "flow_editable": bool(provider_for(job, index) == 'google_flow' and editable(folder, job, index, active)),
                       "flow_prompt": flow_prompt,
                       "flow_model": settings_for(job, index).get('model', '')})
    images = sum(bool(scene["image_url"]) for scene in scenes)
    remote, meta, local = stored_remote, stored_meta, stored_local
    voice = safe_asset(folder, job.get("voice_path"), {".mp3", ".wav", ".mp4"})
    final = safe_asset(folder, job.get("video_path"), {".mp4", ".webm", ".mov", ".mkv"})
    review = voice_review(job)
    locked = voice_locked(job)
    video_mode = job.get("video_generation_mode") or "image_motion"
    selected_video_count = sum(
        1 for scene in scenes
        if scene["source"] == ("meta" if video_mode == "meta_ai" else "flow")
        or (video_mode == "google_flow" and scene["source"] == "local")
    )
    if has_video_plan(job):
        selected_video_count = video_plan['counts']['completed']
        remote, meta, local = (video_plan['counts'][key] for key in ('flow', 'meta', 'local'))
    stages = [
        {"label": "บทเรื่อง", "ready": bool(job.get("narration_script")), "detail": "มีบทแล้ว" if job.get("narration_script") else "รอ AI"},
        {"label": "ภาพ", "ready": bool(scenes) and images == len(scenes), "detail": f"{images}/{len(scenes)} ฉาก"},
        {"label": "เสียง", "ready": bool(voice), "detail": "มีไฟล์แล้ว" if voice else "ตรวจคำอ่านก่อน" if not review["ready"] else "บทพร้อมสร้างเสียง"},
        {"label": "ช่วงวิดีโอ", "ready": selected_video_count == len(scenes) if video_mode in {"google_flow", "meta_ai"} and scenes else bool(final),
         "detail": f"ผู้สร้างที่เลือก {selected_video_count}/{len(scenes)} • เก็บไว้ Flow {remote} • Meta {meta} • ในเครื่อง {local}"},
        {"label": "Final", "ready": bool(final) and job.get("video_status") == "ready", "detail": "มีไฟล์แล้ว" if final else "ยังไม่มีไฟล์ Final"},
    ]
    return {"job_id": job["id"], "revision": int(job.get("revision") or 0), "title": job.get("video_title") or job.get("topic"),
            "visual_style": job.get("visual_style") or "auto", "updated_at": job.get("updated_at") or "",
            "video_generation_mode": video_mode, "flow_clip_count": remote, "meta_clip_count": meta,
            "long_video": bool(job.get('long_video')),
            "meta_landscape_available": meta_landscape_available(),
            "video_plan": video_plan,
            "video_provider_editable": (not has_video_plan(job) and video_mode in {'google_flow', 'meta_ai'} and not active and job.get("status") not in {"running", "recovering", "cancelled", "deleted"}
                and job.get("video_status") not in {"ready", "complete", "completed"}
                and not any(job.get(key) for key in ("video_path", "final_path", "final_video_path"))),
            "active": active, "editable": not active and not locked and job.get("status") not in {"running", "recovering", "cancelled", "deleted"},
            "locked_reason": "มีคำขอเสียงหรือไฟล์เสียงแล้ว ไม่แก้คำอ่านทับงานที่จ่ายแล้ว" if locked else "รอหยุดงานก่อนแก้ไข" if active else "",
            "user_notes": dict(job.get("user_pronunciation_notes") or {}), "effective_notes": pronunciation_notes(job),
            "voice_review": review, "scenes": scenes, "stages": stages,
            "content_review": story_content_review(job),
            "image_result_review": story_image_result_review(job.get("last_error")),
            "last_error": str(job.get("last_error") or "")}
