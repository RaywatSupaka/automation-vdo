"""Versioned image -> stored Meta video barrier (not an audio render pipeline).

No provider commands on status reads. Dispatch identity is durable before it is
published to the bridge; an ACK loss cannot allocate a second operation.
"""
import copy
import hashlib
import json
import uuid
from pathlib import Path

from core.atomic_json import AtomicJsonFile


ANALYSIS_KEYS = ('scene_prompts', 'scene_narrations', 'scene_durations',
                 'scene_dialogue_turns', 'dialogue_turns', 'character_bible',
                 'flow_shot_prompts', 'narration_script', 'visual_bible')
OPTION_KEYS = ('scene_count', 'image_ai_provider', 'video_generation_mode',
               'meta_prompt_version', 'long_video', 'audio_choices',
               'storytelling_options', 'actor_dialogue', 'generated_music_options')


def eligible(job):
    from core.scene_video_plan import enabled as video_plan
    return (job.get('image_ai_provider') == 'chatgpt'
            and job.get('video_generation_mode') == 'meta_ai'
            and job.get('job_type') == 'story_short'
            and not any(job.get(key) for key in ('product_story', 'product_short',
                        'product_presentation_version', 'cast_creation', 'cancel_requested'))
            and job.get('status') not in ('cancelled', 'canceled', 'deleted')
            and not video_plan(job))


def enabled(job):
    return type(job.get('meta_scene_sequence_version')) is int and job['meta_scene_sequence_version'] == 1


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def store_for(folder):
    return AtomicJsonFile(Path(folder) / 'prompts' / 'meta_scene_sequence.json')


def scene_input(stories, job, index):
    """Read exact checkpoint N; never claim missing image slots are ready."""
    if not enabled(job) or not eligible(job):
        raise ValueError('META_SEQUENCE_REVIEW • งานไม่ตรงโหมดภาพและวิดีโอทีละฉาก')
    count = int(job.get('scene_count') or 0)
    if type(index) is not int or not 1 <= index <= count:
        raise ValueError('META_SEQUENCE_REVIEW • ลำดับฉากไม่ตรงงาน')
    folder = (stories.root / job['id']).resolve()
    analysis = AtomicJsonFile(folder / 'prompts' / 'ai_analysis_checkpoint.json').peek({})
    if (analysis.get('job_id') != job['id']
            or any(not isinstance(analysis.get(key), list) or len(analysis[key]) != count
                   for key in ('scene_prompts', 'scene_narrations'))):
        raise ValueError('META_SEQUENCE_REVIEW • ยังไม่มีบทที่บันทึกตรงงานครบทุกฉาก')
    projected = {**copy.deepcopy(job), **{key: copy.deepcopy(analysis[key])
                                         for key in ANALYSIS_KEYS if key in analysis}}
    # Match the existing final-result normalization BEFORE native Meta speech,
    # otherwise its last spoken scene would omit the desktop-added CTA.
    from core import story_performance
    from core.product_script import authored_product_script
    if not (job.get('storytelling_options') or job.get('flow_smoke_test')
            or job.get('cast_creation') or story_performance.enabled(job)
            or authored_product_script(job)):
        projected['narration_script'], projected['scene_narrations'], _ = stories._ensure_engagement_cta(
            projected.get('narration_script') or ' '.join(projected['scene_narrations']),
            projected['scene_narrations'], job.get('topic'))
    image = folder / 'generated' / f'scene_{index:02d}.png'
    relative = image.relative_to(folder).as_posix()
    saved = {str(value).replace('\\', '/') for value in
             (job.get('partial_generated_images') or []) + (job.get('generated_images') or [])}
    if relative not in saved or not image.resolve().is_relative_to(folder) or not image.is_file():
        raise ValueError('META_SEQUENCE_REVIEW • ยังไม่มีภาพฉากที่บันทึกแล้ว')
    from core.meta_video import digest
    sha = digest(image)
    from PIL import Image
    try:
        with Image.open(image) as opened:
            if min(opened.size) < 128:
                raise ValueError('ภาพฉากเล็กเกินไป')
            opened.verify()
    except (OSError, ValueError) as error:
        raise ValueError('META_SEQUENCE_REVIEW • ภาพฉากไม่พร้อมใช้งาน') from error
    prior = (job.get('partial_image_sha256') or {}).get(str(index))
    if prior and prior != sha:
        raise ValueError('META_SEQUENCE_REVIEW • ภาพฉากเปลี่ยนจาก Checkpoint')
    identity = _digest({key: projected.get(key) for key in (*ANALYSIS_KEYS, *OPTION_KEYS)})
    return projected, relative, {'script_options_sha256': identity, 'image_sha256': sha}


