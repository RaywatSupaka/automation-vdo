"""One-shot DEV ChatGPT text request with a durable no-replay receipt.

This adapter never reads the SmartFlow shell DOM. It runs scripts only in the
isolated provider WebView2 control and does not route production Story jobs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from desktop.provider_prototype import LAB_ROOT


RECEIPT_PATH = LAB_ROOT / "embedded-request.json"
COMPOSER = ('rich-textarea div[contenteditable="true"],'
            '#prompt-textarea,textarea[data-testid="prompt-textarea"],'
            'div[contenteditable="true"][data-lexical-editor="true"],'
            'div.ProseMirror[contenteditable="true"]')
SEND = 'button[data-testid="send-button"],button[data-testid="composer-submit-button"]'
USER = '[data-message-author-role="user"]'
ASSISTANT = '[data-message-author-role="assistant"]'
STOP = 'button[data-testid="stop-button"]'
CHAT_URL = re.compile(r"https://chatgpt\.com/c/[A-Za-z0-9_:-]+")


def url_kind(url: str) -> str:
    if url == "https://chatgpt.com/":
        return "root"
    if CHAT_URL.fullmatch(url):
        return "conversation"
    return "other"


def _script(body: str, prompt: str | None = None) -> str:
    value = f"const expected={json.dumps(prompt, ensure_ascii=False)};" if prompt is not None else ""
    return f"""(() => {{
      const visible=n=>{{if(!n)return false;const r=n.getBoundingClientRect(),s=getComputedStyle(n);
        return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';}};
      const one=s=>[...document.querySelectorAll(s)].filter(visible);
      const norm=s=>String(s||'').trim().replace(/\\s+/g,' ');
      const editors=one({json.dumps(COMPOSER)});
      const editor=editors.length===1?editors[0]:null;
      const text=n=>n?(n.value!==undefined?n.value:n.innerText||n.textContent||''):'';
      const users=one({json.dumps(USER)}), assistants=one({json.dumps(ASSISTANT)});
      const sends=one({json.dumps(SEND)}).filter(n=>!n.disabled&&n.getAttribute('aria-disabled')!=='true');
      const stops=one({json.dumps(STOP)});
      const attachments=one('input[type="file"]').filter(n=>n.files?.length);
      {value}
      {body}
    }})()"""


PREFLIGHT = _script("""return {origin:location.origin,url:location.href,ready:document.readyState,
  composer_count:editors.length,draft_length:norm(text(editor)).length,
  attachments:attachments.length,busy:stops.length>0,
  login_visible:one('button,a').some(n=>/^(log in|sign in|เข้าสู่ระบบ)$/i.test(norm(text(n)))),
  user_count:users.length,assistant_count:assistants.length};""")


def prepare_script(prompt: str) -> str:
    return _script("""if(location.origin!=='https://chatgpt.com'||!editor||norm(text(editor))||
      one('button,a').some(n=>/^(log in|sign in|เข้าสู่ระบบ)$/i.test(norm(text(n))))||
      attachments.length||stops.length)return {ok:false,reason:'composer_not_empty_or_ready'};
      editor.focus();
      if(editor.tagName==='TEXTAREA'){editor.value=expected;editor.dispatchEvent(new Event('input',{bubbles:true}));}
      else {const selection=window.getSelection(),range=document.createRange();range.selectNodeContents(editor);
        selection.removeAllRanges();selection.addRange(range);
        if(!document.execCommand('insertText',false,expected))return {ok:false,reason:'insert_failed'};
        editor.dispatchEvent(new InputEvent('input',{bubbles:true,inputType:'insertText',data:expected}));}
      return {ok:norm(text(editor))===norm(expected),reason:'draft_written'};""", prompt)


def ready_script(prompt: str, baseline_users: int, url: str) -> str:
    return _script(f"""return {{ok:location.href==={json.dumps(url)}&&!!editor&&
      norm(text(editor))===norm(expected)&&attachments.length===0&&stops.length===0&&
      !one('button,a').some(n=>/^(log in|sign in|เข้าสู่ระบบ)$/i.test(norm(text(n))))&&
      users.length==={baseline_users}&&sends.length===1,send_count:sends.length,
      user_count:users.length,draft_matches:norm(text(editor))===norm(expected)}};""", prompt)


def click_script(prompt: str, baseline_users: int, url: str) -> str:
    return _script(f"""if(location.href!=={json.dumps(url)}||!editor||
      norm(text(editor))!==norm(expected)||attachments.length||stops.length||
      one('button,a').some(n=>/^(log in|sign in|เข้าสู่ระบบ)$/i.test(norm(text(n))))||
      users.length!=={baseline_users}||sends.length!==1)return {{clicked:false,reason:'send_preflight_changed'}};
      sends[0].click();return {{clicked:true}};""", prompt)


def observe_script(prompt: str) -> str:
    return _script("""const latestUser=users.at(-1),latestAssistant=assistants.at(-1);
      return {origin:location.origin,url:location.href,user_count:users.length,
        latest_user_matches:!!latestUser&&norm(text(latestUser))===norm(expected),
        assistant_count:assistants.length,assistant_text:String(text(latestAssistant)).slice(0,12000),
        busy:stops.length>0,draft_length:norm(text(editor)).length};""", prompt)


class RequestJournal:
    def __init__(self, path: Path = RECEIPT_PATH):
        self.path = Path(path)
        self.lock = threading.Lock()

    def read(self) -> dict:
        try:
            row = json.loads(self.path.read_text(encoding="utf-8"))
            return row if isinstance(row, dict) else {}
        except FileNotFoundError:
            return {}

    def start(self, prompt: str, *, job_id="", run_id="", scene_index=0, baseline=None) -> dict:
        if not prompt or len(prompt) > 12000 or len(prompt.strip()) < 3:
            raise ValueError("Prompt ต้องมี 3–12,000 ตัวอักษร")
        if job_id and not re.fullmatch(r"(?:STORY|LAB)-[A-Za-z0-9_-]{1,80}", job_id):
            raise ValueError("job_id ไม่ถูกต้อง")
        if run_id and not re.fullmatch(r"RUN-[A-Za-z0-9_-]{1,80}", run_id):
            raise ValueError("run_id ไม่ถูกต้อง")
        if type(scene_index) is not int or not 0 <= scene_index <= 50:
            raise ValueError("scene_index ไม่ถูกต้อง")
        with self.lock:
            current = self.read()
            if current.get("phase") not in {None, "completed", "reviewed_completed", "failed_before_send"}:
                raise RuntimeError("มีคำขอเดิมที่ยังไม่ยืนยันผล • ตรวจคำขอเดิมก่อน")
            if current.get("request_id"):
                self._archive(current)
            row = {
                "request_id": "WV2-" + uuid.uuid4().hex[:16].upper(),
                "job_id": job_id or "LAB-" + uuid.uuid4().hex[:12].upper(),
                "run_id": run_id or "RUN-" + uuid.uuid4().hex[:12].upper(),
                "scene_index": scene_index,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "phase": "prepared", "created_at": round(time.time(), 3),
                "baseline_user_count": int((baseline or {}).get("user_count") or 0),
                "baseline_assistant_count": int((baseline or {}).get("assistant_count") or 0),
                "conversation_sha256": hashlib.sha256(str((baseline or {}).get("url") or "").encode()).hexdigest(),
            }
            self._write(row)
            return dict(row)

    def transition(self, request_id: str, from_phases: set[str], phase: str, **fields) -> dict:
        with self.lock:
            row = self.read()
            if row.get("request_id") != request_id or row.get("phase") not in from_phases:
                raise RuntimeError("เจ้าของคำขอหรือสถานะเปลี่ยน • ไม่ส่งซ้ำ")
            row.update(phase=phase, updated_at=round(time.time(), 3), **fields)
            self._write(row)
            return dict(row)

    def _write(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(row, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, self.path)

    def _archive(self, row: dict) -> None:
        request_id = str(row.get("request_id") or "")
        if not re.fullmatch(r"WV2-[0-9A-F]{16}", request_id):
            raise RuntimeError("receipt เดิมไม่ถูกต้อง • ไม่ทับข้อมูล")
        target = self.path.parent / "embedded-request-receipts" / (request_id + ".json")
        if target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(row, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, target)


def preflight(snapshot: dict) -> str:
    if snapshot.get("origin") != "https://chatgpt.com" or snapshot.get("ready") != "complete":
        return "ChatGPT ยังไม่พร้อม"
    if snapshot.get("login_visible"):
        return "กรุณาเข้าสู่ระบบในหน้า AI Chat ก่อน"
    if snapshot.get("composer_count") != 1:
        return "ไม่พบช่องข้อความที่แน่นอน"
    if snapshot.get("draft_length") or snapshot.get("attachments") or snapshot.get("busy"):
        return "ช่องข้อความมีงานเดิมหรือ ChatGPT ยังทำงานอยู่"
    return ""


class OneShotRunner:
    """One isolated text request; unknown Send is review-only, never replayed."""

    def __init__(self, provider, journal: RequestJournal, *, sleep=time.sleep, now=time.monotonic):
        self.provider = provider
        self.journal = journal
        self.sleep = sleep
        self.now = now
        self.answer = ""
        self.message = ""

    def _read(self, script: str) -> dict:
        value = json.loads(self.provider.evaluate(script))
        if not isinstance(value, dict):
            raise ValueError("provider_result_invalid")
        return value

    def probe(self) -> dict:
        snapshot = self._read(PREFLIGHT)
        return {"ready": not bool(preflight(snapshot)), "reason": preflight(snapshot),
                "composer_count": snapshot.get("composer_count"),
                "busy": bool(snapshot.get("busy")), "login_visible": bool(snapshot.get("login_visible"))}

    def run(self, prompt: str, *, job_id="", run_id="", scene_index=0,
            acceptance_timeout=15, result_timeout=180) -> dict:
        snapshot = self._read(PREFLIGHT)
        reason = preflight(snapshot)
        if reason:
            raise ValueError(reason)
        url = str(snapshot["url"])
        if not (url == "https://chatgpt.com/" or CHAT_URL.fullmatch(url)):
            raise ValueError("หน้า ChatGPT ไม่ใช่หน้าแชตที่รองรับ")
        row = self.journal.start(prompt, job_id=job_id, run_id=run_id,
                                 scene_index=scene_index, baseline=snapshot)
        request_id = row["request_id"]
        try:
            prepared = self._read(prepare_script(prompt))
            if not prepared.get("ok"):
                self.journal.transition(request_id, {"prepared"}, "failed_before_send",
                                        reason=str(prepared.get("reason") or "draft_failed")[:80])
                return self.journal.read()
            deadline = self.now() + 6
            ready = False
            while self.now() < deadline:
                current = self._read(ready_script(prompt, row["baseline_user_count"], url))
                if current.get("ok"):
                    ready = True
                    break
                self.sleep(0.25)
            if not ready:
                self.journal.transition(request_id, {"prepared"}, "failed_before_send",
                                        reason="send_not_ready")
                return self.journal.read()
        except Exception:
            self.journal.transition(request_id, {"prepared"}, "needs_review",
                                    reason="pre_send_observation_unknown")
            return self.journal.read()

        # This durable transition precedes the only possible provider click.
        self.journal.transition(request_id, {"prepared"}, "dispatching")
        try:
            clicked = self._read(click_script(prompt, row["baseline_user_count"], url))
        except Exception:
            clicked = {"clicked": False, "reason": "click_outcome_unknown"}
        if not clicked.get("clicked"):
            self.journal.transition(request_id, {"dispatching"}, "needs_review",
                                    reason=str(clicked.get("reason") or "click_outcome_unknown")[:80])
            return self.journal.read()

        deadline = self.now() + acceptance_timeout
        accepted = None
        last_evidence = {}
        while self.now() < deadline:
            try:
                current = self._read(observe_script(prompt))
                current_url = str(current.get("url") or "")
                last_evidence = {
                    "observed_url_kind": url_kind(current_url),
                    "observed_user_count": int(current.get("user_count") or 0),
                    "observed_assistant_count": int(current.get("assistant_count") or 0),
                    "observed_user_matches": current.get("latest_user_matches") is True,
                    "observed_busy": bool(current.get("busy")),
                    "observed_draft_length": int(current.get("draft_length") or 0),
                }
                if CHAT_URL.fullmatch(current_url):
                    last_evidence["conversation_path"] = current_url[len("https://chatgpt.com"):]
                if current.get("origin") != "https://chatgpt.com":
                    break
                if current_url != url and not (url == "https://chatgpt.com/" and
                                               CHAT_URL.fullmatch(current_url)):
                    break
                if (current.get("latest_user_matches") is True and
                        int(current.get("user_count") or 0) > row["baseline_user_count"]):
                    accepted = current
                    break
            except Exception:
                pass
            self.sleep(0.5)
        if accepted is None:
            self.journal.transition(request_id, {"dispatching"}, "needs_review",
                                    reason="send_acceptance_unconfirmed", **last_evidence)
            return self.journal.read()
        owned_url = str(accepted["url"])
        self.journal.transition(request_id, {"dispatching"}, "accepted",
                                conversation_sha256=hashlib.sha256(owned_url.encode()).hexdigest(),
                                conversation_path=(owned_url[len("https://chatgpt.com"):] if
                                                   CHAT_URL.fullmatch(owned_url) else ""))

        deadline = self.now() + result_timeout
        stable_text = ""
        stable_samples = 0
        last_result_evidence = {}
        while self.now() < deadline:
            try:
                current = self._read(observe_script(prompt))
                current_url = str(current.get("url") or "")
                last_result_evidence = {
                    "observed_url_kind": url_kind(current_url),
                    "observed_user_count": int(current.get("user_count") or 0),
                    "observed_assistant_count": int(current.get("assistant_count") or 0),
                    "observed_user_matches": current.get("latest_user_matches") is True,
                    "observed_busy": bool(current.get("busy")),
                }
                if current.get("origin") != "https://chatgpt.com" or url_kind(current_url) == "other":
                    break
                if current_url != owned_url:
                    # ChatGPT can replace provisional /c/WEB:... with a stable
                    # conversation ID. Adopt only after the exact new user turn
                    # is visible on that route, never on URL shape alone.
                    if (CHAT_URL.fullmatch(current_url) and
                            current.get("latest_user_matches") is True and
                            int(current.get("user_count") or 0) > row["baseline_user_count"]):
                        owned_url = current_url
                        self.journal.transition(request_id, {"accepted"}, "accepted",
                                                conversation_path=current_url[len("https://chatgpt.com"):],
                                                conversation_sha256=hashlib.sha256(current_url.encode()).hexdigest())
                    else:
                        stable_samples = 0
                        self.sleep(1)
                        continue
                if current.get("latest_user_matches") is not True:
                    stable_samples = 0
                    self.sleep(1)
                    continue
                answer = str(current.get("assistant_text") or "").strip()
                ready_answer = (int(current.get("assistant_count") or 0) >
                                row["baseline_assistant_count"] and
                                not current.get("busy") and bool(answer))
                if ready_answer:
                    stable_samples = stable_samples + 1 if answer == stable_text else 1
                    stable_text = answer
                    if stable_samples >= 3:
                        self.answer = answer
                        self.journal.transition(request_id, {"accepted"}, "completed",
                                                answer_sha256=hashlib.sha256(answer.encode()).hexdigest(),
                                                answer_length=len(answer))
                        return self.journal.read()
                else:
                    stable_samples = 0
            except Exception:
                pass
            self.sleep(1)
        self.journal.transition(request_id, {"accepted"}, "needs_review",
                                reason="result_unconfirmed", **last_result_evidence)
        return self.journal.read()
