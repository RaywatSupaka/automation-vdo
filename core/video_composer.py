import json
import os
import math
import subprocess
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs, check_cancelled
from core.render_backend import run_render as run_cancellable, resolve_fps
from core.video_logo import VideoLogoError, locate_ffmpeg


class MultiFlowComposer:
    """Normalize and join several Google Flow clips into one vertical sales video."""

    VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}

    def __init__(self, ffmpeg_path=""):
        self.ffmpeg = locate_ffmpeg(ffmpeg_path)
        probe_name = "ffprobe.exe" if self.ffmpeg.suffix.lower() == ".exe" else "ffprobe"
        self.ffprobe = self.ffmpeg.with_name(probe_name)
        if not self.ffprobe.is_file():
            raise VideoLogoError("ไม่พบ FFprobe สำหรับรวมวิดีโอ")

    def media_info(self, path):
        source = Path(path)
        command = [str(self.ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(source)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, **hidden_process_kwargs())
        if result.returncode:
            raise VideoLogoError("อ่านระยะเวลาสื่อไม่สำเร็จ: " + result.stderr.strip()[-400:])
        return {"duration": float((json.loads(result.stdout or "{}").get("format") or {}).get("duration") or 0)}

    def compose(self, clip_paths, output_path, voice_path="", width=720, height=1280, fps=30, crf=18, transition_sec=0.22,
                timing_mode="voice_fit", tail_seconds=0.75, scene_durations=None, extend_mode="smooth", audio_choices=None, cancel_event=None):
        check_cancelled(cancel_event)
        if audio_choices and audio_choices.get("mode") in {"flow_original", "none"}:
            from core.flow_native_audio import compose_native
            import uuid
            candidate = Path(output_path).with_name(f"native-{uuid.uuid4().hex}.mp4")
            try:
                result = compose_native(clip_paths, candidate, str(self.ffmpeg), width=width, height=height,
                    fps=fps, crf=crf, keep_audio=audio_choices["mode"] == "flow_original",
                    allow_silent=audio_choices.get("allow_silent", False), video_audio_volume=audio_choices.get("video_audio_volume",100), cancel_event=cancel_event,
                    silent_scene_indices=audio_choices.get('silent_scene_indices'))
                check_cancelled(cancel_event)
                os.replace(candidate, output_path)
                result.update(output=Path(output_path), voice_duration=0, source_duration=result["duration"], clip_count=len(clip_paths))
                return result
            finally:
                candidate.unlink(missing_ok=True)
        fps = resolve_fps(fps, clip_paths, self.ffprobe, cancel_event)
        width, height = int(width), int(height)
        if width < 360 or height < 640 or width % 2 or height % 2:
            raise ValueError("ความละเอียดวิดีโอต้องเป็นเลขคู่และอย่างน้อย 360 × 640")
        if not 1 <= fps <= 120:
            raise ValueError("FPS ต้องเป็น 24, 30, 50 หรือ 60")
        crf = max(14, min(28, int(crf)))
        clips = [Path(item) for item in clip_paths]
        if not clips:
            raise ValueError("ต้องมีวิดีโออย่างน้อย 1 ช็อตเพื่อรวมคลิป")
        if any(not item.is_file() or item.suffix.lower() not in self.VIDEO_EXTENSIONS for item in clips):
            raise ValueError("มีไฟล์วิดีโอช็อตไม่ถูกต้อง")
        voice = Path(voice_path) if voice_path else None
        if voice and not voice.is_file():
            raise ValueError("ไม่พบไฟล์เสียงพากย์")
        clip_durations = [self.media_info(clip)["duration"] for clip in clips]
        source_duration = sum(clip_durations)
        voice_duration = self.media_info(voice)["duration"] if voice else 0
        if any(not math.isfinite(d) or d <= 0 for d in clip_durations) or (voice and (not math.isfinite(voice_duration) or voice_duration <= 0)):
            raise ValueError("ระยะเวลาภาพหรือเสียงไม่ถูกต้อง")
        if timing_mode not in {"voice_fit", "original"}:
            raise ValueError("รูปแบบจัดเวลาไม่ถูกต้อง")
        fit_voice = bool(voice and timing_mode == "voice_fit")
        if extend_mode not in {"hold", "loop", "smooth"}:
            raise ValueError("รูปแบบต่อความยาวคลิปไม่ถูกต้อง")
        tail_seconds = float(tail_seconds)
        if not math.isfinite(tail_seconds):
            raise ValueError("Invalid video tail duration")
        tail_seconds = min(2.0, max(0.0, tail_seconds))
        weights = list(scene_durations or clip_durations)
        if len(weights) != len(clips) or any(not isinstance(w, (int, float)) or not math.isfinite(w) or w <= 0 for w in weights):
            weights = clip_durations
        target_durations = [voice_duration * w / sum(weights) for w in weights] if fit_voice else []
        if fit_voice:
            target_durations[-1] += tail_seconds
            if min(target_durations) < 0.25:
                raise ValueError("เสียงสั้นเกินไปสำหรับจำนวนฉาก • กรุณาตรวจบทก่อนประกอบ")
        stretch_factor = min(2.0, max(1.0, voice_duration / source_duration)) if source_duration and voice_duration > source_duration else 1.0
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.composing{output.suffix}")
        inputs = []
        filters = []
        concat_inputs = []
        if not fit_voice:
            target_durations = [duration * stretch_factor for duration in clip_durations]
        transition = min(max(0.0, min(0.6, float(transition_sec))), min(target_durations) * 0.45)
        keep_source = bool(audio_choices and audio_choices.get("keep_video_audio"))
        from core.media_audio import video_audio_volume
        source_gain = video_audio_volume((audio_choices or {}).get("video_audio_volume",35 if voice else 100)) / 100
        source_audio = []
        if keep_source:
            from core.flow_native_audio import inspect_clips
            source_audio = inspect_clips(clips, str(self.ffmpeg), cancel_event)
            if (not audio_choices.get("allow_silent") and audio_choices.get('generated_music_version') != 1
                    and any(not row["has_audio"] for row in source_audio)):
                raise ValueError("บางฉากไม่มีเสียงวิดีโอ • เลือกยอมรับช่วงเงียบก่อนรวม")
        for index, clip in enumerate(clips):
            if fit_voice and extend_mode == "loop" and target_durations[index] > clip_durations[index]:
                inputs.extend(["-stream_loop", "-1"])
            inputs.extend(["-i", str(clip)])
            tail = f",tpad=stop_mode=clone:stop_duration={transition:.3f}" if transition and index < len(clips) - 1 else ""
            timing = f"setpts={stretch_factor:.8f}*PTS"
            if fit_voice:
                # Keep EVERY scene. Trim within each clip, never truncate the
                # concatenated story. Explicit legacy hold remains available;
                # the default smooth mode spreads time across source motion.
                factor = min(1.25, max(1.0, target_durations[index] / clip_durations[index]))
                hold = max(0.0, target_durations[index] - clip_durations[index] * factor)
                timing = (f"setpts={factor:.8f}*(PTS-STARTPTS),tpad=stop_mode=clone:stop_duration={hold:.6f},"
                          f"trim=duration={target_durations[index]:.6f},setpts=PTS-STARTPTS")
                if extend_mode == "loop":
                    timing = f"setpts=PTS-STARTPTS,trim=duration={target_durations[index]:.6f},setpts=PTS-STARTPTS"
                if extend_mode == "smooth":
                    # Spread the allocation over real motion, including the
                    # outgoing dissolve. Never append a frozen last frame.
                    extra = transition if index < len(clips) - 1 else 0.0
                    allocated = target_durations[index] + extra
                    factor = max(1.0, allocated / clip_durations[index])
                    timing = (f"setpts={factor:.8f}*(PTS-STARTPTS),"
                              f"trim=duration={allocated:.6f},setpts=PTS-STARTPTS")
                    tail = ""
            filters.append(
                # Flow can ignore a vertical prompt and return 16:9. Filling
                # with black padding produced a technically vertical file whose
                # actual picture occupied only its middle third. Shorts must
                # fill the requested frame; preserve center composition and crop
                # the overflow instead of adding letterbox bars.
                f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}:(iw-ow)/2:(ih-oh)/2,{timing},"
                f"fps={fps},setsar=1,format=yuv420p{tail}[v{index}]"
            )
            concat_inputs.append(f"[v{index}]")
            if keep_source:
                allocated_audio = target_durations[index] + (transition if index < len(clips)-1 else 0)
                speed_factor = (max(1.0, allocated_audio / clip_durations[index]) if fit_voice and extend_mode == "smooth"
                    else min(1.25, max(1.0, target_durations[index]/clip_durations[index])) if fit_voice and extend_mode == "hold"
                    else 1.0 if fit_voice else stretch_factor)
                tempo = 1.0 / speed_factor
                chain=[]
                while tempo < .5:
                    chain.append("atempo=0.5");tempo *= 2
                chain.append(f"atempo={tempo:.8f}")
                audio_input = (f"[{index}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS,"
                    + ",".join(chain) + ",apad") if source_audio[index]["has_audio"] else "anullsrc=r=48000:cl=stereo"
                filters.append(f"{audio_input},atrim=duration={allocated_audio:.6f},asetpts=PTS-STARTPTS[sa{index}]")
        if len(clips) == 1:
            filters.append('[v0]null[vcat]')
        elif transition > 0:
            current = "[v0]"
            elapsed = target_durations[0]
            for index in range(1, len(clips)):
                output_label = "vcat" if index == len(clips) - 1 else f"vx{index}"
                filters.append(f"{current}[v{index}]xfade=transition=fade:duration={transition:.3f}:offset={elapsed:.3f}[{output_label}]")
                current = f"[{output_label}]"
                elapsed += target_durations[index]
        else:
            filters.append("".join(concat_inputs) + f"concat=n={len(clips)}:v=1:a=0[vcat]")
        if voice:
            inputs.extend(["-i", str(voice)])
            voice_index = len(clips)
            padding = f"apad=pad_dur={tail_seconds:.6f}" if fit_voice else "apad"
            filters.append(f"[{voice_index}:a]{padding}[voice]")
        command = [str(self.ffmpeg), "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[vcat]"]
        if keep_source:
            if transition:
                current="sa0"
                for i in range(1,len(clips)):
                    filters.append(f"[{current}][sa{i}]acrossfade=d={transition:.3f}[sx{i}]")
                    current=f"sx{i}"
            else:
                filters.append("".join(f"[sa{i}]" for i in range(len(clips)))+f"concat=n={len(clips)}:v=0:a=1[source_joined]")
                current="source_joined"
            if voice:
                filters.append(f"[{current}]volume={source_gain:.4f}[source_low]")
                filters.append("[voice][source_low]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[mixed_voice]")
            else:
                filters.append(f"[{current}]volume={source_gain:.4f}[mixed_voice]")
            command[command.index("-filter_complex")+1]=";".join(filters)
        if voice:
            command.extend(["-map", "[mixed_voice]" if keep_source else "[voice]", "-c:a", "aac", "-b:a", "192k", "-shortest"])
        elif keep_source:
            command.extend(["-map", "[mixed_voice]", "-c:a", "aac", "-b:a", "192k"])
        if fit_voice:
            command.extend(["-t", f"{voice_duration + tail_seconds:.6f}"])
        level = "4.2" if width >= 1080 and fps >= 50 else "4.1"
        command.extend(["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", level, "-movflags", "+faststart", str(temporary)])
        try:
            result = run_cancellable(command, cancel_event=cancel_event, timeout=3600,
                duration=sum(target_durations), label='ประกอบคลิปและจัดเวลาเสียง')
            check_cancelled(cancel_event)
            if result.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
                raise VideoLogoError("รวมวิดีโอไม่สำเร็จ: " + result.stderr.strip()[-900:])
            measured = self.media_info(temporary)["duration"]
            if fit_voice and abs(measured - (voice_duration + tail_seconds)) > max(0.2, 3 / fps):
                raise VideoLogoError("ระยะเวลาผลลัพธ์ไม่ตรงเสียง • เก็บวิดีโอเดิมไว้ ไม่รับไฟล์ใหม่")
            check_cancelled(cancel_event)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "output": output,
            "clip_count": len(clips),
            "duration": self.media_info(output)["duration"],
            "source_duration": source_duration,
            "voice_duration": voice_duration,
            "timing_mode": timing_mode,
            "extend_mode": extend_mode,
            "timing_method": "planned_scene_weights" if fit_voice and scene_durations else "source_duration_weights" if fit_voice else "original",
            "scene_output_durations": target_durations,
            "tail_seconds": tail_seconds if fit_voice else None,
            "stretch_factor": stretch_factor,
            "voice_included": bool(voice),
            "width": width,
            "height": height,
            "fps": fps,
            "crf": crf,
            "transition_sec": transition,
        }
