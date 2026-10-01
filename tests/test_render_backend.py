import copy
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from core.cancellable_process import OperationCancelled
from core.render_backend import (render_policy, render_session, run_render,
    encoder_command, resolve_fps, optimized_render, nvenc_available)
from core.creation_queue import clean_settings
from core.drama_options import drama_render_options


class RenderBackendTests(unittest.TestCase):
    def test_actual_settings_ui_payload(self):
        from core.cancellable_process import hidden_process_kwargs
        result = subprocess.run(['node', str(Path(__file__).with_name('render_settings_ui.cjs'))],
            capture_output=True, text=True, encoding='utf-8', timeout=45, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legacy_policy_and_context_isolation(self):
        from core.render_backend import green_filter_threads
        with patch('core.render_backend.os.cpu_count', return_value=12):
            self.assertEqual(green_filter_threads(), 1)
            with render_session({'backend_version': 1}):
                self.assertEqual(green_filter_threads(), 4)
            with render_session({}):
                self.assertEqual(green_filter_threads(), 1)
        self.assertEqual(render_policy({'encoder': 'gpu'})['encoder'], 'cpu')
        self.assertFalse(optimized_render())
        with render_session({'backend_version': 1, 'encoder': 'auto'}):
            self.assertTrue(optimized_render())
            result = []
            thread = threading.Thread(target=lambda: result.append(optimized_render()))
            thread.start(); thread.join()
            self.assertEqual(result, [False])
            with render_session({}):
                self.assertFalse(optimized_render())
            self.assertTrue(optimized_render())
        self.assertFalse(optimized_render())

    def test_new_queue_and_drama_snapshot_preserved_without_legacy_migration(self):
        render = {'backend_version': 1, 'encoder': 'gpu', 'fps': 60, 'width': 720, 'height': 1280}
        saved = clean_settings({'render': render})
        render['fps'] = 24
        self.assertEqual(saved['render']['fps'], 60)
        self.assertEqual(drama_render_options({'render_snapshot': saved['render']})['render_snapshot'], saved['render'])
        self.assertNotIn('render_snapshot', drama_render_options({}))
        self.assertNotIn('backend_version', clean_settings({'render': {'fps': 60}})['render'])

    def test_legacy_scene_voice_identity_survives_new_global_encoder_fields(self):
        from core.scene_voice import render_scene_asset
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); video = root/'video.mp4'; video.write_bytes(b'saved-scene')
            job = {'id': 'STORY-TEST', 'audio_choices': {'mode': 'flow_original'}}
            render = {'width': 360, 'height': 640, 'fps': 24, 'crf': 18}
            with patch('core.video_composer.MultiFlowComposer') as composer:
                composer.return_value.compose.return_value = {'duration': 1}
                before = render_scene_asset(root, job, 1, video, None, '', render, '', None, lambda _: None)
                after = render_scene_asset(root, job, 1, video, None, '',
                    {**render, 'backend_version': 1, 'encoder': 'auto', 'green_filter_threads': 4}, '', None, lambda _: None)
            self.assertEqual(before['content_revision'], after['content_revision'])

    def test_quality_options_and_audio_copy_preserved(self):
        command = ['ffmpeg', '-i', 'a', '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
                   '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-c:a', 'copy', 'out.mp4']
        actual = encoder_command(command, 'h264_nvenc')
        self.assertNotIn('-crf', actual)
        self.assertEqual(actual[actual.index('-cq')+1], '18')
        self.assertEqual(actual[actual.index('-c:a')+1], 'copy')
        self.assertIn('yuv420p', actual)
        self.assertEqual(encoder_command(command, 'libx264'), command)

    def test_explicit_fps_never_overridden_by_source(self):
        with patch('core.render_backend.run_cancellable') as runner:
            self.assertEqual(resolve_fps(60, ['a'], 'ffprobe'), 60)
            runner.assert_not_called()
        self.assertEqual(resolve_fps(0), 30)
        with patch('core.render_backend.run_cancellable', return_value=Mock(stdout='{"streams":[{"avg_frame_rate":"24/1"}]}')):
            self.assertEqual(resolve_fps(0, ['a'], 'ffprobe'), 24)
        with patch('core.render_backend.run_cancellable', return_value=Mock(stdout='{"streams":[{"avg_frame_rate":"30000/1001"}]}')):
            self.assertAlmostEqual(resolve_fps(0, ['a'], 'ffprobe'), 30000/1001)

    def render_case(self, failures, available=True, cancel=False, empty=False):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name); target = root/'final.mp4'; target.write_bytes(b'original')
        calls, notices = [], []
        def run(command, **kwargs):
            if '-show_streams' in command:
                return Mock(returncode=0, stdout=json.dumps({'streams': [{'codec_type': 'video',
                    'codec_name': 'h264', 'profile': 'High', 'pix_fmt': 'yuv420p', 'duration': '1'}]}))
            calls.append(command)
            kwargs['on_start'](123)
            if cancel:
                raise OperationCancelled('cancel')
            error = failures.pop(0) if failures else ''
            if not error and not empty:
                Path(command[-1]).write_bytes(b'candidate')
            return subprocess.CompletedProcess(command, 1 if error else 0, '', error)
        command = ['ffmpeg', '-y', '-i', 'source.mp4', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', str(target)]
        context = render_session({'backend_version': 1, 'encoder': 'auto'}, notices.append, root/'diagnostics.json')
        return root, target, calls, notices, command, context, run, available

    def test_hardware_failure_retries_cpu_once_and_preserves_original_until_success(self):
        root, target, calls, notices, command, context, run, _ = self.render_case(['h264_nvenc: No capable devices found'])
        with context, patch('core.render_backend.nvenc_available', return_value=True), patch('core.render_backend.run_cancellable', side_effect=run):
            result = run_render(command)
        self.assertEqual(result.returncode, 0)
        self.assertEqual([c[c.index('-c:v')+1] for c in calls], ['h264_nvenc', 'libx264'])
        self.assertEqual(target.read_bytes(), b'candidate')
        self.assertTrue(all(Path(c[-1]) != target for c in calls))
        self.assertEqual(len(json.loads((root/'diagnostics.json').read_text(encoding='utf-8'))['stages']), 2)
        self.assertTrue(any('CPU' in n for n in notices))
        self.assertEqual(list(root.glob('smartflow-encode-*')), [])

    def test_unavailable_gpu_uses_cpu_without_gpu_attempt(self):
        root, target, calls, notices, command, context, run, _ = self.render_case([])
        with context, patch('core.render_backend.nvenc_available', return_value=False), patch('core.render_backend.run_cancellable', side_effect=run):
            run_render(command)
        self.assertEqual(calls[0][calls[0].index('-c:v')+1], 'libx264')

    def test_disk_error_does_not_retry_or_overwrite_final(self):
        root, target, calls, notices, command, context, run, _ = self.render_case(['h264_nvenc: No space left on device'])
        with context, patch('core.render_backend.nvenc_available', return_value=True), patch('core.render_backend.run_cancellable', side_effect=run):
            self.assertNotEqual(run_render(command).returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(target.read_bytes(), b'original')

    def test_cancel_and_empty_success_never_publish_or_fallback(self):
        for cancel in (True, False):
            with self.subTest(cancel=cancel):
                root, target, calls, notices, command, context, run, _ = self.render_case([], cancel=cancel, empty=True)
                with context, patch('core.render_backend.nvenc_available', return_value=True), patch('core.render_backend.run_cancellable', side_effect=run):
                    with self.assertRaises(RuntimeError):
                        run_render(command)
                self.assertEqual(target.read_bytes(), b'original')
                self.assertEqual(len(calls), 1)

    def test_cancel_after_validating_candidate_never_replaces_original(self):
        root, target, calls, notices, command, context, run, _ = self.render_case([])
        event = threading.Event()
        def progress(message):
            if 'PID' in message:
                event.set()
        with render_session({'backend_version': 1}, progress), patch('core.render_backend.nvenc_available', return_value=True), patch('core.render_backend.run_cancellable', side_effect=run):
            with self.assertRaises(OperationCancelled):
                run_render(command, cancel_event=event)
        self.assertEqual(target.read_bytes(), b'original')
        self.assertEqual(len(calls), 1)
        self.assertEqual(list(root.glob('smartflow-encode-*')), [])

    def test_no_context_or_alpha_does_not_change_commands(self):
        commands = [['ffmpeg', '-c:v', 'libx264', 'out.mp4'], ['ffmpeg', '-c:v', 'ffv1', 'cycle.mkv']]
        with patch('core.render_backend.run_cancellable', return_value=Mock(returncode=0)) as run:
            run_render(commands[0])
            self.assertEqual(run.call_args.args[0], commands[0])
            with render_session({'backend_version': 1}):
                run_render(commands[1])
                self.assertEqual(run.call_args.args[0], commands[1])


class RenderLocalMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.video_logo import locate_ffmpeg
        cls.ffmpeg = locate_ffmpeg()
        cls.probe = cls.ffmpeg.with_name('ffprobe.exe' if cls.ffmpeg.suffix == '.exe' else 'ffprobe')

    def media(self, folder, name='source', fps=24, tone=440, duration=1):
        from core.cancellable_process import run_cancellable
        output = folder/(name+'.mp4')
        result = run_cancellable([str(self.ffmpeg), '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=s=360x640:r={fps}',
            '-f', 'lavfi', '-i', f'sine=frequency={tone}:sample_rate=48000', '-t', str(duration),
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-c:a', 'aac', '-ac', '2', str(output)], timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return output

    def info(self, path):
        from core.cancellable_process import run_cancellable
        return json.loads(run_cancellable([str(self.probe), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]).stdout)

    def test_matching_native_clips_copy_and_mismatch_encodes(self):
        from core.flow_native_audio import compose_native
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            clips = [self.media(folder, 'first'), self.media(folder, 'second', tone=880)]
            with render_session({'backend_version': 1, 'encoder': 'cpu'}):
                result = compose_native(clips, folder/'copy.mp4', str(self.ffmpeg), width=360, height=640, fps=24)
                self.assertEqual(result['video_encoding'], 'copy')
                self.assertAlmostEqual(result['duration'], 2, delta=.1)
                result = compose_native(clips, folder/'encode.mp4', str(self.ffmpeg), width=360, height=640, fps=30)
                self.assertEqual(result['video_encoding'], 'encoded')
                self.assertEqual(self.info(folder/'encode.mp4')['streams'][0]['avg_frame_rate'], '30/1')
            # Fast path keeps the proven audio normalization at scene boundaries.
            compose_native(clips, folder/'legacy.mp4', str(self.ffmpeg), width=360, height=640, fps=24)
            from core.cancellable_process import run_cancellable
            hashes = [run_cancellable([str(self.ffmpeg), '-v', 'error', '-i', str(folder/name),
                '-map', '0:a', '-f', 'hash', '-']).stdout for name in ('copy.mp4', 'legacy.mp4')]
            self.assertEqual(hashes[0], hashes[1])

    def test_fractional_source_rate_is_kept_and_saved_sixty_stays_sixty(self):
        from core.flow_native_audio import compose_native
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = self.media(root, fps='30000/1001')
            with render_session({'backend_version': 1, 'encoder': 'cpu'}):
                plan = compose_native([source], root/'source-rate.mp4', str(self.ffmpeg), width=360, height=640, fps=0)
                self.assertAlmostEqual(plan['fps'], 30000/1001)
                sixty = compose_native([source], root/'sixty.mp4', str(self.ffmpeg), width=360, height=640, fps=60)
                self.assertEqual(sixty['fps'], 60)

    def test_new_green_three_effect_cycle_cache_and_base_audio_preserved(self):
        from core.green_screen import GreenLibrary, render_green
        from core.cancellable_process import run_cancellable
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = self.media(root, 'base', duration=4)
            library = GreenLibrary(root, str(self.ffmpeg))
            clips = [{'file': library.import_file(self.media(root, f'fx{i}', tone=800+i*400))['asset']['file']} for i in range(3)]
            options = {'enabled': True, 'clips': clips}
            with render_session({'backend_version': 1, 'encoder': 'cpu'}):
                first, plan = render_green(root, source, root/'green1.mp4', options, str(self.ffmpeg))
                second, cached = render_green(root, source, root/'green2.mp4', options, str(self.ffmpeg))
            self.assertEqual(plan['filter_threads'], min(4, __import__('os').cpu_count() or 1))
            self.assertFalse(plan['cache_hit']); self.assertTrue(cached['cache_hit'])
            self.assertEqual(first.read_bytes(), second.read_bytes())
            hashes = [run_cancellable([str(self.ffmpeg), '-v', 'error', '-i', str(p), '-map', '0:a', '-f', 'hash', '-']).stdout for p in (source, first)]
            self.assertEqual(hashes[0], hashes[1])

    def test_actual_gpu_profile_audio_and_combined_subtitle_logo(self):
        from core.video_logo import VideoLogoRenderer
        from core.subtitle_renderer import SubtitleVideoRenderer
        from PIL import Image
        if not nvenc_available(self.ffmpeg):
            self.skipTest('No usable NVIDIA encoder on this host')
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); source = self.media(folder)
            logo = folder/'logo.png'; Image.new('RGBA', (32, 32), (255, 255, 0, 180)).save(logo)
            subtitle = folder/'sub.srt'; subtitle.write_text('1\n00:00:00,000 --> 00:00:00,800\nทดสอบเสียงและภาพ\n', encoding='utf-8')
            with render_session({'backend_version': 1, 'encoder': 'gpu'}) as state:
                result = SubtitleVideoRenderer(str(self.ffmpeg)).render(source, subtitle, folder/'gpu.mp4',
                    logo_overlay={'file': str(logo), 'opacity': .7, 'size_percent': 16, 'position': 'top_right', 'margin': 20})
                self.assertTrue(result['logo_included'])
                self.assertEqual(state['records'][-1]['encoder'], 'h264_nvenc')
            info = self.info(folder/'gpu.mp4')
            video = info['streams'][0]
            self.assertEqual((video['codec_name'], video['profile'], video['pix_fmt']), ('h264', 'High', 'yuv420p'))
            self.assertTrue(any(s['codec_type'] == 'audio' for s in info['streams']))
            self.assertAlmostEqual(float(info['format']['duration']), 1, delta=.1)


if __name__ == '__main__':
    unittest.main()
