"""Local, opt-in intro splice after a randomized opening. No provider calls."""
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from fractions import Fraction

from core.atomic_json import AtomicJsonFile
from core.audio_mixer import AudioMixer
from core.cancellable_process import check_cancelled
from core.render_backend import run_render as run_cancellable

EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.m4v', '.avi'}
MAX_INTRO_BYTES = 500 * 1024 * 1024


def choose_intro_point(source, duration, fps, seed, ffmpeg_path='', cancel_event=None):
    """Prefer quiet beats in the opening; keep identical jobs stable on retry.

    The 4–12s window contracts to 25–65% for short clips. Silence is a
    preference, not a generation blocker or a claim of semantic speech recognition.
    Only analyze the opening audio, before added music can hide speech pauses.
    """
    check_cancelled(cancel_event)
    if duration * fps < 2:
        return {'insert_at':duration, 'selection':'short_source_end', 'search_window':[0, duration]}
    low, high = min(4.0, duration*.25), min(12.0, duration*.65)
    rng = random.Random(hashlib.sha256(str(seed).encode('utf-8')).digest())
    mixer = AudioMixer(ffmpeg_path)
    quiet, start = [], None
    try:
        result = run_cancellable([str(mixer.ffmpeg), '-hide_banner', '-nostats', '-i', str(source),
            '-t', str(high), '-map', '0:a:0', '-vn', '-af', 'silencedetect=noise=-38dB:d=0.25',
            '-f', 'null', os.devnull], cancel_event=cancel_event, timeout=30)
        if result.returncode == 0:
            for event, value in re.findall(r'silence_(start|end):\s*(-?[0-9.]+)', result.stderr):
                if event == 'start':
                    start = max(0.0, float(value))
                elif start is not None:
                    quiet.append((start, float(value)))
                    start = None
            if start is not None:
                quiet.append((start, high))
    except (OSError, subprocess.SubprocessError):
        pass  # Missing/undecodable audio must not stop an otherwise playable clip.
    check_cancelled(cancel_event)
    windows = []
    for begin, end in quiet:
        first = math.ceil(max(low, begin + .08) * fps)
        last = math.floor(min(high, end - .08) * fps)
        if first <= last:
            windows.append((first, last))
    method = 'random_quiet_beat' if windows else 'random_opening_no_pause'
    first, last = rng.choice(windows) if windows else (math.ceil(low*fps), math.floor(high*fps))
    frame = rng.randint(first, max(first, last))
    return {'insert_at':min(frame/fps, duration-1/fps), 'selection':method, 'search_window':[low, high]}


def intro_options(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or type(value.get('enabled', False)) is not bool:
        raise ValueError('ตัวเลือกอินโทรไม่ถูกต้อง')
    file = value.get('file', '')
    if not isinstance(file, str) or (file and not re.fullmatch(r'assets/intro/[a-f0-9]{64}\.(mp4|mov|mkv|webm|m4v|avi)', file)):
        raise ValueError('ไฟล์อินโทรไม่ใช่ไฟล์ที่นำเข้าไว้ในโปรแกรม')
    if value.get('enabled') and not file:
        raise ValueError('กรุณาเลือกวิดีโออินโทรในหมวดตกแต่งคลิปก่อน')
    return {'enabled': value.get('enabled', False), 'file': file}


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inspect_video(source, ffmpeg_path='', cancel_event=None):
    mixer = AudioMixer(ffmpeg_path)
    result = run_cancellable([str(mixer.ffprobe), '-v', 'error', '-show_streams', '-show_format',
                              '-of', 'json', str(source)], cancel_event=cancel_event, timeout=30)
    if result.returncode:
        raise ValueError('อ่านวิดีโออินโทรไม่สำเร็จ กรุณาเลือกไฟล์วิดีโอที่เปิดเล่นได้')
    data = json.loads(result.stdout)
    video = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'
                  and not s.get('disposition', {}).get('attached_pic')), None)
    duration = float((video or {}).get('duration') or data.get('format', {}).get('duration') or 0)
    if not video or not math.isfinite(duration) or duration <= 0:
        raise ValueError('ไฟล์นี้ไม่มีวิดีโอที่เล่นได้ ไม่ใช้ภาพนิ่งหรือไฟล์เสียงแทนอินโทร')
    # ffmpeg applies display rotation before filtering.
    rotation = next((int(s.get('rotation', 0)) for s in video.get('side_data_list', []) if 'rotation' in s), 0)
    width, height = int(video['width']), int(video['height'])
    if abs(rotation) % 180 == 90:
        width, height = height, width
    try:
        fps=float(Fraction(video.get('avg_frame_rate') or '30'))
    except (ValueError, ZeroDivisionError):
        fps=30.0
    return {'duration':duration, 'width':width, 'height':height, 'fps':fps if 1 <= fps <= 120 else 30.0,
            'has_audio':any(s.get('codec_type') == 'audio' for s in data.get('streams', []))}