def verified_clip(manager, job_id, index):
    """The existing save path already validates MP4 dimensions and duration."""
    package = manager.package(job_id, index)
    receipt = manager.get(job_id, index)
    if receipt.get('stage') != 'stored':
        return None
    folder = manager._folder(job_id).resolve()
    saved = (folder / str(receipt.get('path') or '')).resolve()
    job = manager._job(job_id)
    proof = (job.get('meta_clip_receipts') or {}).get(str(index)) or {}
    from core.meta_video import digest
    if (receipt.get('context_id') != package['context_id']
            or (job.get('meta_clips') or {}).get(str(index)) != receipt.get('path')
            or not saved.is_relative_to(folder) or not saved.is_file()
            or saved.stat().st_size < 1024 or digest(saved) != receipt.get('sha256')
            or any(proof.get(key) != receipt.get(key) for key in ('request_id', 'context_id', 'sha256'))
            or not 1 <= float(proof.get('duration') or 0) <= 120):
        raise ValueError('META_SEQUENCE_REVIEW • ไฟล์วิดีโอหรือหลักฐานฉากไม่ตรงงาน')
    return {key: receipt[key] for key in ('path', 'sha256', 'request_id', 'context_id')}


def gate(bridge, body):
    """Called only under bridge owner lock, after _validate_story_ai_run_locked."""
    job_id, index, action, run_id = body['job_id'], body['index'], body['action'], body['run_id']
    expected = bridge._extension_runs.get(('ai', job_id, 0)) or {}
    if not run_id or expected.get('run_id') != run_id:
        raise ValueError('META_SEQUENCE_REVIEW • รอบงานรายฉากเปลี่ยนแล้ว')
    if action not in ('ready', 'status'):
        raise ValueError('META_SEQUENCE_REVIEW • คำสั่งรายฉากไม่ถูกต้อง')
    job = bridge.stories.get(job_id)
    _, _, binding = scene_input(bridge.stories, job, index)
    store = store_for(bridge.stories.root / job_id)
    manager = bridge.meta_video
    with store.locked():
        data = store.read_unlocked({'version': 1, 'scenes': {}})
        if data.get('version') != 1 or not isinstance(data.get('scenes'), dict):
            raise ValueError('META_SEQUENCE_REVIEW • รูปแบบจุดบันทึกรายฉากไม่ตรงรุ่น')
        rows = data['scenes']
        # Validate previous saved assets again, not merely a completed flag.
        for previous in range(1, index):
            if (rows.get(str(previous), {}).get('phase') != 'scene_ready'
                    or (action == 'ready' and previous == index - 1
                        and not verified_clip(manager, job_id, previous))):
                raise ValueError('META_SEQUENCE_REVIEW • วิดีโอฉากก่อนหน้ายังบันทึกไม่ครบ')
        row = rows.get(str(index))
        if row and row['binding'] != binding:
            raise ValueError('META_SEQUENCE_REVIEW • ภาพ บท หรือตัวเลือกฉากเปลี่ยนแล้ว')
        if action == 'status' and (not row or row['run_id'] != run_id):
            raise ValueError('META_SEQUENCE_REVIEW • ไม่พบรอบงานรายฉากเดิม')
        if not row:
            row = {'index': index, 'binding': binding, 'run_id': run_id,
                   'phase': 'video_pending', 'commands': {}}
            rows[str(index)] = row
        elif action == 'ready':
            # New validated desktop AI run reattaches, never replaces Meta work.
            row['run_id'] = run_id
        clip = verified_clip(manager, job_id, index)
        if clip:
            row.update(phase='scene_ready', clip=clip)
            store.write_unlocked(data)
            return {'ok': True, 'phase': 'scene_ready', 'index': index,
                    'message': 'บันทึกวิดีโอฉากนี้แล้ว • พร้อมทำฉากถัดไป'}
        if row['phase'] == 'scene_ready':
            raise ValueError('META_SEQUENCE_REVIEW • หลักฐานวิดีโอที่เสร็จแล้วหายไป')
        receipt = manager.get(job_id, index)
        if receipt.get('stage') == 'needs_attention':
            return {'ok': True, 'phase': 'error', 'error': 'META_SEQUENCE_REVIEW • '
                    + str(receipt.get('message') or 'ต้องตรวจคำขอ Meta เดิม')}
        if action == 'ready':
            store.write_unlocked(data)
            receipt = manager.begin(job_id, index)  # never implicit manual Resume
            request_id = receipt['request_id']
            dispatch = row['commands'].get(request_id)
            if not dispatch:
                dispatch = {'id': 'CMD-' + uuid.uuid4().hex[:10].upper(),
                            'run_id': 'RUN-' + uuid.uuid4().hex[:12].upper()}
                row['commands'][request_id] = dispatch
            row['request_id'] = request_id
            store.write_unlocked(data)  # durable BEFORE command publication
            bridge.queue_extension_command('open_meta_video', job_id, index,
                                           run_id=dispatch['run_id'], _meta_sequence=dispatch)
        else:
            dispatch = row['commands'].get(row.get('request_id')) or {}
            command = bridge.extension_command_status(dispatch.get('id'))
            if command and command.get('status') == 'failed':
                return {'ok': True, 'phase': 'error', 'error': 'META_SEQUENCE_REVIEW • '
                        + str(command.get('error') or 'เปิด Meta ไม่สำเร็จ')}
        return {'ok': True, 'phase': 'video_pending', 'index': index,
                'message': str(receipt.get('message') or 'ภาพบันทึกแล้ว • รอวิดีโอ Meta ของฉากนี้')}


