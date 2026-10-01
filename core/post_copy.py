"""Small, provider-neutral guards for user-facing story post copy."""

import re


_PRODUCTION_NOTES = re.compile(
    r"ความยาวเป้าหมาย|จำนวน\s*\d+\s*(?:ภาพ|ฉาก)|แบ่งเป็น\s*\d+\s*ชุด|"
    r"ชุดละ\s*\d+\s*(?:ภาพ|ฉาก)|(?:image|scene|chapter)\s*count",
    re.IGNORECASE,
)
_TAG = re.compile(r"^#[^\s#]{1,50}$", re.UNICODE)


def post_ready_description(value):
    text = str(value or "").strip()
    return bool(text and len(text) <= 1800 and not _PRODUCTION_NOTES.search(text))


def hashtags(value, *, strict=False):
    if isinstance(value, (list, tuple)):
        candidates = [str(part or "").strip() for part in value]
    else:
        candidates = re.split(r"[\s,]+", str(value or "").strip())
    tags = []
    for candidate in candidates:
        if not candidate:
            continue
        tag = candidate if candidate.startswith("#") else "#" + candidate
        if not _TAG.fullmatch(tag):
            if strict:
                raise ValueError("แฮชแท็กต้องเป็นคำเดียวและไม่มีอักขระ # ซ้อน")
            continue
        if tag.casefold() not in {known.casefold() for known in tags}:
            tags.append(tag)
    if strict and not 3 <= len(tags) <= 6:
        raise ValueError("กรุณาใส่แฮชแท็กที่เกี่ยวข้อง 3–6 คำ")
    return " ".join(tags[:6])


def long_video_post_copy(outline, topic):
    """Never publish a production plan; retain usable AI copy without another media request."""
    raw = str(outline.get("video_description") or "").strip()
    found_tags = re.findall(r"(?<!\w)#[^\s#]+", raw)
    description = re.sub(r"(?<!\w)#[^\s#]+", "", raw).strip()
    if not post_ready_description(description):
        subject = str(topic or outline.get("video_title") or "เรื่องนี้").strip()
        description = f"{subject} ลองมาดูเรื่องราวและเหตุผลในคลิป แล้วบอกกันว่าคุณคิดอย่างไร"
    selected = hashtags(outline.get("hashtags") or found_tags)
    if len(selected.split()) < 3:
        names = [entity.get("name") for entity in outline.get("story_entities") or [] if isinstance(entity, dict)]
        selected = hashtags([*selected.split(), *names[:3], "เรื่องเล่า", "วิเคราะห์ตัวละคร", "คลิปยาว"])
    return description, selected
