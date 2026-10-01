"""Explicit Shopee Story video selections and immutable per-scene dispatch claims.

Legacy jobs are never migrated by readers. A save changes only this manifest's
plan; it never stops a provider, clears a receipt, or starts a worker.
"""
import copy
import hashlib
import json
import uuid
from functools import lru_cache
from pathlib import Path

from core.flow_settings import flow_settings

PROVIDERS = {'google_flow', 'meta_ai'}
FIELDS = {'google_flow': 'flow_clips', 'meta_ai': 'meta_clips', 'local': 'flow_fallback_clips'}


def enabled(job):
    return isinstance(job.get('scene_video_plan'), dict) and job['scene_video_plan'].get('version') == 1


def eligible(job):
    return bool(str(job.get('id') or '').startswith('STORY-') and job.get('product_story')
                and job.get('video_generation_mode') in PROVIDERS
                and not job.get('long_video') and not job.get('series_id')
                and job.get('job_type') != 'drama_episode' and not job.get('cast_creation'))


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def _uncached_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=512)
def _cached_digest(path, size, modified, changed):
    return _uncached_digest(path)


def _digest(path, fresh=False):
    path = Path(path).resolve()
    before = path.stat()
    key = (str(path), before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    value = _uncached_digest(path) if fresh else _cached_digest(*key)
    after = path.stat()
    if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != key[1:]:
        raise ValueError('ไฟล์ฉากกำลังเปลี่ยน • รอตรวจหลักฐานอีกครั้ง')
    return value


def _read(folder, name):
    path = Path(folder) / 'prompts' / name
    if not path.exists():
        return {}
    # Atomic primary reads avoid taking a receipt lock under the manifest lock.
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('อ่านหลักฐานฉากเดิมไม่ได้ • เก็บงานไว้ก่อน') from exc
    if not isinstance(value, dict):
        raise ValueError('หลักฐานฉากเดิมไม่ครบ • เก็บงานไว้ก่อน')
    return value


def _scene(plan, index):
    rows = plan.get('scenes') or {}
    value = rows.get(str(index)) if isinstance(rows, dict) else None
    if value is not None and not isinstance(value, dict):
        raise ValueError('หลักฐานฉากเดิมไม่ครบ • เก็บงานไว้ก่อน')
    return value or {}


def _selection(job, index):
    row = _scene(job.get('scene_video_plan') or {}, index) if enabled(job) else {}
    return row.get('claim') or row


def provider_for(job, index):
    return str(_selection(job, index).get('provider') or job.get('video_generation_mode') or 'image_motion')


def settings_for(job, index):
    selected = _selection(job, index)
    if 'flow_settings' in selected:
        return copy.deepcopy(selected['flow_settings'])
    value = flow_settings(job.get('flow_settings'))
    old = (job.get('flow_scene_edits') or {}).get(str(index)) or {}
    if 'model' in old:
        value.pop('model', None)
        if old['model']:
            value['model'] = old['model']
    if isinstance(old.get('flow_settings'), dict):
        value = flow_settings(old['flow_settings'])
    return value


def effective_job(job, index):
    if not enabled(job):
        return job
    result = copy.deepcopy(job)
    result['video_generation_mode'] = provider_for(job, index)
    result['flow_settings'] = settings_for(job, index)
    selected = _selection(job, index)
    if selected.get('meta_prompt_version') is not None:
        result['meta_prompt_version'] = selected['meta_prompt_version']
    # Existing scene-selection/claim logic is authoritative for provider/model.
    # Rebind only its render copy; no words, assets or saved base job are changed.
    from core.product_editorial import rebind_revision
    rebind_revision(job, result, 'video-selection:' + str(selected.get('selection_id') or index))
    return result


def _file(folder, relative):
    root = Path(folder).resolve()
    path = (root / str(relative or '')).resolve()
    if (not relative or not path.is_relative_to(root) or not path.is_file()
            or path.suffix.lower() not in {'.mp4', '.webm', '.mov', '.mkv', '.avi'}
            or path.stat().st_size < 1024):
        raise ValueError('ไฟล์คลิปฉากเดิมหายหรือไม่พร้อม • ไม่สร้างทับอัตโนมัติ')
    return path


@lru_cache(maxsize=256)
def _probe(path, size, modified):
    from core.video_logo import VideoLogoRenderer
    info = VideoLogoRenderer().video_info(path)
    if float(info.get('duration') or 0) <= 0:
        raise ValueError('คลิปฉากเดิมไม่มีระยะเวลาวิดีโอที่อ่านได้')
    return {key: info[key] for key in ('duration', 'width', 'height')}


def _identity(folder, job, index, fresh=False):
    images = [*(job.get('generated_images') or []), *(job.get('partial_generated_images') or [])]
    image_hash = ''
    for relative in images:
        if Path(str(relative)).stem in {f'scene_{index:02d}', f'scene_{index}'}:
            path = (Path(folder) / relative).resolve()
            if not path.is_relative_to(Path(folder).resolve()) or not path.is_file():
                raise ValueError('ภาพอ้างอิงฉากเดิมไม่พร้อม')
            image_hash = _digest(path, fresh=fresh)
            break
    def text_at(key):
        rows = job.get(key) or []
        return rows[index - 1] if len(rows) >= index else ''
    return _hash({'index': index, 'image_sha256': image_hash,
                  'prompt': text_at('scene_prompts'), 'narration': text_at('scene_narrations'),
                  'motion_prompt': ((job.get('flow_scene_edits') or {}).get(str(index)) or {}).get('prompt', ''),
                  'audio': job.get('audio_choices') or {}})


def verified_asset(folder, job, index, *, fresh=False):
    """One verified existing asset; conflicting provider results require review."""
    row = _scene(job.get('scene_video_plan') or {}, index) if enabled(job) else {}
    frozen = row.get('asset')
    if frozen:
        path = _file(folder, frozen.get('path'))
        if _digest(path, fresh=fresh) != frozen.get('sha256') or frozen.get('content_id') != _identity(folder, job, index, fresh=fresh):
            raise ValueError('คลิปหรือข้อมูลฉากเปลี่ยนจากหลักฐานที่เก็บไว้ • ไม่สร้างซ้ำ')
        result = copy.deepcopy(frozen)
    else:
        candidates = [(provider, (job.get(field) or {}).get(str(index))) for provider, field in FIELDS.items()]
        candidates = [(provider, relative) for provider, relative in candidates if relative]
        if len(candidates) > 1:
            # A durable claim identifies a newly completed authorized provider;
            # unrelated historical alternatives must not be guessed.
            owner = (row.get('claim') or {}).get('provider')
            owned = [candidate for candidate in candidates if candidate[0] == owner]
            if len(owned) != 1:
                raise ValueError('ฉากนี้มีคลิปหลายผู้สร้าง • ตรวจคลิปที่จะเก็บก่อนเปลี่ยน')
            candidates = owned
        if not candidates:
            pipeline = _scene(_read(folder, 'scene_pipeline.json'), index)
            receipt = _scene(_read(folder, 'meta_video_receipts.json'), index)
            if pipeline.get('phase') == 'complete' or receipt.get('stage') == 'stored':
                raise ValueError('มี Checkpoint ฉากสำเร็จแต่คลิปต้นทางไม่ครบ • ไม่สร้างซ้ำ')
            return None
        provider, relative = candidates[0]
        path = _file(folder, relative)
        sha = _digest(path, fresh=fresh)
        proof = ((job.get('meta_clip_receipts') or {}).get(str(index)) or {}) if provider == 'meta_ai' else {}
        if proof.get('sha256') and proof['sha256'] != sha:
            raise ValueError('คลิป Meta ไม่ตรงใบรับเดิม • ไม่สร้างซ้ำ')
        stat = path.stat()
        info = _probe(str(path), stat.st_size, stat.st_mtime_ns)
        result = {'index': index, 'provider': provider, 'path': str(path.relative_to(Path(folder).resolve())),
                  'sha256': sha, 'content_id': _identity(folder, job, index, fresh=fresh), **info}
        if proof:
            result['receipt'] = {key: proof[key] for key in ('request_id', 'context_id', 'download_id') if key in proof}
    pipeline = _scene(_read(folder, 'scene_pipeline.json'), index)
    if pipeline.get('phase') == 'complete':
        segment = _file(folder, pipeline.get('segment'))
        sha = _digest(segment, fresh=fresh)
        if sha != pipeline.get('segment_sha256'):
            raise ValueError('ไฟล์ฉากที่รวมเสียงแล้วไม่ตรง Checkpoint เดิม')
        result.update(segment=str(segment.relative_to(Path(folder).resolve())), segment_sha256=sha)
        for key in ('voice', 'duration', 'content_revision'):
            if key in pipeline:
                result[key] = copy.deepcopy(pipeline[key])
    return result


def ordered_assets(folder, job, require_complete=True, *, fresh=False):
    rows = [verified_asset(folder, job, index, fresh=fresh) for index in range(1, int(job.get('scene_count') or 0) + 1)]
    if require_complete and any(row is None for row in rows):
        raise ValueError('คลิปทุกฉากยังไม่ครบ • เก็บฉากสำเร็จเดิมไว้')
    return rows


@lru_cache(maxsize=64)
def _flow_owners(path, size, modified, changed):
    # Read only this job's bounded diagnostic tail. Retain ownership fields,
    # never page excerpts, prompts, URLs, messages or arbitrary diagnostics.
    with Path(path).open('rb') as stream:
        offset = max(0, size - 1024 * 1024)
        stream.seek(offset)
        payload = stream.read(1024 * 1024)
    lines = payload.splitlines()[1:] if offset else payload.splitlines()
    rows = {}
    for line in lines:
        try:
            value = json.loads(line)
        except (ValueError, UnicodeError):
            continue
        index = value.get('shot_index') if isinstance(value, dict) else None
        if type(index) is int and index > 0 and value.get('run_id'):
            rows[index] = {key: str(value.get(key) or '') for key in
                           ('run_id', 'step', 'failure_code', 'failure_card_fingerprint')}
    return rows, bool(offset)


def flow_owner(folder, index):
    path = Path(folder) / 'logs' / 'flow_extension.jsonl'
    if not path.exists():
        return None
    try:
        stat = path.stat()
        rows, truncated = _flow_owners(str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    except OSError as exc:
        raise ValueError('อ่านหลักฐานรอบ Flow เดิมไม่ได้ • ไม่ถือว่าไม่มีงาน') from exc
    return rows.get(index) or ({'uncertain': True} if truncated and index <= max(rows, default=index) else None)


def _busy(folder, index):
    pipe = _scene(_read(folder, 'scene_pipeline.json'), index)
    meta = _scene(_read(folder, 'meta_video_receipts.json'), index)
    if pipe.get('phase') in {'requested', 'video', 'voice'}:
        return True
    if meta:
        stage = str(meta.get('stage') or '')
        if stage == 'stored':
            return False
        if stage == 'needs_attention' and meta.get('retry_exhausted') is True:
            return False
        return True  # Even a prepared/draft receipt still owns permission to Send.
    if flow_owner(folder, index):
        return True  # Includes completed-but-not-yet-imported downloads.
    return False


def summary(folder, job, active=False, active_scene_indices=()):
    supported = eligible(job)
    plan = job.get('scene_video_plan') or {}
    final = job.get('video_status') in {'ready', 'complete', 'completed'} or any(
        job.get(key) for key in ('video_path', 'final_path', 'final_video_path'))
    cancelled = job.get('cancel_requested') or job.get('status') in {'cancelled', 'canceled', 'deleted'}
    editable = supported and not final and not cancelled
    result = {'supported': supported, 'enabled': enabled(job), 'editable': bool(editable),
              'reason': '' if editable else 'ใช้กับงานสินค้า Shopee ที่ยังไม่เสร็จและยังไม่ถูกยกเลิกเท่านั้น',
              'revision': int(plan.get('revision') or 0), 'provider': job.get('video_generation_mode'),
              'flow_settings': flow_settings(job.get('flow_settings')), 'remaining_indices': [],
              'busy_indices': [], 'kept_indices': [], 'scenes': [],
              'counts': {'completed': 0, 'flow': 0, 'meta': 0, 'local': 0, 'pending': 0, 'busy': 0, 'deferred': 0}}
    if not supported:
        return result
    for index in range(1, int(job.get('scene_count') or 0) + 1):
        row = _scene(plan, index)
        error = ''
        try:
            asset = verified_asset(folder, job, index)
            occupied = index in active_scene_indices or _busy(folder, index) or bool(row.get('claim'))
        except ValueError as exc:
            asset, occupied, error = None, True, str(exc)
        state = 'completed' if asset else 'needs_review' if error else 'deferred' if row.get('pending') else 'active' if occupied else 'pending'
        selected = row.get('pending') or _selection(job, index)
        scene = {'index': index, 'provider': (asset or {}).get('provider') or selected.get('provider') or provider_for(job, index),
                 'flow_settings': copy.deepcopy(selected.get('flow_settings', settings_for(job, index))),
                 'state': state, 'editable': bool(editable and not asset and not error), 'reason': error}
        if row.get('pending'):
            scene.update(pending_provider=row['pending']['provider'], pending_flow_settings=copy.deepcopy(row['pending']['flow_settings']))
        result['scenes'].append(scene)
        if asset:
            result['kept_indices'].append(index)
            result['counts']['completed'] += 1
            result['counts'][{'google_flow': 'flow', 'meta_ai': 'meta', 'local': 'local'}[asset['provider']]] += 1
        else:
            if not error:
                result['remaining_indices'].append(index)
            result['counts']['pending'] += 1
            if occupied:
                result['busy_indices'].append(index)
                result['counts']['busy'] += 1
            if row.get('pending'):
                result['counts']['deferred'] += 1
    remaining = next((scene for scene in result['scenes'] if scene['index'] in result['remaining_indices']), None)
    if remaining:
        result.update(provider=remaining['provider'], flow_settings=remaining['flow_settings'])
    return result


def save(manager, job_id, plan_revision, provider, scene_indices, flow_settings=None,
         *, active_scene_indices=(), unknown_active=False):
    from core.flow_settings import flow_settings as normalize
    if provider not in PROVIDERS or type(plan_revision) is not int or not isinstance(scene_indices, list) or not scene_indices:
        raise ValueError('เลือกผู้สร้างและฉากที่จะเปลี่ยนให้ถูกต้อง')
    if any(type(index) is not int for index in scene_indices):
        raise ValueError('ลำดับฉากไม่ถูกต้อง')
    indices = sorted(set(scene_indices))
    settings = normalize(flow_settings)
    request_hash = _hash({'provider': provider, 'indices': indices, 'settings': settings, 'revision': plan_revision})
    folder = manager._folder(job_id)
    store = manager._manifest_store(folder / 'job.json')
    with manager._manifest_lock, store.locked():
        job = store.read_unlocked()
        info = summary(folder, job)
        if not info['editable'] or any(not 1 <= index <= int(job.get('scene_count') or 0) for index in indices):
            raise ValueError(info['reason'] or 'ลำดับฉากไม่ถูกต้อง')
        plan = copy.deepcopy(job.get('scene_video_plan') or {'version': 1, 'revision': 0, 'scenes': {}})
        if plan.get('last_save', {}).get('request_hash') == request_hash:
            return {'job': job, 'job_id': job_id, 'revision': plan['revision'],
                    **copy.deepcopy(plan['last_save']['result']), 'summary': info}
        if int(plan.get('revision') or 0) != plan_revision:
            raise ValueError('แผนวิดีโอเปลี่ยนแล้ว • เปิดรายละเอียดใหม่ก่อนบันทึก')
        applied, staged, completed = [], [], []
        next_revision = plan_revision + 1
        # Freeze every completed asset during explicit opt-in, including those
        # outside the selected set. Reads/Resume never opt legacy jobs in.
        for index in range(1, int(job.get('scene_count') or 0) + 1):
            existing = verified_asset(folder, job, index, fresh=True)
            row = plan['scenes'].setdefault(str(index), {
                'provider': provider_for(job, index), 'flow_settings': settings_for(job, index),
                'selection_id': uuid.uuid4().hex, 'revision': plan_revision})
            # Capture the original Meta prompt contract before choosing a new
            # provider; accepting an active old result must not rewrite it.
            if row['provider'] == 'meta_ai':
                row.setdefault('meta_prompt_version', job.get('meta_prompt_version', 1))
            if existing:
                row['asset'] = existing
                row.pop('pending', None)
                if index in indices:
                    completed.append(index)
                continue
            occupied = index in active_scene_indices or _busy(folder, index)
            if not row.get('claim') and (occupied or unknown_active):
                row['held'] = 'active' if occupied else 'unknown'
                row['legacy_active'] = True
            if index not in indices:
                continue
            selection = {'provider': provider, 'flow_settings': copy.deepcopy(settings),
                         'selection_id': uuid.uuid4().hex, 'revision': next_revision}
            if provider == 'meta_ai':
                from core.meta_prompt import CURRENT_META_PROMPT_VERSION
                selection['meta_prompt_version'] = CURRENT_META_PROMPT_VERSION
            if unknown_active or index in active_scene_indices or row.get('claim') or _busy(folder, index):
                row['pending'] = selection
                row['held'] = 'active' if index in active_scene_indices or row.get('claim') or _busy(folder, index) else 'unknown'
                if not row.get('claim'):
                    row['legacy_active'] = True
                staged.append(index)
            else:
                row.update(selection)
                row.pop('pending', None)
                applied.append(index)
        plan.update(revision=next_revision, last_save={'request_hash': request_hash,
                    'result': {'applied': applied, 'staged': staged, 'completed': completed}})
        job['scene_video_plan'] = plan
        store.write_unlocked(job)
        return {'job': job, 'job_id': job_id, 'revision': next_revision,
                'applied': applied, 'staged': staged, 'completed': completed, 'summary': summary(folder, job)}


def apply_at_safe_boundary(manager, job_id, index):
    folder = manager._folder(job_id)
    store = manager._manifest_store(folder / 'job.json')
    with manager._manifest_lock, store.locked():
        job = store.read_unlocked()
        if not enabled(job):
            return {'job': job, 'provider': provider_for(job, index), 'flow_settings': settings_for(job, index), 'asset': None, 'claim': None}
        if job.get('cancel_requested') or job.get('status') in {'cancelled', 'canceled', 'deleted'}:
            raise ValueError('งานถูกยกเลิก • ไม่เริ่มฉากใหม่')
        if type(index) is not int or not 1 <= index <= int(job.get('scene_count') or 0):
            raise ValueError('ลำดับฉากไม่ถูกต้อง')
        asset = verified_asset(folder, job, index, fresh=True)
        row = job['scene_video_plan']['scenes'][str(index)]
        if (row.get('claim') and row['claim'].get('content_id') != _identity(folder, job, index, fresh=True)):
            raise ValueError('ภาพหรือบทเปลี่ยนหลังเริ่มฉาก • เก็บผลเดิมไว้ตรวจ')
        if asset:
            row['asset'] = asset
            row.pop('pending', None)
            row.pop('held', None)
            row.pop('legacy_active', None)
            store.write_unlocked(job)
            return {'job': job, 'provider': asset['provider'], 'flow_settings': settings_for(job, index), 'asset': asset, 'claim': row.get('claim')}
        if not row.get('claim'):
            if row.get('pending') and row.get('held') != 'active' and not _busy(folder, index):
                row.update(row.pop('pending'))
                row.pop('held', None)
                row.pop('legacy_active', None)
            elif row.get('held') == 'unknown' and not _busy(folder, index):
                row.pop('held', None)
                row.pop('legacy_active', None)
            # A held legacy attempt keeps its original provider/settings. Its
            # existing receipts continue owning the work; pending never replays it.
            if row.get('legacy_active'):
                return {'job': job, 'provider': row['provider'], 'flow_settings': row['flow_settings'], 'asset': None, 'claim': None}
            row['claim'] = {key: copy.deepcopy(row[key]) for key in ('provider', 'flow_settings', 'selection_id', 'revision')}
            if 'meta_prompt_version' in row:
                row['claim']['meta_prompt_version'] = row['meta_prompt_version']
            row['claim'].update(attempt_id=uuid.uuid4().hex, content_id=_identity(folder, job, index))
            store.write_unlocked(job)
        claim = copy.deepcopy(row['claim'])
        return {'job': job, 'provider': claim['provider'], 'flow_settings': claim['flow_settings'], 'asset': None, 'claim': claim}


def finish_scene(manager, job_id, index):
    result = apply_at_safe_boundary(manager, job_id, index)
    if not result['asset']:
        raise ValueError('ยังไม่มีคลิปฉากสำเร็จที่ตรวจแล้ว')
    return result['asset']


def _claim_binding(job, index):
    if not enabled(job):
        return None
    claim = _scene(job['scene_video_plan'], index).get('claim')
    if not claim:
        return None
    return {'version': 1, 'scene_index': int(index), 'plan_revision': claim['revision'],
            'selection_id': claim['selection_id'], 'attempt_id': claim['attempt_id'],
            'provider': claim['provider'], 'settings_sha256': _hash(claim['flow_settings'])}


def package_binding(job, index):
    # Keep the original claim for idempotent result acknowledgements, but no
    # completed scene may advertise permission for another Generate command.
    if enabled(job) and _scene(job['scene_video_plan'], index).get('asset'):
        return None
    return _claim_binding(job, index)


def validate_package(folder, job, index):
    if enabled(job):
        claim = _scene(job['scene_video_plan'], index).get('claim')
        if claim and claim.get('content_id') != _identity(folder, job, index):
            raise ValueError('ภาพหรือบทเปลี่ยนหลังเริ่มฉาก • ไม่ใช้คำสั่งเก่า')


def legacy_active(job, index):
    row = _scene(job.get('scene_video_plan') or {}, index)
    return bool(enabled(job) and row.get('legacy_active') and row.get('held') and not row.get('claim') and not row.get('asset'))


def assert_binding(job, index, binding, *, allow_legacy_active=False):
    if not enabled(job):
        if binding is not None:
            raise ValueError('ไม่พบแผนวิดีโอที่ตรงผลลัพธ์นี้')
        return True
    if binding is None and allow_legacy_active and legacy_active(job, index):
        return True
    expected = _claim_binding(job, index)
    if not expected or not isinstance(binding, dict) or binding != expected:
        raise ValueError('สิทธิ์สร้างวิดีโอฉากนี้เปลี่ยนแล้ว • ไม่ส่งหรือบันทึกผลซ้ำ')
    return True


def retire_terminal(manager, job_id, index, proof, scene_video_plan=None):
    """Retire only a caller-observed terminal attempt, never silence/timeout.

    This is an internal worker API, not a browser action. The worker supplies
    its exact accepted attempt binding and typed terminal provider evidence.
    """
    if (not isinstance(proof, dict) or proof.get('terminal') is not True
            or proof.get('busy') is not False or proof.get('download_pending') is not False
            or proof.get('kind') not in {'provider_failed', 'never_dispatched'}
            or not isinstance(proof.get('code'), str) or not proof['code'].strip()
            or len(proof['code']) > 160):
        raise ValueError('ยังไม่มีหลักฐานว่ารอบเดิมจบ • ไม่เปลี่ยนหรือส่งซ้ำ')
    folder = manager._folder(job_id)
    store = manager._manifest_store(folder / 'job.json')
    with manager._manifest_lock, store.locked():
        job = store.read_unlocked()
        assert_binding(job, index, scene_video_plan, allow_legacy_active=True)
        if not enabled(job):
            return job
        if verified_asset(folder, job, index, fresh=True):
            raise ValueError('ฉากนี้มีคลิปแล้ว • เก็บคลิปเดิมไว้')
        row = job['scene_video_plan']['scenes'][str(index)]
        meta_owner = None
        if provider_for(job, index) == 'meta_ai':
            receipt = _scene(_read(folder, 'meta_video_receipts.json'), index)
            if receipt:
                if (proof.get('request_id') != receipt.get('request_id')
                        or proof.get('kind') != 'provider_failed'
                        or receipt.get('stage') != 'needs_attention'
                        or receipt.get('retry_exhausted') is not True):
                    raise ValueError('ใบรับ Meta ยังไม่ยืนยันว่ารอบเดิมล้มเหลวแล้ว')
                meta_owner = receipt.get('request_id')
        row.setdefault('attempt_history', []).append({'claim': copy.deepcopy(row.get('claim')),
            'legacy_active': bool(row.get('legacy_active')), 'proof': copy.deepcopy(proof),
            'meta_request_id': meta_owner})
        row.pop('claim', None)
        row.pop('held', None)
        row.pop('legacy_active', None)
        if row.get('pending'):
            row.update(row.pop('pending'))
        store.write_unlocked(job)
        return job


def begin_native_retry(manager, job_id, index, retry_id, segment_sha256):
    """Only an existing proven repeated-speech retry may retire a frozen asset."""
    folder = manager._folder(job_id)
    store = manager._manifest_store(folder / 'job.json')
    with manager._manifest_lock, store.locked():
        job = store.read_unlocked()
        if not enabled(job):
            return job
        proof = (job.get('flow_speech_retries') or {}).get(str(index)) or {}
        if (proof.get('status') != 'pending' or proof.get('retry_id') != retry_id
                or proof.get('segment_sha256') != segment_sha256 or not segment_sha256):
            raise ValueError('หลักฐานสร้างเสียงฉากใหม่ไม่ตรง • เก็บคลิปเดิมไว้')
        row = job['scene_video_plan']['scenes'][str(index)]
        if row.get('native_retry_id') == retry_id:
            return job
        asset = row.get('asset') or {}
        if asset.get('provider') != 'google_flow' or asset.get('segment_sha256') != segment_sha256:
            raise ValueError('แก้เสียงซ้ำได้เฉพาะฉาก Flow ที่ตรงหลักฐานเดิม')
        row.setdefault('asset_history', []).append(copy.deepcopy(asset))
        row.pop('asset', None)
        row.pop('claim', None)
        row.pop('pending', None)
        row.pop('held', None)
        row.pop('legacy_active', None)
        row.update(provider='google_flow', selection_id=uuid.uuid4().hex, native_retry_id=retry_id)
        store.write_unlocked(job)
        return job
