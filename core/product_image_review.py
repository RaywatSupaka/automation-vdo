"""On-demand, credential-free desktop review data; never heartbeat decoding."""
from pathlib import Path
from urllib.parse import quote
from core.product_image_recovery import ProductImageRecovery
from core.product_source_images import select_source_images


def product_image_review(manager, job_id):
    job = manager.get_job(job_id)
    _, decisions = select_source_images(Path(manager.root) / job_id, job.get('source_images') or [])
    ledger = ProductImageRecovery(manager, job_id).state()
    candidates = [dict(item, role='source') for item in decisions]
    for index, slot in (ledger.get('slots') or {}).items():
        if slot.get('status') == 'succeeded':
            candidates.append({'path': f'generated/selling_image_{int(index):02d}.png',
                               'decision': 'accept', 'reason': 'saved_ai_image', 'role': 'generated'})
    for index, candidate in enumerate(candidates):
        candidate['preview_url'] = '/api/desktop/media?item_id=' + quote(f'product-ref:{job_id}:{index}', safe='') + '&kind=preview'
    return {'job_id': job_id, 'revision': ledger.get('revision', ''), 'images': candidates,
            'slots': [dict({key: slot.get(key) for key in ('status', 'attempts', 'donor_index', 'origin', 'reason')}, index=int(index))
                      for index, slot in (ledger.get('slots') or {}).items()],
            'can_reuse': bool(ledger and job.get('automation_status') != 'running'
                             and not job.get('flow_clips') and not job.get('flow_local_motion_clips') and not job.get('video_path')
                             and any(s.get('status') in {'failed', 'policy_blocked', 'blocked', 'missing'} for s in ledger['slots'].values())
                             and not any(s.get('status') in {'reserved', 'uncertain', 'download_pending'} for s in ledger['slots'].values()))}


def product_image_asset(manager, job_id, index):
    """Resolve the same ordered list without decoding every image per GET."""
    recovery = ProductImageRecovery(manager, job_id)  # Validates Job ID first.
    job = manager.get_job(job_id)
    paths = list(job.get('source_images') or [])
    paths += [f'generated/selling_image_{int(i):02d}.png'
              for i, slot in recovery.state().get('slots', {}).items() if slot.get('status') == 'succeeded']
    number = int(index)
    if not 0 <= number < len(paths):
        raise ValueError('ไม่พบรูปที่ขอ')
    target = (recovery.folder / paths[number]).resolve()
    if recovery.folder not in target.parents or not target.is_file():
        raise ValueError('รูปอยู่นอกงานหรือไม่มีไฟล์')
    return str(target)
