"""Recoverable product-job management, independent of provider/media state."""
from contextlib import contextmanager
import hashlib
import re
import threading
from pathlib import Path

_DELETE_WORKERS = {}
_DELETE_LOCK = threading.RLock()


@contextmanager
def _idle_source_preparation():
    from core.product_story import _PRODUCT_STORY_PREPARE_LOCK
    # Management runs on the UI thread. Source preparation can be downloading
    # a new Shopee link/image, so never wait for that network work here.
    if not _PRODUCT_STORY_PREPARE_LOCK.acquire(blocking=False):
        raise ValueError('กำลังเตรียมข้อมูลสินค้า • รอให้เตรียมเสร็จก่อนจัดการรายการ')
    try:
        yield
    finally:
        _PRODUCT_STORY_PREPARE_LOCK.release()


def prepare_product_source(app, payload):
    """Keep explicit source/request-ID recovery behind recoverable trash."""
    from core.product_story import _PRODUCT_STORY_PREPARE_LOCK, prepare_link
    with _PRODUCT_STORY_PREPARE_LOCK:
        ident = str(payload.get('product_id') or '')
        request_id = str(payload.get('request_id') or '').strip()
        from core.product_job_deletion import assert_source_request_available
        assert_source_request_available(app.story_queue.path.parent.parent, request_id)
        if not ident and request_id:
            ident = next((str(row['id']) for row in app.products.list_jobs()
                          if str(row.get('story_prepare_request_id') or '') == request_id), '')
        if ident:
            app.story_queue.require_not_trashed(ident)
        return prepare_link(app.products, app.product_cast, app.bridge, payload)


def manage_product_jobs(app, payload):
    operation = payload.get('operation')
    if operation == 'delete':
        try:
            return delete_product_jobs(app, payload)
        except ValueError as exc:
            from core.product_job_deletion import snapshot
            ident = payload.get('request_id')
            old = snapshot(app.story_queue.path.parent.parent)['requests'].get(ident) if isinstance(ident, str) else None
            requested = payload.get('job_ids')
            if (old and isinstance(requested, list) and all(isinstance(value, str) for value in requested)
                    and old['job_ids'] == sorted(set(requested)) and old['scope'] == (payload.get('scope') or 'selected')):
                return product_jobs_delete_status(app, payload)
            return {'ok': False, 'deletion': {'request_id': ident, 'status': 'rejected', 'accepted': False,
                'job_ids': payload.get('job_ids') or [], 'deleted_ids': [], 'failed': [], 'error': str(exc)}}
    ids = payload.get('job_ids')
    all_pending = payload.get('scope') == 'all_pending'
    if operation not in {'hide', 'show', 'trash', 'restore'}:
        raise ValueError('คำสั่งจัดการงานไม่ถูกต้อง')
    if all_pending and operation != 'trash':
        raise ValueError('ลบงานค้างทั้งหมดใช้ได้เฉพาะการย้ายลงถังขยะ')
    if not isinstance(ids, list) or not ids or (len(ids) > 200 and not all_pending) or any(
        not isinstance(i, str) or not re.fullmatch(r'(?:JOB|STORY)-[A-Za-z0-9-]+', i) for i in ids
    ):
        raise ValueError('กรุณาเลือกงานสินค้าที่ต้องการจัดการ')
    ids = list(dict.fromkeys(ids))
    if operation == 'trash' and payload.get('confirmed') is not True:
        raise ValueError('กรุณายืนยันการย้ายงานลงถังขยะ')
    queue = app.story_queue
    # Desktop dispatch is serialized; share the queue lock with claim/retry.
    # Source preparation also runs outside the UI thread; serialize its capture
    # dispatch with this check/commit, in the same prepare -> queue lock order.
    with _idle_source_preparation(), queue._lock, queue._store.locked():
        if all_pending:
            # The UI freezes the full pending-ID set at confirmation. Never
            # expand that set to newer jobs, hidden rows or another tab.
            controls = queue.product_job_controls()
            ids = [ident for ident in ids if not controls.get(ident, {}).get('trashed')]
            if any(controls.get(ident, {}).get('hidden') for ident in ids):
                raise ValueError('รายการงานค้างเปลี่ยนแล้ว • มีงานถูกซ่อนไว้ กรุณาตรวจรายการแล้วลองใหม่')
            if not ids:
                return {'ok': True, 'product_job_controls': controls}
        reason = app._creation_idle_reason()
        if reason:
            raise ValueError(reason)
        if app.bridge.pending_job_commands(ids):
            raise ValueError('ยังมีคำสั่งของงานนี้รอ Extension ยืนยัน • รอหรือยกเลิกงานก่อน')
        from ui.creation_queue import REMOTE_TERMINAL_STEPS
        status = app.bridge.extension_status()
        for client in status.get('clients', []):
            for scope in ('ai', 'flow'):
                if client.get(f'{scope}_job_id') in ids and str(client.get(f'{scope}_step') or '') not in REMOTE_TERMINAL_STEPS:
                    raise ValueError('ยังยืนยันว่า Extension หยุดงานนี้ไม่ได้ • ตรวจหรือยกเลิกงานก่อน')
        source_ids = set()
        for ident in ids:
            job = app.stories.get(ident) if ident.startswith('STORY-') else app.products.get_job(ident)
            if (job.get('series_id') or
                (ident.startswith('STORY-') and not job.get('product_story'))):
                raise ValueError('จัดการได้เฉพาะงานคลิปสินค้า Shopee')
            if job.get('story_source_only'):
                if (not ident.startswith('JOB-') or job.get('story_job_id')
                        or job.get('story_queued_item_id')):
                    raise ValueError('สินค้านี้ส่งเข้าคลิปหรือคิวแล้ว • จัดการจากงานคลิปหรือคิว')
                source_ids.add(ident)
            if operation in {'hide', 'trash'} and (
                (job.get('readiness') or {}).get('ready') or
                (job.get('status') == 'ready' and job.get('video_status') == 'ready') or
                job.get('status') in {'deleted', 'video_deleted'} or job.get('video_status') == 'deleted'
            ):
                raise ValueError('จัดการได้เฉพาะงานที่ยังไม่เสร็จ • คลิปสำเร็จอยู่ในคลังวิดีโอ')
        if source_ids:
            # A lost source-link save must not make an existing Story/queue
            # dependency look orphaned. Match the same links as the UI list.
            linked = {str((row.get('product_story') or {}).get('product_id') or '')
                      for row in app.stories.list_jobs()}
            for item in queue.snapshot().get('items') or []:
                linked.add(str(item.get('job_id') or ''))
                context = (item.get('settings') or {}).get('creative_context') or {}
                if context.get('kind') == 'product_story':
                    linked.add(str(context.get('source_product_id') or ''))
            if source_ids & linked:
                raise ValueError('สินค้านี้ส่งเข้าคลิปหรือคิวแล้ว • จัดการจากงานคลิปหรือคิว')
        controls = queue.manage_product_jobs(ids, operation)
    return {'ok': True, 'product_job_controls': controls}


