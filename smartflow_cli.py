"""Safe, compact terminal client for a locally running SmartFlow AI bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_PORT = 8765
MAX_BODY_BYTES = 2 * 1024 * 1024
READ_PATHS = frozenset(("/health", "/api/desktop/state?mode=compact", "/api/extension/status"))
ACTION_PATH = "/api/desktop/action"
QUEUE_ITEM_FIELDS = ("queue_id", "job_id", "request_id", "status", "mode", "order", "attempt")
PROGRESS_FIELDS = ("product_progress", "story_progress", "presenter_progress")


class CliError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _safe_int(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _request_json(method, path, payload=None, port=DEFAULT_PORT, timeout=8.0):
    method = str(method).upper()
    if method == "GET" and path not in READ_PATHS:
        raise CliError(4, "CLI blocked a non-allowlisted read endpoint.")
    if method == "POST" and path != ACTION_PATH:
        raise CliError(4, "CLI blocked a non-allowlisted write endpoint.")
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:{int(port)}{path}",
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BODY_BYTES + 1)
            if len(raw) > MAX_BODY_BYTES:
                code = 3 if method == "POST" else 2
                message = ("Write response exceeded the safety limit; outcome is unknown, inspect the same request ID."
                           if method == "POST" else "SmartFlow response exceeded the CLI safety limit.")
                raise CliError(code, message)
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("Expected a JSON object")
            return value
    except HTTPError as exc:
        # A received HTTP response is a definite rejection; do not expose its body.
        raise CliError(1, f"SmartFlow rejected the request (HTTP {exc.code}); details redacted.") from None
    except (TimeoutError, URLError, OSError, ValueError, json.JSONDecodeError):
        if method == "POST":
            raise CliError(3, "Write outcome is unknown; inspect the same request ID before retrying.") from None
        raise CliError(2, "SmartFlow bridge is unavailable or returned invalid JSON; CLI did not launch it.") from None


def _snapshot(request_json, port):
    health = request_json("GET", "/health", port=port)
    if health.get("ok") is not True or health.get("service") != "Shopee AutoPost Local Bridge":
        raise CliError(2, "The loopback service is not the expected SmartFlow bridge.")
    state = request_json("GET", "/api/desktop/state?mode=compact", port=port)
    extension = request_json("GET", "/api/extension/status", port=port)
    if state.get("ok") is not True or extension.get("ok") is not True:
        raise CliError(2, "SmartFlow activity or Extension status is unavailable.")
    return health, state, _extension_summary(health, extension)


def _extension_summary(health, payload):
    """Extract version/connection only; never return the bridge's client traces."""
    required = health.get("extension_version_required")
    clients = payload.get("clients") if isinstance(payload.get("clients"), list) else []
    client = payload.get("client") if isinstance(payload.get("client"), dict) else {}
    version = client.get("version")
    connected = payload.get("connected") is True
    compatible = (version == required) if connected and version and required else False if not connected else None
    all_compatible = (all(isinstance(row, dict) and row.get("version") == required for row in clients)
                      if clients and required else None)
    return {
        "connected": connected,
        "version": version,
        "required_version": required,
        "compatible": compatible,
        "client_count": len(clients) if payload.get("connected") is True else 0,
        "all_clients_compatible": all_compatible,
    }


def _queue_summary(state):
    raw = state.get("creation_queue")
    if not isinstance(raw, dict):
        return None
    counts = raw.get("counts") if isinstance(raw.get("counts"), dict) else {}
    rows = raw.get("items") if isinstance(raw.get("items"), list) else []
    safe_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        safe_rows.append({key: row.get(key) for key in QUEUE_ITEM_FIELDS if key in row})
    return {
        "paused": raw.get("paused") if isinstance(raw.get("paused"), bool) else None,
        "pause_reason": raw.get("pause_reason") if isinstance(raw.get("pause_reason"), str) else None,
        "counts": {key: _safe_int(counts.get(key)) for key in ("queued", "running", "completed", "failed", "cancelled")},
        "items": safe_rows,
    }


def _compact_status(health, state, extension):
    required = health.get("extension_version_required")
    connected_version = extension.get("version")
    compatible = extension.get("compatible")
    queue = _queue_summary(state)
    progress = {}
    for key in PROGRESS_FIELDS:
        item = state.get(key) if isinstance(state.get(key), dict) else {}
        active = item.get("active") if isinstance(item.get("active"), bool) else None
        progress[key.removesuffix("_progress")] = {
            "active": active,
            "state": "busy" if active is True else "idle" if active is False else "unknown",
        }
    return {
        "ok": True,
        "program": {
            "version": health.get("release_version"),
            "extension_required": required,
            "desktop_ui": health.get("desktop_ui"),
        },
        "extension": {
            "connected": extension.get("connected") is True,
            "version": connected_version,
            "compatible": compatible if isinstance(compatible, bool) else None,
            "required_version": extension.get("required_version") or required,
        },
        "activity": progress,
        "queue": None if queue is None else {
            "paused": queue["paused"],
            "counts": queue["counts"],
        },
    }


