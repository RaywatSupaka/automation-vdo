"""Read-only routing for pending provider requests, never a permission to resend."""
import json
import re
from pathlib import Path


def conversation_url(value, provider):
    pattern = (r'https://chatgpt\.com/c/[a-zA-Z0-9-]+'
               if provider == 'chatgpt' else r'https://gemini\.google\.com/app/[a-fA-F0-9]{16}')
    value = str(value or '').rstrip('/')
    return value if re.fullmatch(pattern, value) else ''


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def _trace(folder, job_id):
    path = folder / 'logs/extension_trace.jsonl'
    try:
        with path.open('rb') as handle:
            size = handle.seek(0, 2)
            handle.seek(max(0, size - 512_000))
            rows = handle.read().decode('utf-8', errors='replace').splitlines()
    except OSError:
        return []
    result = []
    for line in rows:
        try:
            row = json.loads(line)
            if row.get('job_id') == job_id:
                result.append(row)
        except (ValueError, AttributeError):
            pass
    return result


def request_hash(value):
    # Match the Extension's normalized UTF-16 FNV diagnostic, including emoji.
    raw = re.sub(r'\s+', ' ', value.strip()).encode('utf-16-le')
    result = 2166136261
    for offset in range(0, len(raw), 2):
        result = ((result ^ int.from_bytes(raw[offset:offset + 2], 'little')) * 16777619) & 0xffffffff
    return f'{result:08x}'


