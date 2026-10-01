"""Observe one owned link import; bounded private retries never retry Post."""
import re
import time
import xml.etree.ElementTree as ET

from core.shopee_posting.device import ReviewRequired, ShopeeDevice

P = 'com.shopee.th.dfpluginshopee16:id/'
MAX_IMPORT_ATTEMPTS = 3


class ProductUnavailable(ReviewRequired):
    """Confirmed unusable link/empty result, before any public Send."""


def _bounds(node):
    match = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
    return tuple(map(int, match.groups())) if match else (0, 0, 0, 0)


def inspect_import(xml):
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return {'state': 'unknown'}
    nodes = [n for n in root.iter('node') if n.get('package') == ShopeeDevice.package
             and n.get('visible-to-user', 'true') == 'true']
    def exact(text):
        return [n for n in nodes if n.get('text') == text]
    # Never interpret a general product search/recommendation list as this import.
    headers, headings, footers = exact('กรอกลิงก์สินค้า'), exact('รายการสินค้า'), exact('เลือกทั้งหมด')
    edits = [n for n in nodes if n.get('class') == 'android.widget.EditText']
    adds = [n for n in nodes if re.fullmatch(r'เพิ่ม(?:\s*\(\s*\d+\s*\))?', n.get('text', ''))]
    if not all(len(group) == 1 for group in (headers, headings, footers, edits, adds)):
        return {'state': 'unknown'}
    if any(n.get('resource-id') == P+'et_caption' for n in nodes):
        return {'state': 'unknown'}
    busy = any(n.get('class') == 'android.widget.ProgressBar' or
               n.get('text', '').strip() in ('กำลังโหลด', 'กำลังโหลด...', 'กำลังนำเข้า', 'กำลังนำเข้า...') for n in nodes)
    base = dict(editor=edits[0].get('text', ''), add=adds[0].get('text'), busy=busy)
    if any('สินค้าถูกยกเว้น' in n.get('text', '') for n in nodes):
        return dict(base, state='excluded')
    if any('ลิงก์ไม่ถูกต้อง' in n.get('text', '') for n in nodes):
        return dict(base, state='invalid')
    top, bottom = _bounds(headings[0])[3], _bounds(footers[0])[1]
    if bottom <= top:
        return dict(base, state='unknown')
    region = [n for n in nodes if top <= _bounds(n)[1] < _bounds(n)[3] <= bottom]
    # Price + card ancestry identifies the observed product, commission is optional.
    prices = [n for n in region if re.match(r'^฿\s*\d', n.get('text', ''))]
    if len(prices) > 1:
        return dict(base, state='ambiguous')
    parents = {c: p for p in root.iter() for c in p}
    product = None
    if len(prices) == 1:
        parent = parents[prices[0]]
        for _ in range(4):
            bounds = _bounds(parent)
            if bounds[1] < top or bounds[3] > bottom:
                break
            texts = [n.get('text', '').strip() for n in parent.iter('node') if n in region and n.get('text')]
            titles = [t for t in texts if len(t) > 5 and not re.match(
                r'^(?:\d+$|฿|ค่าคอม|คอมมิชชั่น|ขายแล้ว|ดีลพิเศษ|ส่วนลด|ลดเพิ่ม|ส่งฟรี)', t)]
            if titles:
                product = titles[0]
                break
            parent = parents.get(parent, root)
    if product and not exact('ไม่มีสินค้า'):
        return dict(base, state='product', product=product)
    if prices:
        return dict(base, state='unknown')
    if len(exact('ไม่มีสินค้า')) == 1:
        return dict(base, state='empty')
    return dict(base, state='unknown')


def _notify(progress, message):
    if progress:
        progress(message)


def wait_import(device, timeout=35):
    deadline = time.monotonic() + timeout
    previous, stable = None, 0
    last = {'state': 'unknown'}
    keyboard_dismissed = False
    while time.monotonic() < deadline:
        xml, nodes = device.snapshot()
        keyboard = any(n.get('resource-id') == 'android:id/input_method_nav_back' for n in nodes)
        importer = any(n.get('text') == 'กรอกลิงก์สินค้า' and n.get('package') == device.package for n in nodes)
        if keyboard and importer and not keyboard_dismissed:
            # Shopee can refocus the emptied link field after Import. This hides
            # the entire result list behind the IME; do not call it empty/failed.
            keyboard_dismissed = True
            device.hide_keyboard()  # One Back only after fresh IME proof.
            previous, stable = None, 0
            continue
        last = inspect_import(xml)
        signature = tuple(sorted(last.items()))
        stable = stable + 1 if signature == previous else 1
        previous = signature
        if last['state'] in ('invalid', 'excluded'):
            raise ProductUnavailable('สินค้าถูกยกเว้นหรือลิงก์ไม่ถูกต้อง • ข้ามคลิปนี้ ไม่โพสต์โดยไม่มีสินค้า')
        if last['state'] == 'ambiguous':
            raise ReviewRequired('SHOPEE_PRODUCT_REVIEW • พบหลายสินค้า • ไม่เลือกสินค้าทดแทน')
        if last['state'] == 'product' and not last['busy'] and stable >= 2:
            return last
        time.sleep(.4)
    # Only a positively identified, stable EMPTY form can authorize re-import.
    if stable >= 2 and last['state'] == 'empty' and not last['busy']:
        return last
    raise ReviewRequired('SHOPEE_PRODUCT_REVIEW • หน้านำเข้ายังโหลดหรืออ่านผลไม่ชัด • ยังไม่แนบหรือโพสต์ซ้ำ')


