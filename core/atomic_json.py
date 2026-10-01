"""Durable JSON persistence shared by SmartFlow runtime state.

The desktop shell and hidden engine can be separate processes.  A normal
``threading.Lock`` therefore cannot protect a read/modify/write transaction on
its own.  This module combines a process-local re-entrant lock with a small
cross-process file lock, unique temporary files, fsync, atomic replace and a
last-known-good backup.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class JsonPersistenceError(RuntimeError):
    """Raised when existing JSON cannot be read without discarding state."""


_MISSING = object()
_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS = {}
_LOCK_DEPTH = threading.local()


def _lock_key(path):
    value = str(Path(path).resolve())
    return value.casefold() if os.name == "nt" else value


def _thread_lock(path):
    key = _lock_key(path)
    with _LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _THREAD_LOCKS[key] = lock
        return key, lock


class _ProcessFileLock:
    def __init__(self, target, timeout=10.0):
        digest = hashlib.sha256(_lock_key(target).encode("utf-8")).hexdigest()
        self.path = Path(tempfile.gettempdir()) / "smartflow-ai-json-locks" / f"{digest}.lock"
        self.timeout = max(0.5, float(timeout))
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"\0")
            self.handle.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except (OSError, PermissionError) as exc:
                if time.monotonic() >= deadline:
                    self.handle.close()
                    self.handle = None
                    raise JsonPersistenceError(f"รอสิทธิ์บันทึก JSON นานเกินกำหนด: {self.path.name}") from exc
                time.sleep(0.025)

    def __exit__(self, exc_type, exc, traceback):
        if self.handle is None:
            return False
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
        return False


class AtomicJsonFile:
    """Read and replace one JSON document without exposing partial content."""

    def __init__(self, path, *, backup_path=None, lock_timeout=10.0):
        self.path = Path(path)
        self.backup_path = Path(backup_path) if backup_path else self.path.with_name(f".{self.path.name}.bak")
        self.lock_timeout = max(0.5, float(lock_timeout))
        self._lock_key, self._thread_lock = _thread_lock(self.path)

    @contextmanager
    def locked(self):
        """Hold the process-local and cross-process lock for one transaction."""
        with self._thread_lock:
            depths = getattr(_LOCK_DEPTH, "depths", None)
            if depths is None:
                depths = {}
                _LOCK_DEPTH.depths = depths
            depth = int(depths.get(self._lock_key, 0))
            depths[self._lock_key] = depth + 1
            try:
                if depth:
                    yield self
                else:
                    with _ProcessFileLock(self.path, self.lock_timeout):
                        yield self
            finally:
                remaining = int(depths.get(self._lock_key, 1)) - 1
                if remaining > 0:
                    depths[self._lock_key] = remaining
                else:
                    depths.pop(self._lock_key, None)

    def read(self, default=_MISSING):
        with self.locked():
            return self.read_unlocked(default)

    def peek(self, default=_MISSING):
        """Read primary or backup without restoring either file on a UI poll."""
        with self.locked():
            return self.read_unlocked(default, restore_primary=False)

    def write(self, value):
        with self.locked():
            self.write_unlocked(value)
        return value

    def update(self, updater, *, default=_MISSING):
        """Keep the whole read/modify/write sequence under the same lock."""
        with self.locked():
            value = self.read_unlocked(default)
            updated = updater(value)
            if updated is not None:
                value = updated
            self.write_unlocked(value)
            return value

    @staticmethod
    def _read_path(path):
        last_error = None
        for attempt in range(5):
            try:
                raw = Path(path).read_text(encoding="utf-8")
                if not raw.strip():
                    raise ValueError("ไฟล์ JSON ว่างเปล่า")
                return json.loads(raw)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < 4:
                    time.sleep(0.02 * (attempt + 1))
        raise last_error

    def read_unlocked(self, default=_MISSING, *, restore_primary=True):
        """Read while ``locked()`` is already held; recover only from valid data."""
        from core.product_job_deletion import assert_path_available
        assert_path_available(self.path)
        primary_exists = self.path.is_file()
        primary_error = None
        if primary_exists:
            try:
                return self._read_path(self.path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                primary_error = exc

        if self.backup_path.is_file():
            try:
                recovered = self._read_path(self.backup_path)
                if restore_primary:
                    self._atomic_dump(self.path, recovered)
                return recovered
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as backup_error:
                if primary_exists:
                    raise JsonPersistenceError(
                        f"JSON หลักและไฟล์สำรองเสียหาย: {self.path}"
                    ) from backup_error
                # A missing primary does not mean a new store when a recovery
                # copy exists. Returning defaults here lets update() overwrite
                # the last remaining queue/config evidence with empty state.
                raise JsonPersistenceError(
                    f"ไม่พบ JSON หลักและไฟล์สำรองอ่านไม่ได้: {self.path}"
                ) from backup_error

        if primary_exists:
            raise JsonPersistenceError(
                f"JSON เสียหายและไม่มีไฟล์สำรองที่อ่านได้: {self.path}"
            ) from primary_error
        if default is not _MISSING:
            return copy.deepcopy(default)
        raise FileNotFoundError(self.path)

    def write_unlocked(self, value):
        """Replace primary first, then refresh the last-known-good backup."""
        self._atomic_dump(self.path, value)
        self._atomic_dump(self.backup_path, value)

    @staticmethod
    def _atomic_dump(path, value):
        path = Path(path)
        from core.product_job_deletion import assert_path_available
        assert_path_available(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            last_error = None
            for attempt in range(20):
                try:
                    os.replace(temporary, path)
                    last_error = None
                    break
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(min(0.4, 0.025 * (attempt + 1)))
            if last_error is not None:
                raise last_error
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def runtime_backup_path(project_root, target):
    """Keep recovery copies under one protected project backup directory."""
    project_root = Path(project_root).resolve()
    target = Path(target).resolve()
    try:
        relative = target.relative_to(project_root)
    except ValueError:
        digest = hashlib.sha256(str(target).encode("utf-8")).hexdigest()
        relative = Path("external") / f"{digest}.json"
    return project_root / "backups" / "runtime-state" / relative.parent / f"{relative.name}.bak"
