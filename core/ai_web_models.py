"""Stable model preferences shared by the desktop app and persisted Jobs."""

AI_WEB_MODEL_OPTIONS = {
    "chatgpt": {
        "auto": "ใช้โมเดลปัจจุบัน",
        "instant": "Instant • เร็ว",
        "thinking": "Thinking • คิดละเอียด",
        "pro": "Pro • เหตุผลขั้นสูง",
    },
    "gemini": {
        "auto": "ใช้โมเดลปัจจุบัน",
        "flash_lite": "Flash-Lite • เร็วที่สุด",
        "flash": "Flash • รอบด้าน",
        "pro": "Pro • เหตุผลขั้นสูง",
        "long_thinking": "การคิดที่นานขึ้น • ปัญหาซับซ้อน",
    },
}

AI_WEB_MODEL_DEFAULTS = {
    "chatgpt": "auto",
    # Preserve the established SmartFlow behavior for existing Gemini jobs.
    "gemini": "long_thinking",
}


def normalize_ai_web_model(provider, value=""):
    provider = str(provider or "chatgpt").strip().lower()
    if provider not in AI_WEB_MODEL_OPTIONS:
        provider = "chatgpt"
    model = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "current": "auto",
        "default": "auto",
        "flashlite": "flash_lite",
        "extended": "long_thinking",
        "flash_extended": "long_thinking",
        "longer_thinking": "long_thinking",
    }
    model = aliases.get(model, model)
    return model if model in AI_WEB_MODEL_OPTIONS[provider] else AI_WEB_MODEL_DEFAULTS[provider]


def ai_web_model_label(provider, value=""):
    provider = str(provider or "chatgpt").strip().lower()
    if provider not in AI_WEB_MODEL_OPTIONS:
        provider = "chatgpt"
    model = normalize_ai_web_model(provider, value)
    return AI_WEB_MODEL_OPTIONS[provider][model]
