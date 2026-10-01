"""Durable per-scene release barrier; no provider requests originate here."""
import hashlib
import json
from pathlib import Path
from core.atomic_json import AtomicJsonFile


class ScenePipeline:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.store = AtomicJsonFile(self.folder / 'prompts' / 'scene_pipeline.json')

    @staticmethod
    def _archive_error(row):
        error = row.pop('error', None)
        if error:
            row.setdefault('error_history', []).append({
                'error': error, 'phase': row.get('phase'),
                'run_id': row.get('run_id', ''),
            })

    def request(self, index, count, identity, run_id=''):
        if type(index) is not int or not 1 <= index <= count:
            raise ValueError('หมายเลขฉากไม่ถูกต้อง')
        revision = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.store.locked():
            data = self.store.read_unlocked({'scenes': {}})
            if index > 1 and data['scenes'].get(str(index-1), {}).get('phase') != 'complete':
                raise ValueError('ฉากก่อนหน้ายังไม่ครบภาพ วิดีโอ และเสียง')
            row = data['scenes'].get(str(index))
            if row and row['revision'] != revision:
                raise ValueError('ฉบับงานเปลี่ยน ต้องตรวจสื่อเดิมก่อน')
            if not row:
                row = {'index': index, 'revision': revision, 'phase': 'requested', 'identity': identity}
                data['scenes'][str(index)] = row
            elif row['phase'] in {'error', 'cancelled'} and run_id:
                # Commit the resumed state BEFORE the bridge dispatches the UI
                # worker or returns its ACK. Returning the old error races the
                # worker and stops the AI tab while Flow is still working.
                # An explicit ready/resume can reuse the existing run ID;
                # passive status polling must never call this method.
                self._archive_error(row)
                row.update(phase='requested', message='กำลังทำต่อจากสื่อที่บันทึกไว้')
            if row['phase'] not in {'error', 'cancelled'}:
                self._archive_error(row)
                if run_id and row['phase'] != 'complete':
                    row['run_id'] = run_id
            self.store.write_unlocked(data)
            return row

    def update(self, index, revision, **patch):
        with self.store.locked():
            data = self.store.read_unlocked({'scenes': {}})
            row = data['scenes'].get(str(index))
            if not row or row['revision'] != revision:
                raise ValueError('ผลฉากไม่ตรงฉบับงาน')
            if row['phase'] == 'complete':
                return row
            if patch.get('phase') == 'complete':
                target = (self.folder / str(patch.get('segment') or '')).resolve()
                if not target.is_relative_to(self.folder.resolve()) or not target.is_file() or target.stat().st_size < 1024:
                    raise ValueError('ยังไม่มีไฟล์ฉากสำเร็จ')
                patch['segment_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
            if patch.get('phase') in {'requested', 'video', 'voice', 'complete'}:
                self._archive_error(row)
            row.update(patch)
            self.store.write_unlocked(data)
            return row

    def begin_speech_retry(self, index, retry_id, segment_sha256):
        """Retire only a confirmed repeated-speech scene, preserving its media."""
        if not retry_id or not segment_sha256:
            raise ValueError('หลักฐานเสียงซ้ำไม่ครบ')
        with self.store.locked():
            data = self.store.read_unlocked({'scenes': {}})
            row = data['scenes'].get(str(index))
            if not row:
                raise ValueError('ไม่พบฉากที่จะสร้างเสียงใหม่')
            if row.get('speech_retry_id') == retry_id and row.get('phase') in {'speech_retry', 'video', 'voice', 'complete'}:
                return row
            if row.get('phase') != 'complete' or row.get('segment_sha256') != segment_sha256:
                raise ValueError('ฉากเปลี่ยนจากหลักฐานเสียงซ้ำ • ไม่สร้างซ้ำ')
            old = (self.folder / str(row.get('segment') or '')).resolve()
            if not old.is_relative_to(self.folder.resolve()) or not old.is_file() or hashlib.sha256(old.read_bytes()).hexdigest() != segment_sha256:
                raise ValueError('ไฟล์ฉากเดิมเปลี่ยน • ไม่สร้างซ้ำ')
            row.setdefault('speech_retry_history', []).append({
                'retry_id': retry_id, 'segment': row['segment'], 'segment_sha256': segment_sha256,
                'content_revision': row.get('content_revision'),
            })
            row.update(phase='speech_retry', speech_retry_id=retry_id,
                       message='พบเสียงพูดซ้ำชัดเจน • กำลังสร้างเฉพาะฉากนี้ใหม่')
            self.store.write_unlocked(data)
            return row

    def get(self, index):
        return self.store.read({'scenes': {}})['scenes'].get(str(index), {})

    def segments(self, count):
        paths = []
        for index in range(1, count+1):
            row = self.get(index)
            target = (self.folder / str(row.get('segment') or '')).resolve()
            if row.get('phase') != 'complete' or not target.is_relative_to(self.folder.resolve()) or not target.is_file():
                raise ValueError(f'ฉาก {index} ยังไม่ครบภาพ วิดีโอ และเสียง')
            if hashlib.sha256(target.read_bytes()).hexdigest() != row.get('segment_sha256'):
                raise ValueError('ไฟล์ฉากเปลี่ยนจากหลักฐานที่บันทึก')
            paths.append(target)
        return paths
