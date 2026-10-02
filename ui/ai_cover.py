"""Post-render cover wait and explicit cover-only actions."""
import time
from pathlib import Path
from core.ai_cover import AICovers, ai_cover_options
from core.job_file_guard import guard_for


def _linked_cover_request(service, request_id, job_id=None):
    """Follow only a saved same-job parent/child chain, never the latest job."""
    with service.store.locked():
        row = service.get(request_id)
        job_id = job_id or row['job_id']
        visited = set()
        while True:
            rid = row['request_id']
            if rid in visited or row.get('job_id') != job_id:
                raise ValueError('คำขอปกใหม่ไม่ตรงงานเดิม • ไม่เริ่มงานอื่น')
            visited.add(rid)
            if not row.get('successor_request_id'):
                return row
            child = service.get(row['successor_request_id'])
            if child.get('parent_request_id') != rid:
                raise ValueError('คำขอปกใหม่ไม่ตรงคำขอเดิม • ไม่เริ่มงานอื่น')
            row = child


def _cancel_linked_cover(service, request_id, job_id=None):
    # Resolve and cancel under the same lock as successor creation. A download
    # acknowledgement racing the user's Cancel cannot leave its child running.
    job_id = job_id or service.get(request_id)['job_id']
    guard = guard_for(Path(service.products.root).parent.parent)
    # Deletion probes can inspect every cover while holding this lock. Keep
    # guard -> store ordering even for event()'s nested, reentrant claim.
    with guard.lock, guard.start(job_id):
        with service.store.locked():
            row = _linked_cover_request(service, request_id, job_id)
            return service.event(row['request_id'], {
                'phase':'cancelled','message':'ผู้ใช้ยกเลิกปก • เก็บวิดีโอและปกเดิมไว้'})


def finish_ai_cover(app, job_id, cancel_event, progress):
    service = getattr(getattr(app, 'bridge', None), 'ai_covers', None)
    if not isinstance(service, AICovers):
        return  # Legacy isolated render adapters do not host Extension work.
    try:
        request = service.request(job_id)
    except Exception as exc:
        from core.atomic_json import AtomicJsonFile
        try:
            with guard_for(Path(service.products.root).parent.parent).start(job_id):
                AtomicJsonFile(service.folder(job_id) / 'job.json').update(lambda manifest:{**manifest,
                    'ai_cover_state':{'phase':'needs_review','message':str(exc)[:250],'request_id':''}})
        except ValueError:
            pass  # A deletion claim must not be bypassed by error reporting.
        progress('วิดีโอเสร็จแล้ว • ทำปก AI ไม่ได้: '+str(exc)[:250])
        return
    if not request:
        return
    rid = request['request_id']
    deadline, observed = time.monotonic() + 360, 0
    try:
        while True:
            row = _linked_cover_request(service, rid, job_id)
            if row['request_id'] != rid:
                rid = row['request_id']
                deadline, observed = time.monotonic() + 360, 0
            if cancel_event.is_set():
                _cancel_linked_cover(service, rid, job_id)
                return
            if row['phase'] in service.TERMINAL:
                progress('ปก AI เสร็จแล้ว' if row['phase']=='ready' else 'วิดีโอเสร็จแล้ว • ปก AI ยังไม่สำเร็จ: '+row.get('message',''))
                return
            if row['updated_at'] != observed:
                observed = row['updated_at']
                if row.get('active'):
                    deadline = time.monotonic() + 360
                progress('วิดีโอเสร็จแล้ว • รอปกจาก AI Web • ' + (row.get('message') or 'กำลังเตรียมปก'))
            if time.monotonic() > deadline:
                state = row.get('collector_state') or {}
                if not state and row.get('send_state') == 'unconfirmed':
                    stage = 'ยังยืนยันไม่ได้ว่า ChatGPT รับคำสั่งสร้างปก • ตรวจร่างในแท็บเดิมก่อนสั่งสร้างใหม่'
                    next_step = 'เก็บวิดีโอและคำขอเดิมไว้ • ไม่ส่งปกซ้ำอัตโนมัติ'
                elif not state and row.get('send_state') == 'accepted':
                    stage = 'ChatGPT รับคำสั่งแล้ว แต่ตัวอ่านภาพยังไม่รายงานผล • ตรวจคำตอบเดิมก่อนสั่งสร้างใหม่'
                    next_step = 'เก็บวิดีโอและคำขอเดิมไว้ • ใช้ดึงผลปกเดิมจากเว็บได้โดยไม่สร้างซ้ำ'
                else:
                    stage = {'request_missing':'ยังจับคู่คำขอปกไม่ได้', 'answer_missing':'ยังไม่พบกรอบคำตอบ',
                             'generating':'เว็บยังแสดงกำลังสร้างในรายงานล่าสุด', 'multiple_images':'พบภาพมากกว่าหนึ่งผล',
                             'waiting_image':'ยังไม่พบภาพในคำตอบ', 'loading_image':'พบภาพแต่ยังโหลดไม่ครบ',
                             'stabilizing':'พบภาพแล้วแต่ยังไม่ยืนยันผล', 'downloading':'พบภาพแล้วแต่ยังบันทึกไฟล์ไม่สำเร็จ'}.get(
                                 state.get('stage'), 'ยังไม่มีข้อมูลจากตัวอ่านภาพ')
                    next_step = 'เก็บวิดีโอและคำขอเดิมไว้ ใช้ดึงปกเดิมจากเว็บได้โดยไม่สร้างซ้ำ'
                service.event(rid, {'phase':'needs_review','message':
                    'ขาดความคืบหน้าปก • '+stage+' • '+next_step})
                return
            cancel_event.wait(1)
    except Exception as exc:
        service.event(rid, {'phase':'needs_review','message':str(exc)[:500]})
        progress('วิดีโอเสร็จแล้ว • ปกต้องตรวจเพิ่มเติม')


def ai_cover_action(app, action, payload):
    service = app.bridge.ai_covers
    if action == 'ai_cover_status':
        return {'ok':True,'request':_linked_cover_request(service, payload.get('request_id'))}
    if action == 'ai_cover_cancel':
        return {'ok':True,'request':_cancel_linked_cover(service, payload.get('request_id'))}
    if action == 'ai_cover_recover':
        reason = app._creation_idle_reason()
        if reason:
            raise ValueError(reason)
        job_id = str(payload.get('item_id') or '').split(':')[-1]
        return {'ok':True,'request':service.recover_result(str(payload.get('request_id') or ''), job_id)}
    if action == 'ai_cover_regenerate':
        reason = app._creation_idle_reason()
        if reason:
            raise ValueError(reason)
        job_id = str(payload.get('item_id') or '').split(':')[-1]
        options = ai_cover_options({**(payload.get('settings') or {}),'enabled':True})
        return {'ok':True,'request':service.request(job_id, force=True, options=options)}
    raise ValueError('คำสั่งปกไม่ถูกต้อง')
