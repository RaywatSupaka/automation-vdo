"""Frozen desktop resources and user state; source checkout behavior is unchanged."""
import json
import os
import shutil
import sys
from pathlib import Path

DEFAULTS = {
    "adb_path": "tools/android/adb.exe", "scrcpy_path": "tools/android/scrcpy.exe",
    "shopee_package": "com.shopee.th", "device_serial": "",
    "bridge_host": "127.0.0.1", "bridge_port": 8765,
    "image_ai_provider": "chatgpt", "video_ai_provider": "flow",
    "chatgpt_web_model": "auto", "gemini_web_model": "long_thinking",
    "voice_emotion_id": "normal", "voice_speed": 1.0,
    "subtitle_auto_after_voice": False,
}


def bundled_tool_paths(resource_root):
    root = Path(resource_root)
    return {"adb_path": root / "tools/android/adb.exe",
            "scrcpy_path": root / "tools/android/scrcpy.exe",
            "ffmpeg_path": root / "ffmpeg/ffmpeg.exe"}


def resolve_customer_tools(config, resource_root):
    """Resolve frozen tools without moving data or overwriting user preferences."""
    if not getattr(sys, "frozen", False):
        return config
    resolved = dict(config)
    legacy = {"adb_path": {"tools/adb/adb.exe", "tools/android/adb.exe", "tools/scrcpy-win64-v4.1/adb.exe"},
              "scrcpy_path": {"tools/scrcpy/scrcpy.exe", "tools/android/scrcpy.exe", "tools/scrcpy-win64-v4.1/scrcpy.exe"},
              "ffmpeg_path": {"ffmpeg/ffmpeg.exe"}}
    for key, bundled in bundled_tool_paths(resource_root).items():
        saved = str(resolved.get(key) or "")
        normalized = saved.replace("\\", "/")
        # A real custom absolute tool remains the user's choice. Legacy missing
        # default directories are a packaging defect, not a phone/pairing error.
        if saved and Path(saved).is_absolute() and Path(saved).is_file():
            continue
        if (not saved or normalized in legacy[key]) and bundled.is_file():
            resolved[key] = str(bundled)
    return resolved


def prepare_customer_root(resource_root):
    resource_root = Path(resource_root)
    if not getattr(sys, "frozen", False):
        return resource_root
    root = Path(os.environ.get("SMARTFLOW_TEST_DATA_ROOT") or (Path(os.environ["LOCALAPPDATA"]) / "SmartFlowAI" / "data"))
    root.mkdir(parents=True, exist_ok=True)
    for folder in ("data", "workspace", "logs", "videos", "screenshots", "assets/fonts/user"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    # First install only: preserve the loaded unpacked Extension on future updates.
    extension = root / "browser_extension"
    if not extension.exists() and (resource_root / "browser_extension").is_dir():
        shutil.copytree(resource_root / "browser_extension", extension)
    # Seed the editable audio library without replacing customer sound files.
    # Applies to a fresh install and to older installs missing bundled audio.
    for kind in ("background", "sfx"):
        source = resource_root / "assets/audio" / kind
        destination = root / "assets/audio" / kind
        destination.mkdir(parents=True, exist_ok=True)
        for audio in source.iterdir() if source.is_dir() else ():
            if not audio.is_file() or audio.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:
                continue
            target = destination / audio.name
            if target.exists():
                continue
            try:
                with audio.open("rb") as original, target.open("xb") as output:
                    shutil.copyfileobj(original, output)
            except FileExistsError:
                pass
    # Only shipped UI/fonts/icons are synchronized, never user fonts or media.
    for folder in ("web_ui", "assets/fonts/smartsubai"):
        source = resource_root / folder
        if source.is_dir():
            shutil.copytree(source, root / folder, dirs_exist_ok=True)
    (root / "assets").mkdir(exist_ok=True)
    for name in ("smartflow_icon.ico", "smartflow_icon.png", "smartflow_logo.png", "smartpost_logo.jpg"):
        source = resource_root / "assets" / name
        if source.is_file():
            shutil.copy2(source, root / "assets" / name)
    config = root / "config.json"
    if not config.exists():
        defaults = dict(DEFAULTS, **{key: str(path) for key, path in bundled_tool_paths(resource_root).items()})
        if os.environ.get("SMARTFLOW_TEST_DATA_ROOT"):
            defaults["bridge_port"] = int(os.environ.get("SMARTFLOW_TEST_PORT", "19065"))
        # Exclusive creation avoids overwriting a simultaneous first launch.
        try:
            with config.open("x", encoding="utf-8") as stream:
                json.dump(defaults, stream, ensure_ascii=False, indent=2)
        except FileExistsError:
            pass
    return root
