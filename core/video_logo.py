import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from core.cancellable_process import check_cancelled, hidden_process_kwargs
from core.render_backend import run_render as run_cancellable
from core.logo_layout import logo_geometry, normalize_logo_layout

class VideoLogoError(RuntimeError):
    pass


POSITIONS = {
    "top_left": "บนซ้าย",
    "top_center": "บนกลาง",
    "top_right": "บนขวา",
    "center_left": "กลางซ้าย",
    "center": "กึ่งกลาง",
    "center_right": "กลางขวา",
    "bottom_left": "ล่างซ้าย",
    "bottom_center": "ล่างกลาง",
    "bottom_right": "ล่างขวา",
}


def locate_ffmpeg(configured_path=""):
    candidates = []
    bundled = Path(__file__).resolve().parents[1] / "ffmpeg" / "ffmpeg.exe"
    if bundled.is_file():
        candidates.append(bundled)
    if configured_path:
        candidates.append(Path(configured_path))
    from_path = shutil.which("ffmpeg")
    if from_path:
        candidates.append(Path(from_path))
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    if str(local_app_data):
        candidates.extend((
            local_app_data / "SmartSubAI" / "VoiceCloneOnline" / "ffmpeg" / "bin" / "ffmpeg.exe",
            local_app_data / "SmartSubAI" / "ffmpeg" / "bin" / "ffmpeg.exe",
        ))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise VideoLogoError("ไม่พบ FFmpeg กรุณาติดตั้ง FFmpeg หรือกำหนด ffmpeg_path ใน config.json")


