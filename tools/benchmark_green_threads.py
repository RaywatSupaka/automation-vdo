"""Local-only controlled filter-thread comparison; no persistent settings changed."""
import json
import re
from pathlib import Path
import sys
import tempfile
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.cancellable_process import run_cancellable
from core.video_logo import locate_ffmpeg
from core.green_screen import render_green, GreenLibrary
from core.render_backend import render_session, nvenc_available
from core.video_intro import inspect_video


def main():
    ff = str(locate_ffmpeg())
    def run(command):
        result = run_cancellable(command, timeout=600)
        if result.returncode:
            raise RuntimeError(result.stderr[-1000:])
        return result
    rows = []
    with tempfile.TemporaryDirectory(prefix='smartflow-green-threads-') as directory:
        root = Path(directory); assets = root/'assets'/'screenfx'; assets.mkdir(parents=True)
        base = root/'base.mp4'; effect = assets/'effect.mp4'
        run([ff, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=720x1280:r=60', '-f', 'lavfi',
             '-i', 'sine=frequency=440:sample_rate=48000', '-t', '4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
             '-c:a', 'aac', str(base)])
        run([ff, '-v', 'error', '-f', 'lavfi', '-i', 'color=green:s=720x1280:r=30', '-vf',
             'drawbox=x=200:y=300:w=100:h=300:color=yellow:t=fill', '-t', '4', '-c:v', 'libx264', str(effect)])
        asset = GreenLibrary(root, ff).import_file(effect)['asset']
        options = {'enabled': True, 'clips': [{'file': asset['file']}]}
        for mode in ('cpu', 'gpu'):
            if mode == 'gpu' and not nvenc_available(ff): continue
            for threads in (1, 2, 4, 0):
                started = time.perf_counter()
                with render_session({'backend_version': 1, 'encoder': mode}) as state:
                    output, plan = render_green(root, base, root/f'{mode}-{threads}.mp4', options,
                                                ff, filter_threads=threads)
                audio = run([ff, '-v', 'error', '-i', str(output), '-map', '0:a', '-f', 'hash', '-']).stdout.strip()
                decoded = run([ff, '-v', 'error', '-i', str(output), '-map', '0:v', '-f', 'hash', '-']).stdout.strip()
                row = {'mode': mode, 'threads': threads, 'elapsed': round(plan['overlay_seconds'], 3),
                       'audio_hash': audio, 'decoded_video_hash': decoded,
                       'output': inspect_video(output), 'encoder': state['records'][-1]['encoder']}
                rows.append(row)
                print(json.dumps(row), flush=True)
        for mode in ('cpu', 'gpu'):
            first, other = root/f'{mode}-1.mp4', root/f'{mode}-4.mp4'
            if not other.is_file(): continue
            result = run([ff, '-hide_banner', '-i', str(first), '-i', str(other),
                '-filter_complex', '[0:v][1:v]ssim', '-an', '-f', 'null', '-'])
            match = re.search(r'All:([0-9.]+)', result.stderr)
            print(json.dumps({'quality':mode,'threads1_vs4_ssim':float(match.group(1)) if match else None}),flush=True)
    print(json.dumps({'results': rows}, indent=2))


if __name__ == '__main__': main()
