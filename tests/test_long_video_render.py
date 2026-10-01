import tempfile
import unittest
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.long_video_render import LongVideoBatchComposer, LongFlowBatchComposer


class LongVideoChapterRenderTests(unittest.TestCase):
    def test_real_flow_chapter_join_keeps_saved_clips_and_full_voice(self):
        from core.video_logo import locate_ffmpeg
        try:
            ffmpeg = locate_ffmpeg()
        except Exception:
            self.skipTest('FFmpeg not installed')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            clips = []
            for index in range(18):
                clip = root / f'flow_{index+1:02d}.mp4'
                clip.write_bytes(bytes([index]) * 2048)
                clips.append(clip)
            voice = root / 'voice.wav'
            with wave.open(str(voice), 'wb') as output:
                output.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                output.writeframes(b'\0\0' * 8000 * 36)
            composer = LongFlowBatchComposer(str(ffmpeg))
            calls = []
            def synthetic_flow(source, target, **options):
                calls.append(len(source))
                duration = 20 if len(source) == 10 else 16
                result = subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'lavfi', '-i', 'color=c=green:s=640x360:r=2',
                    '-f', 'lavfi', '-i', 'anullsrc=r=8000:cl=mono',
                    '-t', str(duration), '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(target)],
                    capture_output=True, text=True, timeout=60)
                if result.returncode:
                    raise AssertionError(result.stderr)
            with patch.object(composer.flow, 'compose', synthetic_flow):
                result = composer.compose(clips, root / 'flow_final.mp4', [1] * 18, voice,
                                          width=640, height=360, fps=2)
                self.assertEqual(calls, [10, 8])
                composer.compose(clips, root / 'flow_final.mp4', [1] * 18, voice,
                                 width=640, height=360, fps=2)
                self.assertEqual(calls, [10, 8])
            self.assertAlmostEqual(result['duration'], 36, delta=.5)

    def test_real_local_chapter_concat_keeps_one_voice_track(self):
        from core.video_logo import locate_ffmpeg
        try:
            ffmpeg = locate_ffmpeg()
        except Exception:
            self.skipTest('FFmpeg not installed')
        probe = ffmpeg.with_name('ffprobe.exe')
        if not probe.is_file():
            self.skipTest('FFprobe not installed')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            images = []
            for index in range(18):
                image = root / f'{index:02d}.png'
                image.write_bytes(bytes([index]) * 1024)
                images.append(image)
            voice = root / 'voice.wav'
            with wave.open(str(voice), 'wb') as output:
                output.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                output.writeframes(b'\0\0' * 8000 * 36)
            composer = LongVideoBatchComposer(str(ffmpeg))
            def synthetic_chapter(_source, target, durations, _voice, **_options):
                result = subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'lavfi', '-i', 'color=c=blue:s=640x360:r=2',
                    '-t', str(sum(durations)), '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-pix_fmt', 'yuv420p', str(target)], capture_output=True, text=True, timeout=60)
                if result.returncode:
                    raise AssertionError(result.stderr)
            with patch.object(composer.scenes, 'compose', synthetic_chapter):
                plan = composer.compose(images, root / 'out.mp4', [1] * 18, voice,
                                        width=640, height=360, fps=2)
            self.assertEqual(plan['chapter_count'], 2)
            self.assertAlmostEqual(plan['duration'], 36, delta=.5)
            probe_result = subprocess.run([str(probe), '-v', 'error', '-show_entries',
                'stream=codec_type', '-of', 'json', str(root / 'out.mp4')],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(probe_result.returncode, 0)
            self.assertEqual(probe_result.stdout.count('"codec_type"'), 2)

    def test_ten_image_chapters_reuse_only_matching_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            images = []
            for index in range(23):
                image = root / f'scene_{index+1:02d}.png'
                image.write_bytes(bytes([index]) * 1024)
                images.append(image)
            voice = root / 'narration.mp3'
            voice.write_bytes(b'v' * 2048)
            rendered = []

            class FakeSceneComposer:
                ffmpeg = Path('ffmpeg')

                def __init__(self, _path=''):
                    pass

                @staticmethod
                def duration(_path):
                    return 46.0

                def compose(self, source, target, durations, _voice, **options):
                    rendered.append((len(source), options['min_images'], options['fade_edges']))
                    Path(target).write_bytes(b'chapter' * 512)

            def fake_render(command, **_kwargs):
                Path(command[-1]).write_bytes(b'final' * 512)
                return SimpleNamespace(returncode=0, stderr='')

            with (patch('core.long_video_render.StoryVideoComposer', FakeSceneComposer),
                  patch('core.long_video_render.run_render', fake_render)):
                composer = LongVideoBatchComposer()
                output = root / 'working' / 'final.mp4'
                first = composer.compose(images, output, [1] * 23, voice)
                self.assertEqual(first['chapter_count'], 3)
                self.assertEqual(rendered, [(10, 1, False), (10, 1, False), (3, 1, False)])
                composer.compose(images, output, [1] * 23, voice)
                self.assertEqual(len(rendered), 3)
                images[12].write_bytes(b'changed' * 300)
                composer.compose(images, output, [1] * 23, voice)
                self.assertEqual(len(rendered), 4)
                self.assertEqual(rendered[-1][0], 10)


if __name__ == '__main__':
    unittest.main()