def ai_web_resume_target(folder, job):
    """Return a navigation hint. The content reader must still prove ownership."""
    folder = Path(folder)
    provider = str(job.get('image_ai_provider') or 'chatgpt')
    if provider not in {'chatgpt', 'gemini'}:
        return None
    trace = _trace(folder, job['id'])
    urls = [conversation_url(row.get('page_url'), provider) for row in trace]
    last_url = next((url for url in reversed(urls) if url), '')
    ledger = _read(folder / 'prompts/flow_motion_plans.json', {})
    plans = ledger.get('plans', {}) if isinstance(ledger, dict) else {}
    plans = {key: row for key, row in plans.items() if isinstance(row, dict)} if isinstance(plans, dict) else {}
    # Resolve current context without calling the status action (which can
    # migrate legacy rows). Packaging must not mutate the motion ledger.
    indexes = sorted({(row.get('context') or {}).get('index') for row in plans.values()
                      if type((row.get('context') or {}).get('index')) is int})
    for index in indexes:
        try:
            from core.flow_motion_plan import plan_context
            from core.product_visual_contract import visual_context
            context = plan_context(folder, job, index)
            revised = visual_context(folder, job, context) if job['id'].startswith('JOB-') else None
            if revised and revised['context_id'] in plans:
                context = revised
        except (ValueError, OSError):
            continue
        row = plans.get(context['context_id']) or {}
        if row.get('phase') == 'ready':
            continue
        candidate = row.get('story_visual_repair') or {}
        phase = candidate.get('phase') or row.get('phase')
        if phase not in {'requested', 'answered_text', 'image_requested', 'motion_requested',
                         'motion_answered_text', 'motion_format_requested'}:
            continue
        url = conversation_url(candidate.get('conversation_url') or row.get('conversation_url'), provider) or last_url
        return dict(required=True, stage='motion', provider=provider, index=index,
                    context_id=context['context_id'], conversation_url=url,
                    evidence='checkpoint' if row.get('conversation_url') or candidate.get('conversation_url') else 'job_trace')
    from core.story_receipt_recovery import pending_story_image_target
    image_target = pending_story_image_target(folder, job, trace)
    if image_target:
        return image_target
    # An accepted initial analysis may not have reached the disk checkpoint.
    # Preserve its old request BEFORE package regeneration changes any wording.
    stopped = str(job.get('last_error') or job.get('automation_error') or job.get('error') or
                  next((r.get('message') for r in reversed(trace) if (r.get('action') or r.get('step')) == 'error'), '') or '')
    analysis_ready = job.get('ai_status') == 'ready' or (folder / 'prompts/ai_analysis_checkpoint.json').is_file()
    if not analysis_ready and (job.get('long_video') or {}).get('version') == 2:
        plan = _read(folder / 'prompts/long_video_plan.json', {})
        pending = plan.get('pending_request') if isinstance(plan, dict) and plan.get('job_id') == job['id'] else None
        if isinstance(pending, dict) and pending.get('provider') == provider \
                and isinstance(pending.get('request'), str) and pending['request'].strip():
            return dict(required=True, stage='analysis', provider=provider, conversation_url=last_url,
                        request=pending['request'], evidence='long_video_plan',
                        long_video_stage=pending.get('stage'), chapter_index=pending.get('chapter_index'))
        if isinstance(plan, dict) and plan.get('job_id') == job['id'] \
                and (job.get('ai_resume_checkpoint') or {}).get('evidence') == 'long_video_plan':
            # The accepted outline/chapter was checkpointed after that older
            # read-only resume; its manifest hint must not reopen the old turn.
            return None
    checkpoint = job.get('ai_resume_checkpoint')
    if not analysis_ready and isinstance(checkpoint, dict) and checkpoint.get('stage') == 'analysis' and checkpoint.get('provider') == provider:
        return checkpoint
    accepted_route_review = provider == 'chatgpt' and 'AI_WEB_RESUME_REVIEW' in stopped.upper()
    if analysis_ready or not (accepted_route_review or any(code in stopped.upper() for code in (
            'GEMINI_TEXT_REQUEST_REVIEW', 'GEMINI_TEXT_SEND_REVIEW', 'AI_ANALYSIS_TIMEOUT', 'AI_WEB_WAIT_REVIEW'))):
        return None
    if accepted_route_review:
        # A 428 WEB: -> canonical hydration race can stop after an accepted
        # analysis Send. Reopen only the exact failed run's canonical chat for
        # a read-only result; a review code alone never authorizes a resend.
        failure_index = next((index for index in range(len(trace) - 1, -1, -1)
                              if trace[index].get('action') == 'error'
                              and 'AI_WEB_RESUME_REVIEW' in str(trace[index].get('message') or '').upper()), -1)
        if failure_index < 0:
            return None
        failure = trace[failure_index]
        run_id = str(failure.get('run_id') or '')
        accepted = next((row for row in reversed(trace[:failure_index])
                         if row.get('action') == 'ai_send_accepted'
                         and row.get('service') == 'chatgpt'
                         and row.get('shot_index') == 0
                         and row.get('run_id') == run_id), None)
        exact_url = conversation_url(failure.get('page_url'), provider)
        if not run_id or not accepted or not exact_url:
            return None
        last_url = exact_url
        trace = [row for row in trace[:failure_index + 1] if row.get('run_id') == run_id]
    request = _read(folder / 'ai_request.json', {})
    relative = request.get('prompt_file', '')
    path = (folder / str(relative)).resolve()
    if folder.resolve() not in path.parents or not path.is_file():
        return dict(required=True, stage='analysis', provider=provider, conversation_url=last_url, request='')
    text = path.read_text(encoding='utf-8')
    field = request.get('prompt_field') or ('scene_prompts' if job['id'].startswith('STORY-') else 'selling_points')
    count = request.get('image_count') or job.get('scene_count') or 3
    text += (f'\n\nข้อกำหนดสำหรับระบบอัตโนมัติรอบนี้:\n- รอบนี้ให้วิเคราะห์และตอบ JSON เท่านั้น ยังไม่ต้องสร้างภาพ'
             f'\n- ใส่ job_id เป็น {job["id"]}\n- ต้องมี {field} จำนวน {count} รายการพอดี\n- ห้ามครอบ JSON ด้วยคำอธิบายอื่น')
    expected = next(((r.get('detail') or {}).get('request_hash') for r in reversed(trace)
                     if (r.get('detail') or {}).get('request_hash')), '')
    if expected and request_hash(text) != expected:
        text = ''  # Preserve the unknown original, never send the regenerated one.
    return dict(required=True, stage='analysis', provider=provider, conversation_url=last_url,
                request=text, evidence='job_trace')
