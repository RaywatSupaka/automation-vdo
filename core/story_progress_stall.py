"""Detect a Story image request that stopped reporting before Send proof."""

from datetime import datetime


def image_prompt_ready_stalled(client, job_id, run_id, *, now=None, limit_seconds=180):
    """Return true only for the same run's stale, acknowledged pre-Send step.

    A heartbeat does not refresh ai_updated_at. Later progress, including an
    accepted or uncertain Send, replaces ai_step and vetoes this guard.
    """
    if not isinstance(client, dict) or client.get("ai_step") != "image_prompt_ready":
        return False
    if not job_id or not run_id or client.get("ai_job_id") != job_id or client.get("ai_run_id") != run_id:
        return False
    if (client.get("ai_observation") or {}).get("acknowledged") is False:
        return False
    try:
        updated = datetime.fromisoformat(str(client.get("ai_updated_at") or ""))
    except ValueError:
        return False
    current = now or datetime.now(updated.tzinfo)
    if (current.tzinfo is None) != (updated.tzinfo is None):
        return False
    return (current - updated).total_seconds() >= limit_seconds