def assert_scene_dispatch(stories, job, index):
    """Direct package/command routes cannot jump ahead of the master barrier."""
    if not enabled(job):
        return
    _, _, binding = scene_input(stories, job, index)
    rows = store_for(stories.root / job['id']).peek({}).get('scenes') or {}
    row = rows.get(str(index)) or {}
    if (row.get('binding') != binding or row.get('phase') not in ('video_pending', 'scene_ready')
            or any(rows.get(str(prior), {}).get('phase') != 'scene_ready' for prior in range(1, index))):
        raise ValueError('META_SEQUENCE_REVIEW • ยังไม่ได้รับสิทธิ์เริ่มวิดีโอฉากนี้')


def assert_all_ready(stories, job):
    if not enabled(job):
        return
    from core.meta_video import MetaVideoManager
    manager = MetaVideoManager(stories)
    rows = store_for(stories.root / job['id']).peek({}).get('scenes') or {}
    for index in range(1, int(job['scene_count']) + 1):
        _, _, binding = scene_input(stories, job, index)
        row = rows.get(str(index)) or {}
        if (row.get('phase') != 'scene_ready' or row.get('binding') != binding
                or not verified_clip(manager, job['id'], index)):
            raise ValueError('META_SEQUENCE_REVIEW • ยังรวม Final ไม่ได้ วิดีโอรายฉากไม่ครบ')


def needs_scene_work(stories, job):
    if not enabled(job):
        return False
    rows = store_for(stories.root / job['id']).peek({}).get('scenes') or {}
    return any(rows.get(str(index), {}).get('phase') != 'scene_ready'
               for index in range(1, int(job['scene_count']) + 1))


def adopt(stories, job_id):
    """Explicit desktop action at an idle boundary, never called on read/Resume."""
    from core.ai_web_resume import ai_web_resume_target
    from core.meta_video import MetaVideoManager
    from core.job_file_guard import guard_for
    with guard_for(stories.project_root).start(job_id), stories._manifest_lock, stories._manifest_store(stories._folder(job_id) / 'job.json').locked():
        job = stories.get(job_id)
        if enabled(job):
            return job
        if not eligible(job) or job.get('status') in ('complete', 'completed', 'ready', 'running'):
            raise ValueError('งานนี้ยังเปลี่ยนเป็นภาพและวิดีโอทีละฉากไม่ได้')
        folder = stories.root / job_id
        if ai_web_resume_target(folder, job):
            raise ValueError('ต้องตรวจและบันทึกคำตอบ AI เดิมก่อนเปลี่ยนลำดับ • ไม่ส่งฉากเดิมซ้ำ')
        manager = MetaVideoManager(stories)
        receipts = manager._store(job_id).peek({'scenes': {}}).get('scenes') or {}
        if any(row.get('stage') != 'stored' for row in receipts.values()):
            raise ValueError('ยังมีคำขอ Meta เดิมค้างอยู่ • เก็บคำขอเดิมก่อนเปลี่ยนลำดับ')
        projected = {**job, 'meta_scene_sequence_version': 1}
        # No rewrite of existing receipt-owned text to fit the new adapter.
        analysis = AtomicJsonFile(folder / 'prompts' / 'ai_analysis_checkpoint.json').peek({})
        if receipts and any(job.get(key) != analysis[key] for key in ANALYSIS_KEYS if key in analysis):
            raise ValueError('บทที่ผูกกับคลิปเดิมต่างจาก Checkpoint • ต้องตรวจผลเดิมก่อนเปลี่ยน')
        for key in receipts:
            scene_input(stories, projected, int(key))
            verified_clip(manager, job_id, int(key))
        job['meta_scene_sequence_version'] = 1
        job['meta_scene_sequence_adoption'] = {'version': 1, 'kind': 'explicit_desktop_action',
            'saved_image_count': len(job.get('partial_generated_images') or job.get('generated_images') or []),
            'saved_video_count': len(receipts)}
        stories._save(job)
        return job