def product_jobs_delete_status(app, payload):
    from core.product_job_deletion import REQUEST_ID, response
    ident = payload.get('request_id')
    if not isinstance(ident, str) or not REQUEST_ID.fullmatch(ident):
        raise ValueError('รหัสคำขอลบไม่ถูกต้อง')
    from core.product_job_deletion import snapshot
    with _DELETE_LOCK:
        root = app.story_queue.path.parent.parent
        if ident not in snapshot(root)['requests']:
            return {'ok': True, 'deletion': {'request_id': ident, 'status': 'not_found', 'accepted': False,
                    'job_ids': [], 'deleted_ids': [], 'failed': []}}
        result = response(root, ident, app.story_queue.product_job_controls())
        if result['deletion']['status'] == 'deleting' and (str(root.resolve()), ident) not in _DELETE_WORKERS:
            result['deletion']['status'] = 'partial'
            done = set(result['deletion']['deleted_ids'])
            result['deletion']['failed'] = [{'job_id': job_id, 'error': 'การลบถูกขัดจังหวะ • กดลองลบส่วนที่เหลือ'}
                                            for job_id in result['deletion']['job_ids'] if job_id not in done]
        return result


def _validate_delete_jobs(app, ids, scope, records, root, guard):
    """Preflight the exact frozen set before any irreversible intent or I/O."""
    from core.product_job_deletion import targets, validate_tree
    controls = app.story_queue.product_job_controls()
    queued = app.story_queue.snapshot().get('items') or []
    if any(row.get('job_id') in ids and row.get('status') == 'running' for row in queued):
        raise ValueError('งานยังอยู่ระหว่างทำงาน • รอหรือยกเลิกก่อนลบ')
    if app.bridge.pending_job_commands(ids):
        raise ValueError('Extension ยังมีคำสั่งที่ไม่ได้ยืนยันจบ • ยังลบถาวรไม่ได้')
    from ui.creation_queue import REMOTE_TERMINAL_STEPS
    for client in app.bridge.extension_status().get('clients') or []:
        for kind in ('ai', 'flow'):
            if client.get(kind + '_job_id') in ids and str(client.get(kind + '_step') or '') not in REMOTE_TERMINAL_STEPS:
                raise ValueError('ยังยืนยันว่า Extension หยุดงานไม่ได้ • ไม่ลบถาวร')
    rows = {}
    for ident in ids:
        if ident in records:
            # An explicit retry retains its original authority even when a
            # partial purge already removed job.json. Never choose new paths.
            rows[ident] = dict(records[ident])
            continue
        control = controls.get(ident) or {}
        if scope == 'all_pending' and (control.get('hidden') or control.get('trashed')):
            raise ValueError('รายการเปลี่ยนหลังยืนยัน • ไม่ลบงานซ่อนหรือรายการเก่าโดยอัตโนมัติ')
        if scope == 'legacy_trash' and not control.get('trashed'):
            raise ValueError('รายการนี้ไม่ได้อยู่ในข้อมูลถังขยะเดิมที่ยืนยัน')
        job = app.stories.get(ident) if ident.startswith('STORY-') else app.products.get_job(ident)
        if job.get('id') != ident or job.get('series_id') or (ident.startswith('STORY-') and (
                not job.get('product_story') or job.get('long_video') or job.get('job_type') == 'drama_episode')):
            raise ValueError('ลบจากหน้านี้ได้เฉพาะงานคลิปสินค้า Shopee ที่เลือก')
        if (job.get('readiness') or {}).get('ready') or any(job.get(key) for key in ('video_path', 'final_path', 'final_video_path')) or (
                job.get('video_status') in {'ready', 'complete', 'completed', 'deleted'} or
                job.get('status') in {'ready', 'posted', 'ready_for_phone', 'deleted', 'video_deleted'}):
            raise ValueError('งานสำเร็จหรือมี Final แล้ว • จัดการแยกจากคลังวิดีโอ')
        if job.get('story_source_only') and (job.get('story_job_id') or job.get('story_queued_item_id')):
            raise ValueError('ข้อมูลสินค้ามีงานคลิปหรือคิวอ้างอิงอยู่ • ไม่ลบแหล่งร่วม')
        paths = targets(root, ident)
        identities = [validate_tree(path, root, missing_ok=position == 1) for position, path in enumerate(paths)]
        from core.scene_video_plan import _read, flow_owner
        meta_rows = _read(paths[0], 'meta_video_receipts.json').get('scenes') or {}
        if not isinstance(meta_rows, dict) or any(not isinstance(row, dict) or (
                row and row.get('stage') != 'stored' and not (row.get('stage') == 'needs_attention'
                and row.get('retry_exhausted') is True)) for row in meta_rows.values()):
            raise ValueError('Meta ยังมีคำขอหรือผลดาวน์โหลดที่ไม่ยืนยันจบ • ไม่ลบถาวร')
        for index in range(1, int(job.get('scene_count') or job.get('flow_target_clip_count') or 0) + 1):
            owner = flow_owner(paths[0], index)
            if owner and (owner.get('uncertain') or owner.get('step') not in REMOTE_TERMINAL_STEPS or
                    owner.get('step') == 'generation_complete' and not (job.get('flow_clips') or {}).get(str(index))):
                raise ValueError('Flow ยังมีคำขอหรือผลดาวน์โหลดที่ไม่ยืนยันจบ • ไม่ลบถาวร')
        rows[ident] = {'identities': identities, 'source_request_sha256':
            hashlib.sha256(str(job['story_prepare_request_id']).encode()).hexdigest() if job.get('story_prepare_request_id') else ''}
    # Existing dependent jobs are protected even when they are currently idle.
    for manager in (app.products, app.stories):
        for row in manager.list_jobs():
            owner = str(row.get('id') or '')
            if owner in ids:
                continue
            if set(ids) & guard.references(row, manager.root / owner):
                raise ValueError('งานอื่นยังอ้างถึงไฟล์ของรายการที่เลือก • ไม่ลบไฟล์ร่วม')
    for row in queued:
        referenced = guard.references(row)
        # Only this exact parked row is removed; another row's reference stays.
        own = str(row.get('job_id') or '')
        if (set(ids) & referenced) - ({own} if own in ids else set()):
            raise ValueError('คิวอื่นยังอ้างถึงไฟล์ของรายการที่เลือก')
    # A source may be selected alongside its Story; never turn that into a cascade.
    for ident in ids:
        if ident in records or not ident.startswith('JOB-'):
            continue
        job = app.products.get_job(ident)
        if job.get('story_source_only') and any(
                str((story.get('product_story') or {}).get('product_id') or '') == ident
                for story in app.stories.list_jobs()):
            raise ValueError('ข้อมูลสินค้ามี Story อ้างอิงอยู่ • ไม่ลบแหล่งร่วม')
    return rows


