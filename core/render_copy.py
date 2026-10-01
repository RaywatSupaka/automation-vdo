"""Conservative native concat fast path; every uncertainty uses normal rendering."""
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import time

from core.cancellable_process import run_cancellable, check_cancelled
from core.render_backend import optimized_render, _session, _record, _notify


def _probe(path, ffprobe, cancel_event):
    result = run_cancellable([str(ffprobe), '-v', 'error', '-show_streams', '-show_format',
        '-show_data_hash', 'sha256', '-of', 'json', str(path)], cancel_event=cancel_event, timeout=30)
    if result.returncode:
        raise ValueError('probe failed')
    return json.loads(result.stdout)


def stream_signature(info, width, height, fps, keep_audio):
    streams = info.get('streams') or []
    video = [s for s in streams if s.get('codec_type') == 'video']
    audio = [s for s in streams if s.get('codec_type') == 'audio']
    if len(video) != 1 or len(streams) != 1 + len(audio) or len(audio) > 1 or (keep_audio and not audio):
        return None
    v = video[0]
    if (v.get('codec_name') != 'h264' or v.get('profile') != 'High' or v.get('pix_fmt') != 'yuv420p'
            or v.get('width') != width or v.get('height') != height
            or v.get('sample_aspect_ratio') not in {'1:1', '1/1'}
            or v.get('field_order') != 'progressive' or not v.get('extradata_hash')):
        return None
    if any(s.get('rotation', 0) != 0 for s in v.get('side_data_list', [])):
        return None
    try:
        if abs(float(Fraction(v['avg_frame_rate'])) - fps) > 1e-6 or abs(float(Fraction(v['r_frame_rate'])) - fps) > 1e-6:
            return None
        duration = float(v['duration'])
        if abs(float(v['start_time'])) > .001 or abs(int(v['nb_frames']) / fps - duration) > 1 / fps:
            return None
        if abs(float(info['format']['duration']) - duration) > 1 / fps:
            return None
        if keep_audio:
            a = audio[0]
            if (a.get('codec_name') != 'aac' or a.get('profile') != 'LC'
                    or not a.get('extradata_hash') or not a.get('channel_layout')
                    or abs(float(a['start_time'])) > .001
                    or abs(float(a['duration']) - duration) > .025):
                return None
    except (ValueError, KeyError, ZeroDivisionError):
        return None
    vkeys = ('codec_name', 'codec_tag_string', 'profile', 'level', 'pix_fmt', 'width', 'height',
             'sample_aspect_ratio', 'field_order', 'time_base', 'r_frame_rate', 'avg_frame_rate',
             'extradata_hash', 'color_range', 'color_space', 'color_transfer', 'color_primaries')
    signature = [tuple(v.get(k) for k in vkeys)]
    if keep_audio:
        signature.append(tuple(audio[0].get(k) for k in ('codec_name', 'profile', 'sample_rate',
            'channels', 'channel_layout', 'time_base', 'extradata_hash')))
    return tuple(signature)


def try_native_copy(clips, target, ffmpeg, ffprobe, width, height, fps, keep_audio, gain, cancel_event):
    if not optimized_render() or gain != 1:
        return False
    state, started = _session.get(), time.monotonic()
    try:
        infos = [_probe(p, ffprobe, cancel_event) for p in clips]
        signatures = [stream_signature(info, width, height, fps, keep_audio) for info in infos]
        if not signatures[0] or any(sig != signatures[0] for sig in signatures):
            return False
        total = sum(float(next(s for s in info['streams'] if s['codec_type'] == 'video')['duration']) for info in infos)
        expected_frames = sum(int(next(s for s in info['streams'] if s['codec_type'] == 'video')['nb_frames']) for info in infos)
        with tempfile.TemporaryDirectory(prefix='smartflow-concat-', dir=Path(target).parent) as directory:
            listing = Path(directory) / 'concat.txt'
            paths = [Path(p).resolve().as_posix() for p in clips]
            if any('\n' in p or '\r' in p for p in paths):
                return False
            listing.write_text('\n'.join("file '" + p.replace("'", "'\\''") + "'" for p in paths), encoding='utf-8')
            _notify(state, 'รวมฉากที่รูปแบบตรงกัน • คัดลอกภาพ ไม่เข้ารหัสภาพซ้ำ • จัดเสียงให้ตรงฉาก')
            command = [str(ffmpeg), '-v', 'error', '-n', '-copyts', '-f', 'concat', '-safe', '0', '-i', str(listing)]
            if keep_audio:
                # AAC priming/padding belongs to each source, not to a seamless
                # joined stream. Decode/trim each audio source exactly as the
                # proven native composer does; only video is stream-copied.
                filters = []
                for index, (path, info) in enumerate(zip(paths, infos), 1):
                    command += ['-i', path]
                    length = next(s for s in info['streams'] if s['codec_type'] == 'video')['duration']
                    filters.append(f'[{index}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,'
                        f'asetpts=PTS-STARTPTS,apad,atrim=duration={float(length):.6f},asetpts=PTS-STARTPTS,volume=1.0000[a{index}]')
                filters.append(''.join(f'[a{i}]' for i in range(1, len(paths)+1)) + f'concat=n={len(paths)}:v=0:a=1[audio]')
                command += ['-filter_complex', ';'.join(filters), '-map', '0:v:0', '-map', '[audio]', '-c:a', 'aac', '-b:a', '192k']
            else:
                command += ['-map', '0:v:0', '-an']
            command += ['-c:v', 'copy', '-avoid_negative_ts', 'disabled', '-movflags', '+faststart', str(target)]
            result = run_cancellable(command, cancel_event=cancel_event, timeout=3600)
            if result.returncode:
                return False
            output = _probe(target, ffprobe, cancel_event)
            video = next(s for s in output['streams'] if s['codec_type'] == 'video')
            if (abs(float(output['format']['duration']) - total) > max(.08, 2 / fps)
                    or int(video.get('nb_frames', 0)) != expected_frames
                    or stream_signature(output, width, height, fps, keep_audio) != signatures[0]):
                return False
            # Inspect decoded presentation timestamps, not just container metadata.
            frames = run_cancellable([str(ffprobe), '-v', 'error', '-select_streams', 'v:0',
                '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'csv=p=0', str(target)],
                cancel_event=cancel_event, timeout=3600)
            times = [float(line.split(',')[0]) for line in frames.stdout.splitlines() if line and line.split(',')[0].replace('.', '', 1).isdigit()]
            if (frames.returncode or frames.stderr.strip() or len(times) != expected_frames
                    or any(abs(b - a - 1 / fps) > .002 for a, b in zip(times, times[1:]))):
                return False
            check_cancelled(cancel_event)
            _record(state, {'stage': 'รวมฉากโดยไม่เข้ารหัสซ้ำ', 'encoder': 'copy', 'status': 'complete',
                            'elapsed_seconds': round(time.monotonic()-started, 3)})
            return True
    except (ValueError, KeyError, IndexError, TypeError):
        return False