def import_product(device, url, progress=None):
    """Three same-link attempts at most; never overwrite another link/card."""
    for attempt in range(1, MAX_IMPORT_ATTEMPTS+1):
        xml, _ = device.snapshot()
        state = inspect_import(xml)
        if state['state'] == 'product':
            # A late result from our previous attempt is consumed, not reimported.
            if attempt == 1:
                raise ReviewRequired('หน้านำเข้ามีสินค้าเดิมอยู่ • ไม่แทนที่หรือเลือกอัตโนมัติ')
            return wait_import(device)
        if state['state'] != 'empty' or state['busy']:
            raise ReviewRequired('SHOPEE_PRODUCT_REVIEW • ยังไม่ยืนยันหน้าว่างของคำขอนี้ • ไม่ใส่ลิงก์ซ้ำ')
        editor = state['editor'].strip()
        if editor and editor != url and not editor.startswith('รองรับเฉพาะลิงก์สินค้าใน Shopee'):
            raise ReviewRequired('ลิงก์ในหน้าจอเปลี่ยนจากงานนี้ • ไม่เขียนทับ')
        _notify(progress, f'กำลังนำเข้าลิงก์สินค้า • รอบ {attempt}/{MAX_IMPORT_ATTEMPTS}')
        device.set_text(url, **{'class': 'android.widget.EditText', 'text': state['editor']})
        device.hide_keyboard()
        # Re-observe after editing: a delayed previous response must win over retry.
        xml, _ = device.snapshot()
        prepared = inspect_import(xml)
        if prepared['state'] == 'product' and attempt > 1:
            return wait_import(device)
        if prepared['state'] != 'empty' or prepared['busy'] or prepared['editor'].strip() != url:
            raise ReviewRequired('หน้านำเข้าเปลี่ยนก่อนกด • เก็บคำขอเดิม ไม่ส่งซ้ำ')
        try:
            device.tap(text='นำเข้า')
        except ReviewRequired:
            # Private Import ACK may be lost; inspect result before another action.
            device.verify()
        result = wait_import(device)
        if result['state'] == 'product':
            return result
        _notify(progress, 'ยังไม่มีสินค้าจากลิงก์เดิม • ตรวจหน้าว่างก่อนนำเข้าใหม่')
    raise ProductUnavailable('นำเข้าลิงก์เดิมครบ 3 รอบแล้วยังไม่มีสินค้า • ข้ามคลิปนี้ ไม่โพสต์โดยไม่มีสินค้า')


def attach_imported(device, imported, caption, progress=None, timeout=20):
    product = imported['product']
    for attempt in range(2):
        xml, _ = device.snapshot()
        current = inspect_import(xml)
        if current.get('product') != product or current.get('busy') or current['state'] != 'product':
            raise ReviewRequired('สินค้าก่อนแนบเปลี่ยนไป • ไม่เลือกสินค้าทดแทน')
        if current['add'] == 'เพิ่ม':
            device.tap(text='เลือกทั้งหมด')
            device.wait(text='เพิ่ม(1)')
            xml, _ = device.snapshot()
            selected = inspect_import(xml)
            if selected.get('product') != product or selected.get('busy') or selected.get('add') != 'เพิ่ม(1)':
                raise ReviewRequired('สินค้าหรือจำนวนเปลี่ยนหลังเลือก • ยังไม่กดแนบ')
        elif current['add'] != 'เพิ่ม(1)':
            raise ReviewRequired('จำนวนสินค้าที่เลือกไม่ใช่หนึ่งรายการ • ยังไม่แนบ')
        _notify(progress, 'กำลังแนบสินค้าหนึ่งรายการ' + (' • ลองแนบเดิมอีกครั้ง' if attempt else ''))
        try:
            device.tap(text='เพิ่ม(1)')
        except ReviewRequired:
            device.verify()
        deadline, previous, stable = time.monotonic()+timeout, None, 0
        while time.monotonic() < deadline:
            xml, nodes = device.snapshot()
            own = [n for n in nodes if n.get('package') == device.package and n.get('visible-to-user', 'true') == 'true']
            titles = [n.get('text') for n in own if n.get('resource-id') == P+'tv_product_title']
            captions = [n.get('text') for n in own if n.get('resource-id') == P+'et_caption']
            if titles:
                if titles != [product] or captions != [caption]:
                    raise ReviewRequired('สินค้าหรือแคปชันหลังแนบไม่ตรงกับงาน • ยังไม่โพสต์')
                return product
            state = inspect_import(xml)
            signature = tuple(sorted(state.items()))
            stable = stable + 1 if signature == previous else 1
            previous = signature
            time.sleep(.4)
        if not (stable >= 2 and state.get('product') == product and
                state.get('add') == 'เพิ่ม(1)' and not state.get('busy')):
            raise ReviewRequired('ยังยืนยันผลแนบสินค้าไม่ได้ • ไม่กดเพิ่มหรือโพสต์ซ้ำในหน้าที่ไม่ชัด')
    raise ReviewRequired('แนบสินค้าสองครั้งแล้วยังไม่กลับหน้าส่ง • เก็บคลิปไว้ ยังไม่โพสต์')
