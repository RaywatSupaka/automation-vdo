"""Local-only old/new compositor comparison. All media outputs are temporary.

The legacy graph is frozen from the pre-v2 canonical render_green, not Git HEAD.
No provider, installed bridge, or customer job is read/written.
"""
import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.audio_mixer import AudioMixer
from core.cancellable_process import run_cancellable
from core.green_screen import GreenLibrary, green_options, render_green
from core.video_intro import inspect_video


def run(command):
    result = run_cancellable(command, timeout=600)
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    return result


def legacy_render(root, source, output, options):
    ff = str(AudioMixer().ffmpeg)
    info = inspect_video(source)
    width, height, fps, duration = info['width'], info['height'], info['fps'], info['duration']
    command, graph, elapsed = [ff, '-v', 'error', '-y'], [], 0.
    cycle = output.with_suffix('.mkv')
    for i, clip in enumerate(options['clips']):
        if elapsed >= duration:
            break
        asset = root / clip['file']
        length = min(inspect_video(asset)['duration'], duration - elapsed)
        elapsed += length
        command += ['-i', str(asset)]
        fit = (f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x00000000'
               if options['fit'] == 'contain' else f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}')
        graph.append(f'[{i}:v:0]trim=duration={length:.8f},setpts=PTS-STARTPTS,chromakey=0x{clip["color"][1:]}:{clip["similarity"]}:{clip["blend"]},format=rgba,{fit},setsar=1,fps={fps:.8f},colorchannelmixer=aa={options["opacity"]}[f{i}]')
    graph.append(''.join(f'[f{i}]' for i in range(len(graph))) + f'concat=n={len(graph)}:v=1:a=0[cycle]')
    started = time.perf_counter()
    run(command + ['-filter_complex_threads', '1', '-filter_complex', ';'.join(graph), '-map', '[cycle]',
                   '-an', '-c:v', 'ffv1', '-pix_fmt', 'bgra', str(cycle)])
    prepare = time.perf_counter() - started
    graph = '[0:v:0]setpts=PTS-STARTPTS[base];[1:v:0]setpts=PTS-STARTPTS[fx];[base][fx]overlay=0:0:shortest=1:format=auto,format=yuv420p[v]'
    started = time.perf_counter()
    run([ff, '-v', 'error', '-y', '-i', str(source), '-stream_loop', '-1', '-i', str(cycle),
         '-filter_complex_threads', '1', '-filter_complex', graph, '-map', '[v]', '-map', '0:a?',
         '-c:v', 'libx264', '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-preset', 'veryfast', '-crf', '18',
         '-c:a', 'copy', '-t', str(duration), '-movflags', '+faststart', str(output)])
    return {'prepare_seconds': round(prepare, 3), 'overlay_seconds': round(time.perf_counter()-started, 3),
            'cycle_bytes': cycle.stat().st_size}


def compare(effect=None, duration=4., fps=60):
    ff = str(AudioMixer().ffmpeg)
    with tempfile.TemporaryDirectory(prefix='smartflow-green-benchmark-') as directory:
        root = Path(directory)
        base = root / 'base.mp4'
        run([ff, '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c=0x273650:s=720x1280:r={fps}:d={duration}',
             '-f', 'lavfi', '-i', f'sine=frequency=440:sample_rate=48000:duration={duration}',
             '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(base)])
        if effect is None:
            effect = root / 'synthetic.mp4'
            run([ff, '-v', 'error', '-y', '-f', 'lavfi', '-i',
                 f'color=c=0x00ff00:s=1080x1920:r=60:d={duration},drawbox=x=200:y=400:w=160:h=160:color=red:t=fill,drawbox=x=780:y=1200:w=160:h=160:color=white:t=fill,boxblur=3:1',
                 '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(effect)])
        library = GreenLibrary(root)
        asset = library.import_file(effect)['asset']
        options = green_options({'enabled': True, 'clips': [{'file': asset['file']}], 'opacity': .5})
        measurements = {'source_effect': inspect_video(effect), 'duration': duration, 'output_fps': fps}
        old, new = root / 'legacy.mp4', root / 'new.mp4'
        started = time.perf_counter(); measurements['legacy'] = legacy_render(root, base, old, options)
        measurements['legacy']['wall_seconds'] = round(time.perf_counter()-started, 3)
        print(json.dumps({'stage': 'legacy_complete', **measurements['legacy']}), flush=True)
        started = time.perf_counter()
        notices = []
        _, plan = render_green(root, base, new, options, progress=notices.append)
        measurements['new'] = {k: plan[k] for k in ('strategy','cache_hit','prepare_seconds','overlay_seconds')}
        measurements['new']['wall_seconds'] = round(time.perf_counter()-started, 3)
        measurements['progress_frames_observed'] = any('เฟรม ' in n and '%' in n for n in notices)
        measurements['output'] = inspect_video(new)
        result = run([ff, '-i', str(old), '-i', str(new), '-lavfi', '[0:v][1:v]ssim;[0:v][1:v]psnr', '-f', 'null', '-'])
        measurements['similarity'] = re.findall(r'(?:SSIM Y:.*|PSNR y:.*)', result.stderr)
        def audio_hash(path):
            return run([ff, '-v', 'error', '-i', str(path), '-map', '0:a', '-c:a', 'copy', '-f', 'md5', '-']).stdout.strip()
        measurements['audio_identical'] = audio_hash(base) == audio_hash(old) == audio_hash(new)
        # A second short effect exercises sequential playback and cached reuse.
        short = root / 'short.mp4'
        run([ff, '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=0x00ff00:s=360x640:r=24:d=1,drawbox=x=10:y=10:w=60:h=60:color=yellow:t=fill',
             '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(short)])
        second = library.import_file(short)['asset']
        multi = green_options({**options, 'clips': [{'file': second['file']}, {'file': asset['file']}]})
        measurements['multi_legacy'] = legacy_render(root, base, root/'multi-old.mp4', multi)
        for name in ('multi_cold', 'multi_warm'):
            started = time.perf_counter()
            _, plan = render_green(root, base, root/(name+'.mp4'), multi)
            measurements[name] = {k: plan[k] for k in ('strategy','cache_hit','prepare_seconds','overlay_seconds')}
            measurements[name]['wall_seconds'] = round(time.perf_counter()-started, 3)
        result = run([ff, '-i', str(root/'multi-old.mp4'), '-i', str(root/'multi_cold.mp4'),
                      '-lavfi', '[0:v][1:v]ssim', '-f', 'null', '-'])
        measurements['multi_similarity'] = re.findall(r'SSIM Y:.*', result.stderr)
        return measurements


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--effect', type=Path)
    parser.add_argument('--duration', type=float, default=4.)
    parser.add_argument('--fps', type=int, default=60)
    args = parser.parse_args()
    if not .5 <= args.duration <= 10 or args.fps not in (24, 30, 60):
        parser.error('Bounded local test: 0.5–10 seconds and 24/30/60 fps')
    print(json.dumps(compare(args.effect, args.duration, args.fps), indent=2))
