"""Explicit local Storyboard export, separate from generation and saved finals."""
import copy
import threading
import uuid
from pathlib import Path
from core.flow_native_audio import saved_story_clips, inspect_clips, compose_native
from core.audio_mixer import AudioMixer
from core.cancellable_process import OperationCancelled
from core.job_file_guard import guarded_thread


def native_audio_action(app, action, payload):
    if action == "story_native_status":
        return {"ok": True, "state": copy.deepcopy(getattr(app, "_native_audio_state", {"status": "idle"}))}
    if action == "story_native_cancel":
        if str(payload.get("job_id") or "") != str(getattr(app, "_native_audio_state", {}).get("job_id") or ""):
            raise ValueError("งานไม่ตรงกับการรวมคลิปที่กำลังทำ")
        event = getattr(app, "_native_audio_cancel", None)
        if event:
            event.set()
        return {"ok": True}
    if action == "story_native_open_folder":
        job = app.stories.get(str(payload.get("job_id") or ""))
        target = app.stories._folder(job["id"]) / "videos"
        if not target.is_dir():
            raise ValueError("ยังไม่มีโฟลเดอร์วิดีโอ")
        app._open_folder(target)
        return {"ok": True}
    if app._creation_workers_alive() or app._creation_remote_busy_jobs() or app._story_pipeline_job_id or app._product_pipeline_job_id:
        raise ValueError("มีงานกำลังทำอยู่ กรุณารอให้จบก่อนรวมคลิปเดิม")
    job_id = str(payload.get("job_id") or "")
    job = app.stories.get(job_id)
    folder = app.stories._folder(job_id)
    clips = saved_story_clips(folder, job)
    settings = copy.deepcopy(app.cfg)
    music = payload.get("music", False)
    allow_silent = payload.get("allow_silent", False)
    if not isinstance(music, bool) or not isinstance(allow_silent, bool):
        raise ValueError("ตัวเลือกเสียงไม่ถูกต้อง")
    cancel = threading.Event()
    app._native_audio_cancel = cancel
    state = {"job_id": job_id, "status": "running", "message": "กำลังตรวจคลิปและเสียงต้นฉบับ", "silent_scenes": []}
    app._native_audio_state = state
    root = Path(app.stories.root).parent.parent
    def worker():
        try:
            rows = inspect_clips(clips, settings.get("ffmpeg_path", ""), cancel)
            state["silent_scenes"] = [i + 1 for i, row in enumerate(rows) if not row["has_audio"]]
            if state["silent_scenes"] and not allow_silent:
                state.update(status="needs_confirmation", message="บางฉากไม่มีแทร็กเสียง ตรวจรายการและเลือกยอมรับช่วงเงียบก่อนรวม")
                return
            tag = uuid.uuid4().hex[:12]
            output = folder / "videos" / f"flow_original_{tag}.mp4"
            state["message"] = "กำลังรวมคลิปพร้อมเสียงต้นฉบับ • ไม่เรียก API • ไม่ใส่ซับ"
            landscape = bool(job.get("long_video")) or job.get("aspect_ratio") == "16:9"
            plan = compose_native(clips, output, settings.get("ffmpeg_path", ""), width=1920 if landscape else 720,
                                  height=1080 if landscape else 1280, allow_silent=allow_silent, cancel_event=cancel)
            if music:
                state["message"] = "กำลังเพิ่มเพลงพื้นหลังตามค่าที่บันทึกไว้"
                mixer = AudioMixer(settings.get("ffmpeg_path", ""))
                tracks = mixer.scan_audio(root / "assets" / "audio" / "background")
                if not tracks:
                    raise ValueError("ไม่พบเพลงพื้นหลัง • คลิปรวมเสียงต้นฉบับถูกเก็บไว้แล้วที่ " + str(output))
                mixed = output.with_name(output.stem + "_music.mp4")
                mixer.render(output, mixed, background_files=tracks,
                    background_mode=settings.get("audio_background_mode", "auto"),
                    background_volume=settings.get("audio_background_volume", .12),
                    music_segment_max_sec=settings.get("audio_background_segment_max_sec", 12),
                    music_duck_ratio=float(settings.get("audio_background_duck_percent", 38)) / 100,
                    seed=job_id, cancel_event=cancel)
                plan["output"] = str(mixed)
            state.update(status="complete", message="รวมคลิปด้วยเสียงต้นฉบับแล้ว • เก็บเป็นไฟล์ใหม่ ไม่ทับ Final เดิม", result=plan)
        except OperationCancelled:
            state.update(status="cancelled", message="ยกเลิกการรวมคลิปแล้ว • ไฟล์ต้นฉบับไม่เปลี่ยน")
        except Exception as exc:
            state.update(status="error", message=str(exc))
        finally:
            app.events.put(("log", f"{job_id} • FLOW ORIGINAL AUDIO • {state['status']} • {state['message']}"))
    app._native_audio_worker = guarded_thread(app, job_id, worker, references=(job, settings), daemon=True)
    return {"ok": True, "state": copy.deepcopy(state)}
