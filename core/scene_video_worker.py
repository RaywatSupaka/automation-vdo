"""Desktop consumers of an explicitly saved remaining-scene video plan.

Provider controllers retain their own receipt/recovery rules. This module
selects one controller only at a scene boundary and reuses verified results.
"""
import hashlib
import re
from pathlib import Path

from core.cancellable_process import check_cancelled


class SceneVideoReviewError(ValueError):
    flow_retry_forbidden = True


def flow_download_path(job_id, index, binding=None):
    safe_job = re.sub(r'[^a-zA-Z0-9_-]', '_', str(job_id))
    suffix = ''
    if binding:
        attempt = re.sub(r'[^a-zA-Z0-9_-]', '_', str(binding.get('attempt_id') or ''))[:80]
        if not attempt:
            raise ValueError('คำขอดาวน์โหลดฉากไม่มี attempt ที่บันทึกไว้')
        suffix = '-' + attempt
    return Path.home() / 'Downloads' / 'SmartPost' / safe_job / f'flow-shot-{index:02d}{suffix}.mp4'


def download_receipt(app, job_id, index, binding, path):
    from core.scene_video_plan import assert_binding
    try:
        assert_binding(app.stories.get(job_id), index, binding)
    except ValueError as exc:
        raise SceneVideoReviewError(str(exc)) from exc
    expected = flow_download_path(job_id, index, binding).resolve()
    if Path(path).resolve() != expected:
        raise SceneVideoReviewError('ไฟล์ Flow ไม่ตรง attempt ที่เริ่มไว้ • ไม่สร้างหรือรับไฟล์ซ้ำ')
    clients = app.bridge.extension_status().get('clients') or []
    receipt = next((row for row in clients if row.get('version') == app.bridge.REQUIRED_EXTENSION_VERSION
                    and row.get('flow_job_id') == job_id and row.get('flow_shot_index') == index
                    and row.get('flow_step') == 'generation_complete'
                    and row.get('flow_scene_video_plan') == binding
                    and Path(str(row.get('flow_download_path') or '')).resolve() == expected), None)
    sha = str((receipt or {}).get('flow_download_sha256') or '')
    if not re.fullmatch(r'[a-f0-9]{64}', sha):
        raise SceneVideoReviewError('ยังไม่มีใบรับดาวน์โหลดที่ตรงแผนรายฉาก • เก็บผลเดิมไว้ตรวจ')
    return sha


def collect_scene(app, job_id, index, cancel_event):
    from core.scene_video_plan import apply_at_safe_boundary, finish_scene
    check_cancelled(cancel_event)
    retire_saved_flow_terminal(app, job_id, index)
    retire_saved_meta_terminal(app, job_id, index)
    choice = apply_at_safe_boundary(app.stories, job_id, index)
    folder = app.stories.root / job_id
    asset = choice.get('asset')
    if asset:
        return folder / asset['path']
    provider = choice['provider']
    if provider == 'google_flow':
        paths = app._collect_story_flow_clips(job_id, cancel_event, only_scene=index, _planned_route=True)
    elif provider == 'meta_ai':
        paths = app._collect_story_meta_clips(job_id, cancel_event, only_scene=index, _planned_route=True)
    else:
        raise ValueError('ผู้สร้างฉากไม่ตรงแผนที่บันทึก • ไม่ส่งคำขอใหม่')
    check_cancelled(cancel_event)
    if len(paths) != 1:
        raise ValueError('ผลวิดีโอต้องตรงฉากที่กำลังทำหนึ่งฉาก')
    asset = finish_scene(app.stories, job_id, index)
    if not asset or (folder / asset['path']).resolve() != Path(paths[0]).resolve():
        raise ValueError('ผลฉากยังไม่ตรงหลักฐานที่บันทึก • เก็บไฟล์ไว้ตรวจ')
    return folder / asset['path']


