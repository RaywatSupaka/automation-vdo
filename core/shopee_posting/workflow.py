"""Observed Shopee TH UI adapter. Unknown layout pauses; no blind Retry/Post."""
import re
import time
import xml.etree.ElementTree as ET
from core.shopee_posting.device import ReviewRequired
from core.shopee_posting.publish import P, publish_current
from core.shopee_posting.options import requested_options, option_summary, proof_matches_options
from core.shopee_posting.settings import apply_options, ensure_toggle
from core.shopee_posting.result import await_upload
from core.shopee_posting.contract import flow_version
from core.shopee_posting.product_attachment import import_product, attach_imported

S = 'com.shopee.th:id/'


def video_feed_visible(device):
    _, nodes = device.snapshot()
    own = [n for n in nodes if n.get('package') == device.package
           and n.get('enabled') == 'true' and n.get('visible-to-user', 'true') == 'true']
    return (sum(n.get('content-desc') == 'click me page icon' for n in own) == 1
            and sum(n.get('content-desc') == 'click top right create icon' for n in own) == 1
            and not any(n.get('resource-id') == P+'et_caption' for n in own))


def video_feed_account(device):
    # The fullscreen Video feed has no main Me tab. Enter only its OWN profile
    # button, never the current video's creator avatar or a guessed username.
    device.tap(**{'content-desc': 'click me page icon'})
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        _, nodes = device.snapshot()
        names = [n.get('text', '')[len('ชื่อผู้ใช้: '):].strip() for n in nodes
                 if n.get('package') == device.package and n.get('text', '').startswith('ชื่อผู้ใช้: ')]
        if len(names) == 1 and names[0]:
            device.tap(**{'content-desc': 'click to get back'})
            device.wait(**{'content-desc': 'click me page icon'})
            return names[0]
        if len(names) > 1:
            break
        time.sleep(.3)
    raise ReviewRequired('ยังอ่านบัญชีจากโปรไฟล์วิดีโอของฉันไม่ได้ • ยังไม่โพสต์')


def account_on_home(device):
    device.open()
    if video_feed_visible(device):
        return video_feed_account(device)
    device.wait(**{'content-desc': 'tab_bar_button_me'})
    device.tap(**{'content-desc': 'tab_bar_button_me'})
    account = device.profile_account()
    if not account:
        raise ReviewRequired('กรุณาเข้าสู่ระบบ Shopee บนมือถือก่อน')
    return account


def own_profile_name(nodes):
    own = [n for n in nodes if n.get('package') == 'com.shopee.th'
           and n.get('enabled') == 'true' and n.get('visible-to-user', 'true') == 'true']
    if not any(n.get('content-desc') == 'user name of me' for n in own):
        return None
    names = [n.get('text', '')[len('ชื่อผู้ใช้: '):].strip() for n in own
             if n.get('text', '').startswith('ชื่อผู้ใช้: ')]
    return names[0] if len(names) == 1 and names[0] else None


def prepare_post_page(device, account):
    """Navigate only to create-ready feed, never open a profile's video tile."""
    device.open()  # The previous confirmed clip may have closed only Shopee.
    if video_feed_visible(device):
        return
    _, nodes = device.snapshot()
    own = [n for n in nodes if n.get('package') == device.package
           and n.get('enabled') == 'true' and n.get('visible-to-user', 'true') == 'true']
    if any(n.get('resource-id') == P+'et_caption' for n in own):
        raise ReviewRequired('ยังมีหน้าโพสต์เดิมค้างอยู่ • ไม่ทิ้งร่างหรือกดโพสต์ซ้ำ')
    # Do not navigate to/read a profile. Only veto a contradictory own-account
    # label if it is already visible in this same navigation observation.
    if any(n.get('resource-id') in {'meCircleView','meCircleDisplayName'} for n in own):
        names = {n.get('text', '').strip() for n in own
                 if n.get('resource-id') == 'labelUserName' and n.get('text', '').strip()}
        if names and names != {account}:
            raise ReviewRequired('บัญชีที่เห็นบนมือถือไม่ตรงกับคิวที่ยืนยัน • ยังไม่ส่งโพสต์')
    profile = own_profile_name(nodes)
    if profile:
        if profile != account:
            raise ReviewRequired('บัญชีบนหน้าจอไม่ตรงกับคิว • หยุดก่อนส่งผิดบัญชี')
        device.tap(**{'content-desc': 'click to get back'})
    elif sum(n.get('content-desc') == 'tab_bar_button_video_and_live' for n in own) == 1:
        device.tap(**{'content-desc': 'tab_bar_button_video_and_live'})
    else:
        raise ReviewRequired('ยังไม่พบหน้าสร้างวิดีโอ • เปิดหน้า Live & Video ก่อนทำต่อ ไม่เปิดโพสต์เก่า')
    device.wait(**{'content-desc': 'click me page icon'})
    device.wait(**{'content-desc': 'click top right create icon'})


