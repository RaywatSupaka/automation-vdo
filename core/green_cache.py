"""Disposable, bounded effect cycles; never store or remove customer originals."""
import hashlib
import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path

from core.atomic_json import AtomicJsonFile, JsonPersistenceError
from core.cancellable_process import check_cancelled
from core.video_intro import _digest

MAX_ENTRY_BYTES = 256 * 1024 * 1024
MAX_CACHE_BYTES = 768 * 1024 * 1024


def cycle_key(options, width, height, fps, durations):
    payload = {'renderer': 2, 'options': options, 'width': width, 'height': height,
               'fps': fps, 'durations': durations}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _paths(root, key):
    if not re.fullmatch(r'[a-f0-9]{64}', key):
        raise ValueError('Invalid effect cache key')
    root = Path(root).resolve()
    folder = root / 'workspace' / 'cache' / 'screenfx-v2'
    if folder.resolve() != folder or not folder.resolve().is_relative_to(root):
        raise ValueError('Effect cache must stay inside its own directory')
    folder.mkdir(parents=True, exist_ok=True)
    return folder, folder / (key + '.mkv'), AtomicJsonFile(folder / 'index.json')


def _copy(source, target):
    # An immutable hard link avoids copying large alpha streams on the same disk.
    try:
        os.link(source, target)
    except OSError:
        shutil.copyfile(source, target)


def _index(store):
    data = store.read_unlocked(default={})
    if not isinstance(data, dict):
        return {}
    return {key: row for key, row in data.items()
            if re.fullmatch(r'[a-f0-9]{64}', key) and isinstance(row, dict)
            and type(row.get('size')) is int and 0 < row['size'] <= MAX_ENTRY_BYTES
            and isinstance(row.get('sha256'), str) and re.fullmatch(r'[a-f0-9]{64}', row['sha256'])
            and type(row.get('used_at')) in (float, int)}


def restore_cycle(root, key, target, cancel_event=None):
    check_cancelled(cancel_event)
    try:
        folder, path, store = _paths(root, key)
        with store.locked():
            data = _index(store)
            row = data.get(key, {})
            if (path.resolve().parent != folder or not path.is_file() or not row
                    or path.stat().st_size != row['size'] or _digest(path) != row['sha256']):
                return False
            check_cancelled(cancel_event)
            _copy(path, target)
            data[key] = {**row, 'used_at': time.time()}
            store.write_unlocked(data)
        return True
    except (OSError, ValueError, KeyError, TypeError, JsonPersistenceError):
        # Cache failure must not break a real render. target is this call's temp file.
        try:
            Path(target).unlink(missing_ok=True)
        except OSError:
            pass
        return False


def remember_cycle(root, key, source, cancel_event=None):
    check_cancelled(cancel_event)
    size = Path(source).stat().st_size
    if not 0 < size <= MAX_ENTRY_BYTES:
        return False
    staged = None
    try:
        folder, target, store = _paths(root, key)
        checksum = _digest(source)
        check_cancelled(cancel_event)
        with store.locked():
            data = _index(store)
            # Staging is created under this same cross-process lock. Any staged
            # file left here belongs to a dead writer, not an active render.
            for path in folder.glob('*.tmp'):
                if (re.fullmatch(r'[a-f0-9]{64}-[a-f0-9]{32}\.tmp', path.name)
                        and path.resolve().parent == folder and not path.is_symlink()):
                    try:
                        path.unlink()
                    except OSError:
                        return False  # Do not grow an unbounded orphan cache.
            # Discover only files created by this cache, including orphaned writes.
            files = [p for p in folder.glob('*.mkv') if re.fullmatch(r'[a-f0-9]{64}\.mkv', p.name)
                     and p.resolve().parent == folder and not p.is_symlink()]
            total = sum(p.stat().st_size for p in files if p != target)
            for path in sorted(files, key=lambda p: data.get(p.stem, {}).get('used_at', 0)):
                if total + size <= MAX_CACHE_BYTES:
                    break
                if path == target:
                    continue
                old_size = path.stat().st_size
                try:
                    path.unlink()
                except OSError:
                    continue  # Another render may still be reading it on Windows.
                total -= old_size
                data.pop(path.stem, None)
            if total + size > MAX_CACHE_BYTES:
                return False
            staged = folder / (key + '-' + uuid.uuid4().hex + '.tmp')
            _copy(source, staged)
            check_cancelled(cancel_event)
            os.replace(staged, target)
            data[key] = {'size': size, 'sha256': checksum, 'used_at': time.time()}
            store.write_unlocked(data)
        return True
    except (OSError, ValueError, KeyError, TypeError, JsonPersistenceError):
        return False
    finally:
        if staged is not None:
            try:
                staged.unlink(missing_ok=True)
            except OSError:
                pass
