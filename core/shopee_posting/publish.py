"""At-most-one public Post tap, with all intent persisted before the gesture."""
from pathlib import Path
import re
from core.shopee_posting.device import ReviewRequired, ShopeeDevice
from core.shopee_posting.store import file_hash
from core.shopee_posting.options import requested_options
from core.shopee_posting.settings import observe_options
from core.shopee_posting.result import upload_notice

P = 'com.shopee.th.dfpluginshopee16:id/'


def publish_current(device, store, row_id, account, product_title, evidence_folder):
    row = next(r for r in store.read()['items'] if r['id'] == row_id)
    if row['phase'] not in {'settings', 'editing', 'prepared'} or row.get('publish_intent'):
        raise ReviewRequired('งานนี้ไม่อยู่ในขั้นพร้อมส่ง หรือเคยเริ่มส่งแล้ว')
    if not account or not product_title or not row.get('transfer'):
        raise ReviewRequired('ไม่มีหลักฐานบัญชี สินค้า หรือไฟล์บนมือถือ')
    store.progress(row_id, 'preflight', 'ตรวจขั้นสุดท้าย: ไฟล์ แคปชัน สินค้า และตัวเลือกก่อนโพสต์')
    if file_hash(row['video_path']) != row.get('video_sha256'):
        raise ReviewRequired('วิดีโอเปลี่ยนจากไฟล์ที่ส่งไปมือถือ')

    def check_page(xml, nodes):
        if any(n.get('resource-id') == 'android:id/input_method_nav_back' for n in nodes):
            raise ReviewRequired('แป้นพิมพ์ยังเปิดอยู่ • ยังไม่เริ่มส่งโพสต์')
        ShopeeDevice.find_node(nodes, **{'resource-id': P+'et_caption', 'text': row['caption']})
        ShopeeDevice.find_node(nodes, **{'resource-id': P+'tv_product_title', 'text': product_title})
        if upload_notice(xml, allow_composer=True):
            raise ReviewRequired('ยังมีผลอัปโหลดรอบก่อนบนหน้าจอ • ยังไม่ส่งโพสต์ใหม่')
        if sum(n.get('resource-id') == P+'tv_product_title' for n in nodes) != 1:
            raise ReviewRequired('ต้องมีสินค้าตรงลิงก์หนึ่งรายการเท่านั้น')
        post = ShopeeDevice.find_node(nodes, **{'resource-id': P+'btn_post', 'text': 'โพสต์'})
        ShopeeDevice.center(post['bounds'])
        return post['bounds']

    options = requested_options(row)
    _, screen = observe_options(device, options, validate=check_page)
    device.save_observation(screen, evidence_folder, 'before_post')
    # One fresh shared guard after disk I/O, before committing any Send intent.
    observed, guard = observe_options(device, options, validate=check_page, previous=screen)
    _, _, right, bottom = map(int, re.findall(r'\d+', guard['context']))
    if right > guard['image'].width or bottom > guard['image'].height:
        raise ReviewRequired('ปุ่มโพสต์อยู่นอกหน้าจอ • ยังไม่เริ่มส่ง')
    store.transition(row_id, {row['phase']}, 'ready', account=account, attached_product_title=product_title,
                     observed_options=observed, upload_notice_absent=True,
                     preflight_version=2, dispatch_state='prepared',
                     cover_mode='shopee_default', evidence_folder=str(Path(evidence_folder)), message='ตรวจขั้นสุดท้ายผ่านแล้ว • พร้อมส่งโพสต์หนึ่งครั้ง')
    try:
        if getattr(device, 'membership', None):
            device.membership.require()
        device.commit_observed_post(guard, lambda: store.claim_publish(
            row_id, account=account, device_id=device.identity, video_sha256=row['video_sha256']))
        store.transition(row_id, {'send_pending'}, 'processing', message='กดโพสต์แล้ว กำลังตรวจผลเดิม ห้ามส่งซ้ำ')
    except Exception:
        current = next(r for r in store.read()['items'] if r['id'] == row_id)
        if current.get('publish_intent') and current['phase'] == 'send_pending':
            store.transition(row_id, {'send_pending'}, 'unknown', message='ยังยืนยันผลการส่งไม่ได้ ต้องตรวจโพสต์เดิม ห้ามส่งซ้ำ')
        raise
