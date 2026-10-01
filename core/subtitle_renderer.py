import json
import hashlib
import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from PIL import ImageFont

try:
    from fontTools.ttLib import TTFont
except Exception:
    TTFont = None

from core.video_logo import VideoLogoError, locate_ffmpeg
from core.cancellable_process import check_cancelled, hidden_process_kwargs
from core.render_backend import run_render as run_cancellable

try:
    from pythainlp.tokenize import syllable_tokenize as thai_syllable_tokenize
except Exception:
    thai_syllable_tokenize = None


class SubtitleVideoRenderer:
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}

    def __init__(self, ffmpeg_path=""):
        self.ffmpeg = locate_ffmpeg(ffmpeg_path)
        self.ffprobe = self.ffmpeg.with_name("ffprobe.exe" if self.ffmpeg.suffix.lower() == ".exe" else "ffprobe")

    def _video_size(self, source):
        result = subprocess.run(
            [str(self.ffprobe), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(source)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            **hidden_process_kwargs(),
        )
        try:
            stream = json.loads(result.stdout)["streams"][0]
            width, height = int(stream["width"]), int(stream["height"])
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("อ่านขนาดวิดีโอสำหรับ Subtitle ไม่สำเร็จ") from None
        if width <= 0 or height <= 0:
            raise ValueError("ขนาดวิดีโอสำหรับ Subtitle ไม่ถูกต้อง")
        return width, height

    @staticmethod
    def _filter_path(path):
        value = Path(path).resolve().as_posix().replace("'", r"\'")
        if len(value) > 1 and value[1] == ":":
            value = value[0] + r"\:" + value[2:]
        return value

    @staticmethod
    def _ass_color(value, opacity=1.0):
        value = str(value or "").strip().lstrip("#")
        if len(value) != 6 or any(character not in "0123456789abcdefABCDEF" for character in value):
            raise ValueError("สี Subtitle ต้องอยู่ในรูปแบบ #RRGGBB")
        red, green, blue = value[0:2], value[2:4], value[4:6]
        alpha = round((1 - max(0.0, min(1.0, float(opacity)))) * 255)
        return f"&H{alpha:02X}{blue.upper()}{green.upper()}{red.upper()}"

    @staticmethod
    def _font_family(font_path, fallback):
        if not font_path:
            return str(fallback or "Leelawadee UI"), None, False
        path = Path(font_path).resolve()
        if not path.is_file() or path.suffix.lower() not in {".ttf", ".otf"}:
            raise ValueError("ไม่พบไฟล์ฟอนต์ Subtitle")
        try:
            family, style = ImageFont.truetype(str(path), 24).getname()
        except Exception as exc:
            raise ValueError("FFmpeg ไม่สามารถใช้ไฟล์ฟอนต์นี้ได้") from exc
        embedded_bold = any(token in str(style).lower() for token in ("bold", "semibold", "demibold", "black", "heavy"))
        return str(family), path.parent, embedded_bold

    @staticmethod
    def _thai_mark_font(font_path, gap_percent):
        """Create a private font whose Thai upper marks have real extra clearance.

        ASS ScaleY stretches the whole line and cannot change the distance between
        sara ii and mai tho.  The Windows libass build uses the base Thai mark
        glyphs, so move only U+0E48..U+0E4C inside a uniquely named cached font.
        The selected source font itself is never modified.
        """
        if not font_path or float(gap_percent or 0) <= 0:
            return Path(font_path).resolve() if font_path else None
        source = Path(font_path).resolve()
        if TTFont is None:
            raise ValueError("ยังไม่พบ FontTools สำหรับจัดช่องไฟสระภาษาไทย")
        if not source.is_file():
            raise ValueError("ไม่พบไฟล์ฟอนต์ Subtitle")
        gap = max(0.0, min(20.0, float(gap_percent)))
        stamp = f"{source}|{source.stat().st_size}|{source.stat().st_mtime_ns}|{gap:.2f}"
        digest = hashlib.sha256(stamp.encode("utf-8")).hexdigest()[:12]
        cache_dir = Path(__file__).resolve().parents[1] / "workspace" / "cache" / "subtitle_fonts"
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / f"thai-mark-{digest}.ttf"
        if target.is_file() and target.stat().st_size:
            return target

        font = TTFont(str(source))
        if "glyf" not in font:
            font.close()
            return source
        cmap = font.getBestCmap() or {}
        tone_glyphs = {cmap.get(codepoint) for codepoint in range(0x0E48, 0x0E4D)} - {None}
        shift_units = max(1, round(font["head"].unitsPerEm * gap / 100.0))
        glyf = font["glyf"]
        shifted = 0
        for glyph_name in tone_glyphs:
            glyph = glyf[glyph_name]
            if glyph.isComposite():
                for component in glyph.components:
                    component.y += shift_units
            elif glyph.numberOfContours:
                glyph.coordinates.translate((0, shift_units))
            else:
                continue
            glyph.recalcBounds(glyf)
            shifted += 1
        if not shifted:
            font.close()
            return source

        family = f"SmartPost Thai Marks {digest}"
        style = ImageFont.truetype(str(source), 24).getname()[1] or "Regular"
        postscript_style = re.sub(r"[^A-Za-z0-9]", "", str(style)) or "Regular"
        names = {
            1: family,
            2: str(style),
            3: f"{family}-{postscript_style}",
            4: f"{family} {style}",
            5: "Version 1.000 SmartPost Thai Marks",
            6: f"SmartPostThaiMarks{digest}-{postscript_style}",
            16: family,
            17: str(style),
        }
        for record in font["name"].names:
            if record.nameID not in names:
                continue
            try:
                record.string = names[record.nameID].encode(record.getEncoding())
            except Exception:
                continue
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f"thai-mark-{digest}-", suffix=".ttf", dir=cache_dir,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            font.save(str(temporary))
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
            font.close()
        return target

    @staticmethod
    def _parse_srt(path):
        text = Path(path).read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")
        cues = []
        pattern = re.compile(
            r"(?:^|\n\s*\n)(?:\d+\s*\n)?"
            r"(?P<start>\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*"
            r"(?P<end>\d{2}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n(?P<text>.*?)(?=\n\s*\n|\Z)",
            re.S,
        )
        for match in pattern.finditer(text.strip()):
            cue_text = "\\N".join(line.strip() for line in match.group("text").splitlines() if line.strip())
            if cue_text:
                cues.append((match.group("start"), match.group("end"), cue_text))
        if not cues:
            raise ValueError("ไฟล์ SRT ไม่มีช่วงเวลาที่อ่านได้")
        return cues

    @staticmethod
    def _ass_timestamp(value):
        hours, minutes, rest = str(value).replace(",", ".").split(":")
        seconds, milliseconds = rest.split(".")
        centiseconds = min(99, round(int(milliseconds[:3].ljust(3, "0")) / 10))
        return f"{int(hours)}:{int(minutes):02d}:{int(seconds):02d}.{centiseconds:02d}"

    @staticmethod
    def _seconds(value):
        hours, minutes, rest = str(value).replace(",", ".").split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(rest)

    @staticmethod
    def _karaoke_text(text, duration):
        clean = unicodedata.normalize("NFC", str(text).replace("\\N", " ").strip())
        pieces = [clean]
        if thai_syllable_tokenize:
            try:
                pieces = [unicodedata.normalize("NFC", str(item).strip()) for item in thai_syllable_tokenize(clean, engine="dict", keep_whitespace=False) if str(item).strip()]
            except Exception:
                pieces = [clean]
        if not pieces:
            return clean
        centiseconds = max(1, round(float(duration) * 100 / len(pieces)))
        return "".join(f"{{\\kf{centiseconds}}}{piece}" for piece in pieces)

    @staticmethod
    def _animation_tags(animation, position, margin_v, play_res_x=720, play_res_y=1280, position_y_percent=None):
        custom_y = position_y_percent is not None
        alignment = 5 if custom_y else {"bottom": 2, "center": 5, "top": 8}[position]
        x = play_res_x / 2
        if custom_y:
            y = play_res_y * max(0.0, min(100.0, float(position_y_percent))) / 100.0
        else:
            y = {"bottom": play_res_y - margin_v, "center": play_res_y / 2, "top": margin_v}[position]
        tags = {
            "none": "",
            "fade": r"\fad(180,100)",
            "wordPop": r"\fscx76\fscy76\fad(70,70)\t(0,150,\fscx112\fscy112)\t(150,280,\fscx100\fscy100)",
            "bounce": r"\fscx90\fscy90\frz-1\fad(60,70)\t(0,130,\fscx108\fscy108\frz1)\t(130,260,\fscx100\fscy100\frz0)",
            "glow": r"\blur3\fad(90,80)\t(0,260,\blur0)",
            "shake": r"\frz-2\t(0,70,\frz2)\t(70,150,\frz-1)\t(150,240,\frz0)",
            "scaleRotate": r"\fscx86\fscy86\frz-3\fad(80,80)\t(0,230,\fscx100\fscy100\frz0)",
            "karaoke": "",
        }
        if animation == "slideup":
            return f"\\an{alignment}\\move({int(x)},{int(y + 18)},{int(x)},{int(y)},0,230)\\fad(100,80)"
        position_tag = f"\\pos({int(x)},{int(y)})" if custom_y else ""
        return f"\\an{alignment}{position_tag}" + tags.get(animation, "")

    def _animated_ass(
        self, subtitle_path, target_path, font_name, font_size, text_color,
        highlight_color, outline_color, outline_width, background_enabled,
        background_color, background_opacity, position, margin_v, animation,
        play_res_x=720, play_res_y=1280, letter_spacing=0.0,
        position_y_percent=None, font_embedded_bold=False,
    ):
        cues = self._parse_srt(subtitle_path)
        primary = highlight_color if animation == "karaoke" else text_color
        secondary = text_color if animation == "karaoke" else highlight_color
        alignment = {"bottom": 2, "center": 5, "top": 8}[position]
        border_style = 3 if background_enabled else 1
        # GUI values are native video pixels. Keeping PlayRes equal to the
        # source prevents libass from stretching Thai vowels and tone marks.
        rendered_font_size = max(10, min(96, round(font_size)))
        rendered_outline = max(0, min(10, round(outline_width)))
        rendered_spacing = max(0.0, min(20.0, float(letter_spacing)))
        bold_value = 0 if font_embedded_bold else -1
        # SmartSub's compact box uses more horizontal than vertical padding.
        # ASS BorderStyle 3 normally applies one value to both axes, which made
        # the box either too narrow or too tall. libass supports independent
        # x/y borders, so keep the Thai glyphs unscaled and match that padding.
        box_tags = ""
        if background_enabled:
            box_x = max(float(rendered_outline), round(rendered_font_size * 0.385, 1))
            box_y = max(rendered_outline, round(rendered_font_size * 0.18))
            box_tags = f"\\xbord{box_x}\\ybord{box_y}"
        header = (
            f"[Script Info]\nScriptType: v4.00+\nPlayResX: {play_res_x}\nPlayResY: {play_res_y}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: SmartPost,{font_name.replace(',', '')},{rendered_font_size},{self._ass_color(primary)},{self._ass_color(secondary)},{self._ass_color(outline_color)},{self._ass_color(background_color, background_opacity if background_enabled else 0)},{bold_value},0,0,0,100,100,{rendered_spacing:.1f},0,{border_style},{rendered_outline},0,{alignment},16,16,{margin_v},1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )
        events = []
        for start, end, cue_text in cues:
            safe_text = cue_text.replace("{", "(").replace("}", ")")
            if animation == "karaoke":
                safe_text = self._karaoke_text(safe_text, self._seconds(end) - self._seconds(start))
            tags = self._animation_tags(
                animation, position, margin_v, play_res_x, play_res_y, position_y_percent,
            ) + box_tags
            events.append(f"Dialogue: 0,{self._ass_timestamp(start)},{self._ass_timestamp(end)},SmartPost,,0,0,0,,{{{tags}}}{safe_text}")
        Path(target_path).write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")
        return Path(target_path)

    def render(
        self, source_path, subtitle_path, output_path, font_name="Leelawadee UI",
        font_size=22, margin_v=72, font_path="", text_color="#FFFFFF",
        outline_color="#101010", outline_width=2, background_enabled=False,
        background_color="#000000", background_opacity=0.45, position="bottom",
        highlight_color="#FACC15", animation="none", letter_spacing=0.0,
        position_y_percent=None, thai_mark_gap=14.0, cancel_event=None, crf=18, logo_overlay=None,
    ):
        check_cancelled(cancel_event)
        source, subtitle, output = Path(source_path), Path(subtitle_path), Path(output_path)
        if not source.is_file() or source.suffix.lower() not in self.VIDEO_EXTENSIONS:
            raise ValueError("ไม่พบวิดีโอสำหรับใส่ Subtitle")
        if not subtitle.is_file() or subtitle.suffix.lower() not in {".srt", ".ass", ".vtt"}:
            raise ValueError("ไม่พบไฟล์ Subtitle ที่รองรับ")
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(f".{output.stem}.rendering{output.suffix}")
        font_size = max(10, min(96, int(font_size)))
        margin_v = max(0, min(500, int(margin_v)))
        outline_width = max(0, min(10, int(outline_width)))
        crf = max(14, min(28, int(crf)))
        alignment = {"bottom": 2, "center": 5, "top": 8}.get(str(position))
        if alignment is None:
            raise ValueError("ตำแหน่ง Subtitle ต้องเป็น top, center หรือ bottom")
        render_font_path = self._thai_mark_font(font_path, thai_mark_gap) if font_path else None
        font_name, fonts_dir, font_embedded_bold = self._font_family(render_font_path, font_name)
        play_res_x, play_res_y = self._video_size(source)
        supported_animations = {"none", "fade", "wordPop", "bounce", "slideup", "glow", "shake", "scaleRotate", "karaoke"}
        if animation not in supported_animations:
            raise ValueError("แอนิเมชัน Subtitle ไม่รองรับ")
        generated_ass = None
        subtitle_for_render = subtitle
        if subtitle.suffix.lower() == ".srt":
            generated_ass = output.with_name(f".{output.stem}.animated.ass")
            subtitle_for_render = self._animated_ass(
                subtitle, generated_ass, font_name, font_size, text_color, highlight_color,
                outline_color, outline_width, bool(background_enabled), background_color,
                background_opacity, position, margin_v, animation, play_res_x, play_res_y,
                letter_spacing, position_y_percent, font_embedded_bold,
            )
        subtitle_value = self._filter_path(subtitle_for_render)
        fonts_option = f":fontsdir='{self._filter_path(fonts_dir)}'" if fonts_dir else ""
        video_filter = f"subtitles=filename='{subtitle_value}'{fonts_option}"
        command = [
            str(self.ffmpeg), "-y", "-i", str(source), "-vf", video_filter,
            "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.2",
            "-c:a", "copy", "-movflags", "+faststart", str(temporary),
        ]
        logo_temp = None
        try:
            if logo_overlay:
                from core.video_logo import VideoLogoRenderer
                renderer = VideoLogoRenderer(str(self.ffmpeg))
                opacity, size, logo_position, margin = renderer.validate_options(
                    logo_overlay['opacity'], logo_overlay['size_percent'], logo_overlay['position'], logo_overlay['margin'])
                logo_image, x, y = renderer.prepare_overlay(logo_overlay['file'], play_res_x, play_res_y,
                    opacity, size, logo_position, margin, logo_overlay.get('layout'))
                logo_temp = tempfile.TemporaryDirectory(prefix='smartflow-sub-logo-', dir=output.parent)
                prepared = Path(logo_temp.name)/'logo.png'
                logo_image.save(prepared)
                filter_index = command.index('-vf')
                command[filter_index:filter_index+2] = ['-i', str(prepared), '-filter_complex',
                    f'[0:v]{video_filter}[sub];[sub][1:v]overlay={x}:{y}:format=auto[v]']
                command[command.index('-map')+1] = '[v]'
            result = run_cancellable(command, cancel_event=cancel_event, timeout=3600,
                label='ใส่คำบรรยายและโลโก้ในรอบเดียว' if logo_overlay else 'ใส่คำบรรยาย')
            if result.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
                raise VideoLogoError("ใส่ Subtitle ในวิดีโอไม่สำเร็จ: " + result.stderr.strip()[-1000:])
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
            if generated_ass:
                generated_ass.unlink(missing_ok=True)
            if logo_temp:
                logo_temp.cleanup()
        return {
            "output": output, "source": source, "subtitle": subtitle, "font_name": font_name,
            "font_path": str(font_path or ""), "font_size": font_size, "margin_v": margin_v,
            "text_color": text_color, "outline_color": outline_color, "outline_width": outline_width,
            "background_enabled": bool(background_enabled), "background_color": background_color,
            "background_opacity": float(background_opacity), "position": position,
            "crf": crf,
            "position_y_percent": position_y_percent, "letter_spacing": float(letter_spacing),
            "thai_mark_gap": float(thai_mark_gap), "render_font_path": str(render_font_path or ""),
            "highlight_color": highlight_color, "animation": animation,
            'logo_included': bool(logo_overlay),
        }

    def render_preview_image(
        self, output_path, text="ตัวอย่างข้อความ ภาษาไทย", width=720, height=1280,
        font_name="Leelawadee UI", font_size=28, margin_v=72, font_path="",
        text_color="#FFFFFF", outline_color="#101010", outline_width=2,
        background_enabled=False, background_color="#000000", background_opacity=0.45,
        position="bottom", highlight_color="#FACC15", animation="none",
        letter_spacing=0.0, position_y_percent=None, thai_mark_gap=14.0,
    ):
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        render_font_path = self._thai_mark_font(font_path, thai_mark_gap) if font_path else None
        font_name, fonts_dir, font_embedded_bold = self._font_family(render_font_path, font_name)
        safe_text = str(text or "ตัวอย่างข้อความ ภาษาไทย").replace("\n", " ").strip()
        with tempfile.TemporaryDirectory(prefix="smartpost-subtitle-preview-") as temp:
            folder = Path(temp)
            srt = folder / "preview.srt"
            ass = folder / "preview.ass"
            srt.write_text(f"1\n00:00:00,000 --> 00:00:02,000\n{safe_text}\n", encoding="utf-8")
            self._animated_ass(
                srt, ass, font_name, font_size, text_color, highlight_color,
                outline_color, outline_width, bool(background_enabled), background_color,
                background_opacity, position, margin_v, animation, int(width), int(height),
                letter_spacing, position_y_percent, font_embedded_bold,
            )
            subtitle_value = self._filter_path(ass)
            fonts_option = f":fontsdir='{self._filter_path(fonts_dir)}'" if fonts_dir else ""
            video_filter = f"subtitles=filename='{subtitle_value}'{fonts_option}"
            temporary = output.with_name(f".{output.stem}.rendering{output.suffix}")
            command = [
                str(self.ffmpeg), "-y", "-f", "lavfi", "-i",
                f"color=c=#111831:s={int(width)}x{int(height)}:d=1:r=30",
                "-ss", "0.5", "-vf", video_filter, "-frames:v", "1", str(temporary),
            ]
            try:
                result = subprocess.run(
                    command, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=60, **hidden_process_kwargs(),
                )
                if result.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
                    raise VideoLogoError("สร้างพรีวิว Subtitle ไม่สำเร็จ: " + result.stderr.strip()[-1000:])
                os.replace(temporary, output)
            finally:
                temporary.unlink(missing_ok=True)
        return output

    def render_preview_video(
        self, output_path, text="ตัวอย่างข้อความ ภาษาไทย", width=720, height=1280,
        font_name="Leelawadee UI", font_size=28, margin_v=72, font_path="",
        text_color="#FFFFFF", outline_color="#101010", outline_width=2,
        background_enabled=False, background_color="#000000", background_opacity=0.45,
        position="bottom", highlight_color="#FACC15", animation="none",
        letter_spacing=0.0, position_y_percent=None, thai_mark_gap=14.0,
        duration=2.4,
    ):
        """Render a looping Hybrid preview through the same ASS path as final video."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        render_font_path = self._thai_mark_font(font_path, thai_mark_gap) if font_path else None
        font_name, fonts_dir, font_embedded_bold = self._font_family(render_font_path, font_name)
        safe_text = str(text or "ตัวอย่างข้อความ ภาษาไทย").replace("\n", " ").strip()
        duration = max(1.5, min(5.0, float(duration)))
        cue_end = max(1.0, duration - 0.15)
        end_seconds = int(cue_end)
        end_milliseconds = round((cue_end - end_seconds) * 1000)
        end_stamp = f"00:00:{end_seconds:02d},{end_milliseconds:03d}"
        with tempfile.TemporaryDirectory(prefix="smartpost-subtitle-preview-video-") as temp:
            folder = Path(temp)
            srt = folder / "preview.srt"
            ass = folder / "preview.ass"
            srt.write_text(
                f"1\n00:00:00,150 --> {end_stamp}\n{safe_text}\n",
                encoding="utf-8",
            )
            self._animated_ass(
                srt, ass, font_name, font_size, text_color, highlight_color,
                outline_color, outline_width, bool(background_enabled), background_color,
                background_opacity, position, margin_v, animation, int(width), int(height),
                letter_spacing, position_y_percent, font_embedded_bold,
            )
            subtitle_value = self._filter_path(ass)
            fonts_option = f":fontsdir='{self._filter_path(fonts_dir)}'" if fonts_dir else ""
            video_filter = f"subtitles=filename='{subtitle_value}'{fonts_option}"
            temporary = output.with_name(f".{output.stem}.rendering{output.suffix}")
            command = [
                str(self.ffmpeg), "-y", "-f", "lavfi", "-i",
                f"color=c=#111831:s={int(width)}x{int(height)}:d={duration:.3f}:r=30",
                "-vf", video_filter, "-an", "-c:v", "libx264", "-preset", "ultrafast",
                "-crf", "20", "-pix_fmt", "yuv420p", "-profile:v", "high",
                "-level:v", "4.1", "-movflags", "+faststart", str(temporary),
            ]
            try:
                result = subprocess.run(
                    command, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=90, **hidden_process_kwargs(),
                )
                if result.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
                    raise VideoLogoError("สร้างพรีวิวแอนิเมชัน Subtitle ไม่สำเร็จ: " + result.stderr.strip()[-1000:])
                os.replace(temporary, output)
            finally:
                temporary.unlink(missing_ok=True)
        return output
