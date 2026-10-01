import random


# Adapted from SmartSubAI 2.5.37 built-in subtitle templates. Font sizes are
# scaled for the SRT/ASS render surface used by SmartPost (720x1280 output).
SUBTITLE_THEMES = {
    "standard": {
        "label": "มาตรฐาน • กล่องดำ",
        "font_file": "Kanit-Bold.ttf", "font_size": 28, "letter_spacing": 0,
        "thai_mark_gap": 14,
        "text_color": "#FFFFFF",
        "outline_color": "#000000", "outline_width": 2, "background_enabled": True,
        "background_color": "#000000", "background_opacity": 1.0,
    },
    "clean_impact": {
        "label": "HOT Clean Impact",
        "font_file": "Kanit-ExtraBold.ttf", "font_size": 24, "text_color": "#FFFFFF",
        "outline_color": "#000000", "outline_width": 4, "background_enabled": False,
        "background_color": "#000000", "background_opacity": 0,
    },
    "comic_burst": {
        "label": "HOT Comic Burst",
        "font_file": "Prompt-ExtraBold.ttf", "font_size": 25, "text_color": "#FACC15",
        "outline_color": "#111827", "outline_width": 5, "background_enabled": False,
        "background_color": "#000000", "background_opacity": 0,
    },
    "neon_punch": {
        "label": "HOT Neon Punch",
        "font_file": "Prompt-ExtraBold.ttf", "font_size": 23, "text_color": "#22D3EE",
        "outline_color": "#020617", "outline_width": 3, "background_enabled": False,
        "background_color": "#000000", "background_opacity": 0,
    },
    "creator_badge": {
        "label": "HOT Creator Badge",
        "font_file": "IBMPlexSansThai-Bold.ttf", "font_size": 21, "text_color": "#FFFFFF",
        "outline_color": "#0F172A", "outline_width": 0, "background_enabled": True,
        "background_color": "#0F172A", "background_opacity": 0.88,
    },
    "spotlight_card": {
        "label": "HOT Spotlight Card",
        "font_file": "Kanit-ExtraBold.ttf", "font_size": 22, "text_color": "#FFFFFF",
        "outline_color": "#000000", "outline_width": 2, "background_enabled": True,
        "background_color": "#000000", "background_opacity": 0.74,
    },
    "yellow_pop": {
        "label": "ตัวหนาเด่น • เหลือง",
        "font_file": "Prompt-ExtraBold.ttf", "font_size": 25, "text_color": "#FACC15",
        "outline_color": "#000000", "outline_width": 5, "background_enabled": False,
        "background_color": "#000000", "background_opacity": 0,
    },
    "minimal": {
        "label": "มินิมอล",
        "font_file": "NotoSansThai-Variable.ttf", "font_size": 20, "text_color": "#FFFFFF",
        "outline_color": "#000000", "outline_width": 1, "background_enabled": False,
        "background_color": "#000000", "background_opacity": 0,
    },
    "pastel": {
        "label": "พาสเทล",
        "font_file": "Itim-Regular.ttf", "font_size": 23, "text_color": "#F9A8D4",
        "outline_color": "#FFFFFF", "outline_width": 2, "background_enabled": False,
        "background_color": "#000000", "background_opacity": 0,
    },
    "classic": {
        "label": "คลาสสิก",
        "font_file": "Sarabun-Bold.ttf", "font_size": 20, "text_color": "#FFFFFF",
        "outline_color": "#000000", "outline_width": 0, "background_enabled": True,
        "background_color": "#000000", "background_opacity": 0.82,
    },
    "outline": {
        "label": "เส้นขอบชัด",
        "font_file": "Kanit-ExtraBold.ttf", "font_size": 25, "text_color": "#FFFFFF",
        "outline_color": "#000000", "outline_width": 5, "background_enabled": False,
        "background_color": "#000000", "background_opacity": 0,
    },
    "product_review": {
        "label": "Product Review",
        "font_file": "Kanit-ExtraBold.ttf", "font_size": 22, "text_color": "#FFFFFF",
        "outline_color": "#052E16", "outline_width": 3, "background_enabled": True,
        "background_color": "#10B981", "background_opacity": 0.28,
    },
}


SUBTITLE_ANIMATIONS = {
    "none": "นิ่ง • อ่านง่าย",
    "fade": "Clean Fade",
    "wordPop": "Hook Pop",
    "bounce": "Beat Bounce",
    "slideup": "Swipe Up",
    "glow": "Neon Glow",
    "shake": "Micro Shake",
    "scaleRotate": "Zoom Snap",
    "karaoke": "Karaoke Pulse",
}


def theme_by_label(label):
    return next(((key, dict(value)) for key, value in SUBTITLE_THEMES.items() if value["label"] == label), None)


def animation_by_label(label):
    return next((key for key, value in SUBTITLE_ANIMATIONS.items() if value == label), "none")


def random_theme(rng=None):
    rng = rng or random
    key = rng.choice(list(SUBTITLE_THEMES))
    return key, dict(SUBTITLE_THEMES[key])


def random_animation(rng=None):
    rng = rng or random
    choices = [key for key in SUBTITLE_ANIMATIONS if key != "none"]
    return rng.choice(choices)
