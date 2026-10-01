"""Opt-in local rendering policy. No provider calls, global config or job mutation.

Sessions are thread/context local. Versionless saved work retains CPU behavior;
new jobs freeze version 1 and an encoder preference in their render snapshot.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from fractions import Fraction
from functools import wraps
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid

from core.cancellable_process import run_cancellable, check_cancelled, OperationCancelled
from core.green_progress import read_progress

_session = ContextVar('smartflow_render', default=None)
_cache, _lock = {}, threading.Lock()


def render_policy(value=None):
    value = value or {}
    version = value.get('backend_version', 0)
    preference = value.get('encoder', 'cpu' if version != 1 else 'auto')
    if preference not in {'auto', 'gpu', 'cpu'}:
        raise ValueError('ตัวเข้ารหัสต้องเป็น auto, gpu หรือ cpu')
    threads = value.get('green_filter_threads', 4) if version == 1 else 1
    if type(threads) is not int or threads not in {1, 2, 4}:
        raise ValueError('จำนวนเธรดกรีนสกรีนต้องเป็น 1, 2 หรือ 4')
    return {'backend_version': 1 if version == 1 else 0,
            'encoder': preference if version == 1 else 'cpu', 'green_filter_threads': threads}


@contextmanager
def render_session(options=None, progress=None, diagnostics=None):
    state = {'policy': render_policy(options), 'progress': progress,
             'diagnostics': Path(diagnostics) if diagnostics else None, 'records': [], 'session_id': uuid.uuid4().hex}
    token = _session.set(state)
    try:
        yield state
    finally:
        _session.reset(token)


def optimized_render():
    state = _session.get()
    return bool(state and state['policy']['backend_version'] == 1)


def has_render_session():
    return _session.get() is not None


def green_filter_threads():
    state = _session.get()
    requested = state['policy']['green_filter_threads'] if state else 1
    return min(requested, max(1, os.cpu_count() or 1))


def scene_render(method):
    @wraps(method)
    def wrapped(folder, job, index, video, client, reference_id, render, ffmpeg, cancel_event, progress):
        with render_session(job.get('render_snapshot'), progress,
                            Path(folder)/'logs'/f'render-scene-{index:02d}.json'):
            return method(folder, job, index, video, client, reference_id, render, ffmpeg, cancel_event, progress)
    return wrapped


def render_phase(phase):
    state = _session.get()
    if state:
        state['ui_phase'] = phase


def _record(state, row):
    state['records'].append(row)
    del state['records'][:-2000]
    if state['diagnostics']:
        # Diagnostics must not prevent publication of a valid video.
        from core.atomic_json import AtomicJsonFile, JsonPersistenceError
        try:
            def save(previous):
                history = previous.get('stages', []) if isinstance(previous, dict) else []
                history = [r for r in history if isinstance(r, dict) and r.get('session_id') != state['session_id']]
                return {'version': 1, 'stages': (history + [dict(r, session_id=state['session_id']) for r in state['records']])[-2000:]}
            AtomicJsonFile(state['diagnostics']).update(save, default={})
        except (OSError, JsonPersistenceError):
            pass


def _notify(state, text):
    if state.get('progress'):
        state['progress'](text)


def nvenc_available(ffmpeg, cancel_event=None):
    check_cancelled(cancel_event)
    path = Path(ffmpeg).resolve()
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    # Short process-local TTL also re-probes after a driver/session change.
    with _lock:
        saved = _cache.get(key)
        if saved and time.monotonic() - saved[0] < 300:
            return saved[1]
    try:
        result = run_cancellable([str(path), '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i', 'color=s=256x256:r=24', '-frames:v', '2', '-an',
            '-c:v', 'h264_nvenc', '-preset', 'p5', '-pix_fmt', 'yuv420p',
            '-profile:v', 'high', '-f', 'null', '-'], cancel_event=cancel_event, timeout=15)
        available = result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        available = False
    with _lock:
        _cache[key] = (time.monotonic(), available)
    return available


def encoder_command(command, encoder):
    command = list(map(str, command))
    if encoder in {'libx264', 'copy'}:
        return command
    quality = command[command.index('-crf') + 1] if '-crf' in command else '18'
    result, index = [], 0
    while index < len(command):
        arg = command[index]
        if arg in {'-preset', '-crf'}:
            index += 2
            continue
        if arg == '-c:v':
            result += [arg, encoder]
            index += 2
            continue
        result.append(arg)
        index += 1
    # CQ is an NVENC rate-control setting, not x264 CRF equivalence.
    return result[:-1] + ['-preset', 'p5', '-tune', 'hq', '-rc', 'vbr',
                         '-cq', quality, '-b:v', '0'] + result[-1:]


def _hardware_failure(stderr):
    text = str(stderr or '').lower()
    if any(s in text for s in ('no space left', 'permission denied', 'invalid data found',
                               'error opening input', 'error initializing filter', 'error reinitializing filters')):
        return False
    return any(s in text for s in ('nvenc', 'cuda', 'no capable devices',
                                  'cannot load nvcuda', 'unsupported device'))


def _validate_candidate(path, ffmpeg, cancel_event):
    executable = Path(ffmpeg)
    probe = executable.with_name('ffprobe.exe' if executable.suffix.lower() == '.exe' else 'ffprobe')
    result = run_cancellable([str(probe), '-v', 'error', '-show_streams', '-show_format',
                              '-of', 'json', str(path)], cancel_event=cancel_event, timeout=30)
    try:
        info = json.loads(result.stdout)
        video = next(s for s in info['streams'] if s.get('codec_type') == 'video')
        duration = float(video.get('duration') or info['format']['duration'])
        if (result.returncode or video.get('codec_name') != 'h264' or video.get('profile') != 'High'
                or video.get('pix_fmt') != 'yuv420p' or not math.isfinite(duration) or duration <= 0):
            raise ValueError('invalid video')
    except (ValueError, KeyError, TypeError, StopIteration) as exc:
        raise RuntimeError('ไฟล์วิดีโอไม่ผ่านการตรวจ H.264 High/yuv420p • เก็บผลงานเดิมไว้') from exc


def run_render(command, *, cancel_event=None, timeout=3600, on_wait=None,
               duration=None, label='ประกอบวิดีโอในเครื่อง'):
    """Render only explicit H.264 commands; probes/audio/alpha cache stay unchanged.

    Every attempt uses an owned temporary output. Only a completed non-empty
    candidate is returned to the caller's existing media validation/publication.
    """
    state = _session.get()
    command = list(map(str, command))
    if not state or '-c:v' not in command or command[command.index('-c:v') + 1] not in {'libx264', 'copy'}:
        return run_cancellable(command, cancel_event=cancel_event, timeout=timeout, on_wait=on_wait)
    check_cancelled(cancel_event)
    target = Path(command[-1])
    if '-n' in command and target.exists():
        raise ValueError('ไฟล์ผลลัพธ์มีอยู่แล้ว ไม่เขียนทับ')
    target.parent.mkdir(parents=True, exist_ok=True)
    source_encoder = command[command.index('-c:v') + 1]
    prefer_gpu = source_encoder == 'libx264' and state['policy']['encoder'] != 'cpu'
    encoder = 'h264_nvenc' if prefer_gpu and nvenc_available(command[0], cancel_event) else source_encoder
    reason = 'gpu_probe_unavailable' if prefer_gpu and encoder == 'libx264' else ''
    if reason:
        _notify(state, 'GPU ยังไม่พร้อม • ใช้ CPU สำรองเฉพาะการประกอบในเครื่อง')
    with tempfile.TemporaryDirectory(prefix='smartflow-encode-', dir=target.parent) as directory:
        directory = Path(directory)
        for attempt in range(2):
            check_cancelled(cancel_event)
            candidate = directory / ('candidate' + target.suffix)
            progress_file = directory / f'{attempt}.progress'
            actual = encoder_command(command, encoder)
            actual[-1] = str(candidate)
            # One progress sink per process; bound FFmpeg stderr to errors.
            for flag in ('-progress', '-stats_period', '-loglevel', '-v'):
                while flag in actual:
                    index = actual.index(flag)
                    del actual[index:index + 2]
            actual[1:1] = ['-hide_banner', '-loglevel', 'error', '-nostats',
                            '-stats_period', '0.5', '-progress', str(progress_file)]
            pid, started = [None], time.monotonic()
            row = {'stage': label, 'encoder': encoder, 'attempt': attempt + 1,
                   'fallback_reason': reason, 'status': 'running'}
            _notify(state, f'{label} • {"GPU NVIDIA" if encoder == "h264_nvenc" else "CPU"} • {encoder}')
            def notice(elapsed):
                progress = read_progress(progress_file, duration or 1e12)
                detail = f'{label} • {encoder} • PID {pid[0]} • {elapsed:.0f} วินาที'
                if progress:
                    detail += f' • เฟรม {progress["frame"]} • {progress["speed"]:.2f}x'
                    if elapsed > 0:
                        detail += f' • เฉลี่ย {progress["frame"] / elapsed:.1f} fps'
                    if duration:
                        detail += f' • {progress["percent"]}%'
                _notify(state, detail)
                if on_wait:
                    on_wait(elapsed)
            try:
                result = run_cancellable(actual, cancel_event=cancel_event, timeout=timeout,
                    on_wait=notice, on_start=lambda value: pid.__setitem__(0, value))
                check_cancelled(cancel_event)
                valid_file = candidate.is_file() and candidate.stat().st_size > 0
                if result.returncode == 0 and valid_file:
                    _validate_candidate(candidate, command[0], cancel_event)
                row.update(pid=pid[0], elapsed_seconds=round(time.monotonic()-started, 3),
                           status='complete' if result.returncode == 0 and valid_file else 'failed')
                measured = read_progress(progress_file, duration or 1e12)
                if measured:
                    row.update(frame=measured['frame'], output_seconds=measured['seconds'], speed=measured['speed'])
                _record(state, row)
                if result.returncode == 0 and valid_file:
                    notice(time.monotonic()-started)
                    check_cancelled(cancel_event)
                    os.replace(candidate, target)
                    return result
                if result.returncode == 0:
                    raise RuntimeError('ตัวเข้ารหัสจบแต่ไม่พบไฟล์วิดีโอ • เก็บผลงานเดิมไว้')
                if encoder == 'h264_nvenc' and _hardware_failure(result.stderr) and attempt == 0:
                    encoder, reason = 'libx264', 'gpu_encode_failed'
                    candidate.unlink(missing_ok=True)
                    _notify(state, 'GPU เข้ารหัสไม่สำเร็จ • ทำขั้นตอนนี้ใหม่ด้วย CPU • ไม่สร้าง AI ซ้ำ')
                    continue
                return result
            except (RuntimeError, subprocess.TimeoutExpired, OSError):
                row.update(pid=pid[0], status='interrupted', elapsed_seconds=round(time.monotonic()-started, 3))
                _record(state, row)
                raise


def resolve_fps(value, clips=(), ffprobe=None, cancel_event=None):
    """0 is explicit source-rate selection, never a migration of saved 60 fps."""
    value = int(value)
    if value != 0:
        if value not in {24, 30, 50, 60}:
            raise ValueError('FPS ต้องเป็นตามต้นฉบับ, 24, 30, 50 หรือ 60')
        return value
    if clips and ffprobe:
        result = run_cancellable([str(ffprobe), '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=avg_frame_rate', '-of', 'json', str(clips[0])],
            cancel_event=cancel_event, timeout=30)
        try:
            rate = float(Fraction(json.loads(result.stdout)['streams'][0]['avg_frame_rate']))
            # Keep fractional source rates; explicit saved24/30/50/60 stay exact.
            if math.isfinite(rate) and 1 <= rate <= 120:
                return int(rate) if rate.is_integer() else rate
        except (ValueError, KeyError, IndexError, ZeroDivisionError):
            pass
        raise ValueError('อ่าน FPS ต้นฉบับไม่ได้ • โปรดเลือก 24/30/50/60 อย่างชัดเจน')
    return 30  # Still-image sources have no native frame rate.