class IntroLibrary:
    asset_folder = 'intro'
    settings_name = 'intro_settings.json'
    def __init__(self, root, ffmpeg_path=''):
        self.root = Path(root).resolve()
        self.ffmpeg_path = ffmpeg_path
        self.store = AtomicJsonFile(self.root/'workspace'/self.settings_name)

    def state(self):
        data = self.store.read({})
        return {'settings':self.defaults(data.get('settings')), 'assets':data.get('assets', [])}

    @staticmethod
    def defaults(value):
        options = intro_options(value)
        if isinstance(value, dict) and 'targets' in value:
            targets = value['targets']
            if (not isinstance(targets, dict) or set(targets) != {'story', 'drama'}
                    or any(type(v) is not bool for v in targets.values())):
                raise ValueError('กรุณาเลือกประเภทงานอินโทรให้ถูกต้อง')
            options['targets'] = dict(targets)
        return options

    def validate(self, value):
        options = intro_options(value)
        if options['enabled']:
            source = (self.root/options['file']).resolve()
            if self.root/'assets'/'intro' != source.parent or not source.is_file() or _digest(source) != source.stem:
                raise ValueError('ไฟล์อินโทรที่บันทึกไว้หายหรือถูกเปลี่ยน กรุณานำเข้าใหม่')
        return options

    def save(self, value):
        options = self.defaults(value)
        self.validate({'enabled':options['enabled'] or any(options.get('targets', {}).values()),
                       'file':options['file']})
        self.store.update(lambda data:{**data, 'settings':options}, default={})
        return self.state()

    def import_file(self, path):
        source = Path(path).resolve()
        if source.suffix.lower() not in EXTENSIONS or not source.is_file():
            raise ValueError('กรุณาเลือกไฟล์วิดีโออินโทร ไม่ใช่รูปภาพหรือไฟล์เสียง')
        if not 0 < source.stat().st_size <= MAX_INTRO_BYTES:
            raise ValueError('ไฟล์อินโทรต้องมีขนาดไม่เกิน 500 MB')
        folder = self.root/'assets'/self.asset_folder
        folder.mkdir(parents=True, exist_ok=True)
        # Probe/hash the copied snapshot, never overwrite the user's source.
        with tempfile.TemporaryDirectory(prefix='intro-import-', dir=folder) as tmp:
            snapshot = Path(tmp)/('source'+source.suffix.lower())
            shutil.copy2(source, snapshot)
            info = inspect_video(snapshot, self.ffmpeg_path)
            target = folder/(_digest(snapshot)+source.suffix.lower())
            if not target.exists():
                os.replace(snapshot, target)
        asset = {'file':target.relative_to(self.root).as_posix(), 'name':source.name, **info}
        def update(data):
            assets = [a for a in data.get('assets', []) if a.get('file') != asset['file']]
            return {**data, 'assets':[asset, *assets]}
        self.store.update(update, default={})
        return {'asset':asset, **self.state()}

    def import_stream(self, stream, size, filename):
        """Receive browser bytes, not a browser-supplied server filesystem path."""
        if not 0 < size <= MAX_INTRO_BYTES:
            raise ValueError('ไฟล์อินโทรต้องมีขนาดไม่เกิน 500 MB และไม่ใช่ไฟล์ว่าง')
        if (not filename or len(filename) > 240 or '/' in filename or '\\' in filename
                or ':' in filename or any(ord(c) < 32 for c in filename)
                or Path(filename).suffix.lower() not in EXTENSIONS):
            raise ValueError('กรุณาเลือกไฟล์วิดีโออินโทรที่รองรับ')
        with tempfile.TemporaryDirectory(prefix='smartflow-intro-upload-') as tmp:
            # Fixed temporary name prevents the uploaded name from selecting a path.
            source = Path(tmp) / ('upload' + Path(filename).suffix.lower())
            with source.open('wb') as output:
                remaining = size
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError('อัปโหลดอินโทรไม่ครบ กรุณาเลือกไฟล์อีกครั้ง')
                    output.write(chunk)
                    remaining -= len(chunk)
            result = self.import_file(source)
        # Preserve the user-facing name without ever using it as a disk path.
        result['asset']['name'] = filename
        def rename(data):
            for asset in data.get('assets', []):
                if asset.get('file') == result['asset']['file']:
                    asset['name'] = filename
            return data
        self.store.update(rename, default={})
        return {'asset':result['asset'], **self.state()}


