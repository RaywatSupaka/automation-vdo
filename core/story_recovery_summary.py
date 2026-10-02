"""Read-only, evidence-backed progress for a saved Story job."""

import re
import json
from pathlib import Path


_SCENE_FILE = re.compile(r"scene_0*([1-9][0-9]*)\.(?:png|jpe?g|webp)$", re.I)
_IMAGE_FAILURE = re.compile(r"(?:ภาพฉาก|ภาพ|image)\s*([1-9][0-9]*)", re.I)
_TRACE_FAILURES = ("AI_IMAGE_REFERENCE_UNCONFIRMED", "STORY_IMAGE_RECEIPT_REVIEW")


def _failed_scene_from_trace(folder, job_id):
    """Read only a bounded tail; an older success cannot turn into a failure."""
    path = folder / "logs" / "extension_trace.jsonl"
    try:
        with path.open("rb") as handle:
            length = handle.seek(0, 2)
            start = max(0, length - 128_000)
            handle.seek(start)
            lines = handle.read().decode("utf-8", errors="replace").splitlines()
        if start:
            lines = lines[1:]  # Discard a partial first JSON line.
    except OSError:
        return 0
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(row, dict) or row.get("job_id") != job_id:
            continue
        if row.get("action") == "image_checkpoint_saved":
            return 0
        message = str(row.get("message") or "")
        if row.get("action") == "image_attempt_result" and any(code in message for code in _TRACE_FAILURES):
            match = _IMAGE_FAILURE.search(message)
            return int(match[1]) if match else 0
    return 0


def story_recovery_summary(job, folder):
    """Report only committed local images; never infer a successful send from progress."""
    root = Path(folder).resolve()
    total = max(0, int(job.get("scene_count") or 0))
    saved = set()
    for field in ("generated_images", "partial_generated_images"):
        for relative in job.get(field) or []:
            if not isinstance(relative, str):
                continue
            match = _SCENE_FILE.fullmatch(Path(relative.replace("\\", "/")).name)
            if not match:
                continue
            index = int(match[1])
            candidate = (root / relative.replace("\\", "/")).resolve()
            if 1 <= index <= total and candidate.is_relative_to(root) and candidate.is_file():
                saved.add(index)
    error = str(job.get("last_error") or "")
    image_failure = _IMAGE_FAILURE.search(error) if error else None
    failed_scene = int(image_failure[1]) if image_failure else 0
    if not failed_scene and any(code in error for code in (*_TRACE_FAILURES, "AI_WEB_RESUME_REVIEW")):
        failed_scene = _failed_scene_from_trace(root, str(job.get("id") or root.name))
    if failed_scene < 1 or failed_scene > total or failed_scene in saved:
        failed_scene = 0
    return {
        "analysis_ready": str(job.get("analysis_status") or "").lower() == "ready",
        "saved_image_scenes": sorted(saved),
        "failed_image_scene": failed_scene,
        "send_not_started": bool(failed_scene and "CHATGPT_IMAGE_RESULT_SEND_NOT_STARTED" in error),
    }
