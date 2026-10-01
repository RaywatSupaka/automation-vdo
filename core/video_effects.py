import json
import os
import subprocess
import tempfile
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs
from core.render_backend import run_render
from core.video_logo import VideoLogoError, locate_ffmpeg


EFFECT_PRESETS = {
    "neon_focus": "นีออนโฟกัส",
    "clean_store": "คลีนสโตร์",
    "dynamic_sale": "ไดนามิกเซล",
}


class ProductEffectsRenderer:
    """Burn deterministic animated sales graphics onto a video using ASS vectors."""

    def __init__(self, ffmpeg_path=""):
        self.ffmpeg = locate_ffmpeg(ffmpeg_path)
        probe_name = "ffprobe.exe" if self.ffmpeg.suffix.lower() == ".exe" else "ffprobe"
        self.ffprobe = self.ffmpeg.with_name(probe_name)
        if not self.ffprobe.is_file():
            raise VideoLogoError("ไม่พบ FFprobe สำหรับสร้างเอฟเฟกต์")

    def video_info(self, source_path):
        command = [
            str(self.ffprobe), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:format=duration", "-of", "json", str(source_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, **hidden_process_kwargs())
        if result.returncode:
            raise VideoLogoError("อ่านข้อมูลวิดีโอไม่สำเร็จ: " + result.stderr.strip()[-500:])
        data = json.loads(result.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        return {
            "width": int(stream.get("width") or 0),
            "height": int(stream.get("height") or 0),
            "duration": float((data.get("format") or {}).get("duration") or 0),
        }

    @staticmethod
    def validate_options(preset, accent_color, target_x_percent, target_y_percent, intensity):
        preset = str(preset or "neon_focus")
        if preset not in EFFECT_PRESETS:
            raise ValueError("รูปแบบเอฟเฟกต์ไม่ถูกต้อง")
        color = str(accent_color or "#2AD8F2").strip().upper()
        if len(color) != 7 or not color.startswith("#"):
            raise ValueError("สีเอฟเฟกต์ต้องอยู่ในรูปแบบ #RRGGBB")
        try:
            int(color[1:], 16)
        except ValueError as exc:
            raise ValueError("สีเอฟเฟกต์ไม่ถูกต้อง") from exc
        x, y = float(target_x_percent), float(target_y_percent)
        if not 10 <= x <= 90 or not 15 <= y <= 90:
            raise ValueError("ตำแหน่งสินค้าอยู่นอกพื้นที่ปลอดภัย")
        intensity = int(intensity)
        if not 1 <= intensity <= 3:
            raise ValueError("ระดับเอฟเฟกต์ต้องอยู่ระหว่าง 1-3")
        return preset, color, x, y, intensity

    @staticmethod
    def _ass_color(hex_color):
        value = hex_color.lstrip("#")
        return f"&H00{value[4:6]}{value[2:4]}{value[0:2]}"

    @staticmethod
    def _ass_time(seconds):
        seconds = max(0.0, float(seconds))
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        whole = int(seconds % 60)
        centiseconds = int(round((seconds - int(seconds)) * 100))
        if centiseconds >= 100:
            whole += 1
            centiseconds = 0
        return f"{hours}:{minutes:02d}:{whole:02d}.{centiseconds:02d}"

    @staticmethod
    def _dialogue(layer, start, end, style, text):
        return f"Dialogue: {layer},{ProductEffectsRenderer._ass_time(start)},{ProductEffectsRenderer._ass_time(end)},{style},,0,0,0,,{text}"

    def _ass_script(self, width, height, duration, preset, accent_color, target_x_percent, target_y_percent, intensity, labels=None):
        accent = self._ass_color(accent_color)
        target_x = round(width * target_x_percent / 100)
        target_y = round(height * target_y_percent / 100)
        radius = round(min(width, height) * (0.18 + intensity * 0.018))
        border = 4 + intensity * 2
        labels = list(labels or ["ภาพรวมสินค้า", "ดูรายละเอียดใกล้ ๆ", "พร้อมออกทริป"])
        while len(labels) < 3:
            labels.append("จุดเด่นสินค้า")
        segment = duration / 3
        lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {width}",
            f"PlayResY: {height}",
            "ScaledBorderAndShadow: yes",
            "WrapStyle: 2",
            "",
            "[V4+ Styles]",
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
            "Style: ThaiUI,Leelawadee UI,42,&H00FFFFFF,&H000000FF,&H00231938,&H90070A16,-1,0,0,0,100,100,0,0,1,2,0,7,28,28,28,1",
            "Style: Arrow,Segoe UI Symbol,84,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,5,0,0,0,1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]
        for index in range(3):
            start = index * segment
            end = duration if index == 2 else (index + 1) * segment
            card_width = min(390, width - 56)
            card = f"{{\\an7\\pos(28,52)\\p1\\bord0\\shad0\\1c&H0018122C&\\1a&H28&\\fad(260,260)}}m 0 0 l {card_width} 0 l {card_width} 76 l 0 76"
            lines.append(self._dialogue(1, start + 0.15, min(end, start + 4.8), "ThaiUI", card))
            label = str(labels[index]).replace("{", "").replace("}", "")[:40]
            label_text = f"{{\\an7\\pos(50,68)\\fs34\\c{accent}\\bord0\\shad0\\fad(300,250)}}{label}"
            lines.append(self._dialogue(3, start + 0.2, min(end, start + 4.7), "ThaiUI", label_text))

            for pulse_start in (start + 0.75, start + segment * 0.55):
                pulse_end = min(end - 0.15, pulse_start + 2.5)
                if pulse_end <= pulse_start:
                    continue
                circle = (
                    f"{{\\an7\\pos({target_x-radius},{target_y-radius})\\p1\\bord{border}\\shad0"
                    f"\\1a&HFF&\\3c{accent}\\3a&H18&\\fad(260,420)"
                    f"\\t(0,1000,\\fscx112\\fscy112)\\t(1000,2100,\\fscx100\\fscy100)}}"
                    f"m {radius} 0 b {round(radius*1.55)} 0 {radius*2} {round(radius*.45)} {radius*2} {radius} "
                    f"b {radius*2} {round(radius*1.55)} {round(radius*1.55)} {radius*2} {radius} {radius*2} "
                    f"b {round(radius*.45)} {radius*2} 0 {round(radius*1.55)} 0 {radius} "
                    f"b 0 {round(radius*.45)} {round(radius*.45)} 0 {radius} 0"
                )
                lines.append(self._dialogue(2, pulse_start, pulse_end, "ThaiUI", circle))
                arrow_x = min(width - 80, target_x + radius + 68)
                arrow_y = max(130, target_y - radius - 80)
                arrow = f"{{\\an5\\pos({arrow_x},{arrow_y})\\fs{76 + intensity*8}\\c{accent}\\3c&H0010182F&\\fad(220,350)\\t(0,900,\\fscx118\\fscy118)\\t(900,1800,\\fscx100\\fscy100)}}↙"
                lines.append(self._dialogue(4, pulse_start + 0.15, pulse_end, "Arrow", arrow))

            scan_start = start + 1.0
            scan_end = min(end - 0.2, scan_start + 2.8)
            scan = f"{{\\an7\\move({target_x-radius},{target_y-radius},{target_x-radius},{target_y+radius})\\p1\\bord0\\1c{accent}\\1a&H55&\\fad(200,300)}}m 0 0 l {radius*2} 0 l {radius*2} 3 l 0 3"
            lines.append(self._dialogue(2, scan_start, scan_end, "ThaiUI", scan))

            if index > 0:
                wipe = f"{{\\an7\\move({width},0,{-width},0)\\p1\\bord0\\1c{accent}\\1a&H70&\\fad(80,120)}}m 0 0 l {round(width*.32)} 0 l {round(width*.20)} {height} l 0 {height}"
                lines.append(self._dialogue(8, start, min(duration, start + 0.48), "ThaiUI", wipe))

        cta_start = max(0, duration - 5.2)
        cta_bg = f"{{\\an7\\pos(34,{height-150})\\p1\\bord0\\1c&H0018122C&\\1a&H20&\\fad(320,450)}}m 0 0 l {width-68} 0 l {width-68} 90 l 0 90"
        cta_text = f"{{\\an8\\pos({width//2},{height-118})\\fs32\\c{accent}\\bord0\\fad(350,450)}}ตรวจรายละเอียดก่อนสั่งซื้อ"
        lines.append(self._dialogue(5, cta_start, duration - 0.1, "ThaiUI", cta_bg))
        lines.append(self._dialogue(6, cta_start + 0.12, duration - 0.1, "ThaiUI", cta_text))
        return "\n".join(lines) + "\n"

    def render(self, source_path, output_path, preset="neon_focus", accent_color="#2AD8F2", target_x_percent=50, target_y_percent=56, intensity=2, labels=None, crf=18):
        preset, accent_color, target_x_percent, target_y_percent, intensity = self.validate_options(preset, accent_color, target_x_percent, target_y_percent, intensity)
        crf = max(14, min(28, int(crf)))
        source, output = Path(source_path), Path(output_path)
        if not source.is_file() or source.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi"}:
            raise ValueError("ไฟล์วิดีโอไม่ถูกต้อง")
        info = self.video_info(source)
        if info["width"] <= 0 or info["height"] <= 0 or info["duration"] <= 0:
            raise VideoLogoError("ข้อมูลวิดีโอไม่สมบูรณ์")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.effects{output.suffix}")
        with tempfile.TemporaryDirectory(prefix="smartpost-effects-") as temp:
            temp_path = Path(temp)
            ass_path = temp_path / "effects.ass"
            ass_path.write_text(self._ass_script(info["width"], info["height"], info["duration"], preset, accent_color, target_x_percent, target_y_percent, intensity, labels), encoding="utf-8-sig")
            command = [
                str(self.ffmpeg), "-y", "-i", str(source), "-vf", "ass='" + str(ass_path).replace('\\', '/').replace(':', '\\:').replace("'", "\\'") + "'",
                "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.2",
                "-c:a", "copy", "-movflags", "+faststart", str(temporary),
            ]
            try:
                result = run_render(command, timeout=3600, duration=info['duration'], label='ใส่เอฟเฟกต์สินค้า')
                if result.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
                    raise VideoLogoError("สร้างเอฟเฟกต์วิดีโอไม่สำเร็จ: " + result.stderr.strip()[-900:])
                os.replace(temporary, output)
            finally:
                temporary.unlink(missing_ok=True)
        return {
            "output": output,
            "source": source,
            "crf": crf,
            "preset": preset,
            "preset_label": EFFECT_PRESETS[preset],
            "accent_color": accent_color,
            "target_x_percent": target_x_percent,
            "target_y_percent": target_y_percent,
            "intensity": intensity,
            "duration": info["duration"],
        }
