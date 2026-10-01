import json
import math
import os
import subprocess
from pathlib import Path

from core.cancellable_process import check_cancelled, hidden_process_kwargs
from core.render_backend import run_render as run_cancellable, resolve_fps
from core.video_logo import VideoLogoError, locate_ffmpeg


class StoryVideoComposer:
    """Turn a coherent image sequence into an intentional vertical Story Short."""

    def __init__(self, ffmpeg_path=""):
        self.ffmpeg = locate_ffmpeg(ffmpeg_path)
        probe_name = "ffprobe.exe" if self.ffmpeg.suffix.lower() == ".exe" else "ffprobe"
        self.ffprobe = self.ffmpeg.with_name(probe_name)

    def duration(self, path):
        result = subprocess.run([str(self.ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, **hidden_process_kwargs())
        if result.returncode:
            raise VideoLogoError("อ่านระยะเวลาเสียงไม่สำเร็จ")
        return float((json.loads(result.stdout or "{}").get("format") or {}).get("duration") or 0)

    def render_scene_motion_clip(
        self, image_path, output_path, duration=5.0, width=720, height=1280,
        fps=30, crf=18, motion_strength=0.55, cancel_event=None,
    ):
        """Render one explicit local-motion fallback clip from a Story still.

        This helper intentionally does not label the result as a Google Flow
        clip.  StoryManager keeps it in a separate checkpoint map so a hybrid
        Story remains truthful about which scenes came from Flow.
        """
        check_cancelled(cancel_event)
        image = Path(image_path)
        if not image.is_file() or image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("ไม่พบรูปฉากสำหรับสร้างคลิปสำรอง")
        width, height, fps = int(width), int(height), resolve_fps(fps)
        if width < 360 or height < 640 or width % 2 or height % 2:
            raise ValueError("ความละเอียดวิดีโอต้องเป็นเลขคู่และอย่างน้อย 360 × 640")
        if fps not in {24, 30, 50, 60}:
            raise ValueError("FPS ต้องเป็น 24, 30, 50 หรือ 60")
        seconds = max(2.0, min(12.0, float(duration or 5.0)))
        crf = max(14, min(28, int(crf)))
        motion_strength = max(0.0, min(1.0, float(motion_strength)))
        frames = max(1, round(seconds * fps))
        zoom_delta = 0.055 * motion_strength
        progress_denominator = max(1, frames - 1)
        zoom = f"1+{zoom_delta:.6f}*(0.5-0.5*cos(PI*on/{progress_denominator}))"
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.rendering{output.suffix}")
        video_filter = (
            f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,"
            f"crop={width*2}:{height*2},"
            f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={width}x{height}:fps={fps},"
            "setsar=1,format=yuv420p"
        )
        level = "4.2" if width >= 1080 and fps >= 50 else "4.1"
        command = [
            str(self.ffmpeg), "-y", "-i", str(image), "-vf", video_filter,
            "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "medium",
            "-crf", str(crf), "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-level:v", level, "-movflags", "+faststart", str(temporary),
        ]
        try:
            result = run_cancellable(command, cancel_event=cancel_event, timeout=900)
            if result.returncode or not temporary.is_file() or not temporary.stat().st_size:
                raise VideoLogoError("สร้างคลิปสำรองจากภาพนิ่งไม่สำเร็จ: " + result.stderr[-900:])
            check_cancelled(cancel_event)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "output": str(output), "duration": self.duration(output),
            "source_type": "story_local_motion_fallback", "width": width,
            "height": height, "fps": fps, "crf": crf,
            "motion_strength": motion_strength,
        }

    def compose(
        self, image_paths, output_path, durations=None, voice_path="", width=720, height=1280,
        fps=30, crf=18, motion_strength=1.0, transition_sec=0.22, cancel_event=None,
        min_images=5, fade_edges=True,
    ):
        check_cancelled(cancel_event)
        width, height, fps = int(width), int(height), resolve_fps(fps)
        if width < 360 or height < 640 or width % 2 or height % 2:
            raise ValueError("ความละเอียดวิดีโอต้องเป็นเลขคู่และอย่างน้อย 360 × 640")
        if fps not in {24, 30, 50, 60}:
            raise ValueError("FPS ต้องเป็น 24, 30, 50 หรือ 60")
        crf = max(14, min(28, int(crf)))
        motion_strength = max(0.0, min(1.5, float(motion_strength)))
        requested_transition = max(0.0, min(0.6, float(transition_sec)))
        images = [Path(item) for item in image_paths]
        if len(images) < min_images or any(not item.is_file() for item in images):
            raise ValueError(f"โหมดเรื่องเล่าต้องมีรูปจริงอย่างน้อย {min_images} ฉาก")
        durations = list(durations or [5.0] * len(images))
        if len(durations) != len(images):
            durations = [5.0] * len(images)
        voice = Path(voice_path) if voice_path else None
        if voice and not voice.is_file():
            raise ValueError("ไม่พบไฟล์เสียงพากย์เรื่องเล่า")
        if voice:
            voice_duration = self.duration(voice)
            if voice_duration > 0:
                unit = voice_duration / len(images)
                durations = [unit] * len(images)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.rendering{output.suffix}")
        timeline = []
        for image, seconds in zip(images, durations):
            repeats = max(1, math.ceil(float(seconds) / 6.0))
            timeline.extend((image, float(seconds) / repeats) for _ in range(repeats))
        transition = min(requested_transition, min(seconds for _, seconds in timeline) * 0.45) if len(timeline) > 1 else 0.0
        inputs, filters, segments = [], [], []
        for index, (image, seconds) in enumerate(timeline):
            render_seconds = float(seconds) + (transition if transition and index < len(timeline) - 1 else 0.0)
            frames = max(1, round(render_seconds * fps))
            # A still image already produces one frame.  zoompan expands that
            # single frame to the requested duration.  Combining -loop 1 with
            # zoompan d=frames would expand every looped frame again, leaving
            # later scenes outside the final voice duration and appearing black.
            inputs.extend(["-i", str(image)])
            zoom_delta = 0.085 * motion_strength
            progress_denominator = max(1, frames - 1)
            if index % 2 == 0:
                direction = f"1+{zoom_delta:.6f}*(0.5-0.5*cos(PI*on/{progress_denominator}))"
            else:
                direction = f"1+{zoom_delta:.6f}*(0.5+0.5*cos(PI*on/{progress_denominator}))"
            edge_fades = ""
            if fade_edges and index == 0:
                edge_fades += ",fade=t=in:st=0:d=0.25"
            if fade_edges and index == len(timeline) - 1:
                edge_fades += f",fade=t=out:st={max(0.1, float(seconds)-0.35):.3f}:d=0.35"
            filters.append(
                f"[{index}:v]scale={width*2}:{height*2}:force_original_aspect_ratio=increase,"
                f"crop={width*2}:{height*2},zoompan=z='{direction}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s={width}x{height}:fps={fps}{edge_fades},setsar=1,format=yuv420p[v{index}]"
            )
            segments.append(f"[v{index}]")
        if transition > 0 and len(timeline) > 1:
            current = "[v0]"
            elapsed = float(timeline[0][1])
            for index in range(1, len(timeline)):
                output_label = "vstory" if index == len(timeline) - 1 else f"vx{index}"
                filters.append(f"{current}[v{index}]xfade=transition=fade:duration={transition:.3f}:offset={elapsed:.3f}[{output_label}]")
                current = f"[{output_label}]"
                elapsed += float(timeline[index][1])
        else:
            filters.append("".join(segments) + f"concat=n={len(timeline)}:v=1:a=0[vstory]")
        if voice:
            inputs.extend(["-i", str(voice)])
        command = [str(self.ffmpeg), "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[vstory]"]
        if voice:
            command.extend(["-map", f"{len(timeline)}:a", "-c:a", "aac", "-b:a", "192k", "-shortest"])
        level = "4.2" if width >= 1080 and fps >= 50 else "4.1"
        command.extend(["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", level, "-movflags", "+faststart", str(temporary)])
        try:
            result = run_cancellable(command, cancel_event=cancel_event, timeout=3600)
            if result.returncode or not temporary.is_file() or not temporary.stat().st_size:
                raise VideoLogoError("สร้าง Story Short ไม่สำเร็จ: " + result.stderr[-900:])
            check_cancelled(cancel_event)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return {"output": str(output), "scene_count": len(images), "visual_segment_count": len(timeline), "duration": self.duration(output), "voice_included": bool(voice), "source_type": "story_image_sequence", "width": width, "height": height, "fps": fps, "crf": crf, "motion_strength": motion_strength, "transition_sec": transition}
