import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from core.cancellable_process import check_cancelled
from core.render_backend import run_render as run_cancellable, resolve_fps


class DramaCoverRenderer:
    """Create a deterministic 9:16 episode cover from the first real AI scene."""

    THEMES = {
        "cinematic": {"label": "Cinematic Neon", "accent": (83, 228, 255), "shadow": (5, 7, 20), "badge": (12, 18, 42)},
        "romance": {"label": "Romance Rose", "accent": (255, 154, 190), "shadow": (31, 8, 24), "badge": (69, 20, 49)},
        "thriller": {"label": "Thriller Red", "accent": (255, 94, 94), "shadow": (19, 4, 7), "badge": (58, 10, 15)},
        "clean": {"label": "Clean Premium", "accent": (255, 215, 112), "shadow": (10, 14, 25), "badge": (28, 34, 48)},
    }

    def __init__(self, root):
        self.root = Path(root)

    def render(self, source_image, target, title, episode_no, theme_key="cinematic", *, badge_text=""):
        source_image = Path(source_image)
        target = Path(target)
        if not source_image.is_file():
            raise FileNotFoundError("ไม่พบภาพสำหรับสร้างปกละคร")
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source_image) as opened:
            canvas = ImageOps.fit(opened.convert("RGB"), (1080, 1920), Image.Resampling.LANCZOS)
        theme_key = str(theme_key or "cinematic").strip().lower()
        theme = self.THEMES.get(theme_key, self.THEMES["cinematic"])
        accent = (*theme["accent"], 255)
        shadow = theme["shadow"]
        badge = (*theme["badge"], 220)
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for y in range(840):
            alpha = int(225 * (y / 839) ** 1.7)
            draw.line((0, 1080 + y, 1080, 1080 + y), fill=(*shadow, alpha))
        draw.rectangle((0, 0, 16, 1920), fill=accent)
        small = self._font(46, bold=True)
        title_font = self._font(92, bold=True)
        badge_text = str(badge_text or f"ละครสั้น • EP {int(episode_no)}").strip()
        badge_width = draw.textlength(badge_text, font=small)
        badge_right = min(1006, max(318, int(104 + badge_width + 34)))
        draw.rounded_rectangle((74, 116, badge_right, 206), radius=26, fill=badge, outline=accent, width=3)
        draw.text((104, 135), badge_text, font=small, fill=accent)
        wrapped = self._wrap(str(title or "ละครสั้น"), title_font, 910, draw)
        box = draw.multiline_textbbox((0, 0), wrapped, font=title_font, spacing=18, stroke_width=2)
        text_height = box[3] - box[1]
        draw.multiline_text(
            (78, 1780 - text_height), wrapped, font=title_font, spacing=18,
            fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(6, 9, 24, 245),
        )
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
        temporary = target.with_suffix(".jpg.partial")
        canvas.save(temporary, format="JPEG", quality=94, subsampling=0)
        temporary.replace(target)
        return target

    def _font(self, size, bold=False):
        names = ["Kanit-ExtraBold.ttf", "IBMPlexSansThai-Bold.ttf"] if bold else ["Anuphan-Variable.ttf"]
        for name in names:
            path = self.root / "assets" / "fonts" / "smartsubai" / name
            if path.is_file():
                return ImageFont.truetype(str(path), size=size)
        return ImageFont.load_default()

    @staticmethod
    def _wrap(text, font, max_width, draw):
        lines, current = [], ""
        for character in str(text or ""):
            candidate = current + character
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current.strip())
                current = character
            else:
                current = candidate
        if current.strip():
            lines.append(current.strip())
        return "\n".join(lines[:4])


class StoryCoverRenderer(DramaCoverRenderer):
    """Create the dedicated vertical cover for a standalone Story Shorts job."""

    def render(self, source_image, target, title, theme_key="cinematic"):
        return super().render(
            source_image,
            target,
            title,
            1,
            theme_key,
            badge_text="เรื่องเล่า • SHORTS",
        )