def prepare_queue_account(device, account):
    device.open()
    _, nodes = device.snapshot()
    own = [n for n in nodes if n.get('package') == device.package
           and n.get('enabled') == 'true' and n.get('visible-to-user', 'true') == 'true']
    if any(n.get('resource-id') == P+'et_caption' for n in own):
        raise ReviewRequired('ยังมีร่างโพสต์อยู่ • ไม่ปิดร่างหรือส่งซ้ำอัตโนมัติ')
    # Recover the old baseline reader's known own-video caption panel by leaving
    # it once. This does not open/read any old video or compare its caption.
    if (sum(n.get('content-desc') == 'close the comment panels' for n in own) == 1
            and any(n.get('content-desc') == 'meaning this is the creator' for n in own)):
        return_to_feed(device, account)
        # return_to_feed already read this exact own-profile account on the way
        # out. Do not open the profile again merely to read it a second time.
        observed = account
    else:
        observed = own_profile_name(nodes) or account_on_home(device)
    if observed != account:
        raise ReviewRequired('บัญชีบนมือถือไม่ตรงกับคิวที่ยืนยัน • ยังไม่โพสต์')
    prepare_post_page(device, account)


def close_completed_post(device, store, row_id, account, run_id):
    """Close only Shopee after this worker's durable native success; never reset a send."""
    state = store.read()
    row = next(r for r in state['items'] if r['id'] == row_id)
    if (row.get('run_contract') or {}).get('close_after_publish') is not True:
        return False  # Historical queues retain their captured navigation policy.
    receipt, intent = row.get('receipt') or {}, row.get('publish_intent') or {}
    current = state.get('posting_run') or {}
    if (current.get('id') != run_id or current.get('current_id') != row_id
            or row.get('posting_run_id') != run_id or row['phase'] != 'published'
            or receipt.get('upload_confirmed') is not True
            or receipt.get('source') != 'live_native_upload_banner'
            or not intent.get('id') or receipt.get('intent_id') != intent['id']
            or receipt.get('account') != account or intent.get('device_id') != device.identity):
        raise ReviewRequired('ยังไม่มีผลสำเร็จของคลิปนี้ • ไม่ปิด Shopee หรือเริ่มคลิปถัดไป')
    store.queue_account(row_id, account, device.identity)
    _, nodes = device.snapshot()
    own = [n for n in nodes if n.get('package') == device.package
           and n.get('enabled') == 'true' and n.get('visible-to-user', 'true') == 'true']
    editing = {P+'et_caption', S+'ll_gallery_entrance', S+'tv_pick_title', S+'tv_compress'}
    feed = all(sum(n.get('content-desc') == name for n in own) == 1
               for name in ('click me page icon', 'click top right create icon'))
    home = all(sum(n.get('content-desc') == name for n in own) == 1
               for name in ('tab_bar_button_home', 'tab_bar_button_video_and_live'))
    profile = own_profile_name(nodes)
    if (any(n.get('resource-id') in editing for n in own)
            or profile and profile != account
            or not (feed or home or profile == account)):
        raise ReviewRequired('โพสต์สำเร็จแล้ว แต่หน้าปัจจุบันไม่ปลอดภัยต่อการปิด • เก็บร่างและพักคลิปถัดไป')
    device.verify()  # Recheck identity/cancellation immediately before close.
    result = device.adb.shell('am', 'force-stop', device.package, timeout=10)
    if result.returncode:
        raise ReviewRequired('โพสต์สำเร็จแล้ว แต่ยืนยันการปิด Shopee ไม่ได้ • ไม่ปิดซ้ำหรือส่งซ้ำ')
    device._shopee_closed = True
    return True


