"""Durable local drafts; Facebook, not the desktop clock, owns scheduled posts."""
import copy
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.atomic_json import _ProcessFileLock, JsonPersistenceError

BANGKOK = timezone(timedelta(hours=7), 'Asia/Bangkok')
# Application preflight window, not a claim about every Facebook API surface.
MIN_LEAD = 20 * 60
MAX_LEAD = 180 * 86400


def timestamp(value):
    """HTML datetime-local is ALWAYS Bangkok, regardless of the PC timezone."""
    try:
        return int(datetime.strptime(str(value), '%Y-%m-%dT%H:%M').replace(tzinfo=BANGKOK).timestamp())
    except (ValueError, TypeError, OverflowError):
        raise ValueError('กรอกวันและเวลาให้ครบ (เวลาไทย Asia/Bangkok)') from None


def local_time(value):
    return datetime.fromtimestamp(int(value), BANGKOK).strftime('%Y-%m-%dT%H:%M')


def validate_time(value, now=None):
    now = time.time() if now is None else now
    if value < now + MIN_LEAD:
        raise ValueError('ตั้งเวลาล่วงหน้าอย่างน้อย 20 นาที เพื่อเผื่อเวลาอัปโหลด • ระบบไม่เลื่อนเวลาให้เอง')
    if value > now + MAX_LEAD:
        raise ValueError('หน้านี้รองรับแผนล่วงหน้าไม่เกิน 180 วัน')


