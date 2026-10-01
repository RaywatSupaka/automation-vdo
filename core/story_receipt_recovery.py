"""Read-only evidence for the narrowly identified 0.15.259 pre-image failure.

Never infer no submission from a missing checkpoint or from an arbitrary error.
Only a complete, adjacent saved-analysis -> first-image -> old receipt-ACK error
trace qualifies. Every other receipt remains a manual-review stop.
"""
import json
import re
from datetime import datetime
from pathlib import Path


def pending_story_image_target(folder, job, rows):
    """Route to the pending image's chat; navigation alone never permits Send.

    The optional v373 proof is limited to the observed *pre-click* rejection.
    The Extension must additionally match its receipt, intact draft, URL, no
    dispatch nonce and no accepted request before preparing the first Send.
    """
    if not str(job.get('id', '')).startswith('STORY-') or job.get('image_ai_provider', 'chatgpt') != 'chatgpt':
        return None
    rows = [r for r in rows if r.get('job_id') == job['id'] and r.get('service') == 'chatgpt']
    position = next((i for i in range(len(rows) - 1, -1, -1) if rows[i].get('action') == 'image_prompt_ready'), None)
    if position is None:
        return None
    ready = rows[position]
    detail = ready.get('detail') or {}
    index = detail.get('scene_index')
    if type(index) is not int or index < 1:
        return None
    if (Path(folder) / 'generated' / f'scene_{index:02d}.png').is_file():
        return None
    scope = ('job_id', 'service', 'client_id', 'run_id', 'tab_id')
    same = lambda row: all(row.get(k) == ready.get(k) for k in scope)
    from core.ai_web_resume import conversation_url
    # Root -> /c/ after the FIRST accepted send is normal. Only the same
    # job/run/tab's later URL may bind that initially unknown conversation.
    url = conversation_url(ready.get('page_url'), 'chatgpt') or next((
        conversation_url(r.get('page_url'), 'chatgpt') for r in reversed(rows[position:])
        if same(r) and conversation_url(r.get('page_url'), 'chatgpt')), '')
    if not url:
        return None
    # The latest owned image request has an explicit completed no-image answer.
    # It is no longer a pending Send that must reopen the old conversation.
    # A later image_prompt_ready supersedes this proof automatically because
    # `position` is always the newest request for this Job.
    terminal = next((i for i in range(position + 1, len(rows))
                     if same(rows[i]) and rows[i].get('action') == 'image_attempt_result'
                     and re.search(rf'^ภาพ {index} • ครั้ง [1-9][0-9]* • CHATGPT_NO_IMAGE • reference_required • ',
                                   str(rows[i].get('message') or ''))), None)
    if terminal is not None and any(
        same(row) and row.get('action') == 'error'
        and f'STORY_REFERENCE_REQUIRED • ' in str(row.get('message') or '')
        and f'ฉาก {index}' in str(row.get('message') or '')
        for row in rows[terminal + 1:]
    ):
        return None
    target = dict(required=True, stage='image', provider='chatgpt', index=index,
                  conversation_url=url, evidence='image_prompt_ready')
    try:
        attempt, failed = rows[position + 1:position + 3]
        prior = rows[max(0, position - 2):position]
        start = next(r for r in prior if r.get('action') == 'generating_images')
        expected = (rf'ผิดพลาด: STORY_IMAGE_RECEIPT_REVIEW • ภาพฉาก {index} • '
                    r'CHATGPT_IMAGE_RESULT_SEND_UNCONFIRMED • Prompt เปลี่ยนหรือไม่ครบก่อนกดส่ง '
                    r'\([0-9]+/[0-9]+ ตัวอักษร\) จึงยังไม่คลิก • เก็บฉากเดิมไว้ ไม่สร้างภาพซ้ำ')
        group = [start, ready, attempt, failed]
        if any(not same(r) or r.get('version') != '0.15.373' or r.get('page_url') != url for r in group):
            return target
        if (attempt.get('action') != 'image_attempt_result' or failed.get('action') != 'error'
                or type(ready.get('sequence')) is not int
                or attempt.get('sequence') != ready['sequence'] + 1
                or failed.get('sequence') != ready['sequence'] + 2
                or not re.fullmatch(expected, str(failed.get('message', '')))):
            return target
        passive = {'ai_model_ready', 'waiting_for_analysis', 'analysis_saved', 'generating_images',
                   'recovering_images', 'waiting_for_image', 'story_image_result_review', 'error'}
        if any(r.get('action') not in passive or r.get('client_id') != ready.get('client_id')
               for r in rows[position + 3:]):
            return target
        prompt = re.sub(r'\s+', ' ', str(detail.get('prompt') or '').strip())
        if not prompt or prompt != re.sub(r'\s+', ' ', str(detail.get('composer_text') or '').strip()) or detail.get('composer_matches') is not True:
            return target
        start_ms = int(datetime.fromisoformat(start['at']).timestamp() * 1000)
        end_ms = int(datetime.fromisoformat(failed['at']).timestamp() * 1000) + 999
        if not 0 <= end_ms - start_ms <= 15000:
            return target
        target['pre_send_proof'] = dict(reason='v373_draft_preflight_no_click', job_id=job['id'],
            provider='chatgpt', scene_index=index, run_id=ready['run_id'], client_id=ready['client_id'],
            prompt=prompt, conversation_url=url, trace_sequence=failed['sequence'],
            created_after_ms=start_ms, created_before_ms=end_ms)
    except (ValueError, TypeError, KeyError, StopIteration, OverflowError):
        pass
    return target