def retire_saved_flow_terminal(app, job_id, index):
    from core.scene_video_plan import enabled, provider_for, flow_owner, retire_terminal
    from core.story_manager import StoryManager
    job = app.stories.get(job_id)
    if not enabled(job) or provider_for(job, index) != 'google_flow':
        return False
    row = job['scene_video_plan']['scenes'].get(str(index)) or {}
    if not row.get('pending') or not row.get('legacy_active') or row.get('claim') or row.get('asset'):
        return False
    owner = flow_owner(app.stories.root / job_id, index) or {}
    if owner.get('step') not in {'generation_failed', 'attachment_failed'}:
        return False
    histories = (StoryManager._authenticated_flow_policy_history(job, index)
                 + StoryManager._authenticated_flow_attachment_history(job, index))
    match = next((value for value in reversed(histories)
                  if value.get('flow_run_id') == owner.get('run_id')
                  and value.get('failure_card_fingerprint') == owner.get('failure_card_fingerprint')
                  and value.get('failure_code', 'FLOW_POLICY_BLOCKED') == owner.get('failure_code')), None)
    if not match:
        return False
    retire_terminal(app.stories, job_id, index, {'terminal': True, 'busy': False,
        'download_pending': False, 'kind': 'never_dispatched' if owner['step'] == 'attachment_failed' else 'provider_failed',
        'code': owner['failure_code'], 'run_id': owner['run_id'],
        'fingerprint': owner['failure_card_fingerprint']})
    return True


def retire_saved_meta_terminal(app, job_id, index):
    """A persisted exhausted, completed answer is terminal; silence is not."""
    from core.atomic_json import AtomicJsonFile
    from core.scene_video_plan import enabled, package_binding, provider_for, retire_terminal
    job = app.stories.get(job_id)
    if not enabled(job) or provider_for(job, index) != 'meta_ai':
        return False
    row = job['scene_video_plan']['scenes'].get(str(index)) or {}
    if not row.get('pending') or row.get('asset'):
        return False
    receipt = (AtomicJsonFile(app.stories.root / job_id / 'prompts' / 'meta_video_receipts.json')
               .read({}).get('scenes') or {}).get(str(index)) or {}
    return retire_meta_terminal(app, job_id, index, receipt, package_binding(job, index))


def retire_meta_terminal(app, job_id, index, receipt, binding):
    from core.scene_video_plan import enabled, retire_terminal
    if (not enabled(app.stories.get(job_id)) or receipt.get('stage') != 'needs_attention'
            or receipt.get('retry_exhausted') is not True
            or receipt.get('failure_reason') != 'completed_no_video'
            or receipt.get('scene_video_plan') != binding
            or not receipt.get('request_id')
            or not re.fullmatch(r'[a-f0-9]{64}', str(receipt.get('failure_answer_sha256') or ''))):
        return False
    retire_terminal(app.stories, job_id, index, {'terminal': True, 'busy': False,
        'download_pending': False, 'kind': 'provider_failed', 'code': 'META_COMPLETED_NO_VIDEO',
        'request_id': receipt['request_id']}, scene_video_plan=binding)
    return True


def collect_all(app, job_id, cancel_event):
    job = app.stories.get(job_id)
    return [collect_scene(app, job_id, index, cancel_event)
            for index in range(1, int(job['scene_count']) + 1)]


def provenance(assets):
    counts = {provider: sum(row['provider'] == provider for row in assets)
              for provider in ('google_flow', 'meta_ai', 'local')}
    flow, meta, local = (counts[key] for key in ('google_flow', 'meta_ai', 'local'))
    source_type = ('mixed_ai_story_composite' if sum(bool(value) for value in (flow, meta, local)) > 1 else
                   'meta_ai_story_composite' if meta else
                   'google_flow_story_hybrid_fallback' if local else 'google_flow_story_composite')
    return {'source_type': source_type, 'flow_clip_count': flow,
            'meta_clip_count': meta, 'flow_fallback_count': local,
            'flow_fallback_scenes': [row['index'] for row in assets if row['provider'] == 'local'],
            'scene_source_count': len(assets),
            'scene_video_sources': [{'index': row['index'], 'provider': row['provider'],
                'sha256': row['sha256']} for row in assets]}


