"""Update-only barrier; ordinary creation and posting concurrency stays unchanged."""
import secrets


PENDING_MESSAGE = 'กำลังเตรียมอัปเดต • ยังไม่เริ่มงานใหม่'
READ_OR_STOP = frozenset({
    'shopee_post_status', 'shopee_post_library', 'shopee_post_pause',
    'android_wifi_status', 'facebook_status', 'facebook_planner_pause',
})


def direct_action(owner, action, callback):
    """Serialize a direct service dispatch with committing the update barrier.

    Never hold this lock while waiting for the Tk request queue. The installer
    preparation runs on Tk and uses a nonblocking acquire below.
    """
    if action in READ_OR_STOP:
        return callback()
    with owner._app_update_lock:
        if getattr(owner, '_app_update_pending', False):
            raise ValueError(PENDING_MESSAGE)
        return callback()


def idle_reason(owner):
    reason = owner._creation_idle_reason()
    if reason:
        return reason
    posting = getattr(owner, 'shopee_posting', None)
    if posting is not None and posting._busy:
        return 'กำลังทำงานกับมือถือ Shopee • รอให้งานจบก่อนอัปเดต'
    facebook = getattr(owner, 'facebook_post', None)
    if facebook is not None:
        if any(worker.is_alive() for worker in facebook.workers.values()):
            return 'กำลังส่งคลิปไป Facebook • รอให้งานจบก่อนอัปเดต'
        if facebook.state().get('planner', {}).get('batch', {}).get('active'):
            return 'คิว Facebook ยังทำงานอยู่ • รอให้งานจบก่อนอัปเดต'
    wifi = getattr(owner, 'android_wifi', None)
    if wifi is not None and wifi.state().get('busy'):
        return 'กำลังตรวจหรือเชื่อมต่อมือถือ • รอให้เสร็จก่อนอัปเดต'
    return ''


def prepare(owner, payload):
    if not owner._app_update_lock.acquire(blocking=False):
        raise ValueError('กำลังรับคำสั่งงาน • รอให้เสร็จก่อนอัปเดต')
    try:
        if payload.get('cancel') is True:
            nonce = getattr(owner, '_app_update_nonce', '')
            if not nonce or not secrets.compare_digest(str(payload.get('nonce') or ''), nonce):
                raise ValueError('ไม่พบการเตรียมอัปเดตเดิมที่ตรงกัน')
            owner._app_update_pending = False
            owner._app_update_nonce = ''
            # The user must resume explicitly; never restart a queue on failure.
            return {'ok': True, 'cancelled': True}
        if getattr(owner, '_app_update_pending', False):
            raise ValueError(PENDING_MESSAGE)
        reason = idle_reason(owner)
        if reason:
            raise ValueError(reason)
        owner.story_queue.pause('app_update')
        owner._app_update_nonce = secrets.token_hex(16)
        owner._app_update_pending = True
        return {'ok': True, 'nonce': owner._app_update_nonce}
    finally:
        owner._app_update_lock.release()
