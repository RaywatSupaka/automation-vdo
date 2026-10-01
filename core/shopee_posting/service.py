"""Library → durable Shopee drafts. Phone actions never run on the Tk thread."""
import threading
import time
from pathlib import Path

from core.shopee_posting.store import PostingStore, file_hash, product_url
from core.shopee_posting.device import ShopeeDevice, DeviceUnavailable
from core.workspace_cleaner import FinalVideoValidator
from core.shopee_posting.media import transfer
from core.shopee_posting.workflow import account_on_home, prepare_queue_account, close_completed_post, restart_before_first_post, run
from core.shopee_posting.options import DEFAULT_OPTIONS, validate_options, requested_options
from core.shopee_posting.progress import selection_ids, start_run, snapshot
from core.shopee_posting.result import reconcile_saved_upload
from core.shopee_posting.contract import account_check_mode
from core.shopee_posting.restart import restartable, reset_preparation
from core.shopee_posting.product_attachment import ProductUnavailable


class ShopeePosting:
    def __init__(self, root, library, wifi, ffmpeg_path='', *, validator=None):
        self.root, self.library, self.wifi = Path(root), library, wifi
        self.store = PostingStore(root)
        self.validator = validator or FinalVideoValidator(ffmpeg_path)
        self._lock = threading.Lock()
        self._busy = False
        self._message = ''
        self._pause = threading.Event()
        self.store.recover()

    def candidates(self):
        rows = []
        for item in self.library.list_items():
            if item.get('content_kind', item.get('kind')) != 'product':
                continue
            try:
                detail = self.library.item_detail(item['item_id'], preloaded_item=item)
                url = product_url(detail.get('affiliate_link'))
                rows.append({k: detail.get(k, '') for k in ('item_id', 'title', 'description', 'hashtags', 'cover_path')} | {'product_url': url})
            except (ValueError, OSError):
                continue
        return rows

    def detail(self, item_id):
        item = self.library.item_detail(item_id)
        if item.get('content_kind', item.get('kind')) != 'product':
            raise ValueError('เลือกเฉพาะคลิปสินค้า Final จากคลังวิดีโอ')
        video = Path(item['path']).resolve()
        workspace = (self.root / 'workspace').resolve()
        if workspace not in video.parents or not video.is_file():
            raise ValueError('ไฟล์ Final ไม่อยู่ในคลังวิดีโอ')
        return dict(item_id=item['item_id'], title=item['title'], video_path=str(video),
                    product_url=product_url(item.get('affiliate_link')),
                    caption=str(item['title']).strip())

    def state(self):
        state = self.store.read()
        state['posting_run'] = snapshot(state.get('posting_run'))
        state['defaults'] = validate_options(state.get('defaults', DEFAULT_OPTIONS))
        for row in state['items']:
            if row['phase'] in self.store.editable and not row.get('publish_intent'):
                row['post_options'] = requested_options(row)  # Display only; no historical rewrite.
        state['restartable_ids'] = [row['id'] for row in state['items'] if restartable(row)]
        return dict(state, busy=self._busy, paused=self._pause.is_set(), message=self._message,
                    auto_available=True, capability_message='Shopee TH • ADB Wi-Fi • ส่งเฉพาะวิดีโอ • ตรวจตัวเลือกจริงก่อนโพสต์')

    def action(self, action, payload=None):
        payload = payload or {}
        if action == 'shopee_post_status':
            return {'ok': True, 'posting': self.state()}
        if action == 'shopee_post_library':
            return {'ok': True, 'items': self.candidates(), 'posting': self.state()}
        if action == 'shopee_post_add':
            ids = payload.get('item_ids')
            if not isinstance(ids, list) or not 1 <= len(ids) <= 30 or any(not isinstance(x, str) for x in ids):
                raise ValueError('เลือกคลิปสินค้า 1–30 คลิป')
            self.store.add([self.detail(x) for x in dict.fromkeys(ids)])
        elif action == 'shopee_post_edit':
            with self._lock:
                if self._busy:
                    raise ValueError('กำลังทำงานกับมือถือ กรุณาพักคิวก่อนแก้ข้อมูล')
                fields = {k: payload[k] for k in ('caption', 'product_url', 'removed', 'post_options') if k in payload}
                self.store.edit(str(payload.get('id')), payload.get('revision'), **fields)
        elif action in {'shopee_post_defaults', 'shopee_post_apply_options'}:
            with self._lock:
                if self._busy:
                    raise ValueError('กำลังทำงานกับมือถือ กรุณาพักคิวก่อนแก้ตัวเลือก')
                if action == 'shopee_post_apply_options' and not isinstance(payload.get('ids'), list):
                    raise ValueError('เลือกงานในคิวก่อนใช้ตัวเลือก')
                self.store.save_options(payload.get('revision'), payload.get('post_options'),
                                        payload.get('ids') if action == 'shopee_post_apply_options' else None)
        elif action == 'shopee_post_pause':
            with self._lock:
                if payload.get('run_id') and payload['run_id'] != (self.store.read().get('posting_run') or {}).get('id'):
                    raise ValueError('รอบโพสต์เปลี่ยนแล้ว ไม่พักรอบใหม่ด้วยคำสั่งจากหน้าต่างเก่า')
                self._pause.set()
                self.store.request_pause()
        elif action == 'shopee_post_reconcile':
            with self._lock:
                if self._busy:
                    raise ValueError('กำลังโพสต์อยู่ กรุณารอผลรอบปัจจุบัน')
                reconcile_saved_upload(self.store, str(payload.get('id')), payload.get('revision'))
                self._message = 'โพสต์สำเร็จแล้ว • ตรวจจากหลักฐานเดิม ไม่ได้ส่งซ้ำ'
        elif action == 'shopee_post_skip_unavailable':
            with self._lock:
                if self._busy or payload.get('confirm') is not True:
                    raise ValueError('พักคิวให้หยุดและยืนยันข้ามสินค้าก่อน')
                self.store.skip_product(str(payload.get('id')), 'ผู้ใช้ยืนยันว่าสินค้าถูกยกเว้นหรือนำเข้าไม่ได้', revision=payload.get('revision'))
                self._message = 'ข้ามสินค้าที่นำเข้าไม่ได้แล้ว • รายการอื่นพร้อมทำต่อ'
        elif action == 'shopee_post_reset_unsent':
            with self._lock:
                if self._busy:
                    raise ValueError('ตัวทำงานยังไม่หยุด • พักคิวและรอให้หยุดก่อนล้างสถานะ')
                if payload.get('confirm') is not True:
                    raise ValueError('ยืนยันล้างสถานะเฉพาะคลิปที่ยังไม่โพสต์ก่อน')
                def reset(state):
                    current = state.get('posting_run') or {}
                    if state['revision'] != payload.get('revision') or current.get('id') != payload.get('run_id'):
                        raise ValueError('คิวเปลี่ยนแล้ว • ไม่ล้างรอบใหม่ด้วยหน้าต่างเก่า')
                    ids = [row['id'] for row in state['items'] if restartable(row)]
                    # Preserve the original selection order for its remaining rows.
                    ids = [i for i in current.get('ids', []) if i in ids] + [i for i in ids if i not in current.get('ids', [])]
                    reset_preparation(state, ids)
                    account = state.get('account') or {}
                    start_run(state, ids, account.get('name',''), current.get('phone','มือถือที่เลือก'))
                    ready = state['posting_run']
                    ready.update(status='ready', finished_at=ready['started_at'], message=f'ล้างสถานะเดิมแล้ว • พร้อมเริ่มใหม่ 0/{len(ids)} คลิป')
                    for item in ready['rows'].values():
                        item.update(phase='draft',step='pending',message='พร้อมเริ่มใหม่ • ยังไม่ได้โพสต์')
                    return len(ids)
                count = self.store.change(reset)
                self._pause.clear()
                self._message = f'ล้างสถานะเดิมแล้ว • พร้อมเริ่มใหม่ 0/{count} คลิป • ยังไม่สั่งโพสต์'
        elif action == 'shopee_post_account':
            with self._lock:
                if self._busy:
                    raise ValueError('กำลังใช้มือถืออยู่ กรุณารอ')
                self._busy = True; self._pause.clear()
                self._message = 'กำลังเปิด Shopee และอ่านบัญชีจากมือถือ • ยังไม่โพสต์'
                threading.Thread(target=self._account, daemon=True).start()
        elif action == 'shopee_post_start':
            ids = selection_ids(payload.get('ids'))
            if payload.get('confirm') is not True:
                raise ValueError('กรุณายืนยันบัญชีและจำนวนคลิปก่อนโพสต์จริง')
            with self._lock:
                if self._busy:
                    raise ValueError('มีคิวกำลังใช้มือถืออยู่')
                def claim(state):
                    if state['revision'] != payload.get('revision'):
                        raise ValueError('คิวเปลี่ยนแล้ว กรุณาโหลดใหม่ก่อนโพสต์')
                    account = state.get('account') or {}
                    selected = self.wifi.state().get('selected') or {}
                    if not account.get('name') or account.get('device_id') != selected.get('device_id'):
                        raise ValueError('กรุณาอ่านบัญชี Shopee จากเครื่องที่เลือกก่อน')
                    rows = {r['id']: r for r in state['items']}
                    for row_id in ids:
                        row = rows.get(row_id)
                        if not row or not restartable(row):
                            raise ValueError('งานที่เลือกเริ่มส่งแล้ว หรือไม่พร้อมโพสต์')
                        if not row.get('caption','').strip() or len(row['caption'].encode('utf-16-le'))//2 > 150:
                            raise ValueError('กรุณาแก้แคปชันให้ไม่เกิน 150 ตัวอักษรก่อนโพสต์')
                        requested_options(row)
                    reset_preparation(state, ids)
                    for row_id in ids:
                        options = requested_options(rows[row_id])
                        # New Starts follow the user-requested available-controls
                        # policy; an explicit strict choice remains respected.
                        options.setdefault('allow_missing_controls', True)
                        rows[row_id].update(phase='queued', post_options=options,
                                            waiting_for_device=False,
                                            run_contract={'schema':1, 'posting_flow_version':2, 'account_check_mode':'confirmed_selection', 'close_before_first_post':True, 'close_after_publish':True, 'skip_unavailable_products':True, 'account':account['name'], 'device_id':account['device_id'], 'post_options':dict(options)},
                                            revision=rows[row_id]['revision']+1, message='อยู่ในคิวที่ยืนยันให้โพสต์')
                    run_id = start_run(state, ids, account['name'], selected.get('model') or 'มือถือที่ตรวจแล้ว')
                    state['posting_run'].update(account_check_mode='confirmed_selection',
                                                start_confirmation=dict(run_id=run_id, account=account['name'],
                                                                        device_id=account['device_id'], confirmed_at=time.time()))
                    return account['name'], run_id
                account, run_id = self.store.change(claim)
                self._busy = True; self._pause.clear()
                self._message = ''
                try:
                    threading.Thread(target=self._post, args=(ids, account, run_id), daemon=True).start()
                except Exception:
                    self._busy = False
                    self.store.settle_run(ids, run_id, 'เริ่มตัวทำงานไม่ได้ • ยังไม่โพสต์')
                    raise
        elif action == 'shopee_post_check':
            ids = selection_ids(payload.get('ids'))
            with self._lock:
                if self._busy:
                    raise ValueError('กำลังตรวจคิวอยู่ กรุณารอ')
                rows = {r['id']: r for r in self.store.read()['items']}
                if any(i not in rows or rows[i]['phase'] not in self.store.editable for i in ids):
                    raise ValueError('งานที่เลือกไม่พร้อมตรวจ หรือเคยเริ่มส่งแล้ว')
                self._busy = True; self._pause.clear()
                self._message = 'กำลังตรวจคลิปที่เลือก • ยังไม่โพสต์'
                threading.Thread(target=self._check, args=(list(dict.fromkeys(ids)),), daemon=True).start()
        else:
            raise ValueError('ไม่รองรับคำสั่งโพสต์นี้')
        return {'ok': True, 'posting': self.state()}

    def _account(self):
        try:
            with self.wifi.verified_device() as adb:
                identity = self.wifi.state()['selected']['device_id']
                device = ShopeeDevice(adb, identity, self._pause)
                device.membership = getattr(self, 'membership', None)
                try:
                    name = account_on_home(device)
                    self.store.change(lambda state: state.update(account={'name': name, 'device_id': identity}))
                    self._message = 'บัญชีที่อ่านจากมือถือ: ' + name
                finally:
                    device.close()
        except Exception as exc:
            self._message = str(exc)[:500]
        finally:
            with self._lock:
                self._busy = False

    def _post(self, ids, account, run_id):
        try:
            with self.wifi.verified_device() as adb:
                identity = self.wifi.state()['selected']['device_id']
                device = ShopeeDevice(adb, identity, self._pause)
                try:
                    account_bound = False  # Never reused across starts/restarts.
                    for row_id in ids:
                        if self._pause.is_set():
                            break
                        if getattr(self, 'membership', None):
                            self.membership.require()
                        row = self.store.transition(row_id, {'queued'}, 'checking', message='ตรวจ Final ก่อนโอนไปมือถือ')
                        device.on_device_state = lambda waiting, message, evidence, owned_id=row_id: self.store.device_observation(owned_id, waiting, message, evidence)
                        if (row['run_contract']['device_id'] != identity or row['run_contract']['account'] != account):
                            raise ValueError('เครื่องหรือบัญชีไม่ตรงกับคิวที่ยืนยัน หยุดก่อนส่ง')
                        # Transfer is private local-device I/O, not publication.
                        # Explicit new Starts use the user's confirmed selection.
                        # Each later clip validates the saved batch/device binding;
                        # it never opens a previous publication to compare captions.
                        fresh = self.detail(row['item_id'])
                        if row['video_path'] != fresh['video_path']:
                            raise ValueError('ไฟล์คลิปเปลี่ยนหลังเลือก กรุณานำเข้าร่างใหม่')
                        media = self.validator.validate(row['video_path'])
                        digest = file_hash(row['video_path'])
                        row = self.store.transition(row_id, {'checking'}, 'transferring', media=media,
                                                    run_contract={**row['run_contract'], 'video_sha256':digest},
                                                    video_sha256=digest, message='กำลังโอนเฉพาะวิดีโอไปอัลบั้มเฉพาะงาน')
                        receipt = transfer(adb, row, self._pause)
                        self.store.transition(row_id, {'transferring'}, 'prepared', transfer=receipt, message='ไฟล์บนมือถือครบ กำลังเตรียมโพสต์')
                        if not account_bound:
                            if row['run_contract'].get('close_before_first_post') is True:
                                self.store.progress(row_id, 'restart_app', 'ปิด Shopee เดิมแล้วเปิดใหม่ก่อนเริ่มคิว • ไม่ล้างข้อมูลแอป')
                                restart_before_first_post(device, self.store, row_id, account, run_id)
                            if account_check_mode(row) == 'live_ui':
                                # Preserve captured historical policy; new work never tours the profile.
                                self.store.progress(row_id, 'account', 'ตรวจบัญชีตามค่ารอบเดิม')
                                prepare_queue_account(device, account)
                            device.verify()
                            self.store.bind_queue_account(run_id, account, identity)
                            account_bound = True
                        folder = self.root/'workspace'/'shopee_posting'/'receipts'/row_id
                        try:
                            run(device, self.store, row_id, account, folder)
                        except ProductUnavailable as exc:
                            if row['run_contract'].get('skip_unavailable_products') is not True:
                                raise
                            self.store.skip_product(row_id, str(exc), run_id=run_id)
                            if not self._pause.is_set() and row_id != ids[-1]:
                                restart_before_first_post(device, self.store, row_id, account, run_id, after_skip=True)
                            continue
                        finished = next(r for r in self.store.read()['items'] if r['id'] == row_id)
                        if finished['phase'] != 'published':
                            raise ValueError('คลิปปัจจุบันยังไม่ยืนยันอัปโหลด • ไม่ส่งคลิปนี้ซ้ำ')
                        if not self._pause.is_set():
                            close_completed_post(device, self.store, row_id, account, run_id)
                    self._message = 'คิวโพสต์จบแล้ว' if not self._pause.is_set() else 'พักคิวแล้ว'
                finally:
                    device.close()
        except Exception as exc:
            self._message = str(exc)[:500]
            if isinstance(exc, DeviceUnavailable) and 'row_id' in locals():
                self.store.device_observation(row_id, False, self._message, exc.evidence)
        finally:
            try:
                self.store.settle_run(ids, run_id, self._message or 'พักก่อนทำต่อ ตรวจหน้ามือถือ', self._pause.is_set())
            finally:
                with self._lock:
                    self._busy = False

    def _check(self, ids):
        try:
            for row_id in ids:
                if self._pause.is_set():
                    break
                row = self.store.transition(row_id, self.store.editable, 'checking', message='กำลังตรวจไฟล์และมือถือ ยังไม่ส่งโพสต์')
                try:
                    fresh = self.detail(row['item_id'])
                    if fresh['video_path'] != row['video_path']:
                        raise ValueError('ไฟล์ Final เปลี่ยน กรุณานำเข้าร่างใหม่')
                    metadata = self.validator.validate(row['video_path'])
                    digest = file_hash(row['video_path'])
                    with self.wifi.verified_device() as adb:
                        identity = self.wifi.state()['selected']['device_id']
                        device = ShopeeDevice(adb, identity)
                        try:
                            device.snapshot()
                        finally:
                            device.close()
                    self.store.transition(row_id, {'checking'}, 'prepared', video_sha256=digest, media=metadata,
                                          message='ไฟล์และมือถือพร้อม • ยังไม่เผยแพร่ รอยืนยันเส้นทางโพสต์จริง')
                except Exception as exc:
                    self.store.transition(row_id, {'checking'}, 'review', message=str(exc)[:500])
                    break
        finally:
            with self._lock:
                self._busy = False
