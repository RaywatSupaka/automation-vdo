"""Explicit checkpoint edits; never clear receipts or start generation."""
from core.flow_motion_plan import plan_context
from core.flow_settings import flow_settings
from core.studio_review import scene_asset


def editable(folder, job, index, active=False):
    from core.scene_video_plan import enabled, provider_for, verified_asset
    if enabled(job):
        row = (job['scene_video_plan'].get('scenes') or {}).get(str(index)) or {}
        try:
            kept = verified_asset(folder, job, index)
        except ValueError:
            return False
        if row.get('claim') or row.get('held') or kept:
            return False
    return bool(not active and job.get('status') not in {'running', 'active', 'recovering', 'deleted', 'cancelled', 'canceled'}
                and not job.get('cancel_requested') and provider_for(job, index) == 'google_flow'
                and not any(job.get(k) for k in ('video_path', 'final_path', 'final_video_path'))
                and scene_asset(folder, job, index) and not scene_asset(folder, job, index, 'flow')
                and not scene_asset(folder, job, index, 'local')
                and not scene_asset(folder, job, index, 'meta')
                and not (job.get('flow_clips') or {}).get(str(index)))


def override(folder, job, index, relative=None):
    value = (job.get('flow_scene_edits') or {}).get(str(index))
    if not value:
        return None
    if value['context_id'] != plan_context(folder, job, index, relative)['context_id']:
        raise ValueError('ภาพหรือบทฉากเปลี่ยน กรุณาตรวจและบันทึกค่าฉากอีกครั้ง')
    return value


def save(manager, job_id, index, prompt, model, revision):
    if type(index) is not int or type(revision) is not int:
        raise ValueError('ลำดับฉากหรือรุ่นข้อมูลไม่ถูกต้อง')
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 12000:
        raise ValueError('กรอกพรอมต์วิดีโอ 1–12000 ตัวอักษร')
    settings = flow_settings({'model': model})
    folder = manager._folder(job_id)
    store = manager._manifest_store(folder / 'job.json')
    with manager._manifest_lock, store.locked():
        job = store.read_unlocked()
        if int(job.get('revision') or 0) != revision:
            raise ValueError('งานเปลี่ยนระหว่างแก้ไข กรุณาอ่านสถานะใหม่')
        if not editable(folder, job, index):
            raise ValueError('แก้ได้เฉพาะฉากที่มีภาพและยังไม่มีคลิป กรุณาหยุดงานก่อน')
        from core.scene_video_plan import enabled, settings_for
        if enabled(job):
            # This old action edits authored text only for opted-in plans.
            # Model/type/resolution/duration belong to the independent plan.
            settings = settings_for(job, index)
        previous = (job.get('flow_scene_edits') or {}).get(str(index))
        job.setdefault('flow_scene_edit_history', []).append({'index': index, 'previous': previous, 'revision': revision})
        job.setdefault('flow_scene_edits', {})[str(index)] = {
            'prompt': prompt.strip(), 'model': settings.get('model', ''),
            'context_id': plan_context(folder, job, index)['context_id'], 'revision': revision + 1,
        }
        job['revision'] = revision + 1
        store.write_unlocked(job)
        return job


def save_settings(manager, job_id, indices, settings, plan_revision, **activity):
    """Detailed settings are independent from the scene's authored motion text."""
    from core.scene_video_plan import save as save_plan
    return save_plan(manager, job_id, plan_revision, 'google_flow', indices, settings, **activity)