def _queue_state(request_json, port):
    health = request_json("GET", "/health", port=port)
    if health.get("ok") is not True or health.get("service") != "Shopee AutoPost Local Bridge":
        raise CliError(2, "The loopback service is not the expected SmartFlow bridge.")
    state = request_json("GET", "/api/desktop/state?mode=compact", port=port)
    if state.get("ok") is not True:
        raise CliError(2, "SmartFlow queue state is unavailable.")
    queue = _queue_summary(state)
    if queue is None:
        raise CliError(2, "This SmartFlow build does not expose queue state in compact mode.")
    return queue


def _emit(data, output):
    output.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    output.flush()


def _request_identifier(value):
    value = str(value or "").strip()
    if not value:
        value = uuid.uuid4().hex
    if len(value) > 100 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise CliError(4, "request_id must use 1-100 letters, numbers, underscores or hyphens.")
    return value


def _load_enqueue_payload(path):
    try:
        raw = Path(path).read_bytes()
        if len(raw) > MAX_BODY_BYTES:
            raise CliError(4, "Input JSON exceeds the CLI safety limit.")
        payload = json.loads(raw.decode("utf-8-sig"))
    except CliError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise CliError(4, "Could not read a valid UTF-8 JSON request file.") from None
    if not isinstance(payload, dict):
        raise CliError(4, "Request file must contain one JSON object.")
    if "action" in payload or "commands" in payload:
        raise CliError(4, "Request file cannot choose raw actions or Extension commands.")
    mode = payload.get("mode")
    values = payload.get("values")
    if mode not in {"story", "product"} or not isinstance(values, list) or not values:
        raise CliError(4, "Request must include mode=story|product and a non-empty values array.")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise CliError(4, "Every values entry must be a non-empty string.")
    return payload


def _queue_add(args, request_json, output):
    payload = _load_enqueue_payload(args.input)
    values = payload["values"]
    request_id = _request_identifier(args.request_id or payload.get("request_id"))
    if len(values) > 1 and not args.allow_batch:
        raise CliError(4, "Batch enqueue requires --allow-batch; no items were sent.")
    payload = {**payload, "request_id": request_id}
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    if not args.commit:
        _emit({"ok": True, "mode": "dry_run", "request_id": request_id, "item_count": len(values),
               "payload_sha256": digest, "sent": False}, output)
        return 0

    queue = _queue_state(request_json, args.port)
    existing = next((row for row in queue["items"] if row.get("request_id") == request_id), None)
    if existing:
        _emit({"ok": True, "mode": "already_queued", "request_id": request_id,
               "queue_id": existing.get("queue_id"), "job_id": existing.get("job_id"), "sent": False}, output)
        return 0

    # Print the caller-owned ID before dispatch so a lost ACK can be reconciled without resending.
    _emit({"ok": None, "mode": "submitting", "request_id": request_id,
           "item_count": len(values), "payload_sha256": digest}, output)
    result = request_json("POST", ACTION_PATH, {"action": "creation_enqueue", "payload": payload}, port=args.port)
    if result.get("ok") is not True:
        raise CliError(1, "SmartFlow did not accept the queue request; inspect this request ID before retrying.")
    items = result.get("items") if isinstance(result.get("items"), list) else []
    duplicates = _safe_int(result.get("duplicates"))
    _emit({"ok": True, "mode": "deduplicated" if duplicates and not items else "queued", "request_id": request_id,
           "queue_ids": [row.get("queue_id") for row in items if isinstance(row, dict) and row.get("queue_id")],
           "duplicates": duplicates, "paused": result.get("paused")}, output)
    return 0


def _queue_start(args, request_json, output):
    if not args.confirm_all:
        raise CliError(4, "Starting the queue requires --confirm-all because it runs every queued item.")
    health, state, extension = _snapshot(request_json, args.port)
    queue = _queue_summary(state)
    if queue is None:
        raise CliError(2, "SmartFlow queue state is unavailable.")
    queued = queue["counts"].get("queued")
    if queued is None:
        queued = sum(1 for row in queue["items"] if row.get("status") == "queued")
    if queued < 1:
        raise CliError(4, "There are no queued items to start.")
    if queue["paused"] is not True:
        raise CliError(4, "Queue is not confirmed paused; refusing a start action from an unknown state.")
    if args.expect_queued != queued:
        raise CliError(4, f"Queue changed: expected {args.expect_queued}, now {queued}; nothing was started.")
    # Check Extension readiness before invoking the existing all-queue action.
    if extension.get("connected") is not True or extension.get("compatible") is not True:
        raise CliError(4, "Extension is not connected with a compatible version; nothing was started.")
    result = request_json("POST", ACTION_PATH, {"action": "creation_start", "payload": {}}, port=args.port)
    if result.get("ok") is not True:
        raise CliError(1, "SmartFlow rejected queue start; inspect status before another command.")
    _emit({"ok": True, "mode": "started", "started_queue_count": queued,
           "warning": "This starts the whole current queue, not a single item."}, output)
    return 0