class FacebookPlanner:
    def __init__(self, host):
        self.host = host
        self.store = host.store

    def lease(self):
        return _ProcessFileLock(self.store.path.with_suffix('.dispatch'), timeout=0.5)

    def recover(self):
        # Another desktop instance may still be sending. Never steal its work.
        lease = self.lease()
        try:
            lease.__enter__()
        except JsonPersistenceError:
            return
        try:
            if not self.store.path.exists():
                return
            with self.store.locked():
                data = self.store.read_unlocked({'posts': {}})
                changed = False
                for row in data.get('posts', {}).values():
                    if row.get('status') == 'uploading':
                        row.update(status='review', message='โปรแกรมปิดระหว่างส่ง ตรวจในเพจก่อน ไม่ส่งซ้ำ')
                        changed = True
                for row in data.get('planner', []):
                    if row.get('status') == 'queued':
                        row.update(status='draft', message='พักรายการที่ยังไม่ส่งหลังเปิดโปรแกรมใหม่')
                        changed = True
                data['planner_batch'] = {'active': False, 'paused': True}
                if changed:
                    self._save_revision(data)
                self.store.write_unlocked(data)
        finally:
            lease.__exit__(None, None, None)

    @staticmethod
    def view(data):
        rows = copy.deepcopy(data.get('planner', []))
        for row in rows:
            post = data.get('posts', {}).get(row.get('post_id'))
            if post:
                for key in ('status', 'message', 'video_id', 'url', 'remote_scheduled_at', 'checked_at'):
                    if key in post:
                        row[key] = post[key]
        return {'rows': rows, 'revision': data.get('planner_revision', 0),
                'batch': data.get('planner_batch', {}), 'timezone': 'Asia/Bangkok'}

    @staticmethod
    def _revision(data, revision):
        if revision != data.get('planner_revision', 0):
            raise ValueError('แผนถูกเปลี่ยนจากหน้าต่างอื่น กรุณารีเฟรชก่อนแก้ต่อ')

    @staticmethod
    def _save_revision(data):
        data['planner_revision'] = data.get('planner_revision', 0) + 1

    @staticmethod
    def _ids(ids):
        if not isinstance(ids, list) or not ids or len(ids) > 200 or not all(isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
            raise ValueError('เลือกรายการ 1–200 รายการ ไม่ซ้ำกัน')
        return set(ids)

    def _selected(self, data, ids):
        selected = self._ids(ids)
        rows = [r for r in data.get('planner', []) if r['id'] in selected]
        if len(rows) != len(selected):
            raise ValueError('ไม่พบแถวที่เลือก กรุณารีเฟรช')
        if any(r.get('post_id') or r['status'] != 'draft' for r in rows):
            raise ValueError('แก้ได้เฉพาะแบบร่างที่ยังไม่ส่ง • ตารางที่ Facebook รับแล้วไม่ถูกแก้หรือลบจากที่นี่')
        return rows

    def add(self, ids, revision):
        self._ids(ids)
        items = [self.host.library.item_detail(i) for i in ids]
        with self.store.locked():
            data = self.store.read_unlocked({'posts': {}})
            self._revision(data, revision)
            page = data.get('page')
            if not page:
                raise ValueError('เชื่อมต่อเพจก่อนเพิ่มคลิปเข้าแผน')
            rows = data.setdefault('planner', [])
            existing = {r['item_id'] for r in rows if r['page_id'] == page['id']}
            if len(rows) + len(items) > 1000:
                raise ValueError('Planner เต็ม กรุณาลบแบบร่างที่ไม่ใช้ก่อน')
            for item_id, item in zip(ids, items):
                if item_id in existing:
                    continue
                rows.append({'id': uuid.uuid4().hex, 'item_id': item_id, 'title': item['title'],
                             'page_id': page['id'], 'page_name': page['name'], 'caption': str(item.get('post_text') or item['title'])[:5000],
                             'status': 'draft', 'scheduled_at': None, 'created_at': time.time()})
            self._save_revision(data)
            self.store.write_unlocked(data)
        return self.host.state()

    def edit(self, payload):
        with self.store.locked():
            data = self.store.read_unlocked({'posts': {}})
            self._revision(data, payload.get('revision'))
            rows = self._selected(data, payload.get('ids'))
            op = payload.get('operation')
            if op == 'remove':
                data['planner'] = [r for r in data['planner'] if r not in rows]
            elif op == 'save':
                updates = payload.get('updates')
                if not isinstance(updates, dict) or set(updates) != {r['id'] for r in rows}:
                    raise ValueError('ข้อมูลแบบร่างไม่ครบ')
                for row in rows:
                    update = updates[row['id']]
                    caption = str(update.get('caption') or '').strip()
                    if len(caption) > 5000:
                        raise ValueError('ข้อความยาวเกิน 5,000 ตัวอักษร')
                    row.update(caption=caption, scheduled_at=timestamp(update['time']) if update.get('time') else None)
            elif op == 'move':
                if len(rows) != 1 or payload.get('direction') not in (-1, 1):
                    raise ValueError('ย้ายทีละหนึ่งแถว')
                positions = [i for i, r in enumerate(data['planner']) if r['page_id'] == rows[0]['page_id']]
                index = data['planner'].index(rows[0])
                target_index = positions.index(index) + payload['direction']
                if 0 <= target_index < len(positions):
                    target = positions[target_index]
                    data['planner'][index], data['planner'][target] = data['planner'][target], data['planner'][index]
            elif op in ('spread', 'shift'):
                minutes = payload.get('minutes')
                if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 259200:
                    raise ValueError('ระบุช่วงเวลาจำนวนเต็มที่มากกว่า 0')
                base = timestamp(payload.get('start')) if op == 'spread' else None
                for i, row in enumerate(rows):
                    if op == 'shift' and row.get('scheduled_at') is None:
                        raise ValueError('ตั้งเวลาแถวที่เลือกให้ครบก่อนบวกเวลา')
                    row['scheduled_at'] = base + i * minutes * 60 if op == 'spread' else row['scheduled_at'] + minutes * 60
                self._validate_schedule(data, rows)
                if payload.get('preview') is True:
                    return {'ok': True, 'preview': [{'id': r['id'], 'title': r['title'], 'time': local_time(r['scheduled_at'])} for r in rows]}
            else:
                raise ValueError('คำสั่งจัดแผนไม่ถูกต้อง')
            self._save_revision(data)
            self.store.write_unlocked(data)
        return self.host.state()

    @staticmethod
    def _validate_schedule(data, rows):
        for row in rows:
            if row.get('scheduled_at') is None:
                raise ValueError('ตั้งเวลาให้ครบทุกแถวที่เลือกก่อนส่ง')
            validate_time(row['scheduled_at'])
            for other in FacebookPlanner.view(data)['rows']:
                if (other['id'] != row['id'] and other['page_id'] == row['page_id']
                        and other.get('scheduled_at') == row['scheduled_at']):
                    raise ValueError('เวลาโพสต์ซ้ำกับอีกแถวในเพจเดียวกัน กรุณาจัดเวลาใหม่')

    def start(self, ids, revision, page_id, mode):
        if mode not in ('schedule', 'now'):
            raise ValueError('เลือกตั้งเวลาหรือโพสต์ทันที')
        lease = self.lease()
        try:
            lease.__enter__()
        except JsonPersistenceError:
            raise ValueError('มีชุดโพสต์กำลังส่งอยู่ รอหรือกดพักก่อน') from None
        try:
            with self.host.lock, self.store.locked():
                data = self.store.read_unlocked({'posts': {}})
                self._revision(data, revision)
                page = data.get('page') or {}
                if page.get('id') != page_id or not self.host.credentials.load():
                    raise ValueError('ตรวจเพจและ Token ก่อนส่ง')
                if any(w.is_alive() for w in self.host.workers.values()) or any(p.get('status') == 'uploading' for p in data.get('posts', {}).values()):
                    raise ValueError('รออัปโหลดปัจจุบันก่อนส่งชุดใหม่')
                rows = self._selected(data, ids)
                if any(r['page_id'] != page_id for r in rows):
                    raise ValueError('รายการที่เลือกมีงานของเพจอื่น')
                if mode == 'schedule':
                    self._validate_schedule(data, rows)
                elif any(r.get('scheduled_at') for r in rows):
                    raise ValueError('แถวนี้ตั้งเวลาไว้แล้ว ใช้ปุ่มส่งตาราง หรือเคลียร์เวลาแล้วบันทึกก่อนโพสต์ทันที')
                batch_id = uuid.uuid4().hex
                for row in rows:
                    row.update(status='queued', batch_id=batch_id, send_mode=mode)
                data['planner_batch'] = {'id': batch_id, 'active': True, 'paused': False}
                self._save_revision(data)
                self.store.write_unlocked(data)
                worker = threading.Thread(target=self._run, args=(batch_id, lease), daemon=True)
                self.host.workers['planner'] = worker
                try:
                    worker.start()
                except Exception:
                    for row in rows:
                        row.update(status='draft')
                    data['planner_batch'].update(active=False, paused=True)
                    self._save_revision(data)
                    self.store.write_unlocked(data)
                    raise ValueError('เริ่มตัวส่งไม่ได้ เก็บแบบร่างไว้แล้ว ยังไม่อัปโหลด') from None
        except Exception:
            lease.__exit__(None, None, None)
            raise
        return self.host.state()

    def pause(self):
        with self.store.locked():
            data = self.store.read_unlocked({'posts': {}})
            data.setdefault('planner_batch', {})['paused'] = True
            self.store.write_unlocked(data)
        return self.host.state()

    def _run(self, batch_id, lease):
        try:
            while True:
                with self.store.locked():
                    data = self.store.read_unlocked()
                    batch = data.get('planner_batch', {})
                    if batch.get('id') != batch_id or batch.get('paused'):
                        break
                    row = next((r for r in data['planner'] if r.get('batch_id') == batch_id and r['status'] == 'queued'), None)
                    if not row:
                        break
                    row = dict(row)
                # Hash and network never run on the UI thread or under the JSON lock.
                try:
                    if getattr(self.host, 'membership', None):
                        self.host.membership.require()
                    item = self.host.library.item_detail(row['item_id'])
                    path = Path(item['path'])
                    if not path.is_file() or path.stat().st_size < 1024:
                        raise ValueError('ไม่พบไฟล์ Final ที่พร้อมโพสต์')
                    digest = self.host._hash(path)
                    token = self.host.credentials.load()
                    if not token:
                        raise ValueError('ไม่พบ Token กรุณาเชื่อมต่อเพจเดิมก่อน')
                    with self.store.locked():
                        data = self.store.read_unlocked()
                        if data['planner_batch'].get('paused'):
                            break
                        if (data.get('page') or {}).get('id') != row['page_id']:
                            raise ValueError('เพจเปลี่ยนแล้ว พักชุดโพสต์')
                        if row['send_mode'] == 'schedule':
                            validate_time(row['scheduled_at'])
                        key = self.host.post_key(row['page_id'], row['item_id'], digest)
                        current = next(r for r in data['planner'] if r['id'] == row['id'])
                        current.update(status='submitted', post_id=key)
                        duplicate = key in data['posts']
                        if not duplicate:
                            data['posts'][key] = {**row, 'id': key, 'sha256': digest, 'status': 'uploading', 'created_at': time.time()}
                        self._save_revision(data)
                        self.store.write_unlocked(data)
                    if not duplicate:
                        self.host._upload(key, path, token, row['caption'], row['title'])
                    if self.store.read()['posts'][key]['status'] == 'review':
                        self.pause()
                except Exception:
                    # No POST has been claimed here. Keep draft editable; no invented success.
                    with self.store.locked():
                        data = self.store.read_unlocked()
                        current = next(r for r in data['planner'] if r['id'] == row['id'])
                        if not current.get('post_id'):
                            current.update(status='draft', message='ตรวจไฟล์ Final / เพจ / เวลาอีกครั้งก่อนส่ง • ยังไม่อัปโหลด')
                        data['planner_batch']['paused'] = True
                        self._save_revision(data)
                        self.store.write_unlocked(data)
                    break
        finally:
            try:
                with self.store.locked():
                    data = self.store.read_unlocked()
                    if data.get('planner_batch', {}).get('id') == batch_id:
                        data['planner_batch'].update(active=False)
                        for row in data.get('planner', []):
                            if row.get('batch_id') == batch_id and row['status'] == 'queued':
                                row.update(status='draft', message='ยังไม่ส่ง • เลือกเพื่อส่งต่อได้')
                        self._save_revision(data)
                        self.store.write_unlocked(data)
            finally:
                lease.__exit__(None, None, None)

    def action(self, action, payload):
        if action == 'facebook_planner_add':
            return self.add(payload.get('ids'), payload.get('revision'))
        if action == 'facebook_planner_edit':
            return self.edit(payload)
        if action == 'facebook_planner_start':
            return self.start(payload.get('ids'), payload.get('revision'), payload.get('page_id'), payload.get('mode'))
        if action == 'facebook_planner_pause':
            return self.pause()
        raise ValueError('คำสั่ง Planner ไม่ถูกต้อง')