def restart_before_first_post(device, store, row_id, account, run_id, after_skip=False):
    """New queues start from a closed Shopee, not the previous in-memory page.

    Later clips already close after their exact native success. Do not clear app
    data, dismiss every recent app, or use lifecycle reset to replay a Send.
    """
    state = store.read()
    row = next(r for r in state['items'] if r['id'] == row_id)
    if (row.get('run_contract') or {}).get('close_before_first_post') is not True:
        return False

    def guard():
        current_state = store.read()
        current = current_state.get('posting_run') or {}
        target = next(r for r in current_state['items'] if r['id'] == row_id)
        contract = target.get('run_contract') or {}
        if (device.package != 'com.shopee.th'
                or current.get('id') != run_id or current.get('status') != 'running'
                or current.get('current_id') != row_id or (not after_skip and current.get('ids', [])[:1] != [row_id])
                or current.get('account') != account or target.get('posting_run_id') != run_id
                or target['phase'] != ('skipped' if after_skip else 'prepared') or target.get('publish_intent')
                or after_skip and (not target.get('skip_reason') or target.get('receipt') or target.get('published_at')
                                   or contract.get('skip_unavailable_products') is not True)
                or contract.get('close_before_first_post') is not True
                or contract.get('account') != account or contract.get('device_id') != device.identity):
            raise ReviewRequired('คิวไม่อยู่ในขั้นเริ่มโพสต์ใหม่ • ไม่ปิดแอปหรือส่งซ้ำ')
        for other in current_state['items']:
            intent = other.get('publish_intent') or {}
            if intent and other['phase'] != 'published' and intent.get('device_id') in (None, '', device.identity):
                raise ReviewRequired('มือถือมีโพสต์เดิมที่ยังไม่ยืนยันผล • ไม่ปิด Shopee หรือเริ่มส่งใหม่')

    guard()
    device.verify()
    info = device.ui.info
    if info.get('screenOn') is not True:
        raise ReviewRequired('ปลดล็อกมือถือก่อนเปิด Shopee ใหม่ • ยังไม่ปิดแอปหรือโพสต์')
    if after_skip and info.get('currentPackageName') != device.package:
        raise ReviewRequired('ข้ามสินค้าแล้ว แต่มือถือเปลี่ยนหน้า • ไม่แย่งแอปอื่นเพื่อโพสต์ต่อ')
    if info.get('currentPackageName') == device.package:
        _, nodes = device.snapshot()
        if after_skip and not any(n.get('package') == device.package and n.get('text') == 'กรอกลิงก์สินค้า' for n in nodes):
            raise ReviewRequired('ข้ามสินค้าแล้ว แต่ไม่ใช่หน้านำเข้าที่ตรวจไว้ • ไม่ปิดร่างอื่น')
        uploading = {'กำลังอัปโหลด', 'กำลังอัปโหลด...', 'กำลังอัปโหลด…', 'uploading', 'uploading...', 'uploading…'}
        if any(n.get('package') == device.package and n.get('visible-to-user', 'true') == 'true'
               and n.get('resource-id') not in {P+'et_caption', P+'tv_product_title'}
               and n.get('text', '').strip().casefold() in uploading for n in nodes):
            raise ReviewRequired('Shopee ยังแสดงว่ากำลังอัปโหลด • ไม่ปิดแอปกลางการส่ง')
    device.verify()
    guard()  # Recheck ownership after potentially slow phone reads.
    result = device.adb.shell('am', 'force-stop', device.package, timeout=10)
    if result.returncode:
        raise ReviewRequired('ยังยืนยันการปิด Shopee ก่อนเริ่มไม่ได้ • ไม่ปิดซ้ำหรือเริ่มโพสต์')
    device._shopee_closed = True
    device.verify()
    # Accessibility may briefly still report Shopee after force-stop. Explicitly
    # launch here; ordinary open() intentionally avoids relaunching a visible app.
    device.ui.app_start(device.package)
    device.foreground(timeout=20, stable_samples=3)
    device._shopee_closed = False
    return True