def _delete_product_files(app, root, request_id, ids, claim):
    from core.product_job_deletion import journal, targets, purge_tree, snapshot, response
    try:
        for ident in ids:
            if snapshot(root)['jobs'][ident]['state'] == 'deleted':
                continue
            error = ''
            try:
                claim.guard.recheck(claim, ident)
                row = snapshot(root)['jobs'][ident]
                for path, identity in zip(targets(root, ident), row['identities']):
                    if identity is None:
                        if path.exists():
                            raise ValueError('พบโฟลเดอร์ใหม่หลังยืนยัน • ไม่ขยายขอบเขตลบ')
                    else:
                        purge_tree(path, root, identity)
            except Exception as exc:
                error = str(exc)[:350] or type(exc).__name__
            store = journal(root)
            with store.locked():
                data = store.read_unlocked()
                data['jobs'][ident].update(state='failed' if error else 'deleted', error=error)
                store.write_unlocked(data)
        result = response(root, request_id)
        if hasattr(app, 'events'):
            failed = len(result['deletion']['failed'])
            app.events.put(('desktop_operation', ('warning' if failed else 'success',
                f"ลบถาวรแล้ว {len(result['deletion']['deleted_ids'])} รายการ" + (f' • ลบไม่ครบ {failed} รายการ กดลองลบส่วนที่เหลือ' if failed else ' • กู้คืนไม่ได้'))))
    finally:
        claim.release()
        with _DELETE_LOCK:
            _DELETE_WORKERS.pop((str(root), request_id), None)


