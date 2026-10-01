"""Native upload acknowledgement, not a successful tap or a guessed feed state."""
import time
import xml.etree.ElementTree as ET

from core.shopee_posting.device import ReviewRequired

PACKAGE = 'com.shopee.th'
SUCCESS = 'อัปโหลดสำเร็จ'
VIEW = 'คลิกที่นี่เพื่อดูวิดีโอ'


def upload_notice(xml, *, allow_composer=False):
    try:
        root = ET.fromstring(xml)
    except (ET.ParseError, TypeError):
        return False
    def own(n):
        return (n.get('package') == PACKAGE and n.get('enabled') == 'true'
                and n.get('visible-to-user', 'true') == 'true')
    nodes = list(root.iter('node'))
    if not allow_composer and any(own(n) and n.get('resource-id', '').endswith(':id/et_caption') for n in nodes):
        return False
    # The observed native banner has these two TextViews as direct siblings.
    # Bounds may be offscreen during its exit animation; never click the banner.
    banners = [n for n in nodes if own(n) and n.get('class') == 'android.view.ViewGroup'
               and n.get('clickable') == 'true'
               and sorted(c.get('text') for c in n if own(c) and c.get('text')) == sorted([SUCCESS, VIEW])]
    return len(banners) == 1


def await_upload(device, store, row_id, timeout=60):
    row = next(r for r in store.read()['items'] if r['id'] == row_id)
    intent = row.get('publish_intent') or {}
    # Versionless historical sends use the existing exact-result verifier.
    if intent.get('upload_notice_absent') is not True:
        return False
    deadline = time.monotonic() + timeout
    while True:
        xml, _ = device.snapshot()
        if upload_notice(xml):
            store.confirm_uploaded(row_id, intent['id'], time.time(), 'live_native_upload_banner')
            return True
        if time.monotonic() >= deadline:
            return False  # Missing notice is NOT a failure or permission to resend.
        time.sleep(.3)


def reconcile_saved_upload(store, row_id, revision):
    """Recover the old verifier's own after-send capture; no phone input or Post."""
    row = next(r for r in store.read()['items'] if r['id'] == row_id)
    intent = row.get('publish_intent') or {}
    if row['revision'] != revision or row['phase'] != 'unknown' or not intent.get('id'):
        raise ReviewRequired('สถานะเปลี่ยนแล้ว กรุณาโหลดคิวใหม่ • ไม่ส่งซ้ำ')
    folder = store.file.path.parent / 'receipts' / row_id
    path = folder / 'profile_after.xml'
    try:
        stamp = path.stat().st_mtime
        xml = path.read_text(encoding='utf-8')
        nodes = list(ET.fromstring(xml).iter('node'))
    except (OSError, ET.ParseError):
        raise ReviewRequired('ไม่มีหลักฐานอัปโหลดสำเร็จที่บันทึกไว้ • ตรวจโพสต์เดิม ไม่ส่งซ้ำ')
    names = [n.get('text') for n in nodes if n.get('package') == PACKAGE
             and n.get('text', '').startswith('ชื่อผู้ใช้: ')]
    # Capture must belong to this last send, before its terminal error, and show
    # both the real native success banner and the exact account's own profile.
    if (not intent.get('at', 0) <= stamp <= row['updated_at']
            or names != ['ชื่อผู้ใช้: ' + intent.get('account', '')] or not upload_notice(xml)):
        raise ReviewRequired('หลักฐานไม่ยืนยันผลของรอบนี้ • เก็บสถานะเดิม ไม่ส่งซ้ำ')
    store.confirm_uploaded(row_id, intent['id'], stamp, 'saved_native_upload_banner',
                           evidence_path=str(path), revision=revision)
