"""Durable recovery of an owned Meta conversation that now redirects to Home.

Never infer an unsent request from a missing DOM node. A fresh document read of
the exact saved URL, then stable empty Home evidence, is required for one new
scene attempt. Completed scenes and archived receipts are not replaced.
"""
import math
import re
import time
import uuid


def empty_home(proof):
    return (isinstance(proof, dict)
            and proof.get('observed_url') == 'https://www.meta.ai/'
            and isinstance(proof.get('document_id'), str) and 0 < len(proof['document_id']) <= 128
            and all(proof.get(key) is True for key in ('ready', 'composer_empty', 'answer_empty'))
            and all(proof.get(key) is False for key in ('login', 'busy', 'stop', 'dialog'))
            and type(proof.get('composer_count')) is int and proof['composer_count'] == 1
            and all(type(proof.get(key)) is int and proof[key] == 0
                    for key in ('user_count', 'image_count', 'video_count', 'message_count')))


def route_event(data, store, receipt, body):
    action = body['stage']
    expected = receipt.get('conversation_url', '')
    if (receipt['stage'] not in ('submitted', 'generating')
            or not re.fullmatch(r'https://www\.meta\.ai/prompt/[\w-]+/?', expected)
            or body.get('conversation_url') != expected):
        raise ValueError('ยังตรวจบทสนทนา Meta เดิมไม่ได้ • ไม่เริ่มฉากซ้ำ')
    check = receipt.get('route_recovery')
    if action == 'route_restored':
        if not check or body.get('route_check_id') != check['check_id']:
            raise ValueError('ผลตรวจหน้า Meta ไม่ตรงรอบที่บันทึก')
        receipt.pop('route_recovery', None)
        receipt.update(updated_at=time.time(), message='พบหน้า Meta ของฉากเดิม • ตรวจผลต่อ')
        store.write_unlocked(data)
        return dict(receipt)
    proof = body.get('route_evidence')
    if not empty_home(proof):
        raise ValueError('หน้า Meta ยังไม่พร้อมหรือมีงานอยู่ • ไม่เริ่มฉากซ้ำ')
    if action == 'route_recheck':
        if not check:
            count = int(receipt.get('route_retry_count') or 0)
            delay = (15, 30, 60, 120, 300)[min(count, 4)]
            receipt['route_recovery'] = dict(check_id=uuid.uuid4().hex,
                document_id=proof['document_id'], observed_url=proof['observed_url'],
                checked_at=time.time(), next_retry_at=time.time() + delay)
            receipt.update(updated_at=time.time(), message='กำลังเปิดลิงก์ Meta ของฉากเดิมเพื่อตรวจผลอีกครั้ง')
            store.write_unlocked(data)
        return dict(receipt)
    stable = proof.get('stable_ms')
    if (not check or body.get('route_check_id') != check['check_id']
            or proof['document_id'] == check['document_id']
            or type(proof.get('samples')) is not int or proof['samples'] < 2
            or type(stable) not in (int, float) or not math.isfinite(stable) or stable < 5000):
        raise ValueError('ยังไม่มีผลตรวจหน้า Meta หลังเปิดลิงก์เดิมใหม่ • ไม่เริ่มฉากซ้ำ')
    if time.time() < check['next_retry_at']:
        return dict(receipt)
    archived = dict(receipt, failure_reason='saved_route_redirected_home',
                    route_observation={**proof, 'check_id':check['check_id']})
    data.setdefault('attempt_history', {}).setdefault(str(receipt['index']), []).append(archived)
    successor = dict(job_id=receipt['job_id'], index=receipt['index'], context_id=receipt['context_id'],
        request_id=uuid.uuid4().hex, stage='prepared', updated_at=time.time(),
        retry_previous_request_id=receipt['request_id'], route_previous_check_id=check['check_id'],
        route_retry_count=int(receipt.get('route_retry_count') or 0) + 1,
        retry_count=int(receipt.get('retry_count') or 0),
        service_retry_count=int(receipt.get('service_retry_count') or 0),
        message='ลิงก์ Meta เดิมกลับหน้าแรกหลังตรวจซ้ำ • เริ่มเฉพาะฉากนี้ด้วยรูปและพรอมต์ที่บันทึกไว้')
    data['scenes'][str(receipt['index'])] = successor
    store.write_unlocked(data)
    return dict(successor)