class VideoLogoRenderer:
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}
    LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

    def __init__(self, ffmpeg_path=""):
        self.ffmpeg = locate_ffmpeg(ffmpeg_path)
        probe_name = "ffprobe.exe" if self.ffmpeg.suffix.lower() == ".exe" else "ffprobe"
        self.ffprobe = self.ffmpeg.with_name(probe_name)
        if not self.ffprobe.is_file():
            found = shutil.which("ffprobe")
            if not found:
                raise VideoLogoError("ไม่พบ FFprobe ที่ใช้ตรวจขนาดวิดีโอ")
            self.ffprobe = Path(found)

    @staticmethod
    def validate_options(opacity, size_percent, position, margin):
        opacity = float(opacity)
        size_percent = float(size_percent)
        margin = int(margin)
        if not 0.05 <= opacity <= 1.0:
            raise ValueError("ความทึบของโลโก้ต้องอยู่ระหว่าง 5-100 เปอร์เซ็นต์")
        if not 3 <= size_percent <= 60:
            raise ValueError("ขนาดโลโก้ต้องอยู่ระหว่าง 3-60 เปอร์เซ็นต์ของความกว้างวิดีโอ")
        if position not in POSITIONS:
            raise ValueError("ตำแหน่งโลโก้ไม่ถูกต้อง")
        if not 0 <= margin <= 500:
            raise ValueError("ระยะขอบต้องอยู่ระหว่าง 0-500 พิกเซล")
        return opacity, size_percent, position, margin

    def video_info(self, source_path):
        source = Path(source_path)
        if not source.is_file() or source.suffix.lower() not in self.VIDEO_EXTENSIONS:
            raise ValueError("ไฟล์วิดีโอไม่ถูกต้อง")
        command = [
            str(self.ffprobe), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration", "-of", "json", str(source),
        ]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, **hidden_process_kwargs())
        if result.returncode:
            raise VideoLogoError("อ่านข้อมูลวิดีโอไม่สำเร็จ: " + result.stderr.strip()[-500:])
        data = json.loads(result.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
        if width <= 0 or height <= 0:
            raise VideoLogoError("ไม่พบขนาดภาพของวิดีโอ")
        return {"width": width, "height": height, "duration": float((data.get("format") or {}).get("duration") or 0)}

    @staticmethod
    def _position(video_width, video_height, logo_width, logo_height, position, margin):
        left = margin
        center_x = max(0, (video_width - logo_width) // 2)
        right = max(0, video_width - logo_width - margin)
        top = margin
        center_y = max(0, (video_height - logo_height) // 2)
        bottom = max(0, video_height - logo_height - margin)
        x = {"left": left, "center": center_x, "right": right}[position.rsplit("_", 1)[-1] if "_" in position else "center"]
        if position.startswith("top"):
            y = top
        elif position.startswith("bottom"):
            y = bottom
        else:
            y = center_y
        return x, y

    @staticmethod
    def _logo_image(logo_path, video_width, opacity, size_percent):
        source = Path(logo_path)
        if not source.is_file() or source.suffix.lower() not in VideoLogoRenderer.LOGO_EXTENSIONS:
            raise ValueError("รองรับโลโก้ PNG, JPG, JPEG หรือ WEBP เท่านั้น")
        with Image.open(source) as opened:
            logo = opened.convert("RGBA")
        target_width = max(8, round(video_width * size_percent / 100))
        target_height = max(1, round(logo.height * target_width / logo.width))
        logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)
        alpha = logo.getchannel("A").point(lambda value: round(value * opacity))
        logo.putalpha(alpha)
        return logo

    def prepare_overlay(self, logo_path, width, height, opacity, size_percent, position, margin, layout=None):
        opacity, size_percent, position, margin = self.validate_options(opacity, size_percent, position, margin)
        layout = normalize_logo_layout(layout)
        if layout is None:
            logo = self._logo_image(logo_path, width, opacity, size_percent)
            x, y = self._position(width, height, logo.width, logo.height, position, margin)
            return logo, x, y
        source = Path(logo_path)
        if not source.is_file() or source.suffix.lower() not in self.LOGO_EXTENSIONS:
            raise ValueError("รองรับโลโก้ PNG, JPG, JPEG หรือ WEBP เท่านั้น")
        with Image.open(source) as opened:
            logo = opened.convert('RGBA')
        rect = logo_geometry(layout, width, height, logo.width, logo.height)
        logo = logo.resize((rect['width'], rect['height']), Image.Resampling.LANCZOS)
        logo.putalpha(logo.getchannel('A').point(lambda value: round(value * opacity)))
        return logo, rect['x'], rect['y']

    def compose_preview(self, frame, logo_path, opacity=0.8, size_percent=18, position="bottom_right", margin=28, layout=None):
        opacity, size_percent, position, margin = self.validate_options(opacity, size_percent, position, margin)
        base = frame.convert("RGBA")
        logo, x, y = self.prepare_overlay(logo_path, base.width, base.height, opacity, size_percent, position, margin, layout)
        base.alpha_composite(logo, (x, y))
        return base.convert("RGB")

    def extract_preview_frame(self, source_path, at_seconds=0.5):
        source = Path(source_path)
        self.video_info(source)
        with tempfile.TemporaryDirectory(prefix="smartpost-logo-preview-") as temp:
            target = Path(temp) / "frame.png"
            command = [
                str(self.ffmpeg), "-y", "-ss", str(max(0, float(at_seconds))), "-i", str(source),
                "-frames:v", "1", "-update", "1", str(target),
            ]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90, **hidden_process_kwargs())
            if result.returncode or not target.is_file():
                raise VideoLogoError("สร้างภาพตัวอย่างไม่สำเร็จ: " + result.stderr.strip()[-500:])
            with Image.open(target) as opened:
                return opened.convert("RGB").copy()

    def render(self, source_path, logo_path, output_path, opacity=0.8, size_percent=18, position="bottom_right", margin=28, cancel_event=None, crf=18, layout=None):
        check_cancelled(cancel_event)
        opacity, size_percent, position, margin = self.validate_options(opacity, size_percent, position, margin)
        crf = max(14, min(28, int(crf)))
        source, output = Path(source_path), Path(output_path)
        info = self.video_info(source)
        layout = normalize_logo_layout(layout)
        logo, x, y = self.prepare_overlay(logo_path, info['width'], info['height'], opacity, size_percent, position, margin, layout)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = output.with_name(f".{output.stem}.rendering{output.suffix}")
        with tempfile.TemporaryDirectory(prefix="smartpost-logo-render-") as temp:
            prepared_logo = Path(temp) / "logo.png"
            logo.save(prepared_logo, "PNG")
            command = [
                str(self.ffmpeg), "-y", "-i", str(source), "-i", str(prepared_logo),
                "-filter_complex", f"[0:v][1:v]overlay={x}:{y}:format=auto[v]",
                "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.2",
                "-c:a", "copy", "-movflags", "+faststart", str(temporary_output),
            ]
            try:
                result = run_cancellable(command, cancel_event=cancel_event, timeout=3600,
                    duration=info['duration'], label='ใส่โลโก้')
                if result.returncode or not temporary_output.is_file() or temporary_output.stat().st_size == 0:
                    raise VideoLogoError("ใส่โลโก้ในวิดีโอไม่สำเร็จ: " + result.stderr.strip()[-800:])
                os.replace(temporary_output, output)
            finally:
                temporary_output.unlink(missing_ok=True)
        return {
            "output": output,
            "source": source,
            "logo": Path(logo_path),
            "opacity": opacity,
            "size_percent": size_percent,
            "crf": crf,
            "position": position,
            "position_label": "ตำแหน่งที่จัดวาง" if layout else POSITIONS[position],
            **({'layout': layout} if layout else {}),
            "margin": margin,
            "video_width": info["width"],
            "video_height": info["height"],
            "duration": info["duration"],
        }