def insert_intro(root, source, output, options, ffmpeg_path='', cancel_event=None, crf=18, *, timing_source=None, seed=None):
    options = IntroLibrary(root, ffmpeg_path).validate(options)
    if not options['enabled']:
        return Path(source), {'enabled':False}
    check_cancelled(cancel_event)
    source, output = Path(source).resolve(), Path(output).resolve()
    intro = (Path(root)/options['file']).resolve()
    if source == output or intro == output:
        raise ValueError('ต้องเก็บวิดีโอต้นฉบับไว้ก่อนแทรกอินโทร')
    main, clip = inspect_video(source, ffmpeg_path, cancel_event), inspect_video(intro, ffmpeg_path, cancel_event)
    placement = choose_intro_point(timing_source or source, main['duration'], main['fps'],
        seed if seed is not None else f'{source}|{options["file"]}', ffmpeg_path, cancel_event)
    cut = placement['insert_at']
    width, height = main['width']//2*2, main['height']//2*2
    mixer = AudioMixer(ffmpeg_path)
    # Subtitles, voice, logo and music are already part of the source. Splitting
    # both streams at the same point moves them together, without deleting speech.
    video = f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={main["fps"]:.8f},format=yuv420p'
    graph = [f'[0:v:0]setpts=PTS-STARTPTS,{video},split=2[m0][m1]',
             f'[m0]trim=end={cut:.6f},setpts=PTS-STARTPTS[v0]',
             f'[m1]trim=start={cut:.6f},setpts=PTS-STARTPTS[v2]',
             f'[1:v:0]trim=duration={clip["duration"]:.6f},setpts=PTS-STARTPTS,{video}[v1]']
    audio = 'aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS'
    for i, info in enumerate((main, clip)):
        base = f'[{i}:a:0]{audio},apad' if info['has_audio'] else 'anullsrc=r=48000:cl=stereo'
        graph.append(f'{base},atrim=duration={info["duration"]:.6f}[a{i}full]')
    graph += ['[a0full]asplit=2[am0][am1]', f'[am0]atrim=end={cut:.6f},asetpts=PTS-STARTPTS[a0]',
              f'[am1]atrim=start={cut:.6f},asetpts=PTS-STARTPTS[a2]']
    if cut < main['duration'] - .001:
        graph.append('[v0][a0][v1][a1full][v2][a2]concat=n=3:v=1:a=1[v][a]')
    else:
        graph += ['[v2]nullsink', '[a2]anullsink', '[v0][a0][v1][a1full]concat=n=2:v=1:a=1[v][a]']
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='intro-render-', dir=output.parent) as tmp:
        candidate = Path(tmp)/'candidate.mp4'
        result = run_cancellable([str(mixer.ffmpeg), '-hide_banner', '-loglevel', 'error', '-y',
            '-i', str(source), '-i', str(intro), '-filter_complex_threads', '1', '-filter_complex', ';'.join(graph),
            '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-profile:v', 'high', '-preset', 'fast',
            '-crf', str(crf), '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2',
            '-movflags', '+faststart', str(candidate)], cancel_event=cancel_event)
        if result.returncode:
            raise ValueError('แทรกอินโทรไม่สำเร็จ • เก็บคลิปเดิมไว้: '+result.stderr[-400:])
        actual = inspect_video(candidate, ffmpeg_path, cancel_event)
        if abs(actual['duration']-main['duration']-clip['duration']) > .15:
            raise ValueError('ความยาวหลังแทรกอินโทรไม่ตรง • เก็บคลิปเดิมไว้')
        check_cancelled(cancel_event)
        os.replace(candidate, output)
    return output, {'enabled':True, 'file':options['file'], **placement, 'intro_duration':clip['duration'],
                    'source_duration':main['duration'], 'duration':actual['duration'], 'audio':'intro_own_audio',
                    'timing':'random_opening_prefer_pause_v2'}
