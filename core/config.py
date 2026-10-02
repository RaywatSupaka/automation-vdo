from pathlib import Path

from core.atomic_json import AtomicJsonFile, runtime_backup_path

from core.customer_runtime import DEFAULTS, prepare_customer_root, resolve_customer_tools

ROOT = prepare_customer_root(Path(__file__).resolve().parents[1])


def _config_store():
    path = ROOT / "config.json"
    return AtomicJsonFile(path, backup_path=runtime_backup_path(ROOT, path))


def _update_config(updater):
    # A clean source checkout has no user config yet. Create it only on the
    # first explicit settings save; reads use in-memory defaults.
    return _config_store().update(updater, default=DEFAULTS)


def save_chrome_profile(values):
    def update(config):
        for key in ('chrome_user_data_dir', 'chrome_profile_directory'):
            config[key] = values[key]
        return config
    _update_config(update)


def save_android_selection(serial, identity):
    """Persist only the explicitly verified device. Pairing codes are never accepted."""
    def update(config):
        config['device_serial'] = str(serial)
        config['android_device_identity'] = str(identity)
        return config
    _update_config(update)

def load_config():
    saved = _config_store().read(default={})
    if not isinstance(saved, dict):
        raise ValueError("config.json ต้องเป็น JSON object")
    config = resolve_customer_tools({**DEFAULTS, **saved}, Path(__file__).resolve().parents[1])
    config.setdefault("video_resolution", "720x1280")
    config.setdefault("video_fps", 30)
    config.setdefault("logo_file", str(ROOT / "assets" / "smartflow_logo.png"))
    saved_segment_max = float(config.get("audio_background_segment_max_sec", 12.0))
    config["audio_background_segment_max_sec"] = 12.0 if saved_segment_max < 8 else min(12.0, saved_segment_max)
    # SmartFlow clips always use the stable Voice profile.  Normalize legacy
    # configs in memory so old emotion/speed values cannot leak into a run.
    config["voice_emotion_id"] = "normal"
    config["voice_speed"] = 1.0
    config.setdefault("chatgpt_web_model", "auto")
    config.setdefault("gemini_web_model", "long_thinking")
    for key in ("adb_path", "scrcpy_path"):
        path = Path(config[key])
        config[key] = path if path.is_absolute() else ROOT / path
    return config


VOICE_SETTING_KEYS = {
    "voice_reference_id",
    "voice_reference_file",
    "voice_language",
    "voice_emotion_id",
    "voice_engine",
    "voice_speed",
    "voice_silence_sec",
    "voice_output_format",
}

LOGO_SETTING_KEYS = {
    "logo_layout",
    "logo_file",
    "logo_opacity",
    "logo_size_percent",
    "logo_position",
    "logo_margin",
    "ffmpeg_path",
}

SUBTITLE_SETTING_KEYS = {
    "subtitle_client_id",
    "subtitle_language",
    "subtitle_auto_after_voice",
    "subtitle_api_base_url",
    "subtitle_syllables_per_cue",
    "subtitle_font_file",
    "subtitle_font_size",
    "subtitle_letter_spacing",
    "subtitle_thai_mark_gap",
    "subtitle_text_color",
    "subtitle_outline_color",
    "subtitle_outline_width",
    "subtitle_background_enabled",
    "subtitle_background_color",
    "subtitle_background_opacity",
    "subtitle_highlight_color",
    "subtitle_theme",
    "subtitle_theme_random",
    "subtitle_animation",
    "subtitle_animation_random",
    "subtitle_position",
    "subtitle_position_y_percent",
    "subtitle_margin_v",
}

AUDIO_SETTING_KEYS = {
    "audio_background_selection", "audio_background_track_count",
    "audio_background_enabled",
    "audio_background_mode",
    "audio_background_file",
    "audio_background_volume",
    "audio_background_segment_max_sec",
    "audio_background_duck_percent",
    "audio_sfx_enabled",
    "audio_sfx_mode",
    "audio_sfx_file",
    "audio_sfx_volume",
    "audio_sfx_min_interval",
    "audio_sfx_max_count",
}

VIDEO_SETTING_KEYS = {
    "video_encoder",
    "image_ai_provider",
    "chatgpt_web_model",
    "gemini_web_model",
    "video_ai_provider",
    "video_resolution",
    "video_fps",
    "video_quality",
    "video_motion_strength",
    "video_transition_sec",
}


def save_voice_settings(values):
    """Persist reusable non-secret voice options. API keys are intentionally rejected."""
    if "voice_api_key" in values or "api_key" in values:
        raise ValueError("ไม่อนุญาตให้บันทึก API Key ลง config.json")
    def update(config):
        for key in VOICE_SETTING_KEYS:
            if key in values:
                config[key] = values[key]
        config["voice_emotion_id"] = "normal"
        config["voice_speed"] = 1.0
        return config

    _update_config(update)


def save_logo_settings(values):
    """Persist reusable, non-secret video-logo options atomically."""
    def update(config):
        for key in LOGO_SETTING_KEYS:
            if key in values:
                config[key] = values[key]
        return config

    _update_config(update)


def save_subtitle_settings(values):
    """Persist non-secret Subtitle options. SOT/SOD credentials are always rejected."""
    forbidden = {"token", "sot", "sod", "device_credential", "deviceCredential"}
    if forbidden.intersection(values):
        raise ValueError("ไม่อนุญาตให้บันทึก Token หรือรหัสอุปกรณ์ลง config.json")
    def update(config):
        for key in SUBTITLE_SETTING_KEYS:
            if key in values:
                config[key] = values[key]
        return config

    _update_config(update)


def save_audio_settings(values):
    """Persist reusable non-secret background music and subtitle-SFX settings."""
    def update(config):
        for key in AUDIO_SETTING_KEYS:
            if key in values:
                config[key] = values[key]
        return config

    _update_config(update)


def save_video_settings(values):
    """Persist non-secret AI image-provider and video rendering preferences."""
    def update(config):
        for key in VIDEO_SETTING_KEYS:
            if key in values:
                config[key] = values[key]
        return config

    _update_config(update)