def screenshot_toggle(device, name, desired):
    return ensure_toggle(device, name, desired)


def return_to_feed(device, account):
    device.tap(**{'content-desc': 'close the comment panels'})
    # Closing the panel animates. Immediate Back was consumed by that animation
    # on the observed Android16 build instead of returning to the profile.
    stable = 0
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        _, nodes = device.snapshot()
        closed = not any(n.get('content-desc') == 'close the comment panels' for n in nodes)
        player = any(n.get('content-desc') == 'video caption content' for n in nodes)
        stable = stable + 1 if closed and player else 0
        if stable >= 3:
            break
        time.sleep(.3)
    else:
        raise ReviewRequired('แผงคำอธิบายยังปิดไม่เสร็จ ยังไม่เปิดคลิปใหม่')
    device.foreground(); device.ui.press('back')
    device.wait(text='ชื่อผู้ใช้: ' + account)
    device.tap(**{'content-desc': 'click to get back'})
    device.wait(**{'content-desc': 'click me page icon'})


def latest_baseline(device, account, caption, folder):
    """Observed own-profile flow; ambiguous/empty profiles need manual review."""
    device.wait(**{'content-desc': 'click me page icon'})
    device.tap(**{'content-desc': 'click me page icon'})
    device.wait(text='ชื่อผู้ใช้: ' + account)
    device.wait(**{'content-desc': 'click video 0'})
    device.tap(**{'content-desc': 'click video 0'})
    device.wait(**{'content-desc': 'video caption content'})
    device.tap(**{'content-desc': 'video caption content'})
    device.wait(**{'content-desc': 'meaning this is the creator'})
    _, nodes = device.snapshot()
    captions = [n.get('text', '')[:-len('  ซ่อน')] for n in nodes
                if n.get('text', '').endswith('  ซ่อน')]
    if len(captions) != 1 or not captions[0].strip():
        raise ReviewRequired('ยังอ่านแคปชันเต็มของโพสต์ล่าสุดเพื่อแยกผลใหม่ไม่ได้')
    device.capture(folder, 'latest_before')
    if captions[0] == caption:
        raise ReviewRequired('แคปชันตรงโพสต์ล่าสุด แยกผลใหม่ไม่ได้ กรุณาแก้แคปชันก่อนเริ่ม')
    proof = {'account': account, 'latest_caption': captions[0], 'checked_at': time.time(),
             'screenshot': str(folder/'latest_before.png')}
    return_to_feed(device, account)
    return proof


def choose_video(device, row):
    device.wait(**{'resource-id': S+'lyt_pick_title'})
    device.tap(**{'resource-id': S+'lyt_pick_title'})
    device.wait(**{'resource-id': S+'rv_folder'})
    device.album(row['transfer']['album'])
    title = device.wait(**{'resource-id': S+'tv_pick_title'})['text']
    prefix = title.removesuffix('...').removesuffix('…')
    if not prefix or not row['transfer']['album'].startswith(prefix):
        raise ReviewRequired('ยังไม่ได้เลือกอัลบั้มของงานนี้')
    xml, _ = device.snapshot()
    root = ET.fromstring(xml)
    parents = {child: parent for parent in root.iter() for child in parent}
    durations = [n for n in root.iter('node') if n.get('resource-id') == S+'tv_duration']
    checks = [n for n in root.iter('node') if n.get('resource-id') == S+'ll_check']
    # Only a saved legacy transfer receipt can account for an old cover tile.
    # A cover in the desktop library is not a file transferred to this album.
    has_legacy_cover = bool(row['transfer'].get('files', {}).get('cover'))
    permitted_counts = {1, 2} if has_legacy_cover else {1}
    if len(durations) != 1 or len(checks) not in permitted_counts:
        raise ReviewRequired('อัลบั้มมีไฟล์ไม่ตรงชุดงาน ไม่เลือกจากลำดับภาพ')
    pieces = durations[0].get('text', '').split(':')
    if len(pieces) != 2 or not all(p.isdigit() for p in pieces):
        raise ReviewRequired('อ่านความยาวคลิปในคลังภาพไม่ได้')
    if abs(int(pieces[0])*60+int(pieces[1])-row['media']['duration']) > 1.1:
        raise ReviewRequired('ความยาวคลิปในคลังภาพไม่ตรงกับ Final')
    parent = parents[durations[0]]
    while parent is not root and not any(n.get('resource-id') == S+'ll_check' for n in parent.iter('node')):
        parent = parents[parent]
    targets = [n for n in parent.iter('node') if n.get('resource-id') == S+'ll_check']
    if len(targets) != 1:
        raise ReviewRequired('แยกปุ่มเลือกวิดีโอจากปกไม่ได้')
    device.tap(**{'resource-id': S+'ll_check', 'bounds': targets[0].get('bounds')})
    device.wait(**{'resource-id': S+'tv_pick_top_next', 'text': 'ถัดไป (1)'})
    device.tap(**{'resource-id': S+'tv_pick_top_next', 'text': 'ถัดไป (1)'})


