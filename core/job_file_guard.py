"""In-process ownership of Product/Story files shared by starts and deletion.

Claims are reserved before dispatch and released after workers finish. Persistent
queue/remote ownership is supplied by the desktop probe, including after restart.
"""
import functools
import json
import re
import threading
from contextlib import contextmanager
from pathlib import Path


_REGISTRY_LOCK = threading.RLock()
_REGISTRY = {}
_JOB = re.compile(r'(?:JOB|STORY)-[A-Za-z0-9_-]+')


def guard_for(root):
    key = str(Path(root).resolve()).casefold()
    with _REGISTRY_LOCK:
        if key not in _REGISTRY:
            _REGISTRY[key] = JobFileGuard(root)
        return _REGISTRY[key]


class Claim:
    def __init__(self, guard, targets, deleting=False):
        self.guard, self.targets, self.deleting = guard, frozenset(targets), deleting
        self.released = False

    def release(self):
        with self.guard.lock:
            self.guard.claims.discard(self)
            self.released = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


class JobFileGuard:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self.claims = set()
        self.probe = None
        self.local = threading.local()

    def job_id(self, value, base=None):
        text = str(value or '')
        if ':' in text and text.split(':', 1)[0] in {'product', 'story'}:
            text = text.split(':', 1)[1]
        if _JOB.fullmatch(text):
            return text
        try:
            path = Path(text)
            if base is not None and not path.is_absolute():
                path = Path(base) / path
            relative = path.resolve().relative_to(self.root / 'workspace')
            if len(relative.parts) >= 2 and relative.parts[0] in {'products', 'stories'} and _JOB.fullmatch(relative.parts[1]):
                return relative.parts[1]
        except (ValueError, OSError):
            pass
        return ''

    def folder(self, job_id):
        return self.root / 'workspace' / ('products' if job_id.startswith('JOB-') else 'stories') / job_id

    def references(self, values, base=None):
        found = set()
        def visit(value):
            if isinstance(value, dict):
                for child in value.values():
                    visit(child)
            elif isinstance(value, (tuple, list, set)):
                for child in value:
                    visit(child)
            elif isinstance(value, (str, Path)):
                ident = self.job_id(value, base)
                if ident:
                    found.add(ident)
        visit(values)
        return found

    def job_references(self, job_id):
        try:
            value = json.loads((self.folder(job_id) / 'job.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {job_id}
        return {job_id} | self.references(value, self.folder(job_id))

    def _busy_reason(self, job_id, allow_queued_job_ids=()):
        # Standalone library callers still protect manifests that explicitly
        # say a worker is running. UI/remote evidence is stricter and scoped.
        try:
            row = json.loads((self.folder(job_id) / 'job.json').read_text(encoding='utf-8'))
            if any(row.get(key) in {'running', 'rendering', 'generating', 'processing'}
                   for key in ('status', 'automation_status', 'video_status', 'voice_status', 'subtitle_status')):
                return 'งานนี้ยังทำงานอยู่'
        except (OSError, ValueError):
            pass
        if self.probe and allow_queued_job_ids:
            return self.probe(job_id, allow_queued_job_ids=allow_queued_job_ids)
        return self.probe(job_id) if self.probe else ''

    def start(self, job_id='', references=()):
        targets = self.references((job_id, references))
        for ident in tuple(targets):
            targets.update(self.job_references(ident))
        with self.lock:
            from core.product_job_deletion import assert_job_available
            for ident in targets:
                assert_job_available(self.root, ident)
            if any(row.deleting and row.targets.intersection(targets) for row in self.claims):
                raise ValueError('กำลังลบไฟล์ของงานนี้หรือไฟล์อ้างอิง • รอให้เสร็จก่อนเริ่มงาน')
            claim = Claim(self, targets)
            self.claims.add(claim)
            return claim

    def reserve_delete(self, job_ids, skip_busy=False, allow_queued_job_ids=()):
        targets = self.references(job_ids)
        if not targets:
            raise ValueError('เป้าหมายลบไม่ถูกต้อง')
        with self.lock:
            allowed, skipped = set(), {}
            for job_id in sorted(targets):
                reason = ''
                if any(job_id in row.targets for row in self.claims):
                    reason = 'งานหรือการลบเดิมยังใช้ไฟล์นี้อยู่'
                reason = reason or self._busy_reason(job_id, allow_queued_job_ids)
                if reason:
                    if not skip_busy:
                        raise ValueError(f'{job_id} • {reason}')
                    skipped[job_id] = reason
                else:
                    allowed.add(job_id)
            if not allowed:
                raise ValueError('ไม่มีรายการที่ลบได้ • ' + '; '.join(f'{key}: {value}' for key, value in skipped.items()))
            claim = Claim(self, allowed, deleting=True)
            claim.allow_queued_job_ids = tuple(allow_queued_job_ids)
            claim.skipped = skipped
            self.claims.add(claim)
            return claim

    def recheck(self, claim, job_id):
        with self.lock:
            if claim is None or claim.released or claim not in self.claims or job_id not in claim.targets:
                raise ValueError('สิทธิ์ลบไม่ตรงกับเป้าหมาย • ตรวจรายการใหม่')
            reason = self._busy_reason(job_id, getattr(claim, 'allow_queued_job_ids', ()))
            if reason:
                raise ValueError(f'{job_id} • {reason}')

    @contextmanager
    def deletion(self, job_id):
        claim = getattr(self.local, 'deletion', None)
        previous = claim
        if claim is not None and job_id not in claim.targets:
            reason = getattr(claim, 'skipped', {}).get(job_id, 'รายการนี้ไม่ได้ถูกจองลบ • ตรวจรายการใหม่')
            raise ValueError(f'{job_id} • {reason}')
        owned = bool(claim and job_id in claim.targets and not claim.released)
        if not owned:
            claim = self.reserve_delete([job_id])
        try:
            self.local.deletion = claim
            self.recheck(claim, job_id)
            yield claim
        finally:
            self.local.deletion = previous
            if not owned:
                claim.release()

    def run_delete(self, claim, function, *args):
        previous = getattr(self.local, 'deletion', None)
        self.local.deletion = claim
        try:
            return function(*args)
        finally:
            self.local.deletion = previous
            claim.release()


def _app_root(app):
    library = getattr(app, 'video_library', None)
    root = getattr(library, 'root', None)
    if not isinstance(root, (str, Path)):
        product_root = getattr(getattr(app, 'products', None), 'root', None)
        story_root = getattr(getattr(app, 'stories', None), 'root', None)
        manager_root = product_root if isinstance(product_root, (str, Path)) else story_root
        root = Path(manager_root).parent.parent if isinstance(manager_root, (str, Path)) else None
    return root


def app_guard(app):
    root = _app_root(app)
    if root is None:
        raise ValueError('ไม่พบพื้นที่ไฟล์งานสำหรับตรวจสิทธิ์ลบ')
    guard = guard_for(root)
    probe = getattr(app, '_job_delete_reason', None)
    if callable(probe):
        guard.probe = probe
    return guard


def uses_job_files(selector, *, serialize=False):
    """Reserve before a synchronous start; workers retain their own claim."""
    def decorate(function):
        @functools.wraps(function)
        def wrapped(app, *args, **kwargs):
            # Legacy isolated adapters without a filesystem cannot delete it.
            if _app_root(app) is None:
                return function(app, *args, **kwargs)
            guard = app_guard(app)
            if serialize:
                # Only creation/dispatch, never the long-running worker body.
                with guard.lock, guard.start(references=selector(app, *args, **kwargs)):
                    return function(app, *args, **kwargs)
            with guard.start(references=selector(app, *args, **kwargs)):
                return function(app, *args, **kwargs)
        return wrapped
    return decorate


def guarded_thread(app, job_id, target, args=(), references=(), **kwargs):
    """The claim exists even while the OS has not scheduled the new thread."""
    if _app_root(app) is None:
        worker = threading.Thread(target=target, args=args, **kwargs)
        worker.start()
        return worker
    guard = app_guard(app)
    claim = guard.start(job_id, (references, args))
    def run():
        try:
            return target(*args)
        finally:
            claim.release()
    try:
        worker = threading.Thread(target=run, **kwargs)
        worker.start()
        return worker
    except BaseException:
        claim.release()
        raise
