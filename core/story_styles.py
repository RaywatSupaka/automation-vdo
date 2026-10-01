"""Canonical image direction shared by Story, batches, Drama and Extension."""

STORY_VISUAL_STYLES = (
    {"value": "auto", "label": "ตามเนื้อเรื่อง", "description": "ให้ AI เลือกแนวภาพและรักษาแนวเดียวกันทั้งเรื่อง", "prompt": "Choose one coherent visual medium suited to the story; keep it consistent in every scene."},
    {"value": "realistic", "label": "เสมือนจริง", "description": "รายละเอียดธรรมชาติ แสงและวัสดุสมจริง", "prompt": "Photorealistic imagery, believable anatomy, natural light and physically plausible materials; no illustration or cartoon rendering."},
    {"value": "cinematic", "label": "ภาพยนตร์", "description": "จัดแสงแบบภาพยนตร์ มิติภาพชัด โทนสีต่อเนื่อง", "prompt": "Live-action cinematic photography, controlled film lighting, dimensional composition and consistent film color grading."},
    {"value": "anime", "label": "อนิเมะ 2D", "description": "เส้นคม เซลเชด สีและตัวละครต่อเนื่อง", "prompt": "2D anime illustration, clean linework, cel shading, expressive consistent character designs; do not switch to live action or 3D."},
    {"value": "3d", "label": "แอนิเมชัน 3D", "description": "ตัวละครสามมิติ แสงนุ่ม เหมาะกับเรื่องผจญภัย", "prompt": "Stylized 3D animated film imagery, appealing consistent character proportions, soft global illumination and tactile materials."},
    {"value": "watercolor", "label": "สีน้ำ / นิทาน", "description": "สีอ่อน พื้นผิวกระดาษ บรรยากาศอบอุ่น", "prompt": "Hand-painted watercolor storybook illustration, subtle paper texture, layered washes and consistent character silhouettes."},
    {"value": "comic", "label": "คอมิก", "description": "เส้นหมึกและแสงเงาชัด ภาพเดี่ยวเต็มเฟรม", "prompt": "Inked comic illustration with bold linework and dramatic shading. One full-frame scene, no panels, speech bubbles or printed words."},
    {"value": "custom", "label": "กำหนดเอง", "description": "ระบุแนวภาพ แสง และโทนสีที่ต้องการ", "prompt": "Follow the user's visual direction consistently across every scene."},
)


def normalize_story_style(value="auto", custom=""):
    value = str(value or "auto").strip().lower()
    if value not in {item["value"] for item in STORY_VISUAL_STYLES}:
        raise ValueError("สไตล์ภาพเรื่องเล่าไม่ถูกต้อง")
    custom = str(custom or "").strip()
    if len(custom) > 400:
        raise ValueError("แนวภาพเพิ่มเติมต้องไม่เกิน 400 ตัวอักษร")
    if value == "custom" and not custom:
        raise ValueError("กรุณาระบุแนวภาพที่ต้องการ")
    return value, custom


def story_style_instruction(value="auto", custom=""):
    value, custom = normalize_story_style(value, custom)
    item = next(item for item in STORY_VISUAL_STYLES if item["value"] == value)
    return (f"VISUAL STYLE — {item['label']}: {item['prompt']}"
            "\nThe visual medium changes only the rendering. Preserve the story's named characters, entities, universe, events, relationships and established visual identities."
            " Do not replace them with generic or newly invented characters. Actor likeness is not implied; use it only when explicitly requested by the user."
            + (f"\nAdditional visual direction: {custom}" if custom else ""))


def story_render_instruction(value="auto", custom=""):
    """Rendering facts for a new image, separate from analysis/identity policy.

    Auto already resolves its medium in the scene plan. Do not ask the image
    request to choose again, or copy the analysis-only preservation wrapper.
    Keep the user's additional visual direction without rewriting its content.
    """
    value, custom = normalize_story_style(value, custom)
    item = next(item for item in STORY_VISUAL_STYLES if item["value"] == value)
    parts = [] if value == "auto" else [item["prompt"]]
    if custom:
        parts.append(custom)
    return "\n".join(parts)
