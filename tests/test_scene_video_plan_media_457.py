"""Real, local-only mixed-provider composition; no provider/browser requests."""
import copy
import array
import hashlib
import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs
from core.config import load_config
from core.scene_video_plan import ordered_assets
from core.video_composer import MultiFlowComposer


class SceneVideoPlanMedia457Tests(unittest.TestCase):
    def test_mixed_sources_keep_order_audio_and_original_bytes(self):
        composer = MultiFlowComposer(load_config().get('ffmpeg_path', ''))

        def run(*args):
            return subprocess.run(list(map(str, args)), capture_output=True,
                                  check=True, timeout=60, **hidden_process_kwargs()).stdout

        with tempfile.TemporaryDirectory(prefix='smartflow-mixed-457-') as temp:
            folder = Path(temp)
            job = {'id': 'STORY-MEDIA-457', 'product_story': {'version': 1},
                   'scene_count': 2, 'video_generation_mode': 'google_flow',
                   'scene_prompts': ['scene one', 'scene two'],
                   'scene_narrations': ['', ''], 'flow_clips': {'1': 'flow.mp4'},
                   'meta_clips': {'2': 'meta.mp4'},
                   'audio_choices': {'mode': 'flow_original'}}
            for name, color, tone in [('flow', 'red', 440), ('meta', 'blue', 880)]:
                run(composer.ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    f'color=c={color}:s=360x640:r=24:d=0.8', '-f', 'lavfi', '-i',
                    f'sine=frequency={tone}:sample_rate=48000:duration=0.8',
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                    '-shortest', folder / f'{name}.mp4')
            originals = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                         for name in ('flow.mp4', 'meta.mp4')}
            assets = ordered_assets(folder, job, fresh=True)
            self.assertEqual([row['provider'] for row in assets], ['google_flow', 'meta_ai'])
            # Freeze the same accepted assets that the real saved plan consumes.
            job['scene_video_plan'] = {'version': 1, 'revision': 1, 'scenes': {
                str(row['index']): {'asset': copy.deepcopy(row)} for row in assets}}
            clips = [folder / row['path'] for row in ordered_assets(folder, job, fresh=True)]
            for mode in ('flow_original', 'none'):
                with self.subTest(mode=mode):
                    output = folder / f'joined-{mode}.mp4'
                    result = composer.compose(clips, output, width=360, height=640,
                        fps=24, crf=25, transition_sec=0, audio_choices={'mode': mode})
                    info = json.loads(run(composer.ffprobe, '-v', 'error', '-show_streams',
                                          '-show_format', '-of', 'json', output))
                    video = next(row for row in info['streams'] if row['codec_type'] == 'video')
                    self.assertEqual((video['codec_name'], video['pix_fmt']), ('h264', 'yuv420p'))
                    self.assertEqual((video['width'], video['height']), (360, 640))
                    self.assertAlmostEqual(float(info['format']['duration']), 1.6, delta=.2)
                    self.assertEqual(result['clip_count'], 2)
                    audio = [row for row in info['streams'] if row['codec_type'] == 'audio']
                    self.assertEqual(bool(audio), mode == 'flow_original')
                    # Read actual pixels, not output metadata, to check scene order.
                    for moment, dominant in [(.25, 0), (1.1, 2)]:
                        pixel = run(composer.ffmpeg, '-v', 'error', '-ss', moment, '-i',
                            output, '-frames:v', 1, '-vf', 'scale=1:1', '-f', 'rawvideo',
                            '-pix_fmt', 'rgb24', 'pipe:1')
                        self.assertEqual(len(pixel), 3)
                        self.assertGreater(pixel[dominant], 180)
                        self.assertLess(max(pixel[i] for i in range(3) if i != dominant), 70)
                    if mode == 'flow_original':
                        # Both source tones must survive, in the matching scene.
                        for moment, expected in [(.2, 440), (1.0, 880)]:
                            pcm = run(composer.ffmpeg, '-v', 'error', '-ss', moment, '-i',
                                output, '-t', .25, '-vn', '-ac', 1, '-ar', 8000,
                                '-f', 'f32le', 'pipe:1')
                            samples = array.array('f')
                            samples.frombytes(pcm)
                            self.assertGreater(len(samples), 1000)
                            def amplitude(frequency):
                                real = sum(value * math.cos(2 * math.pi * frequency * i / 8000)
                                           for i, value in enumerate(samples))
                                imag = sum(value * math.sin(2 * math.pi * frequency * i / 8000)
                                           for i, value in enumerate(samples))
                                return math.hypot(real, imag)
                            self.assertGreater(amplitude(expected), 10)
                            self.assertGreater(amplitude(expected), 4 * amplitude(1320 - expected))
            for name, original in originals.items():
                self.assertEqual(hashlib.sha256((folder / name).read_bytes()).hexdigest(), original)
            self.assertEqual(len(ordered_assets(folder, job, fresh=True)), 2)
            # A silently replaced saved clip must not enter Final.
            (folder / 'meta.mp4').write_bytes((folder / 'flow.mp4').read_bytes())
            with self.assertRaisesRegex(ValueError, 'หลักฐาน'):
                ordered_assets(folder, job, fresh=True)


if __name__ == '__main__':
    unittest.main()