def _queue_pause(args, request_json, output):
    if not args.confirm:
        raise CliError(4, "Pausing the queue requires --confirm.")
    queue = _queue_state(request_json, args.port)
    if queue["paused"] is True:
        _emit({"ok": True, "mode": "already_paused", "sent": False}, output)
        return 0
    result = request_json("POST", ACTION_PATH, {"action": "creation_pause", "payload": {}}, port=args.port)
    if result.get("ok") is not True:
        raise CliError(1, "SmartFlow rejected queue pause.")
    _emit({"ok": True, "mode": "paused", "note": "Pauses queued work; it does not claim to stop an active provider request."}, output)
    return 0


def _run_service(args, request_json, host_factory, output):
    try:
        health = request_json("GET", "/health", port=args.port, timeout=2.0)
    except CliError as exc:
        if exc.code != 2:
            raise
        health = None
    if health and health.get("service") != "Shopee AutoPost Local Bridge":
        raise CliError(4, "Port is occupied by a different service; refusing to start an engine.")
    if health and health.get("ok") is True:
        _emit({"ok": True, "mode": "already_running", "port": args.port,
               "note": "Attached to existing program; CLI will not open or focus its UI."}, output)
        return 0
    if not args.confirm_startup_recovery:
        raise CliError(4, "Starting the hidden engine runs the program's normal checkpoint-recovery pass; add --confirm-startup-recovery to allow it.")

    host = host_factory(args.port)
    try:
        host.start_engine()
        _emit({"ok": True, "mode": "headless_service_running", "port": args.port,
               "engine_pid": host.engine_pid, "owned_engine": bool(host.owns_engine),
               "stop": "Press Ctrl+C in this terminal; only an engine started by this CLI will be stopped."}, output)
        try:
            # Block without polling. Individual CLI commands read the bridge separately.
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0
    except Exception:
        raise CliError(2, "Headless engine failed to start; see SmartFlow's local engine log.") from None
    finally:
        host.stop()


def build_parser():
    parser = argparse.ArgumentParser(description="SmartFlow AI local terminal client; loopback only.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SMARTFLOW_BRIDGE_PORT", DEFAULT_PORT)))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Read compact program, queue and Extension status.")
    queue = sub.add_parser("queue", help="Inspect or explicitly operate the existing creation queue.")
    qsub = queue.add_subparsers(dest="queue_command", required=True)
    qsub.add_parser("list", help="List queue IDs and states without topics or prompts.")
    add = qsub.add_parser("add", help="Dry-run an enqueue; --commit sends exactly once.")
    add.add_argument("--input", required=True, help="UTF-8 JSON file using the existing creation_enqueue payload shape.")
    add.add_argument("--request-id", help="Stable ID for reconciliation after an unknown response.")
    add.add_argument("--commit", action="store_true", help="Send the enqueue request; otherwise dry-run only.")
    add.add_argument("--allow-batch", action="store_true", help="Explicitly allow more than one item in the request file.")
    start = qsub.add_parser("start", help="Start all currently queued work (may invoke provider generation).")
    start.add_argument("--expect-queued", type=int, required=True, help="Expected queue count from a recent `queue list`.")
    start.add_argument("--confirm-all", action="store_true", help="Confirm starting the entire queue.")
    pause = qsub.add_parser("pause", help="Pause future queue dispatch; does not stop an active request.")
    pause.add_argument("--confirm", action="store_true")
    service = sub.add_parser("service", help="Run or attach to the hidden SmartFlow engine.")
    service_sub = service.add_subparsers(dest="service_command", required=True)
    run = service_sub.add_parser("run", help="Start the engine without opening WebView; keep this terminal session alive.")
    run.add_argument("--confirm-startup-recovery", action="store_true",
                     help="Allow the normal startup pass to mark orphaned running items for checkpoint review.")
    return parser


def main(argv=None, *, request_json=None, host_factory=None, output=None, error_output=None):
    output = output or sys.stdout
    error_output = error_output or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        _emit({"ok": False, "error": "port must be between 1 and 65535"}, error_output)
        return 4
    request_json = request_json or _request_json
    try:
        if args.command == "status":
            health, state, extension = _snapshot(request_json, args.port)
            _emit(_compact_status(health, state, extension), output)
            return 0
        if args.command == "queue":
            if args.queue_command == "list":
                queue = _queue_state(request_json, args.port)
                _emit({"ok": True, "paused": queue["paused"], "counts": queue["counts"], "items": queue["items"]}, output)
                return 0
            if args.queue_command == "add":
                return _queue_add(args, request_json, output)
            if args.queue_command == "start":
                return _queue_start(args, request_json, output)
            if args.queue_command == "pause":
                return _queue_pause(args, request_json, output)
        if args.command == "service" and args.service_command == "run":
            if host_factory is None:
                from desktop.hybrid import HybridHost
                host_factory = lambda port: HybridHost(port=port, page="dashboard")
            return _run_service(args, request_json, host_factory, output)
    except CliError as exc:
        _emit({"ok": False, "code": exc.code, "error": str(exc)}, error_output)
        return exc.code
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