def product_link_target(nodes, package):
    """Bind the link icon to the actual picker, never the composer's same label."""
    nodes = [n for n in nodes if n.get('package') == package
             and n.get('enabled') == 'true' and n.get('visible-to-user', 'true') == 'true']
    if any(n.get('resource-id') == P+'et_caption' for n in nodes):
        return None
    titles = [n for n in nodes if n.get('text') == 'เพิ่มสินค้า'
              and not n.get('resource-id') and n.get('class') == 'android.widget.TextView']
    back = [n for n in nodes if n.get('content-desc') == 'click to get back']
    search = [n for n in nodes if n.get('class') == 'android.widget.EditText'
              and n.get('text') == 'ค้นหาสินค้า']
    if len(titles) != 1 or len(back) != 1 or len(search) != 1:
        return None
    coords = list(map(int, re.findall(r'\d+', titles[0].get('bounds', ''))))
    if len(coords) != 4:
        return None
    icons = []
    for n in nodes:
        if n.get('class') != 'android.widget.ImageView' or n is back[0]:
            continue
        b = list(map(int, re.findall(r'\d+', n.get('bounds',''))))
        if len(b) == 4 and b[0] >= coords[2] and abs((b[1]+b[3])-(coords[1]+coords[3])) < 16:
            icons.append(n)
    return icons[0] if len(icons) == 1 else None


class ProductPickerNotReady(ReviewRequired):
    pass


def wait_product_link(device, timeout=12):
    deadline, previous = time.monotonic() + timeout, None
    while time.monotonic() < deadline:
        _, nodes = device.snapshot()
        icon = product_link_target(nodes, device.package)
        signature = (icon['class'], icon['bounds']) if icon else None
        if signature and signature == previous:
            return icon
        previous = signature
        time.sleep(.3)
    raise ProductPickerNotReady('หน้าเลือกสินค้ายังไม่พร้อม • ยังไม่ใส่ลิงก์หรือกดโพสต์ ตรวจหน้ามือถือก่อนทำต่อ')


def retry_product_navigation(device, caption):
    """One navigation-only retry after three unchanged unsent composer reads.

    Samsung/Shopee can consume the first tap after setText without navigating.
    This guard is deliberately not reusable for Import, switches or Post.
    """
    previous = None
    for _ in range(3):
        _, nodes = device.snapshot()
        if product_link_target(nodes, device.package):
            return wait_product_link(device)
        own = [n for n in nodes if n.get('package') == device.package
               and n.get('enabled') == 'true' and n.get('visible-to-user', 'true') == 'true']
        captions = [n for n in own if n.get('resource-id') == P+'et_caption']
        buttons = [n for n in own if n.get('resource-id') == P+'ll_add_product_symbol']
        post = [n for n in own if n.get('resource-id') == P+'btn_post' and n.get('text') == 'โพสต์']
        blocked = any(n.get('resource-id') == 'android:id/input_method_nav_back'
                      or n.get('resource-id') == P+'tv_product_title'
                      or n.get('resource-id', '').startswith(S+'buttonDefault')
                      or n.get('resource-id') == S+'tv_no_save' for n in nodes)
        if (blocked or len(captions) != 1 or captions[0].get('text') != caption
                or len(buttons) != 1 or len(post) != 1):
            raise ProductPickerNotReady('หน้าเดิมเปลี่ยนหรือยืนยันไม่ได้ • ยังไม่แตะเพิ่มสินค้าอีกครั้ง')
        signature = (captions[0].get('bounds'), buttons[0].get('bounds'), post[0].get('bounds'))
        if previous is not None and signature != previous:
            raise ProductPickerNotReady('หน้าเพิ่มสินค้ายังขยับ • ยังไม่แตะซ้ำ')
        previous = signature
        time.sleep(.3)
    device.tap(**{'resource-id': P+'ll_add_product_symbol'})
    return wait_product_link(device)