def delete_product_jobs(app, payload):
    from core.product_job_deletion import JOB_ID, REQUEST_ID, RUN_OWNER, journal, snapshot, response
    from core.job_file_guard import app_guard
    ids, request_id = payload.get('job_ids'), payload.get('request_id')
    scope = payload.get('scope') or 'selected'
    if (scope not in {'selected', 'all_pending', 'legacy_trash'} or payload.get('confirmed') is not True
            or not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id)
            or not isinstance(ids, list) or not ids or scope == 'selected' and len(ids) > 200
            or any(not isinstance(i, str) or not JOB_ID.fullmatch(i) for i in ids)):
        raise ValueError('กรุณายืนยันรายการและคำขอลบถาวรให้ถูกต้อง')
    ids = sorted(set(ids))
    queue = app.story_queue
    root = queue.path.parent.parent.resolve()
    worker_key = (str(root), request_id)
    claim = None
    with _DELETE_LOCK, _idle_source_preparation():
        existing = snapshot(root)
        old = existing['requests'].get(request_id)
        if old and (old['job_ids'] != ids or old['scope'] != scope):
            raise ValueError('คำขอลบเดิมมีรายการต่างกัน • ไม่ขยายขอบเขตหลังยืนยัน')
        if worker_key in _DELETE_WORKERS or old and all(existing['jobs'][i]['state'] == 'deleted' for i in ids):
            return response(root, request_id, queue.product_job_controls())
        pending = [i for i in ids if existing['jobs'].get(i, {}).get('state') != 'deleted']
        if not pending:
            store = journal(root)
            with store.locked():
                data = store.read_unlocked()
                data['requests'][request_id] = {'job_ids': ids, 'scope': scope}
                store.write_unlocked(data)
            return response(root, request_id, queue.product_job_controls())
        guard = app_guard(app)
        claim = guard.reserve_delete(pending, allow_queued_job_ids=pending) if pending else None
        try:
            with queue._lock, queue._store.locked():
                rows = _validate_delete_jobs(app, pending, scope, existing['jobs'], root, guard)
                store = journal(root)
                with store.locked():
                    data = store.read_unlocked({'version': 1, 'jobs': {}, 'requests': {}})
                    data['requests'][request_id] = {'job_ids': ids, 'scope': scope}
                    for ident in pending:
                        data['jobs'][ident] = {**rows[ident], 'state': 'deleting', 'error': '',
                                               'request_id': request_id, 'owner': RUN_OWNER}
                    store.write_unlocked(data)
                # The journal is authoritative even if a subsequent queue
                # write is interrupted; _load filters permanent IDs forever.
                queue_data = queue._load()
                queue._save(queue_data)
            worker = threading.Thread(target=_delete_product_files,
                args=(app, root, request_id, pending, claim), daemon=True)
            _DELETE_WORKERS[worker_key] = worker
            worker.start()
            claim = None  # Owned until the background worker finally releases.
        except Exception:
            _DELETE_WORKERS.pop(worker_key, None)
            if snapshot(root)['requests'].get(request_id):
                store = journal(root)
                with store.locked():
                    data = store.read_unlocked()
                    for ident in pending:
                        if ident in data['jobs']:
                            data['jobs'][ident].update(state='failed', error='เริ่มลบไม่สำเร็จ • กดลองลบส่วนที่เหลือ')
                    store.write_unlocked(data)
            raise
        finally:
            if claim is not None:
                claim.release()
    return response(root, request_id, queue.product_job_controls())
