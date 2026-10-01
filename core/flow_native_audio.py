"""Local-only composition of saved scenes; never invokes a provider or TTS."""
import json
import math
import uuid
from pathlib import Path

from core.cancellable_process import check_cancelled
from core.render_backend import run_render as run_cancellable, resolve_fps
from core.video_composer import MultiFlowComposer
from core.studio_review import scene_asset


def inspect_clips(clips, ffmpeg_path="", cancel_event=None):
    composer = MultiFlowComposer(ffmpeg_path)
    result = []
    for path in clips:
        path = Path(path)
        probe = run_cancellable([str(composer.ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], cancel_event=cancel_event, timeout=30)
        if probe.returncode:
            raise ValueError(f"อ่านคลิปไม่ได้: {path.name}")
        info = json.loads(probe.stdout)
        videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
        duration = float((videos[0].get("duration") if videos else None) or info.get("format", {}).get("duration") or 0)
        if not videos or not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"คลิปไม่มีภาพหรือระยะเวลาไม่ถูกต้อง: {path.name}")
        result.append({"path": str(path), "duration": duration, "has_audio": any(s.get("codec_type") == "audio" for s in info.get("streams", []))})
    return result


def saved_story_clips(folder, job):
    count = int(job.get("scene_count") or 0)
    if count < 1:
        raise ValueError("งานไม่มีฉาก")
    clips = []
    for index in range(1, count + 1):
        clip = scene_asset(folder, job, index, "flow") or scene_asset(folder, job, index, "local")
        if clip is None:
            raise ValueError(f"ฉาก {index} ยังไม่มีคลิปที่บันทึกไว้ • ไม่สร้างหรือดาวน์โหลดซ้ำ")
        clips.append(clip)
    return clips


def compose_native(clips, output, ffmpeg_path="", *, width=720, height=1280,
                   fps=30, crf=18, keep_audio=True, allow_silent=False, video_audio_volume=100, cancel_event=None, silent_scene_indices=None):
    from core.media_audio import video_audio_volume as validate_volume
    gain = validate_volume(video_audio_volume) / 100
    output = Path(output)
    if output.exists():
        raise ValueError("ไฟล์ผลลัพธ์มีอยู่แล้ว ไม่เขียนทับ")
    if not clips:
        raise ValueError("ไม่มีคลิปให้รวม")
    width, height = int(width), int(height)
    if min(width, height) < 240 or width % 2 or height % 2:
        raise ValueError("ขนาดภาพต้องเป็นเลขคู่และอย่างน้อย 240 พิกเซล")
    fps = resolve_fps(fps, clips, MultiFlowComposer(ffmpeg_path).ffprobe, cancel_event)
    if not 1 <= fps <= 120:
        raise ValueError("FPS ต้องเป็น 24, 30, 50 หรือ 60")
    crf = max(14, min(28, int(crf)))
    rows = inspect_clips(clips, ffmpeg_path, cancel_event)
    silent = [i + 1 for i, row in enumerate(rows) if not row["has_audio"]]
    missing_required = [i for i in silent if i not in (silent_scene_indices or [])]
    if keep_audio and missing_required and not allow_silent:
        raise ValueError("ฉากไม่มีแทร็กเสียง: " + ", ".join(map(str, silent)) + " • เลือกยอมรับช่วงเงียบก่อนรวม")
    composer = MultiFlowComposer(ffmpeg_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.mp4")
    inputs, filters, joins = [], [], []
    for i, row in enumerate(rows):
        inputs += ["-i", row["path"]]
        d = row["duration"]
        filters.append(f"[{i}:v:0]setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p,trim=duration={d:.6f}[v{i}]")
        joins.append(f"[v{i}]")
        if keep_audio:
            source = f"[{i}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS,apad" if row["has_audio"] else "anullsrc=r=48000:cl=stereo"
            filters.append(f"{source},atrim=duration={d:.6f},asetpts=PTS-STARTPTS,volume={gain:.4f}[a{i}]")
            joins.append(f"[a{i}]")
    filters.append("".join(joins) + f"concat=n={len(rows)}:v=1:a={int(keep_audio)}[video]" + ("[audio]" if keep_audio else ""))
    command = [str(composer.ffmpeg), "-n", *inputs, "-filter_complex", ";".join(filters), "-map", "[video]"]
    command += ["-map", "[audio]", "-c:a", "aac", "-b:a", "192k"] if keep_audio else ["-an"]
    command += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-profile:v", "high", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)]
    try:
        from core.render_copy import try_native_copy
        copied = try_native_copy(clips, temporary, composer.ffmpeg, composer.ffprobe,
            width, height, fps, keep_audio, gain, cancel_event)
        if not copied:
            temporary.unlink(missing_ok=True)  # Only this invocation's failed fast-path candidate.
            process = run_cancellable(command, cancel_event=cancel_event, timeout=3600,
                duration=sum(r['duration'] for r in rows), label='รวมฉากและเสียงต้นฉบับ')
            if process.returncode:
                raise RuntimeError("รวมเสียงต้นฉบับไม่สำเร็จ: " + (process.stderr or "")[-700:])
        verified = inspect_clips([temporary], ffmpeg_path, cancel_event)[0]
        if abs(verified["duration"] - sum(r["duration"] for r in rows)) > max(.25, len(rows) / fps):
            raise ValueError("ระยะเวลาผลลัพธ์ไม่ตรงคลิปต้นฉบับ")
        if verified["has_audio"] != bool(keep_audio):
            raise ValueError("เสียงผลลัพธ์ไม่ตรงโหมดที่เลือก")
        check_cancelled(cancel_event)
        # rename refuses an existing target on Windows; the user file stays intact.
        temporary.rename(output)
        return {"output": str(output), "duration": verified["duration"], "silent_scenes": silent,
                "audio_mode": "flow_original" if keep_audio else "none", "subtitle_included": False,
                "fps": fps, "crf": crf, "video_encoding": "copy" if copied else "encoded"}
    finally:
        temporary.unlink(missing_ok=True)