def add_product(device, url, progress=None):
    caption = device.find(**{'resource-id': P+'et_caption'}).get('text')
    device.tap(**{'resource-id': P+'ll_add_product_symbol'})
    try:
        icon = wait_product_link(device)
    except ProductPickerNotReady:
        icon = retry_product_navigation(device, caption)
    device.tap(**{'class': icon['class'], 'bounds': icon['bounds']})
    device.wait(text='กรอกลิงก์สินค้า')
    imported = import_product(device, url, progress)
    return attach_imported(device, imported, caption, progress)


def verify_result(device, store, row_id, account, product, folder):
    if await_upload(device, store, row_id):
        return  # Native upload success finishes the job; no second profile tour.
    row = next(r for r in store.read()['items'] if r['id'] == row_id)
    intent = row.get('publish_intent', {})
    if intent.get('posting_flow_version') == 2:
        raise ReviewRequired('ยังไม่ได้รับคำยืนยันอัปโหลดจาก Shopee • ไม่เปิดโพสต์เก่าและไม่ส่งซ้ำ')
    options = requested_options({'post_options': intent.get('post_options'), 'publish_intent': intent})
    observed = intent.get('observed_options') or {}
    missing_ai = 'ai_label' in observed.get('unavailable_options',[])
    if missing_ai and not proof_matches_options(observed, options):
        raise ReviewRequired('หลักฐานการข้ามป้าย AI ไม่ตรงกับรอบส่ง • ตรวจโพสต์เดิม ไม่ส่งซ้ำ')
    baseline = intent.get('latest_baseline', {})
    if baseline.get('account') != account or not baseline.get('latest_caption') or baseline['latest_caption'] == row['caption']:
        raise ReviewRequired('ยังแยกผลโพสต์ใหม่จากโพสต์ล่าสุดก่อนส่งไม่ได้')
    # Observe only. A timeout cannot return this item to the start of the queue.
    device.wait(timeout=60, **{'content-desc': 'click me page icon'})
    device.tap(**{'content-desc': 'click me page icon'})
    device.wait(text='ชื่อผู้ใช้: ' + account)
    device.capture(folder, 'profile_after')
    device.wait(**{'content-desc': 'click video 0'})
    device.tap(**{'content-desc': 'click video 0'})
    device.wait(text=product)
    if options['ai_label'] and not missing_ai:
        device.wait(text='ครีเอเตอร์เพิ่มป้ายกำกับ AI')
    device.tap(**{'content-desc': 'video caption content'})
    device.wait(text=row['caption'] + '  ซ่อน')
    device.find(**{'content-desc': 'meaning this is the creator'})
    device.find(text=product)
    if not options['ai_label'] and not missing_ai:
        # Absence is checked only on the verified own result, twice, never on loading UI.
        for _ in range(2):
            _, nodes = device.snapshot()
            if any(n.get('text') == 'ครีเอเตอร์เพิ่มป้ายกำกับ AI' for n in nodes):
                raise ReviewRequired('ผลโพสต์มีป้าย AI ไม่ตรงค่าที่เลือก ต้องตรวจโพสต์เดิม')
            time.sleep(.3)
    device.capture(folder, 'verified_post')
    store.transition(row_id, {'processing'}, 'published', published_at=time.time(),
                     message='ตรวจพบโพสต์ใหม่ • บัญชี แคปชัน และสินค้าตรงกัน'
                     + (' • หน้าส่งไม่มีปุ่ม AI ข้ามตามที่อนุญาต' if missing_ai else ' • ป้าย AI ตรงกัน'),
                     receipt={'account': account, 'caption_verified': True, 'product_verified': True,
                              'ai_label': None if missing_ai else options['ai_label'], 'new_latest_caption_verified': True,
                              'reuse_verified_before_post_only': True,
                              'screenshot': str(folder/'verified_post.png')})
    # Navigation after durable success is allowed to fail without un-publishing.
    return_to_feed(device, account)