def legacy_first_image_receipt_proof(folder, job_id, provider):
    folder = Path(folder)
    path = folder / "logs" / "extension_trace.jsonl"
    try:
        if provider not in {"gemini", "chatgpt"} or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            return {}
        if any((folder / "generated").glob("scene_*")):
            return {}
        with path.open("r", encoding="utf-8") as handle:
            content = handle.read(4 * 1024 * 1024 + 1)
        if len(content) > 4 * 1024 * 1024:
            return {}
        rows = [json.loads(line) for line in content.splitlines() if line.strip()]
        if not rows or any(not isinstance(row, dict) or type(row.get("sequence")) is not int for row in rows):
            return {}
        if any(a["sequence"] >= b["sequence"] for a, b in zip(rows, rows[1:])):
            return {}
        if any(row.get("action") in {"image_prompt_ready", "image_attempt_result", "complete"} for row in rows):
            return {}
        expected_error = ("ผิดพลาด: STORY_IMAGE_RECEIPT_REVIEW • ภาพฉาก 1 • "
                          "ยังยืนยันการบันทึกหลักฐานภาพไม่ได้ • เก็บฉากเดิมไว้ ไม่สร้างภาพซ้ำ")
        for index in range(len(rows) - 2):
            saved, started, failed = rows[index:index + 3]
            if [row.get("action") for row in (saved, started, failed)] != ["analysis_saved", "generating_images", "error"]:
                continue
            if started["sequence"] != saved["sequence"] + 1 or failed["sequence"] != started["sequence"] + 1:
                continue
            if failed.get("message") != expected_error:
                continue
            if any(row.get("job_id") != job_id or row.get("service") != provider
                   or row.get("version") != "0.15.259" for row in (saved, started, failed)):
                continue
            if any(row.get(field) != failed.get(field) for row in (saved, started)
                   for field in ("run_id", "client_id", "tab_id")):
                continue
            if (not re.fullmatch(r"RUN-[A-Za-z0-9_-]+", str(failed.get("run_id", "")))
                    or not re.fullmatch(r"[a-p]{32}", str(failed.get("client_id", "")))
                    or type(failed.get("tab_id")) is not int or failed["tab_id"] <= 0):
                continue
            if not re.fullmatch(r"กำลังสร้างภาพผ่านหน้า (Gemini|ChatGPT) Web 1/[1-9][0-9]*", str(started.get("message", ""))):
                continue
            # A later image audit/send/result/unknown transition invalidates
            # the proof. Reopening just to read the saved plan is harmless.
            passive = {"ai_model_ready", "analysis_saved", "generating_images", "recovering_images", "error"}
            if any(row.get("job_id") != job_id or row.get("service") != provider
                   or row.get("action") not in passive for row in rows[index + 3:]):
                continue
            start_ms = int(datetime.fromisoformat(started["at"]).timestamp() * 1000)
            end_ms = int(datetime.fromisoformat(failed["at"]).timestamp() * 1000) + 999
            if end_ms < start_ms or end_ms - start_ms > 5000:
                continue
            return {"1": {"reason": "v259_first_image_receipt_ack", "job_id": job_id,
                          "provider": provider, "scene_index": 1, "run_id": failed["run_id"],
                          "client_id": failed["client_id"], "created_after_ms": start_ms,
                          "created_before_ms": end_ms, "trace_sequence": failed["sequence"]}}
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return {}
    return {}
