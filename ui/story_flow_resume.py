"""Resume a verified, completed new-image handoff at Flow, not at the AI tab."""
import hashlib
from uuid import uuid4
from core.flow_review import ready_home_replacement, restartable_proposal_review
from core.scene_pipeline import ScenePipeline


def start_saved_flow_scene(app, job, permit):
    if (job.get('scene_pipeline_version') != 1 or job.get('video_generation_mode') != 'google_flow'
            or not permit or app._story_cancel_event.is_set()):
        return False
    job_id, index = job['id'], permit['index']
    folder = app.stories.root / job_id
    ready = ready_home_replacement(folder, job, index, permit)
    restart = None if ready else restartable_proposal_review(folder, job, index, permit)
    if not ready and not restart:
        return False
    prior = app._story_scene_threads.get((job_id, index))
    if prior and prior.is_alive():
        raise ValueError('ฉากนี้มีงานกำลังทำอยู่แล้ว')
    job = app.stories.prepare_scene_pipeline(job_id, index)
    image = folder / job['generated_images'][index-1]
    identity = {'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                'narration': job['scene_narrations'][index-1], 'audio_choices': job.get('audio_choices')}
    if job.get('actor_dialogue'):
        identity.update(actor_dialogue=True, scene_dialogue_turns=job['scene_dialogue_turns'][index-1],
                        character_bible=job['character_bible'])
    run_id = f'DESKTOP-FLOW-{uuid4().hex}'
    row = ScenePipeline(folder).request(index, int(job['scene_count']), identity, run_id=run_id)
    app.stories.mark_running(job_id, 'google_flow')
    app._update_story_progress({'percent': 10+int(80*(index-1)/int(job['scene_count'])), 'stage': 'video',
        'message': f'ฉาก {index} • กำลังเริ่มฉากที่ล้มเหลวใหม่' if restart else f'ฉาก {index} • ภาพและพรอมต์พร้อม กำลังเปิด Google Flow ใหม่',
        'detail': 'สร้างภาพและพรอมต์ใหม่เฉพาะฉากนี้ • เก็บฉากที่สำเร็จแล้ว' if restart else 'ใช้ภาพใหม่ที่บันทึกไว้ • ไม่เปิด AI เพื่อขอภาพหรือพรอมต์ซ้ำ'})
    app._start_story_scene_worker({'job_id': job_id, 'index': index, 'revision': row['revision'],
        'run_id': run_id, 'desktop_saved_resume': True, 'desktop_scene_rebuild': bool(restart)})
    return True


def finish_saved_flow_scene(app, payload):
    """Only a completed exact scene releases the usual AI driver for the next image."""
    job_id = payload['job_id']
    cancel = payload.get('cancel_event')
    if (app._story_pipeline_job_id != job_id or cancel is not app._story_cancel_event
            or cancel is None or cancel.is_set()):
        return
    row = ScenePipeline(app.stories.root / job_id).get(payload['index'])
    if row.get('phase') != 'complete' or row.get('run_id') != payload['run_id']:
        return
    owner = (job_id, payload['index'], payload['run_id'])
    if getattr(app, '_story_saved_scene_handoff', None) == owner:
        return
    app._story_saved_scene_handoff = owner  # Claim before dispatch; unknown ACK must not requeue.
    job = app.stories.get(job_id)
    images = job.get('generated_images') or []
    if (job.get('ai_status') == 'ready' and len(images) == int(job.get('scene_count') or 0)
            and all((app.stories.root / job_id / path).is_file() for path in images)):
        app.root.after(300, app._render_story)
        return
    # Durable completed scene/media remain; the normal driver skips them and
    # asks for the next missing scene only. No second direct-resume dispatch.
    app.bridge.clear_ai_progress(job_id)
    app.bridge.queue_extension_command('resume_chatgpt', job_id)
    app._story_monitor_after = app.root.after(700, lambda: app._monitor_story_browser_progress(job_id))
