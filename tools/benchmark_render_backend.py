"""CPU/GPU/local copy benchmark. Owned temp media only; no bridge/AI/Final writes."""
import json
import argparse
import hashlib
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.video_logo import locate_ffmpeg, VideoLogoRenderer
from core.video_composer import MultiFlowComposer
from core.cancellable_process import run_cancellable
from core.render_backend import render_session, nvenc_available
from core.video_intro import inspect_video
from PIL import Image


def run(args):
    result = run_cancellable(args, timeout=600)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return result


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=2)
    parser.add_argument('--source', nargs=2)
    args = parser.parse_args()
    ffmpeg = str(locate_ffmpeg())
    report = {'nvenc_available': nvenc_available(ffmpeg), 'runs': []}
    originals = {p: digest(p) for p in (args.source or [])}
    with tempfile.TemporaryDirectory(prefix='smartflow-render-benchmark-') as directory:
        root = Path(directory)
        clips = []
        for index in range(2):
            path = root/f'source{index}.mp4'
            if args.source:
                run([ffmpeg, '-v', 'error', '-i', args.source[index], '-t', str(args.seconds), '-c', 'copy', str(path)])
            else:
                run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=720x1280:rate=24',
                    '-f', 'lavfi', '-i', f'sine=frequency={440*(index+1)}:sample_rate=48000',
                    '-t', str(args.seconds), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-profile:v', 'high',
                    '-c:a', 'aac', '-ac', '2', str(path)])
            clips.append(path)
        logo = root/'logo.png'
        Image.new('RGBA', (80, 80), (0, 200, 255, 180)).save(logo)
        finals = {}
        for fps in (24, 60):
            for mode in ('legacy', 'cpu', 'gpu'):
                if mode == 'gpu' and not report['nvenc_available']:
                    continue
                started = time.perf_counter()
                with render_session({} if mode == 'legacy' else {'backend_version': 1, 'encoder': mode}) as state:
                    # Legacy and versioned sessions use the same public composer.
                    joined = root/f'{mode}-{fps}-joined.mp4'
                    plan = MultiFlowComposer(ffmpeg).compose(clips, joined, width=720, height=1280, fps=fps,
                        audio_choices={'mode': 'flow_original', 'allow_silent': False}, transition_sec=0)
                    final = root/f'{mode}-{fps}-final.mp4'
                    VideoLogoRenderer(ffmpeg).render(joined, logo, final, opacity=.65, size_percent=16,
                                                    position='top_right', margin=28)
                    row = {'mode': mode, 'fps': fps, 'elapsed': round(time.perf_counter()-started, 3),
                           'compose_strategy': plan.get('video_encoding'), 'stages': state['records'],
                           'output': inspect_video(final), 'size': final.stat().st_size}
                audio = run([ffmpeg, '-v', 'error', '-i', str(final), '-map', '0:a:0',
                             '-f', 'hash', '-hash', 'sha256', '-']).stdout.strip()
                row['audio_hash'] = audio
                finals[(mode, fps)] = final
                report['runs'].append(row)
                print(json.dumps({'finished': mode, 'fps': fps, 'elapsed': row['elapsed']}, ensure_ascii=False), flush=True)
            if ('gpu', fps) in finals:
                quality = run([ffmpeg, '-hide_banner', '-i', str(finals[('legacy', fps)]),
                    '-i', str(finals[('gpu', fps)]), '-filter_complex', '[0:v][1:v]ssim', '-an', '-f', 'null', '-'])
                match = re.search(r'All:([0-9.]+)', quality.stderr)
                report[f'gpu_vs_cpu_ssim_{fps}'] = float(match.group(1)) if match else None
    # Do not expose expired temporary paths as usable results.
    for row in report['runs']:
        row['output'].pop('path', None)
    report['originals_unchanged'] = all(digest(p) == expected for p, expected in originals.items())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
