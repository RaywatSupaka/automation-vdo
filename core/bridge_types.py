"""Static shapes for the browser bridge; validation remains in the bridge."""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


class AISendDiagnostics(TypedDict, total=False):
    gesture_phase: Literal["not_started", "pressed", "released", "release_uncertain"]
    dispatch_completed: bool
    trusted_click_seen: bool
    accepted: bool
    request_turn_id: str
    request_message_id: str
    preflight_reason: str
    tool_reason: str
    send_target_strategy: Literal["center", "viewport_scroll", "interior_point"]
    click_events: list[dict[str, object]]


class ExtensionCommand(TypedDict):
    action: str
    job_id: str
    shot_index: int
    run_id: str
    provider_hint: NotRequired[str]
