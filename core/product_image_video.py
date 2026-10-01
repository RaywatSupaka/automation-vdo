import json
import math
import os
from pathlib import Path

from core.cancellable_process import check_cancelled
from core.render_backend import run_render as run_cancellable, resolve_fps
from core.video_logo import VideoLogoError, locate_ffmpeg


class ProductImageVideoComposer:
    """Create a deterministic product video from the approved three-image set."""

    IMAGE_COUNT = 3

    def __init__(self, ffmpeg_path=""):
        self.ffmpeg = locate_ffmpeg(ffmpeg_path)
        probe_name = "ffprobe.exe" if self.ffmpeg.suffix.lower() == ".exe" else "ffprobe"
        self.ffprobe = self.ffmpeg.with_name(probe_name)
        if not self.ffprobe.is_file():
            raise VideoLogoError("ไม่พบ FFprobe สำหรับสร้างวิดีโอจากรูปสินค้า")

    def duration(self, path, cancel_event=None):
        result = run_cancellable([
            str(self.ffprobe), "-v", "error", "-show_entries", "format=duration",
            "-of", "json", str(path),
        ], cancel_event=cancel_event, timeout=30)
        if result.returncode:
            raise VideoLogoError("อ่านระยะเวลาเสียงหรือวิดีโอไม่สำเร็จ")
        return float((json.loads(result.stdout or "{}").get("format") or {}).get("duration") or 0)

    def render_motion_segment(
        self, image_path, output_path, duration=10.0, width=720, height=1280,
        fps=30, crf=18, motion_strength=0.55, cancel_event=None,
    ):
        """Render one truthful local-motion segment from one Product still.

        This is intentionally a restrained camera move over the exact source
        image.  It does not regenerate, morph or invent product details and it
        is checkpointed separately from genuine Google Flow clips.
        """
        check_cancelled(cancel_event)
        image = Path(image_path)
        if not image.is_file() or image.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("ไม่พบรูปสินค้าสำหรับสร้างคลิปเคลื่อนไหวในเครื่อง")
        width, height, fps = int(width), int(height), resolve_fps(fps)
        if width < 360 or height < 640 or width % 2 or height % 2:
            raise ValueError("ความละเอียดวิดีโอต้องเป็นเลขคู่และอย่างน้อย 360 × 640")
        if fps not in {24, 30, 50, 60}:
            raise ValueError("FPS ต้องเป็น 24, 30, 50 หรือ 60")
        seconds = max(2.0, min(12.0, float(duration or 10.0)))
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
                raise VideoLogoError("สร้างคลิปเคลื่อนไหวจากรูปสินค้าไม่สำเร็จ: " + result.stderr.strip()[-900:])
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "output": str(output),
            "source_type": "product_local_motion_policy_fallback",
            "duration": self.duration(output, cancel_event=cancel_event),
            "width": width,
            "height": height,
            "fps": fps,
            "crf": crf,
            "motion_strength": motion_strength,
            "motion": "deterministic_center_zoom_v1",
        }

    def compose(
        self, image_paths, output_path, voice_path, width=720, height=1280,
        fps=30, crf=18, transition_sec=0.22, cancel_event=None,
    ):
        check_cancelled(cancel_event)
        images = [Path(item) for item in image_paths]
        if len(images) != self.IMAGE_COUNT or any(not item.is_file() for item in images):
            raise ValueError("Local Product fallback ต้องใช้รูปสินค้าจริงครบ 3 รูป")
        if len({item.resolve() for item in images}) != self.IMAGE_COUNT:
            raise ValueError("Local Product fallback ห้ามใช้ไฟล์รูปซ้ำกัน")
        voice = Path(voice_path)
        if not voice.is_file():
            raise ValueError("Local Product fallback ต้องใช้เสียงพากย์เดิมที่สร้างสำเร็จแล้ว")

        width, height, fps = int(width), int(height), resolve_fps(fps)
        if width < 360 or height < 640 or width % 2 or height % 2:
            raise ValueError("ความละเอียดวิดีโอต้องเป็นเลขคู่และอย่างน้อย 360 × 640")
        if fps not in {24, 30, 50, 60}:
            raise ValueError("FPS ต้องเป็น 24, 30, 50 หรือ 60")
        crf = max(14, min(28, int(crf)))
        transition = max(0.0, min(0.6, float(transition_sec)))
        voice_duration = self.duration(voice, cancel_event=cancel_event)
        if voice_duration <= 0:
            raise ValueError("เสียงพากย์เดิมไม่มีระยะเวลาที่ใช้งานได้")
        seconds_per_image = max(0.8, voice_duration / self.IMAGE_COUNT)
        transition = min(transition, seconds_per_image * 0.35)

        inputs = []
        filters = []
        for index, image in enumerate(images):
            inputs.extend(["-i", str(image)])
            render_seconds = seconds_per_image + (transition if index < self.IMAGE_COUNT - 1 else 0.0)
            frames = max(1, math.ceil(render_seconds * fps))
            progress_denominator = max(1, frames - 1)
            # A restrained centre zoom moves the whole approved frame without
            # warping, morphing, regenerating or inventing any product detail.
            zoom_delta = 0.035
            if index % 2 == 0:
                zoom = f"1+{zoom_delta:.6f}*(0.5-0.5*cos(PI*on/{progress_denominator}))"
            else:
                zoom = f"1+{zoom_delta:.6f}*(0.5+0.5*cos(PI*on/{progress_denominator}))"
            edge_fades = ",fade=t=in:st=0:d=0.20" if index == 0 else ""
            if index == self.IMAGE_COUNT - 1:
                edge_fades += f",fade=t=out:st={max(0.1, seconds_per_image-0.30):.3f}:d=0.30"
            filters.append(
                f"[{index}:v]scale={width*2}:{height*2}:force_original_aspect_ratio=increase,"
                f"crop={width*2}:{height*2},zoompan=z='{zoom}':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s={width}x{height}:fps={fps}{edge_fades},"
                f"setsar=1,format=yuv420p[v{index}]"
            )

        current = "[v0]"
        elapsed = seconds_per_image
        for index in range(1, self.IMAGE_COUNT):
            output_label = "vproduct" if index == self.IMAGE_COUNT - 1 else f"vx{index}"
            filters.append(
                f"{current}[v{index}]xfade=transition=fade:duration={transition:.3f}:"
                f"offset={elapsed:.3f}[{output_label}]"
            )
            current = f"[{output_label}]"
            elapsed += seconds_per_image

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.rendering{output.suffix}")
        command = [
            str(self.ffmpeg), "-y", *inputs, "-i", str(voice),
            "-filter_complex", ";".join(filters),
            "-map", "[vproduct]", "-map", f"{self.IMAGE_COUNT}:a:0",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-level:v", "4.2" if width >= 1080 and fps >= 50 else "4.1",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
            str(temporary),
        ]
        try:
            result = run_cancellable(command, cancel_event=cancel_event, timeout=3600)
            if result.returncode or not temporary.is_file() or not temporary.stat().st_size:
                raise VideoLogoError("สร้างวิดีโอสำรองจากรูปสินค้าไม่สำเร็จ: " + result.stderr.strip()[-900:])
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)

        return {
            "output": str(output),
            "source_type": "product_image_sequence_fallback",
            "image_count": self.IMAGE_COUNT,
            "duration": self.duration(output, cancel_event=cancel_event),
            "voice_duration": voice_duration,
            "voice_included": True,
            "width": width,
            "height": height,
            "fps": fps,
            "crf": crf,
            "transition_sec": transition,
            "motion": "deterministic_center_zoom_v1",
        }
