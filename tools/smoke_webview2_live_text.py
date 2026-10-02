"""Explicit DEV-only one-request ChatGPT smoke using the embedded profile.

Close the source SmartFlow window before running so WebView2 can reuse its
profile. This script never resumes a Story job or replays an uncertain Send.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import webview

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop import embedded_provider
from desktop.embedded_provider import EmbeddedProvider
from desktop.webview2_request import OneShotRunner, RequestJournal, observe_script


def recent_owned_conversation(created_at):
    history = embedded_provider.PROFILE / "EBWebView" / "Default" / "History"
    if not history.is_file():
        return ""
    chrome_time = int((created_at + 11644473600) * 1_000_000)
    with sqlite3.connect(f"file:{history.as_posix()}?mode=ro", uri=True) as database:
        rows = list(database.execute(
            "SELECT DISTINCT urls.url FROM visits JOIN urls ON visits.url=urls.id "
            "WHERE urls.url LIKE ? AND visits.visit_time BETWEEN ? AND ?",
            ("https://chatgpt.com/c/%", chrome_time - 120_000_000, chrome_time + 120_000_000)))
    matches = []
    for (url,) in rows:
        if re.fullmatch(r"https://chatgpt\.com/c/[A-Za-z0-9_:-]+", url):
            matches.append(url)
    return matches[0] if len(matches) == 1 else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="send one harmless text request")
    parser.add_argument("--inspect-pending", action="store_true", help="read only the saved one-request chat")
    args = parser.parse_args()
    if os.environ.get("SMARTFLOW_DEV_BYPASS_MEMBERSHIP") != "1":
        raise SystemExit("DEV MODE only")
    if args.send and RequestJournal().read().get("phase") not in {None, "completed", "failed_before_send"}:
        raise SystemExit("An earlier Send needs review; no replay")

    result = {"ok": False, "ready": False, "phase": "", "answer_matches": False}
    prompt = "ตอบเพียงคำว่า WEBVIEW2_OK โดยไม่มีข้อความอื่น"
    if args.inspect_pending:
        receipt = RequestJournal().read()
        if receipt.get("phase") != "needs_review":
            raise SystemExit("No uncertain request")
        conversation = recent_owned_conversation(float(receipt["created_at"]))
        if not conversation:
            raise SystemExit("No unique recent conversation for this receipt")
        embedded_provider.PROVIDER_URL = conversation
    window = webview.create_window("SmartFlow AI Chat live smoke", html="<body style='background:#080c18'></body>",
                                   width=1150, height=780)
    provider = EmbeddedProvider(window)

    def check():
        try:
            deadline = time.monotonic() + 15
            while getattr(window, "native", None) is None and time.monotonic() < deadline:
                time.sleep(0.2)
            window.evaluate_js("document.readyState")
            rect = {"left": 0, "top": 0, "width": 1100, "height": 730,
                    "viewport_width": 1150, "viewport_height": 780}
            shown = provider.show(rect)
            if not shown.get("ok"):
                result["reason"] = shown.get("error") or "provider_not_open"
                return
            runner = OneShotRunner(provider, RequestJournal())
            deadline = time.monotonic() + 35
            probe = {}
            while time.monotonic() < deadline:
                try:
                    probe = runner.probe()
                    if probe.get("ready") or probe.get("login_visible"):
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            result["ready"] = bool(probe.get("ready"))
            if args.inspect_pending:
                observed = json.loads(provider.evaluate(observe_script(prompt)))
                structure = json.loads(provider.evaluate("""(() => ({
                  legacy_turns:document.querySelectorAll('[data-message-author-role]').length,
                  conversation_turns:document.querySelectorAll('[data-testid="conversation-turn"]').length,
                  message_ids:document.querySelectorAll('[data-message-id]').length,
                  articles:document.querySelectorAll('article').length,
                  prompt_visible:document.body.innerText.includes('WEBVIEW2_OK'),
                  body_length:document.body.innerText.length,
                  path_kind:location.pathname.startsWith('/c/')?'conversation':'other'
                }))()"""))
                result.update(phase="needs_review",
                              latest_user_matches=observed.get("latest_user_matches") is True,
                              user_count=observed.get("user_count"),
                              assistant_count=observed.get("assistant_count"),
                              busy=observed.get("busy"),
                              answer_matches=str(observed.get("assistant_text") or "").strip() == "WEBVIEW2_OK")
                result["structure"] = structure
                result["ok"] = bool(result["latest_user_matches"])
                return
            if not result["ready"]:
                result["reason"] = probe.get("reason") or "provider_not_ready"
                return
            if not args.send:
                result["ok"] = True
                return
            receipt = runner.run(prompt, acceptance_timeout=20, result_timeout=120)
            result["phase"] = receipt.get("phase") or ""
            result["request_id"] = receipt.get("request_id") or ""
            result["answer_matches"] = runner.answer.strip() == "WEBVIEW2_OK"
            result["ok"] = result["phase"] == "completed" and result["answer_matches"]
            if not result["ok"]:
                result["reason"] = receipt.get("reason") or "answer_unexpected"
        except Exception as exc:
            result["reason"] = type(exc).__name__
        finally:
            time.sleep(1)
            window.destroy()

    webview.start(func=check, gui="edgechromium", private_mode=False,
                  storage_path=str(ROOT / "build" / "webview2-provider-prototype" / "smoke-shell-profile"))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
