"""Flow-only acquisition must never silently substitute local animation."""

def completed_proposal_error(error):
    """Completed text-only errors, not unknown Send, login or image outcomes."""
    error = str(error or '')
    return error.startswith(('ภาพทางเลือกต้องเปลี่ยนสาระหรือยังต้องตรวจ', 'FLOW_ALTERNATIVE_SCHEMA_REVIEW')) or error in {
        'ChatGPT Web ไม่ได้ตอบข้อมูล JSON ตามรูปแบบที่โปรแกรมต้องใช้',
        'Gemini Web ไม่ได้ตอบข้อมูล JSON ตามรูปแบบที่โปรแกรมต้องใช้',
    }


def restartable_proposal_review(folder, job, index, permit):
    """Read-only proof for starting ONLY an explicitly resumed failed scene anew."""
    import re
    from core.atomic_json import AtomicJsonFile
    if (not isinstance(permit, dict) or not permit.get('token') or permit.get('job_id') != job.get('id')
            or not str(job.get('id') or '').startswith('STORY-')
            or type(index) is not int or permit.get('index') != index
            or not 1 <= index <= len(job.get('generated_images') or [])
            or job.get('cancel_requested') or job.get('status') in {'cancelled', 'deleted'}
            or (job.get('flow_clips') or {}).get(str(index))
            or any(job.get(k) for k in ('video_path', 'final_video_path', 'final_path'))):
        return None
    rows = AtomicJsonFile(folder / 'prompts' / 'flow_recovery.json').read({}).get('scenes', {}).get(str(index), [])
    last = rows[-1] if rows else {}
    if (last.get('phase') != 'needs_review' or last.get('alternative') is not True
            or last.get('alternative_stage') not in {'proposal', 'proposal_correction'}
            or not completed_proposal_error(last.get('error'))
            or not permit.get('event_digest') or last.get('digest') != permit['event_digest']
            or not permit.get('request_id') or last.get('request_id') != permit['request_id']
            or not re.fullmatch(r'/project/[a-zA-Z0-9-]+/?', last.get('project_path', ''))
            or not all(last.get(k) for k in ('fingerprint', 'reason', 'original_prompt'))):
        return None
    attempts = [row for row in rows if row.get('request_id') == last['request_id']]
    if any(row.get('phase') not in {'requested', 'rewrite_sent', 'needs_review'} or row.get('fresh_project')
           or row.get('alternative_stage', '') not in {'', 'proposal', 'proposal_correction'} for row in attempts):
        return None
    replacement = AtomicJsonFile(folder / 'prompts' / 'flow_replacement.json').read({}).get('scenes', {}).get(str(index), {})
    if (replacement.get('request_id') != last['request_id'] or replacement.get('phase') != 'requested'
            or replacement.get('image_file') or replacement.get('revision')):
        return None
    return last


def ready_home_replacement(folder, job, index, permit):
    """Read-only desktop proof for a saved NEW image stopped BEFORE any Flow project.

    A browser cache is not the authoritative media store. However, missing
    browser data alone must never authorize replay of an unknown Generate.
    Require the append-only, pre-project audit plus the verified ready media.
    """
    import re
    from core.atomic_json import AtomicJsonFile
    from core.flow_replacement import apply_replacement
    if (not isinstance(permit, dict) or not permit.get('token') or permit.get('job_id') != job.get('id')
            or type(index) is not int or permit.get('index') != index
            or (job.get('flow_clips') or {}).get(str(index))
            or any(job.get(k) for k in ('video_path', 'final_video_path', 'final_path'))):
        return None
    rows = AtomicJsonFile(folder / 'prompts' / 'flow_recovery.json').read({}).get('scenes', {}).get(str(index), [])
    last = rows[-1] if rows else {}
    if (last.get('phase') != 'needs_review' or last.get('project_path') != '/'
            or last.get('alternative') is not True or last.get('alternative_stage') != 'motion_sent'
            or last.get('error') or last.get('fresh_project')
            or last.get('pause_reason') not in ('ต้องตรวจผลเดิมก่อนย้ายโปรเจกต์',
                'พบผลหรือสถานะใหม่ของฉากเดิม • เก็บโปรเจกต์ไว้ตรวจ ไม่สร้างซ้ำ')
            or not permit.get('event_digest') or last.get('digest') != permit['event_digest']
            or not permit.get('request_id') or last.get('request_id') != permit['request_id']):
        return None
    indexes = [i for i, row in enumerate(rows) if row.get('request_id') == last['request_id']]
    attempts = [rows[i] for i in indexes]
    if not attempts or any(row.get('project_path') != '/' or row.get('fresh_project')
            or row.get('phase') not in {'requested', 'rewrite_sent', 'ready', 'needs_review'} for row in attempts):
        return None
    if not any(row.get('phase') == 'ready' and row.get('prompt') == last.get('prompt')
               and row.get('fingerprint') == last.get('fingerprint') for row in attempts[:-1]):
        return None
    prior = rows[indexes[0]-1] if indexes[0] else {}
    if (prior.get('phase') != 'needs_review' or not re.fullmatch(r'/project/[a-zA-Z0-9-]+/?', prior.get('project_path', ''))
            or prior.get('fingerprint') != last.get('fingerprint')
            or prior.get('original_prompt') != last.get('original_prompt')):
        return None
    package = {}
    apply_replacement(folder, job, index, package)  # Context, file existence, SHA256 and reviewed motion.
    if package.get('replacement_id') != last['request_id'] or package.get('video_prompt') != last.get('prompt'):
        return None
    return {'version': 1, 'request_id': last['request_id'], 'event_digest': last['digest'],
            'source_project_path': prior['project_path'], 'fingerprint': last['fingerprint'],
            'image_file': package['image_files'][0], 'prompt': package['video_prompt']}

def request_scene_repair_resume(folder, job):
    """Explicit user resume only; authorize one new cycle for the failed scene."""
    from core.atomic_json import AtomicJsonFile
    from uuid import uuid4
    error = str(job.get('last_error') or '')
    if job.get('status') != 'error' or not any(marker in error for marker in (
            'FLOW_REPAIR_REVIEW', 'ภาพใหม่หรือหลักฐานก่อนเปิดโปรเจกต์ยังไม่ตรง ไม่ส่งสร้างซ้ำ')):
        return None
    ledger = AtomicJsonFile(folder / 'prompts' / 'flow_recovery.json').read({'scenes': {}})
    rows = [(int(index), events[-1]) for index, events in ledger.get('scenes', {}).items()
            if events and events[-1].get('phase') == 'needs_review']
    if not rows:
        return None
    index, last = max(rows, key=lambda pair: pair[1].get('at', ''))
    store = AtomicJsonFile(folder / 'prompts' / 'flow_manual_resume.json')
    with store.locked():
        old = store.read_unlocked({})
        if old.get('event_digest') == last.get('digest'):
            return old
        value = {'token': str(uuid4()), 'index': index, 'request_id': last['request_id'],
                 'event_digest': last.get('digest'), 'job_id': job['id']}
        store.write_unlocked(value)
        return value


class FlowVideoReviewError(RuntimeError):
    flow_retry_forbidden = True

    def __init__(self, shot_index, reason):
        super().__init__(
            f"FLOW_REPAIR_REVIEW • ฉาก {shot_index}: {reason} • "
            "พักฉากไว้ เก็บภาพและคลิปเดิม ไม่ใช้ภาพนิ่งแทนวิดีโอ"
        )
