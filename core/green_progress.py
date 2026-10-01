"""Read completed FFmpeg -progress records without changing other process runners."""
import math
from pathlib import Path


def read_progress(path, duration):
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 8192))
            text = stream.read(8192).decode('utf-8', errors='replace')
    except OSError:
        return None
    records, current = [], {}
    for line in text.splitlines():
        key, sep, value = line.partition('=')
        if not sep:
            continue
        current[key.strip()] = value.strip()
        if key == 'progress':
            records.append(current)
            current = {}
    if not records:
        return None
    row = records[-1]
    try:
        seconds = max(0., float(row['out_time_us']) / 1_000_000)
        frame = max(0, int(row['frame']))
        speed = float(row.get('speed', '').rstrip('x'))
        if not all(math.isfinite(v) for v in (seconds, speed, duration)) or duration <= 0:
            return None
        return {'seconds': min(seconds, duration), 'frame': frame,
                'percent': min(99, int(seconds / duration * 100)), 'speed': max(0., speed)}
    except (ValueError, KeyError, TypeError):
        return None


def progress_notice(path, duration, label, callback):
    def notice(elapsed):
        if callback is None:
            return
        row = read_progress(path, duration)
        if row is None:
            callback(f'{label} • รอข้อมูลเฟรมจากตัวประกอบวิดีโอ • {int(elapsed)} วินาที')
        else:
            callback(f'{label} • {row["percent"]}% • เฟรม {row["frame"]} • '
                     f'{row["seconds"]:.1f}/{duration:.1f} วินาที • {row["speed"]:.2f}x')
    return notice
