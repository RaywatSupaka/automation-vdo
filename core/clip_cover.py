"""Optional cover metadata and local, non-destructive cover composition.

Never generates AI media, changes a title/narration, or restarts a job.
"""
import base64
import io
import re
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


COVER_PROMPT = """ข้อมูลเสริมปกคลิป (ไม่เปลี่ยนชื่อคลิป บท หรือคำสั่งภาพ): เพิ่ม cover เป็น object
{\"headline\":\"ข้อความปกที่แนะนำ\",\"alternatives\":[\"แบบที่สอง\",\"แบบที่สาม\"],\"scene_index\":1,\"emphasis\":\"คำเด่น\",\"theme\":\"bold\",\"position\":\"bottom\"}
ข้อความปกภาษาไทยต้องเป็นวลีสั้นสมบูรณ์ ประเด็นเดียว อ่านเร็ว ไม่เกิน 40 ตัวอักษรหรือ 2 บรรทัด ชวนสงสัยแต่ตรงบทจริง ไม่แต่งเหตุการณ์ ผลลัพธ์ สรรพคุณ ส่วนลด หรือข้อกล่าวหา ห้ามใช้ชื่อคลิปยาวทั้งประโยค
scene_index เป็นเลขฉากที่มีในแผนจริงและเหมาะเป็นปกที่สุด emphasis เป็นคำที่อยู่ใน headline; theme เลือก bold/mystery/product; position เลือก top/center/bottom เพื่อหลบตัวแบบ ไม่สั่งสร้างภาพเพิ่มและไม่ใส่ตัวหนังสือลงภาพฉาก หากให้ข้อมูลปกไม่ได้ให้ข้าม cover โดยตอบข้อมูลหลักให้ครบ"""


def _text(value):
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""


def normalize_cover(value):
    """Malformed optional AI metadata is ignored, never a pipeline error."""
    raw = value if isinstance(value, dict) else {}
    choices = []
    alternatives = raw.get("alternatives") if isinstance(raw.get("alternatives"), list) else []
    for value in [raw.get("headline"), *alternatives[:3]]:
        text = _text(value)
        if text and len(text) <= 60 and text not in choices:
            choices.append(text)
    try:
        index = int(raw.get("scene_index", 1))
    except (TypeError, ValueError, OverflowError):
        index = 1
    emphasis = _text(raw.get("emphasis"))
    return {
        "headline": choices[0] if choices else "",
        "alternatives": choices[1:3],
        "scene_index": max(1, min(50, index)),
        "emphasis": emphasis if choices and emphasis and emphasis in choices[0] else "",
        "theme": raw.get("theme") if raw.get("theme") in ("bold", "mystery", "product", "romance") else "bold",
        "position": raw.get("position") if raw.get("position") in ("top", "center", "bottom") else "bottom",
    }


def tokens(text):
    # Keep Thai lexical words intact; no character-by-character truncation.
    try:
        from pythainlp.tokenize import word_tokenize
        return word_tokenize(text, engine="newmm", keep_whitespace=True)
    except ImportError:
        return re.findall(r"\S+\s*", text)


def fallback_headline(manifest):
    title = _text(manifest.get("episode_title") or manifest.get("video_title")
                  or manifest.get("topic") or manifest.get("product_name") or manifest.get("name"))
    if title and len(title) <= 40:
        return title
    # Prefer an intact short clause, not a made-up sensational claim.
    for clause in re.split(r"[!?！？:：|•…\n]", title):
        if clause.strip() and len(clause.strip()) <= 40:
            return clause.strip()
    return "เรื่องนี้น่าติดตาม" if manifest.get("job_type") in ("story_short", "drama_episode") else "ดูสินค้าชิ้นนี้"


def image_choices(folder, manifest):
    folder = Path(folder).resolve()
    result = []
    values = manifest.get("generated_images")
    for index, relative in enumerate(values if isinstance(values, list) else [], 1):
        if not isinstance(relative, str):
            continue
        path = (folder / relative).resolve()
        if folder not in path.parents or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            continue
        if path.is_file():
            result.append((index, path))
    return result


def cover_settings(manifest, choices):
    settings = normalize_cover(manifest.get("cover_settings") or manifest.get("cover"))
    if manifest.get("job_type") == "drama_episode" and not manifest.get("cover_settings"):
        # Preserve the existing series palette until explicitly edited for this EP.
        settings["theme"] = {"cinematic": "bold", "thriller": "mystery", "clean": "product", "romance": "romance"}.get(manifest.get("cover_theme"), settings["theme"])
    settings["headline"] = settings["headline"] or fallback_headline(manifest)
    if choices and settings["scene_index"] not in {i for i, _ in choices}:
        settings["scene_index"] = choices[0][0]
    return settings