def run(device, store, row_id, account, folder):
    row = next(r for r in store.read()['items'] if r['id'] == row_id)
    if row['phase'] != 'prepared':
        raise ReviewRequired('ยังไม่ได้เตรียมไฟล์ก่อนเข้า Shopee')
    if flow_version(row) == 2:
        store.queue_account(row_id, account, device.identity)
        store.progress(row_id, 'prepare_post', 'เตรียมโพสต์คลิปถัดไปในคิว • ไม่ตรวจโพสต์เก่า')
        prepare_post_page(device, account)
    else:
        if account_on_home(device) != account:
            raise ReviewRequired('บัญชีบนมือถือเปลี่ยนไป หยุดก่อนโพสต์ผิดบัญชี')
        if not video_feed_visible(device):
            device.tap(**{'content-desc': 'tab_bar_button_video_and_live'})
        store.progress(row_id, 'baseline', 'กำลังตรวจโพสต์ล่าสุดของบัญชี เพื่อแยกผลโพสต์ใหม่')
        baseline = latest_baseline(device, account, row['caption'], folder)
        store.transition(row_id, {'prepared'}, 'prepared', latest_baseline=baseline)
    device.wait(**{'content-desc': 'click top right create icon'})
    device.tap(**{'content-desc': 'click top right create icon'})
    device.wait(**{'resource-id': S+'ll_gallery_entrance'})
    device.tap(**{'resource-id': S+'ll_gallery_entrance'})
    store.transition(row_id, {'prepared'}, 'editing', message='กำลังเลือกคลิปของงานนี้ใน Shopee')
    choose_video(device, row)
    device.wait(timeout=60, **{'resource-id': S+'tv_compress'})
    device.tap(**{'resource-id': S+'tv_compress'})
    device.wait(timeout=60, **{'resource-id': P+'et_caption'})
    store.progress(row_id, 'caption', 'กำลังใส่และตรวจแคปชัน')
    device.set_text(row['caption'], **{'resource-id': P+'et_caption'})
    device.hide_keyboard()
    # User chose Shopee's automatic cover. Do not open a cover picker/upload.
    store.progress(row_id, 'product', 'กำลังนำเข้าลิงก์และแนบสินค้าของคลิปนี้')
    try:
        product = add_product(device, row['product_url'],
                              lambda message: store.progress(row_id, 'product', message))
    except ReviewRequired:
        # Failure evidence stays with this unsent row; never navigate to obtain it.
        try:
            device.capture(folder, f'product_failure_{int(time.time()*1000)}')
        except Exception:
            pass
        raise
    store.transition(row_id, {'editing'}, 'settings', message='กำลังตรวจสวิตช์จริงบนมือถือ')
    observed = apply_options(device, requested_options(row))
    store.transition(row_id, {'settings'}, 'settings', observed_options=observed,
                     message='ตั้งค่าตามที่อนุญาตแล้ว: ' + option_summary(requested_options(row))
                     + (' • หน้านี้ไม่มีปุ่ม AI ไม่ได้ตั้งป้าย' if 'ai_label' in observed.get('unavailable_options',[]) else '')
                     + ' • ต่อไปตรวจขั้นสุดท้าย')
    publish_current(device, store, row_id, account, product, folder)
    try:
        verify_result(device, store, row_id, account, product, folder)
    except Exception as exc:
        current = next(r for r in store.read()['items'] if r['id'] == row_id)
        if current['phase'] == 'published':
            raise ReviewRequired('โพสต์สำเร็จแล้ว แต่กลับหน้าหลักไม่ได้ พักคลิปถัดไป') from exc
        store.transition(row_id, {'processing'}, 'unknown', message='กดโพสต์แล้วแต่ยังยืนยันผลไม่ได้ • ตรวจโพสต์เดิม ห้ามส่งซ้ำ')
        raise
