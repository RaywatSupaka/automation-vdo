"""Isolated, read-only WebView2 lab for a future provider adapter.

This entry point is deliberately separate from app.py and the Chrome
Extension. It does not send prompts, upload files, download media, or touch
Story checkpoints. Run ``python -m desktop.provider_prototype --smoke`` for an
offline WebView2 check, or ``--provider chatgpt`` to inspect a separate session.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAB_ROOT = ROOT / "build" / "webview2-provider-prototype"
PROVIDERS = {"chatgpt": "https://chatgpt.com/"}
PROBE_SCRIPT = """(() => {
  const shown = node => {
    if (!node) return false;
    const r = node.getBoundingClientRect();
    const s = getComputedStyle(node);
    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const composer = [...document.querySelectorAll(
    '#prompt-textarea,textarea[data-testid="prompt-textarea"],[contenteditable="true"][role="textbox"]'
  )].find(shown);
  const send = [...document.querySelectorAll(
    'button[data-testid="send-button"],button[data-testid="composer-submit-button"]'
  )].find(button => shown(button) && !button.disabled && button.getAttribute('aria-disabled') !== 'true');
  return {
    origin: location.origin,
    ready: document.readyState,
    composer_visible: Boolean(composer),
    send_enabled: Boolean(send),
    file_inputs: document.querySelectorAll('input[type="file"]').length,
    user_turns: document.querySelectorAll('[data-message-author-role="user"]').length,
    assistant_turns: document.querySelectorAll('[data-message-author-role="assistant"]').length,
    images: document.querySelectorAll('img').length
  };
})()"""


def profile_path(base: Path, provider: str) -> Path:
    """A stable profile under the lab root, never the user's Chrome profile."""
    if provider not in {*PROVIDERS, "smoke"}:
        raise ValueError("Unknown prototype provider")
    base = Path(base).resolve()
    profile = (base / f"profile-{provider}").resolve()
    if profile.parent != base:
        raise ValueError("Prototype profile escaped its root")
    return profile


def bounded_snapshot(raw: object, provider: str) -> dict:
    """Allow only coarse UI signals into diagnostics; no page text or URLs."""
    if not isinstance(raw, dict):
        raise ValueError("WebView2 probe did not return an object")
    origin = str(raw.get("origin") or "")
    if provider == "chatgpt" and origin not in {"https://chatgpt.com", "https://auth.openai.com"}:
        return {"page": "other_origin", "ready": "unknown"}
    if provider == "smoke" and origin not in {"null", "about:blank", ""}:
        return {"page": "other_origin", "ready": "unknown"}
    result = {
        "page": ("auth" if origin == "https://auth.openai.com" else "provider")
        if provider == "chatgpt" else "offline_fixture",
        "ready": raw.get("ready") if raw.get("ready") in {"loading", "interactive", "complete"} else "unknown",
    }
    for key in ("composer_visible", "send_enabled"):
        result[key] = raw.get(key) is True
    for key in ("file_inputs", "user_turns", "assistant_turns", "images"):
        value = raw.get(key)
        result[key] = min(value, 1000) if type(value) is int and value >= 0 else 0
    return result


class TraceWriter:
    def __init__(self, path: Path, provider: str, session_id: str) -> None:
        self.path = Path(path)
        self.provider = provider
        self.session_id = session_id

    def write(self, event: str, snapshot: dict | None = None) -> None:
        if event not in {"started", "snapshot", "closed", "probe_error"}:
            raise ValueError("Unknown prototype event")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size >= 1024 * 1024:
            return  # Bounded diagnostics; never rotate by deleting user data.
        row = {
            "time": round(time.time(), 3),
            "session": self.session_id,
            "provider": self.provider,
            "event": event,
        }
        if snapshot is not None:
            row["snapshot"] = bounded_snapshot(snapshot, self.provider)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def run(provider: str = "chatgpt", *, smoke: bool = False,
        check_provider: bool = False, base: Path = LAB_ROOT) -> dict:
    import webview

    selected = "smoke" if smoke else provider
    if selected not in ({"smoke"} if smoke else PROVIDERS):
        raise ValueError("Unknown prototype provider")
    profile = profile_path(base, selected)
    profile.mkdir(parents=True, exist_ok=True)
    session = uuid.uuid4().hex
    trace = TraceWriter(Path(base) / "events.jsonl", selected, session)
    trace.write("started")
    finished = threading.Event()
    result: dict = {"ok": False, "provider": selected, "profile": str(profile), "session": session}

    if smoke:
        window = webview.create_window(
            "SmartFlow WebView2 Lab [OFFLINE]",
            html="<!doctype html><meta charset='utf-8'><title>Offline fixture</title>"
                 "<main><div id='prompt-textarea' role='textbox' contenteditable='true'></div>"
                 "<button data-testid='send-button'>Send</button><input type='file'></main>",
            width=720, height=500,
        )
    else:
        window = webview.create_window(
            "SmartFlow WebView2 Lab — ChatGPT (separate profile)",
            url=PROVIDERS[selected], width=1100, height=780,
        )
    if window is None:
        raise RuntimeError("WebView2 did not create a window")
    window.events.closed += finished.set

    def observe() -> None:
        previous = None
        deadline = time.monotonic() + 30 if check_provider else None
        while not finished.is_set():
            try:
                raw = window.evaluate_js(PROBE_SCRIPT)
                snapshot = bounded_snapshot(raw, selected)
                if snapshot != previous:
                    trace.write("snapshot", raw)
                    previous = snapshot
                if smoke:
                    result.update(ok=snapshot.get("page") == "offline_fixture"
                                  and snapshot.get("ready") == "complete",
                                  snapshot=snapshot)
                    window.destroy()
                    break
                if check_provider and snapshot.get("ready") == "complete" and snapshot.get("page") in {"provider", "auth"}:
                    result.update(ok=True, snapshot=snapshot)
                    window.destroy()
                    break
            except Exception as exc:
                # Navigation can interrupt JS evaluation. Keep observing the
                # new document; never persist exception text or page content.
                if previous != "probe_error":
                    trace.write("probe_error")
                    previous = "probe_error"
                result["error_type"] = type(exc).__name__
                if smoke:
                    window.destroy()
                    break
            if deadline is not None and time.monotonic() >= deadline:
                result["error_type"] = "Timeout"
                window.destroy()
                break
            finished.wait(1 if check_provider else 5)

    try:
        webview.start(func=observe, gui="edgechromium", debug=False,
                      private_mode=False, storage_path=str(profile))
    finally:
        finished.set()
        trace.write("closed")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolated WebView2 provider lab")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="chatgpt")
    parser.add_argument("--smoke", action="store_true", help="open a local, offline fixture and close automatically")
    parser.add_argument("--check-provider", action="store_true", help="read-only provider page load check, closing within 30 seconds")
    args = parser.parse_args()
    if args.smoke and args.check_provider:
        parser.error("choose one of --smoke and --check-provider")
    result = run(args.provider, smoke=args.smoke, check_provider=args.check_provider)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") or not (args.smoke or args.check_provider) else 1


if __name__ == "__main__":
    raise SystemExit(main())
