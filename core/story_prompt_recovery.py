"""Append-only scene-repair audit; never replaces analysis or completed images."""
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit
from core.atomic_json import AtomicJsonFile


def record_recovery(folder, job, body, flow=False):
    index = body.get('index')
    if type(index) is not int or not 1 <= index <= int(job.get('scene_count') or 0):
        raise ValueError('ฉากกู้คืนไม่ตรงกับงาน')
    event = body.get('event')
    if not isinstance(event, dict) or event.get('phase') not in {
        'requested', 'rewrite_sent', 'ready', 'image_pending', 'completed', 'needs_review', 'cancelled',
        *({'preparing', 'submit_ready', 'submitted', 'fallback'} if flow else set())
    }:
        raise ValueError('สถานะกู้คืนไม่ถูกต้อง')
    if type(event.get('round')) is not int or event['round'] < 1 or (not flow and event['round'] > 2):
        raise ValueError('กู้คืนได้ไม่เกินสองรอบต่อฉาก')
    clean = {key: str(event.get(key) or '')[:limit] for key, limit in {
        'original_prompt': 20000, 'prompt': 12000, 'reason': 1500,
        'helper_url': 300, 'request_id': 160, 'phase': 40,
        **({'fingerprint': 160, 'failure_card_key': 160, 'failure_id': 200, 'project_path': 300,
            'pause_reason': 1500, 'error': 1500, 'change_summary': 1500} if flow else {}),
    }.items()}
    clean['round'] = event['round']
    if flow and event.get('alternative') is True:
        clean['alternative'] = True
        clean['alternative_stage'] = str(event.get('alternative_stage') or '')[:40]
        review = event.get('proposal_review')
        if isinstance(review, dict):
            clean['proposal_review'] = {key: review[key] for key in
                ('needs_review', 'reference_compatible', 'material_change') if type(review.get(key)) is bool}
    if flow and 'repair_reference' in event:
        reference = event['repair_reference']
        if not isinstance(reference, dict) or reference.get('source') not in {'original', 'replacement'}:
            raise ValueError('ที่มาภาพแก้พรอมต์ไม่ถูกต้อง')
        image_url = reference.get('image_url')
        if not isinstance(image_url, str) or not 1 <= len(image_url) <= 1000:
            raise ValueError('ลิงก์ภาพแก้พรอมต์ไม่ถูกต้อง')
        parsed = urlsplit(image_url)
        scope = 'stories' if str(job['id']).startswith('STORY-') else 'jobs'
        prefix = f'/api/{scope}/{job["id"]}/files/'
        path = unquote(parsed.path)
        if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'}
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or not path.startswith(prefix) or path == prefix
                or '..' in path.split('/') or '\\' in path):
            raise ValueError('ภาพแก้พรอมต์ไม่ตรงกับงานเดิม')
        # Provenance only: a text repair keeps the original reference and must
        # not create or claim an alternate-image checkpoint.
        clean['repair_reference'] = {'source': reference['source'], 'image_url': image_url}
    if flow and isinstance(event.get('fresh_project'), dict):
        fresh = event['fresh_project']
        clean['fresh_project'] = {key: str(fresh.get(key) or '')[:300] for key in ('source_path','target_path','phase')}
        clean['fresh_project']['click_claimed'] = fresh.get('click_claimed') is True
    if flow and clean['phase'] == 'completed':
        # Prior error remains in earlier append-only events, not active status.
        clean['error'] = ''
        clean['pause_reason'] = ''
    if not clean['request_id']:
        raise ValueError('ไม่มีรหัสคำขอกู้คืน')
    if clean['helper_url'] and not clean['helper_url'].startswith(('https://chatgpt.com/', 'https://gemini.google.com/')):
        raise ValueError('ลิงก์แท็บช่วยงานไม่ถูกต้อง')
    digest = hashlib.sha256(json.dumps(clean, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    store = AtomicJsonFile(folder / 'prompts' / ('flow_recovery.json' if flow else 'scene_recovery.json'))
    with store.locked():
        data = store.read_unlocked({'schema': 1, 'scenes': {}})
        scene = data['scenes'].setdefault(str(index), [])
        if not any(row['digest'] == digest for row in scene):
            if not flow and len(scene) >= 40:
                raise ValueError('บันทึกกู้คืนเกินขอบเขต')
            scene.append({**clean, 'digest': digest, 'run_id': body.get('run_id'),
                          'at': datetime.now(timezone.utc).isoformat()})
            store.write_unlocked(data)
    return {'ok': True, 'job_id': job['id'], 'index': index}
