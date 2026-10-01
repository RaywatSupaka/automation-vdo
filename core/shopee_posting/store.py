"""Separate, atomic Shopee draft/receipt store; never changes source jobs."""
import hashlib
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from core.atomic_json import AtomicJsonFile
from core.shopee_posting.options import DEFAULT_OPTIONS, validate_options, requested_options, proof_matches_options
from core.shopee_posting.progress import selection_ids, observe, finish_run, ACTIVE, STEPS
from core.shopee_posting.contract import flow_version, queue_account, account_check_mode, confirmed_selection


def product_url(value):
    value = str(value or '').strip()
    p = urlsplit(value)
    if (p.scheme != 'https' or p.hostname not in {'shopee.co.th', 'www.shopee.co.th', 's.shopee.co.th'}
            or p.username or p.password or p.port not in (None, 443) or not p.path.strip('/')
            or any(c.isspace() for c in value)):
        raise ValueError('ต้องมีลิงก์สินค้า Shopee ประเทศไทยที่ถูกต้อง')
    return value


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class PostingStore:
    editable = {'draft', 'review', 'prepared', 'skipped'}

    def __init__(self, root):
        self.file = AtomicJsonFile(Path(root) / 'workspace' / 'shopee_posting' / 'queue.json')

    def read(self):
        value = self.file.read({'schema': 1, 'revision': 0, 'items': []})
        if value.get('schema') != 1 or not isinstance(value.get('items'), list):
            raise ValueError('ข้อมูลคิว Shopee ไม่ถูกต้อง เก็บไฟล์เดิมเพื่อตรวจสอบ')
        return value

    def change(self, fn):
        with self.file.locked():
            value = self.read()
            result = fn(value)
            value['revision'] += 1
            self.file.write(value)
        return result

    def add(self, details):
        def update(state):
            added = []
            for detail in details:
                # Same library item cannot accidentally enter the queue twice.
                old = next((x for x in state['items'] if x['item_id'] == detail['item_id'] and x['phase'] != 'removed'), None)
                if old:
                    added.append(old['id']); continue
                row = dict(detail, id=uuid.uuid4().hex, phase='draft', revision=0,
                           post_options=validate_options(state.get('defaults', DEFAULT_OPTIONS)),
                           created_at=time.time(), updated_at=time.time(), message='รอตรวจข้อมูลก่อนโพสต์')
                state['items'].append(row); added.append(row['id'])
            return added
        return self.change(update)

    def edit(self, row_id, revision, **fields):
        if set(fields) - {'caption', 'product_url', 'removed', 'post_options'}:
            raise ValueError('แก้ได้เฉพาะข้อมูลร่าง')
        def update(state):
            row = next(x for x in state['items'] if x['id'] == row_id)
            if row['revision'] != revision or row['phase'] not in self.editable or row.get('publish_intent'):
                raise ValueError('สถานะงานเปลี่ยนแล้ว กรุณาโหลดคิวใหม่ ห้ามแก้งานที่เริ่มส่ง')
            if 'caption' in fields:
                caption = str(fields['caption']).strip()
                if not caption or len(caption.encode('utf-16-le')) // 2 > 150:
                    raise ValueError('แคปชัน Shopee ต้องมี 1–150 ตัวอักษร (อีโมจิอาจนับเป็น 2)')
                row['caption'] = caption
            if 'product_url' in fields:
                row['product_url'] = product_url(fields['product_url'])
            row['post_options'] = validate_options(fields['post_options']) if 'post_options' in fields else requested_options(row)
            if row['phase'] == 'skipped':
                row.setdefault('skip_history', []).append({'reason':row.pop('skip_reason', ''), 'at':row.pop('skipped_at', None)})
                row['message'] = 'แก้ไขร่างแล้ว • เลือกเพื่อเริ่มใหม่ได้'
            row.update(phase='removed' if fields.get('removed') is True else 'draft', revision=row['revision']+1, updated_at=time.time())
        self.change(update)

    def save_options(self, revision, options, ids=None):
        options = validate_options(options)
        if ids is not None:
            selection_ids(ids)
        def update(state):
            if type(revision) is not int or state['revision'] != revision:
                raise ValueError('คิวเปลี่ยนแล้ว กรุณาโหลดใหม่ก่อนบันทึกตัวเลือก')
            if ids is None:
                state['defaults'] = dict(options)
                return
            rows = {r['id']: r for r in state['items']}
            if any(i not in rows or rows[i]['phase'] not in self.editable or rows[i].get('publish_intent') for i in ids):
                raise ValueError('มีงานที่เริ่มส่งแล้วหรือไม่พร้อมแก้ ไม่เปลี่ยนตัวเลือกทั้งชุด')
            for i in ids:
                rows[i].update(post_options=dict(options), revision=rows[i]['revision']+1, updated_at=time.time())
        self.change(update)

    def transition(self, row_id, expected, phase, **values):
        def update(state):
            row = next(x for x in state['items'] if x['id'] == row_id)
            if row['phase'] not in expected:
                raise ValueError('คิวเปลี่ยนสถานะแล้ว ไม่เริ่มงานซ้ำ')
            row.update(values, phase=phase, revision=row['revision']+1, updated_at=time.time())
            observe(state, row)
            return dict(row)
        return self.change(update)

    def progress(self, row_id, step, message):
        if step not in STEPS:
            raise ValueError('ไม่รู้จักขั้นตอนติดตามโพสต์')
        def update(state):
            row = next(x for x in state['items'] if x['id'] == row_id)
            if row['phase'] not in {'prepared','editing','settings','processing','checking','transferring'}:
                raise ValueError('งานไม่ได้อยู่ในขั้นที่ติดตามได้')
            row.update(message=message, updated_at=time.time(), revision=row['revision']+1)
            observe(state, row, step)
        self.change(update)

    def request_pause(self):
        def update(state):
            run = state.get('posting_run') or {}
            if run.get('status') in ACTIVE:
                run.update(status='pausing', message='กำลังพักคิว • ถ้าเริ่มส่งแล้วต้องตรวจผลเดิม ไม่ส่งซ้ำ', updated_at=time.time())
        self.change(update)

    def device_observation(self, row_id, waiting, message, evidence):
        def update(state):
            row = next(x for x in state['items'] if x['id'] == row_id)
            run = state.get('posting_run') or {}
            if run.get('status') not in ACTIVE or row.get('posting_run_id') != run.get('id') or row['phase'] in {'published','unknown','skipped'}:
                return
            row.update(waiting_for_device=bool(waiting), device_observation=dict(evidence),
                       message=message, revision=row['revision']+1, updated_at=time.time())
            previous = run.get('rows', {}).get(row_id, {})
            observe(state, row, previous.get('step'))
        self.change(update)

    def settle_run(self, ids, run_id, message, paused=False):
        def update(state):
            if (state.get('posting_run') or {}).get('id') != run_id:
                return
            for row in state['items']:
                if row['id'] not in ids or row.get('posting_run_id') != run_id or row['phase'] in {'published','unknown','skipped'}:
                    continue
                row.update(phase='draft' if row['phase']=='queued' else 'unknown' if row.get('publish_intent') else 'review',
                           waiting_for_device=False,
                           message='พักคลิปที่เหลือ ยังไม่ได้เริ่มโพสต์' if row['phase']=='queued' else message,
                           revision=row['revision']+1, updated_at=time.time())
                observe(state, row)
            finish_run(state, run_id, message, paused)
        self.change(update)

    def recover(self):
        # Skipped products remain terminal until the user explicitly edits them.
        def update(state):
            run = state.get('posting_run') or {}
            for row in state['items']:
                owned_prepared = row['phase']=='prepared' and run.get('status') in ACTIVE and row.get('posting_run_id')==run.get('id')
                if owned_prepared or row['phase'] in {'queued', 'checking', 'transferring', 'editing', 'settings', 'ready', 'send_pending', 'processing'}:
                    # No restart path may reset a publish intent into an editable draft.
                    sent = bool(row.get('publish_intent'))
                    row.update(phase='unknown' if sent else 'review', revision=row['revision']+1,
                               message='ต้องตรวจผลโพสต์เดิมก่อน ห้ามส่งซ้ำ' if sent else 'งานหยุดระหว่างเตรียม กรุณาตรวจมือถือก่อนทำต่อ')
                    observe(state, row)
            if run:
                finish_run(state, run['id'], 'โปรแกรมเปิดใหม่ • เก็บผลเดิมไว้ ไม่เริ่มโพสต์ซ้ำ', interrupted=True)
        self.change(update)

    def skip_product(self, row_id, reason, *, run_id=None, revision=None):
        def update(state):
            row = next(r for r in state['items'] if r['id'] == row_id)
            run = state.get('posting_run') or {}
            if row.get('publish_intent') or row.get('receipt') or row.get('published_at') or row.get('dispatch_state') == 'press_committed':
                raise ValueError('งานเริ่มส่งแล้ว • ไม่ข้ามหรือเปลี่ยนหลักฐานโพสต์')
            if run_id:
                if (run.get('id') != run_id or run.get('status') != 'running' or run.get('current_id') != row_id
                        or row.get('posting_run_id') != run_id or row['phase'] != 'editing'
                        or run.get('rows', {}).get(row_id, {}).get('step') != 'product'):
                    raise ValueError('ข้ามได้เฉพาะสินค้าในขั้นแนบของรอบปัจจุบัน')
            elif state['revision'] != revision or row['phase'] not in self.editable:
                raise ValueError('คิวเปลี่ยนหรือรายการนี้ข้ามไม่ได้')
            row.update(phase='skipped', skip_reason=reason, skipped_at=time.time(),
                       message='ข้ามสินค้า • '+reason, waiting_for_device=False,
                       revision=row['revision']+1, updated_at=time.time())
            observe(state, row)
        self.change(update)

    def bind_queue_account(self, run_id, account, device_id):
        def update(state):
            run = state.get('posting_run') or {}
            rows = [r for r in state['items'] if r.get('posting_run_id') == run_id]
            if (run.get('id') != run_id or run.get('status') not in ACTIVE
                    or run.get('account') != account or run.get('account_receipt') or not rows
                    or any(flow_version(r) != 2 or r.get('publish_intent')
                           or r['run_contract'].get('account') != account
                           or r['run_contract'].get('device_id') != device_id for r in rows)):
                raise ValueError('คิวเปลี่ยนหรือยืนยันบัญชีแล้ว • ไม่เขียนทับหลักฐานรอบเดิม')
            modes = {account_check_mode(row) for row in rows}
            if len(modes) != 1:
                raise ValueError('วิธียืนยันของงานในคิวไม่ตรงกัน • ยังไม่ส่งโพสต์')
            mode = modes.pop()
            if mode == 'confirmed_selection':
                proof = confirmed_selection(run, account, device_id)
            else:
                proof = dict(run_id=run_id, account=account, device_id=device_id, verified_at=time.time())
            run['account_receipt'] = dict(proof, source=mode)
        self.change(update)

    def queue_account(self, row_id, account, device_id):
        state = self.read()
        row = next(r for r in state['items'] if r['id'] == row_id)
        return queue_account(state, row, account, device_id)

    def claim_publish(self, row_id, *, account, device_id, video_sha256):
        if not account or not device_id or len(video_sha256) != 64:
            raise ValueError('ยังยืนยันบัญชี โทรศัพท์ และไฟล์วิดีโอไม่ได้')
        def update(state):
            row = next(x for x in state['items'] if x['id'] == row_id)
            if row['phase'] != 'ready' or row.get('publish_intent'):
                raise ValueError('งานไม่พร้อมส่งหรือเคยเริ่มส่งแล้ว')
            if row.get('video_sha256') != video_sha256:
                raise ValueError('ไฟล์วิดีโอเปลี่ยนหลังตรวจ')
            options = requested_options(row)
            contract = row.get('run_contract') or {}
            baseline = row.get('latest_baseline') or {}
            if (contract.get('account') != account or contract.get('device_id') != device_id
                    or contract.get('post_options') != options or contract.get('video_sha256') != video_sha256
                    or not proof_matches_options(row.get('observed_options'), options)):
                raise ValueError('บัญชี เครื่อง หรือค่าที่ตรวจบนมือถือไม่ตรงกับงานที่ยืนยัน')
            version = flow_version(row)
            account_proof = queue_account(state, row, account, device_id) if version == 2 else {}
            if version == 2:
                if row.get('upload_notice_absent') is not True:
                    raise ValueError('ยังไม่ได้เตรียมรับคำยืนยันอัปโหลดของคลิปนี้')
            elif (baseline.get('account') != account or not baseline.get('latest_caption')
                  or baseline['latest_caption'] == row['caption']):
                raise ValueError('ยังแยกโพสต์ใหม่จากโพสต์ล่าสุดก่อนส่งไม่ได้')
            for previous in state['items']:
                intent = previous.get('publish_intent') or {}
                if intent.get('account') == account and intent.get('video_sha256') == video_sha256:
                    raise ValueError('คลิปนี้เคยเริ่มโพสต์ในบัญชีนี้แล้ว ต้องตรวจผลเดิมก่อน')
            row.update(phase='send_pending', revision=row['revision']+1,
                       publish_intent=dict(id=uuid.uuid4().hex, at=time.time(), account=account, device_id=device_id,
                                           video_sha256=video_sha256, product_url=row['product_url'],
                                           post_options=dict(options), observed_options=row['observed_options'],
                                           latest_baseline=dict(baseline),
                                           posting_flow_version=version, queue_account_receipt=account_proof,
                                           upload_notice_absent=row.get('upload_notice_absent') is True,
                                           caption_sha256=hashlib.sha256(row['caption'].encode()).hexdigest()))
            if row.get('preflight_version') == 2:
                row['dispatch_state'] = 'press_committed'
                row['publish_intent']['dispatch_state'] = 'press_committed'
            row['message'] = 'บันทึกเจตนาส่งแล้ว • กำลังส่งโพสต์หนึ่งครั้ง'
            observe(state, row)
            return dict(row)
        return self.change(update)

    def confirm_uploaded(self, row_id, intent_id, observed_at, source, *, evidence_path='', revision=None):
        def update(state):
            row = next(x for x in state['items'] if x['id'] == row_id)
            intent = row.get('publish_intent') or {}
            contract = row.get('run_contract') or {}
            if (row['phase'] not in {'processing', 'unknown'} or intent.get('id') != intent_id
                    or revision is not None and row['revision'] != revision
                    or not intent.get('at', 0) <= observed_at <= time.time()
                    or not intent.get('account') or not intent.get('device_id')
                    or any(contract.get(k) != intent.get(k) for k in ('account', 'device_id', 'video_sha256', 'post_options'))
                    or intent.get('caption_sha256') != hashlib.sha256(row['caption'].encode()).hexdigest()
                    or intent.get('product_url') != row['product_url']
                    or not proof_matches_options(intent.get('observed_options'), intent.get('post_options'))):
                raise ValueError('ผลอัปโหลดไม่ตรงกับรอบส่งที่บันทึกไว้ • ไม่เปลี่ยนสถานะ')
            row.update(phase='published', published_at=observed_at, waiting_for_device=False,
                       revision=row['revision']+1, updated_at=time.time(),
                       message='โพสต์สำเร็จแล้ว • Shopee ยืนยันอัปโหลดสำเร็จ',
                       receipt={'source': source, 'upload_confirmed': True, 'intent_id': intent_id,
                                'account': intent['account'], 'observed_at': observed_at,
                                'preflight_verified': True, 'evidence_path': evidence_path})
            run = state.get('posting_run') or {}
            if row.get('posting_run_id') == run.get('id') and row_id in run.get('rows', {}):
                # Reconcile a finished review atomically; never restart a worker.
                terminal = run.get('status') not in ACTIVE
                if terminal:
                    run['status'] = 'running'
                observe(state, row)
                if terminal:
                    finish_run(state, run['id'], 'โพสต์สำเร็จแล้ว • ตรวจพบหลักฐานอัปโหลดเดิม')
        self.change(update)