class ClipCoverRenderer:
    THEMES = {"bold": (83, 228, 255), "mystery": (255, 94, 94), "product": (255, 215, 112), "romance": (255, 154, 190)}

    def __init__(self, root):
        self.root = Path(root)

    def font(self, size):
        for root in dict.fromkeys((self.root, Path(__file__).resolve().parents[1])):
            for name in ("Kanit-ExtraBold.ttf", "IBMPlexSansThai-Bold.ttf"):
                path = root / "assets" / "fonts" / "smartsubai" / name
                if path.is_file():
                    return ImageFont.truetype(str(path), size=size)
        raise ValueError("ไม่พบฟอนต์ภาษาไทยสำหรับปก • กรุณาตรวจไฟล์ติดตั้งโปรแกรม")

    @staticmethod
    def wrap(text, font, width, draw):
        lines, line = [], ""
        for token in tokens(text):
            if draw.textlength(token.strip(), font=font) > width:
                return None
            if line and draw.textlength(line + token, font=font) > width:
                lines.append(line.strip())
                line = token.lstrip()
            else:
                line += token
        if line.strip():
            lines.append(line.strip())
        return lines if len(lines) <= 2 else None

    def render(self, source, manifest, settings):
        headline = _text(settings.get("headline"))
        if not headline or len(headline) > 60:
            raise ValueError("ข้อความปกต้องมี 1–60 ตัวอักษร • แนะนำวลีสั้นไม่เกิน 40 ตัวอักษร")
        landscape = bool(manifest.get("long_video"))
        width, height = (1920, 1080) if landscape else (1080, 1920)
        with Image.open(source) as opened:
            canvas = ImageOps.fit(opened.convert("RGB"), (width, height), Image.Resampling.LANCZOS)
        overlay = Image.new("RGBA", canvas.size)
        draw = ImageDraw.Draw(overlay)
        margin = int(width * .075)
        for size in range(132 if landscape else 112, 43, -4):
            font = self.font(size)
            lines = self.wrap(headline, font, width - margin * 2, draw)
            if lines:
                break
        else:
            raise ValueError("ข้อความปกยาวเกิน 2 บรรทัด กรุณาย่อข้อความ • ระบบไม่ตัดคำทิ้ง")
        line_height = int(size * 1.55)
        block_height = line_height * len(lines)
        position = settings.get("position", "bottom")
        y = int(height * .16) if position == "top" else (height - block_height) // 2 if position == "center" else int(height * .83) - block_height
        accent = self.THEMES.get(settings.get("theme"), self.THEMES["bold"])
        # A bounded scrim keeps the main subject visible; user can move the text.
        pad = 32
        draw.rounded_rectangle((margin - pad, y - pad, width - margin + pad, y + block_height + pad), radius=32, fill=(5, 9, 22, 200))
        draw.rounded_rectangle((margin, y - 16, margin + 108, y - 9), radius=3, fill=(*accent, 255))
        emphasis = _text(settings.get("emphasis"))
        for line in lines:
            draw.text((margin, y), line, font=font, fill="white", stroke_width=2, stroke_fill=(3, 6, 15))
            if emphasis and emphasis in line:
                left = line.split(emphasis, 1)[0]
                draw.text((margin + draw.textlength(left, font=font), y), emphasis, font=font, fill=(*accent, 255), stroke_width=2, stroke_fill=(3, 6, 15))
            y += line_height
        if manifest.get("job_type") == "drama_episode":
            badge = f"EP {int(manifest.get('episode_no') or 1)}"
            draw.text((margin, 55), badge, font=self.font(46), fill=(*accent, 255), stroke_width=2, stroke_fill="black")
        return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")


def compose_cover(root, folder, manifest, settings=None, *, preview=False):
    automatic = settings is None
    choices = image_choices(folder, manifest)
    if not choices:
        raise ValueError("ยังไม่มีภาพฉากจริงสำหรับสร้างปก • ไม่สร้างภาพซ้ำ")
    settings = dict(settings) if settings is not None else cover_settings(manifest, choices)
    selected = next((path for i, path in choices if i == settings.get("scene_index")), None)
    if selected is None:
        raise ValueError("ไม่พบภาพฉากที่เลือก กรุณาเปิดหน้าปกใหม่")
    renderer = ClipCoverRenderer(root)
    try:
        image = renderer.render(selected, manifest, settings)
    except (OSError, ValueError):
        if not automatic:
            raise
        settings["headline"] = fallback_headline(manifest)
        settings["emphasis"] = ""
        for index, candidate in choices:
            try:
                image = renderer.render(candidate, manifest, settings)
                settings["scene_index"] = index
                break
            except (OSError, ValueError):
                continue
        else:
            raise ValueError("ไม่พบภาพหรือฟอนต์ที่เปิดอ่านได้สำหรับปก • เก็บวิดีโอเดิมไว้") from None
    if preview:
        image.thumbnail((960, 960), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=87)
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    folder = Path(folder).resolve()
    target = folder / "covers" / f"cover_{uuid.uuid4().hex}.jpg"
    # Rendering runs outside the Story manifest lock so cancellation stays
    # responsive. Every invocation needs its own file: a stale renderer must
    # not overwrite a newer cover before its completion token is rejected.
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, format="JPEG", quality=94, subsampling=0)
    return {"cover_path": str(target.relative_to(folder)), "cover_status": "ready",
            "cover_size": list(image.size), "cover_settings": settings,
            "cover_revision": uuid.uuid4().hex, "cover_renderer": "short-hook-v1"}


def ensure_cover(root, folder, manifest):
    """Create only when absent. Existing covers and completed media are immutable here."""
    folder = Path(folder).resolve()
    existing = (folder / str(manifest.get("cover_path") or "")).resolve()
    if folder in existing.parents and existing.is_file():
        return {}
    # AI cover is a separate post-video request. Never create a typography
    # substitute before that request, including startup cover repair.
    options = manifest.get('ai_cover_options')
    if isinstance(options, dict) and options.get('enabled') is True:
        return {'cover_status': 'pending_ai'}
    return compose_cover(root, folder, manifest)