class DramaContinuityValidator:
    """Validate real files and continuity signals before a Drama result enters rendering."""

    def validate(self, image_paths, prompts, characters, visual_bible, previous_visual_bible=None):
        image_paths = [Path(value) for value in list(image_paths or [])]
        prompts = [str(value or "").strip() for value in list(prompts or [])]
        characters = [dict(value) for value in list(characters or []) if isinstance(value, dict)]
        if not image_paths:
            raise ValueError("Drama Continuity: ไม่พบภาพฉากสำหรับตรวจสอบ")
        image_checks = []
        for index, path in enumerate(image_paths, 1):
            try:
                with Image.open(path) as opened:
                    opened.verify()
                with Image.open(path) as opened:
                    width, height = opened.size
                    image_format = str(opened.format or path.suffix.lstrip(".")).upper()
            except (OSError, ValueError):
                raise ValueError(f"Drama Continuity: รูปฉากที่ {index} เปิดอ่านไม่ได้") from None
            if width < 128 or height < 128:
                raise ValueError(f"Drama Continuity: รูปฉากที่ {index} มีขนาดเล็กเกินไป")
            if height <= width:
                raise ValueError(f"Drama Continuity: รูปฉากที่ {index} ไม่ใช่ภาพแนวตั้ง Shorts")
            image_checks.append({"index": index, "width": width, "height": height, "format": image_format, "passed": True})

        names = [str(item.get("name") or "").strip() for item in characters]
        names = [name for name in names if name]
        mentioned = sum(bool(names and any(name in prompt for name in names)) for prompt in prompts)
        prompt_coverage = round(mentioned / max(1, len(prompts)), 3)
        bible = visual_bible if isinstance(visual_bible, dict) else {}
        previous = previous_visual_bible if isinstance(previous_visual_bible, dict) else {}
        shared_bible_keys = sorted(set(bible).intersection(previous)) if previous else []
        score = 40
        score += round(prompt_coverage * 30)
        score += 20 if bible else 0
        score += 10 if not previous or shared_bible_keys else 4
        warnings = []
        if prompt_coverage < 0.6:
            warnings.append("Scene Prompt กล่าวถึงตัวละครจาก Character Bible น้อยกว่า 60% ของฉาก")
        if not bible:
            warnings.append("AI ไม่ได้ส่ง Visual Bible สำหรับตรวจเสื้อผ้า สถานที่ และโทนภาพ")
        if previous and not shared_bible_keys:
            warnings.append("Visual Bible ตอนนี้ไม่มีหัวข้อร่วมกับตอนก่อนหน้า")
        score = max(0, min(100, int(score)))
        return {
            "status": "passed" if score >= 70 else "needs_review",
            "score": score,
            "image_count": len(image_checks),
            "image_checks": image_checks,
            "character_names": names,
            "prompt_character_coverage": prompt_coverage,
            "visual_bible_present": bool(bible),
            "shared_visual_bible_keys": shared_bible_keys,
            "warnings": warnings,
        }


class DramaFootageMixer:
    """Insert short moving cutaways while preserving the generated narration audio."""

    def __init__(self, ffmpeg_path=""):
        configured = Path(str(ffmpeg_path or "")) if ffmpeg_path else None
        found = str(configured) if configured and configured.is_file() else shutil.which("ffmpeg")
        if not found:
            raise FileNotFoundError("ไม่พบ FFmpeg สำหรับแทรกฟุตเทจ")
        self.ffmpeg = Path(found)

    def mix(self, base_video, footage_paths, target, *, duration, width, height, fps, crf=20, cancel_event=None):
        base_video = Path(base_video)
        fps = resolve_fps(fps, [base_video], self.ffmpeg.with_name('ffprobe.exe' if self.ffmpeg.suffix == '.exe' else 'ffprobe'), cancel_event)
        footage = [Path(value) for value in list(footage_paths or [])[:3] if Path(value).is_file()]
        if not footage:
            return base_video, {"footage_count": 0, "footage_segments": []}
        check_cancelled(cancel_event)
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".rendering.mp4")
        command = [str(self.ffmpeg), "-y", "-i", str(base_video)]
        for source in footage:
            command.extend(["-stream_loop", "-1", "-i", str(source)])
        duration = max(3.0, float(duration or 3.0))
        cut = max(1.5, min(3.2, duration / max(4, len(footage) * 4)))
        filters = []
        previous = "0:v"
        segments = []
        for index, _source in enumerate(footage, 1):
            center = duration * index / (len(footage) + 1)
            start = max(0.2, min(duration - cut - 0.2, center - cut / 2))
            end = start + cut
            filters.append(
                f"[{index}:v]scale={int(width)}:{int(height)}:force_original_aspect_ratio=increase,"
                f"crop={int(width)}:{int(height)},fps={fps},trim=duration={cut:.3f},"
                f"setpts=PTS-STARTPTS+{start:.3f}/TB,format=yuv420p[ft{index}]"
            )
            output = f"mix{index}"
            filters.append(
                f"[{previous}][ft{index}]overlay=0:0:eof_action=pass:shortest=0:"
                f"enable='between(t,{start:.3f},{end:.3f})'[{output}]"
            )
            previous = output
            segments.append({"source": str(footage[index - 1]), "start": round(start, 3), "duration": round(cut, 3)})
        command.extend([
            "-filter_complex", ";".join(filters),
            "-map", f"[{previous}]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(int(crf)),
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(int(fps)),
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(temporary),
        ])
        result = run_cancellable(command, cancel_event=cancel_event, timeout=3600)
        if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size < 1024:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("แทรกฟุตเทจไม่สำเร็จ: " + (result.stderr or "ไม่ทราบสาเหตุ")[-1200:])
        temporary.replace(target)
        return target, {"footage_count": len(footage), "footage_segments": segments}
