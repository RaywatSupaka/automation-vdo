"""Permanent Product-job denial and exact-target deletion journal.

Only an explicit confirmed UI request creates an intent. No startup cleanup,
automatic purge, provider cancellation, or recycle/restore behavior lives here.
"""
import copy
import hashlib
import json
import os
import re
import stat
import uuid
from pathlib import Path

from core.atomic_json import AtomicJsonFile

JOB_ID = re.compile(r'(?:JOB|STORY)-[A-Za-z0-9-]+')
REQUEST_ID = re.compile(r'[A-Za-z0-9_-]{8,100}')
RUN_OWNER = uuid.uuid4().hex


class ProductJobDeletedError(ValueError):
    code = 'PRODUCT_JOB_DELETED'


def journal(root):
    return AtomicJsonFile(Path(root) / 'workspace/product_job_deletions.json')


def snapshot(root):
    """Atomic primary observation without taking another manager's lock."""
    path = journal(root).path
    backup = path.with_name('.' + path.name + '.bak')
    selected = path if path.exists() else backup
    if not selected.exists():
        return {'version': 1, 'jobs': {}, 'requests': {}}
    try:
        value = json.loads(selected.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or not isinstance(value.get('jobs'), dict) or not isinstance(value.get('requests'), dict):
            raise ValueError('invalid deletion journal')
        if any(not isinstance(row, dict) or row.get('state') not in {'deleting', 'deleted', 'failed'}
               for row in value['jobs'].values()):
            raise ValueError('invalid permanent tombstone')
        return value
    except (OSError, ValueError) as exc:
        raise ValueError('อ่านหลักฐานการลบถาวรไม่ได้ • หยุดไว้ก่อนเพื่อไม่สร้างงานคืน') from exc


def assert_job_available(root, job_id):
    if snapshot(root)['jobs'].get(str(job_id)):
        raise ProductJobDeletedError('งานนี้ถูกสั่งลบถาวรแล้ว • ทำต่อหรือกู้คืนไม่ได้')


def assert_source_request_available(root, request_id):
    if not request_id:
        return
    digest = hashlib.sha256(str(request_id).encode()).hexdigest()
    if any(row.get('source_request_sha256') == digest for row in snapshot(root)['jobs'].values()):
        raise ProductJobDeletedError('คำขอสินค้านี้ถูกลบถาวรแล้ว • เริ่มรายการใหม่ด้วยคำขอใหม่')


def job_path_identity(path):
    """Recognize only canonical Product/Story files (and their exact backups)."""
    value = Path(path).absolute()
    for parent in (value, *value.parents):
        if (JOB_ID.fullmatch(parent.name) and parent.parent.name in {'products', 'stories'}
                and parent.parent.parent.name == 'workspace'):
            root = parent.parent.parent.parent
            if root.name == 'runtime-state' and root.parent.name == 'backups':
                root = root.parent.parent
            return root, parent.name
    return None


def assert_path_available(path):
    identity = job_path_identity(path)
    if identity:
        assert_job_available(*identity)


def controls(root):
    return {ident: {'permanently_deleted': True, 'deleted': True, 'hidden': False,
                    'trashed': False, 'delete_status': row['state']}
            for ident, row in snapshot(root)['jobs'].items()}


def targets(root, ident):
    if not isinstance(ident, str) or not JOB_ID.fullmatch(ident):
        raise ValueError('รหัสงานสำหรับลบไม่ถูกต้อง')
    root = Path(root).resolve()
    kind = 'products' if ident.startswith('JOB-') else 'stories'
    return (root / 'workspace' / kind / ident,
            root / 'backups/runtime-state/workspace' / kind / ident)


def _not_link(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024):
        raise ValueError('พบลิงก์หรือ Junction ในไฟล์งาน • ไม่ลบเพื่อป้องกันข้อมูลนอกงาน')
    return info


def validate_tree(path, root, *, missing_ok=False):
    path, root = Path(path).absolute(), Path(root).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('เป้าหมายลบอยู่นอกพื้นที่งานที่อนุญาต')
    # Check ancestors before resolve: a junction must not become a new root.
    for ancestor in reversed(path.parents):
        if ancestor == root or ancestor.is_relative_to(root):
            if ancestor.exists():
                _not_link(ancestor)
    if not path.exists() and not path.is_symlink():
        if missing_ok:
            return None
        raise ValueError('ไม่พบโฟลเดอร์งานสำหรับลบ')
    info = _not_link(path)
    if not stat.S_ISDIR(info.st_mode) or path.resolve() != path:
        raise ValueError('พาธโฟลเดอร์งานไม่ตรงเป้าหมายที่อนุญาต')
    for directory, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            _not_link(Path(directory) / name)
    return [info.st_dev, info.st_ino]


def purge_tree(path, root, expected_identity):
    """Never follows links and never deletes a broad or replacement directory."""
    actual = validate_tree(path, root, missing_ok=True)
    if actual is None:
        return
    if actual != expected_identity:
        raise ValueError('โฟลเดอร์เปลี่ยนหลังยืนยัน • ไม่ลบเป้าหมายใหม่')
    base = Path(path).absolute()
    def remove(directory):
        _not_link(directory)
        if not directory.resolve().is_relative_to(base):
            raise ValueError('ไฟล์ออกนอกโฟลเดอร์ที่ยืนยัน')
        for entry in list(os.scandir(directory)):
            child = Path(entry.path)
            info = _not_link(child)
            if not child.resolve().is_relative_to(base):
                raise ValueError('ไฟล์ออกนอกโฟลเดอร์ที่ยืนยัน • หยุดลบ')
            if stat.S_ISDIR(info.st_mode):
                remove(child)
            elif stat.S_ISREG(info.st_mode):
                child.unlink()
            else:
                raise ValueError('พบไฟล์ชนิดพิเศษ • หยุดลบรายการนี้')
        directory.rmdir()
    remove(base)


def response(root, request_id, product_controls=None):
    data = snapshot(root)
    request = data['requests'].get(request_id)
    if not request:
        raise ValueError('ไม่พบคำขอลบถาวรนี้')
    ids = request['job_ids']
    deleted = [ident for ident in ids if data['jobs'][ident]['state'] == 'deleted']
    failed = [{'job_id': ident, 'error': data['jobs'][ident].get('error') or 'การลบถูกขัดจังหวะ • กดลองลบส่วนที่เหลือ'}
              for ident in ids if data['jobs'][ident]['state'] == 'failed' or (
                  data['jobs'][ident]['state'] == 'deleting' and data['jobs'][ident].get('owner') != RUN_OWNER)]
    status = 'complete' if len(deleted) == len(ids) else 'partial' if failed else 'deleting'
    return {'ok': True, 'product_job_controls': {**(product_controls or {}), **controls(root)},
            'deletion': {'request_id': request_id, 'status': status, 'job_ids': copy.deepcopy(ids),
                         'deleted_ids': deleted, 'failed': failed}}