def complete_missing_segments(app, job_id, api_key, reference_id, reference_file, cancel_event):
    """Resume missing sequential segments from saved images; never replay analysis."""
    from core.scene_pipeline import ScenePipeline
    pipeline = ScenePipeline(app.stories.root / job_id)
    job = app.stories.get(job_id)
    folder = app.stories.root / job_id
    for index in range(1, int(job['scene_count']) + 1):
        check_cancelled(cancel_event)
        row = pipeline.get(index)
        if row.get('phase') == 'complete':
            continue
        # The per-scene gate and the full render worker share one local owner.
        prior = getattr(app, '_story_scene_threads', {}).get((job_id, index))
        if prior and prior.is_alive():
            raise ValueError(f'ฉาก {index} ยังทำงานอยู่ • รอผลเดิมก่อนประกอบ')
        from core.scene_video_plan import apply_at_safe_boundary
        job = apply_at_safe_boundary(app.stories, job_id, index)['job']
        image = (folder / job['generated_images'][index - 1]).resolve()
        if not image.is_relative_to(folder.resolve()) or not image.is_file():
            raise ValueError(f'ภาพฉาก {index} ที่บันทึกไว้ไม่พร้อม')
        identity = row.get('identity') or {
            'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
            'narration': job['scene_narrations'][index - 1], 'audio_choices': job.get('audio_choices')}
        if job.get('actor_dialogue') and not row:
            identity.update(actor_dialogue=True, scene_dialogue_turns=job['scene_dialogue_turns'][index - 1],
                            character_bible=job['character_bible'])
        run_id = str(row.get('run_id') or f'DESKTOP-PLAN-{job_id}-{index}')
        row = pipeline.request(index, int(job['scene_count']), identity, run_id=run_id)
        render = job.get('render_snapshot') or app._creation_settings(job_id).get('render') or app._video_render_settings()
        app._run_story_scene_worker({'job_id': job_id, 'index': index, 'revision': row['revision'],
            'run_id': run_id, 'desktop_plan_render': True}, api_key, reference_id, reference_file, render, cancel_event)
        result = pipeline.get(index)
        if result.get('phase') != 'complete':
            raise ValueError(str(result.get('error') or f'ฉาก {index} ยังไม่เสร็จ • เก็บผลเดิมไว้'))
    return pipeline.segments(int(job['scene_count']))


def active_scenes(app, job_id):
    """Bounded local evidence only; never focus or interrogate an AI tab."""
    from core.scene_pipeline import ScenePipeline
    result = {int(key[1]) for key, worker in getattr(app, '_story_scene_threads', {}).items()
              if key[0] == job_id and worker and worker.is_alive()}
    current = str(getattr(app, '_story_pipeline_job_id', '') or '') == job_id
    if current:
        pipeline = ScenePipeline(app.stories.root / job_id)
        job = app.stories.get(job_id)
        for index in range(1, int(job.get('scene_count') or 0) + 1):
            if pipeline.get(index).get('phase') in {'requested', 'video', 'voice', 'speech_retry'}:
                result.add(index)
    bridge = getattr(app, 'bridge', None)
    lock = getattr(bridge, '_extension_lock', None)
    if lock is not None:
        with lock:
            for client in getattr(bridge, '_extension_clients', {}).values():
                index = client.get('flow_shot_index')
                if (client.get('flow_job_id') == job_id and client.get('flow_run_id')
                        and isinstance(index, int) and index > 0):
                    result.add(index)  # A missing desktop worker is not an idle browser.
            for command in getattr(bridge, '_extension_commands', []):
                if command.get('job_id') != job_id or command.get('status') not in {'pending', 'delivered'}:
                    continue
                index = command.get('shot_index') or command.get('index')
                if isinstance(index, int) and index > 0:
                    result.add(index)
    return sorted(result), bool(current and not result)
