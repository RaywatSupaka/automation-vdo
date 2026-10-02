"""Pure UI state decisions shared by the legacy window and focused tests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def story_video_mode_key(
    selected_label: str = "",
    context: Mapping[str, Any] | None = None,
    modes: Mapping[str, str] | None = None,
) -> str:
    """Resolve the visible Story/Drama video choice without hidden overrides."""
    requested = str((context or {}).get("video_generation_mode") or "").strip().lower()
    if requested in {"image_motion", "google_flow", "meta_ai"}:
        return requested
    return (modes or {}).get(str(selected_label or ""), "image_motion")


def credit_state(configured: bool = False, message: str = "ยังไม่ได้เชื่อมต่อ", **values: Any) -> dict[str, Any]:
    state = {
        "configured": bool(configured),
        "connected": False,
        "loading": False,
        "credits": None,
        "unlimited": False,
        "message": str(message or ""),
        "expires_at": "",
    }
    state.update(values)
    return state


def video_render_settings(config: Mapping[str, Any], resolutions: Mapping[str, str]) -> dict[str, Any]:
    resolution = str(config.get("video_resolution", "720x1280"))
    if resolution not in set(resolutions.values()):
        resolution = "720x1280"
    width, height = (int(value) for value in resolution.split("x", 1))
    fps = int(config.get("video_fps", 30))
    if fps not in {0, 24, 30, 50, 60}:
        fps = 30
    quality = str(config.get("video_quality", "high"))
    crf = {"standard": 21, "high": 18, "maximum": 16}.get(quality, 18)
    return {
        "width": width, "height": height, "fps": fps, "crf": crf,
        "backend_version": 1, "encoder": config.get("video_encoder", "auto"), "green_filter_threads": 4,
        "motion_strength": max(0.0, min(1.5, float(config.get("video_motion_strength", 1.0)))),
        "transition_sec": max(0.0, min(0.6, float(config.get("video_transition_sec", 0.22)))),
    }
