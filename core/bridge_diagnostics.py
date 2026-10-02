"""Bounded, prompt-free browser evidence validators.

These pure functions do not own bridge state or provider actions.
"""

import re
from collections.abc import Mapping

from core.bridge_types import AISendDiagnostics


def safe_ai_send_diagnostics(payload: Mapping[str, object]) -> AISendDiagnostics:
    """Keep bounded send evidence, never prompt text or arbitrary browser detail."""
    detail = payload.get("detail")
    sources = (detail if isinstance(detail, dict) else {}, payload)
    result = {}
    enums = {
        "request_reason": {"request_missing", "request_ambiguous", "conversation_changed",
                           "request_owner_changed", "request_changed", "owned_request",
                           "first_conversation_bound", "request_remounted"},
        "send_method": {
            "trusted_ai_send", "single_trusted_ai_send", "single_trusted_ai_send_unconfirmed",
        },
        "submission_proof": {
            "stop_button", "new_user_turn", "user_signature_changed",
            "new_assistant_turn", "composer_cleared", "owned_story_user_turn", "owned_motion_user_turn",
            "owned_chatgpt_user_turn", "owned_gemini_user_turn",
        },
        "gesture_phase": {
            "not_started", "pressed", "released", "release_uncertain",
        },
        "send_target_strategy": {
            "center", "viewport_scroll", "interior_point",
        },
        "tool_reason": {
            "composer_not_ready", "opener_missing", "opener_disabled", "menu_missing",
            "option_detached", "chip_unconfirmed", "response_active", "owner_changed",
            "draft_changed", "menu_ambiguous",
        },
        "preflight_reason": {
            "cancelled", "job_changed", "run_changed", "prompt_changed",
            "image_retry_guard", "text_guard_changed", "text_guard_unavailable",
            "readiness_unconfirmed", "response_active", "gemini_image_preflight",
            "draft_mismatch", "send_not_ready", "capture_missing", "target_changed",
            "readiness_changed", "target_blocked", "rejected_before_press",
            "chatgpt_image_tool", "send_target_ambiguous", "composer_form_changed",
        },
    }
    click_types = {"pointerdown", "mousedown", "pointerup", "mouseup", "click"}
    for source in sources:
        turn_id = source.get('request_turn_id')
        if isinstance(turn_id, str) and re.fullmatch(
            r'(?:conversation-turn-\d{1,8}|fallback-turn-\d{1,8}:\d{1,8}:user)', turn_id
        ):
            result['request_turn_id'] = turn_id
        message_id = source.get('request_message_id')
        if isinstance(message_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', message_id):
            result['request_message_id'] = message_id
        for key, allowed in enums.items():
            value = source.get(key)
            if isinstance(value, str) and value in allowed:
                result[key] = value
        for key in (
            "dispatch_completed", "trusted_click_seen", "draft_still_present",
            "target_changed", "release_on_send_target", "target_stable_before_press",
            "claim_match", "accepted", "request_owner_found", "request_matches",
        ):
            if type(source.get(key)) is bool:
                result[key] = source[key]
        length = source.get("prompt_length")
        if type(length) is int and 0 <= length <= 1_000_000:
            result["prompt_length"] = length
        for key in ("request_hash", "draft_hash"):
            value = source.get(key)
            if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{1,8}", value):
                result[key] = value
        wait_ms = source.get("request_recovery_wait_ms")
        if type(wait_ms) is int and 0 <= wait_ms <= 360_000:
            result["request_recovery_wait_ms"] = wait_ms
        for key in (
            "target_node_changes_prepress", "target_geometry_changes_prepress",
            "target_node_changes_during_gesture", "target_geometry_changes_during_gesture",
        ):
            value = source.get(key)
            if type(value) is int and 0 <= value <= 1000:
                result[key] = value
        allowed_fields = {
            "job", "run", "url", "prompt", "userCount", "userSignature",
            "assistantCount", "assistantSignature", "imageSignature", "sourceSignature",
            "send_not_ready", "response_active", "upload_busy", "image_expanded",
        }
        for key in ("changed_fields", "wait_changed_fields"):
            changed = source.get(key)
            if isinstance(changed, list):
                result[key] = list(dict.fromkeys(
                    item for item in changed[:32] if isinstance(item, str) and item in allowed_fields
                ))
        events = source.get("click_events")
        if isinstance(events, list):
            result["click_events"] = []
            for event in events[-10:]:
                if not (isinstance(event, dict)
                        and isinstance(event.get("type"), str) and event["type"] in click_types
                        and type(event.get("trusted")) is bool):
                    continue
                safe_event = {"type": event["type"], "trusted": event["trusted"]}
                if type(event.get("on_target")) is bool:
                    safe_event["on_target"] = event["on_target"]
                elapsed = event.get("elapsed_ms")
                if type(elapsed) is int and 0 <= elapsed <= 60_000:
                    safe_event["elapsed_ms"] = elapsed
                if isinstance(event.get("phase"), str) and event["phase"] in {"pressed", "released"}:
                    safe_event["phase"] = event["phase"]
                result["click_events"].append(safe_event)
    return result


def safe_ai_image_observation(payload: Mapping[str, object]) -> dict[str, object]:
    """Keep bounded image wait/reload facts; exclude provider text and prompts."""
    if payload.get("step") not in {"waiting_for_image", "recovering_result", "story_image_result_review",
                                   "image_refresh_check", "image_restart_pending", "image_restart_started",
                                   "image_result_verified"}:
        return {}
    result = {}
    for key, lower, upper in (("scene_index", 1, 50), ("candidate_count", 0, 20),
                              ("progress_count", 0, 20),
                              ("refresh_attempts", 0, 3), ("refreshed_check_ms", 0, 3_600_000),
                              ("stable_samples", 0, 100_000)):
        value = payload.get(key)
        if type(value) is int and lower <= value <= upper:
            result[key] = value
    enums = {
        "result_reason": {"waiting_response", "no_image", "image_loading", "image_ready",
                          "request_missing", "request_ambiguous", "wrong_conversation",
                          "request_not_latest", "conversation_pending", "multiple_images", "generating"},
        "refresh_outcome": {"not_attempted", "requested", "scheduled", "rejected_preclaim",
                            "rejected_unconfirmed", "ack_unknown", "receipt_unverified", "retry_exhausted"},
        "refresh_reason": {"none", "live_guard_changed", "owner_changed", "budget_used",
                           "refresh_in_progress", "invalid_proof", "claim_uncertain",
                           "controller_error", "transport_unknown"},
        "recovery_kind": {"missing_after_refresh", "unusable_after_refresh"},
        "recovery_phase": {"refresh_requested", "checking", "missing", "unusable",
                           "successor_claimed", "successor_created", "successor_resumed", "result_found"},
    }
    for key, allowed in enums.items():
        value = payload.get(key)
        if isinstance(value, str) and value in allowed:
            result[key] = value
    if type(payload.get("response_active")) is bool:
        result["response_active"] = payload["response_active"]
    for key in ("stop_visible", "stale_progress"):
        if type(payload.get(key)) is bool:
            result[key] = payload[key]
    signature = payload.get("response_signature")
    if isinstance(signature, str) and re.fullmatch(r"[0-9a-f]{1,16}", signature):
        result["response_signature"] = signature
    # These identify an attempt without copying the full prompt-bearing receipt identity.
    nonce = payload.get("send_nonce")
    if isinstance(nonce, str) and re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", nonce):
        result["send_nonce"] = nonce
    identifiers = safe_ai_send_diagnostics(payload)
    for key in ("request_message_id", "request_turn_id"):
        if key in identifiers:
            result[key] = identifiers[key]
    return result
