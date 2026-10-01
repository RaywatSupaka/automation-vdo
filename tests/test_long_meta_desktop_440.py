"""Offline desktop contract for the gated 16:9 Meta long-video route."""
import base64
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import wave
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image

from core.creation_queue import CreationQueue
from core.atomic_json import AtomicJsonFile
from core.long_video import long_video_settings
from core.long_video_render import LongFlowBatchComposer, LongMetaBatchComposer
from core.story_manager import StoryManager
from core.story_queue import StoryBatchQueue
from core.video_library import VideoLibrary
from ui.main_window import interrupted_story_restart_candidate


LONG = {'version': 2, 'duration_seconds': 180, 'scene_count': 18}


class LongMetaDesktopTests(unittest.TestCase):
    def test_restart_resumes_only_owned_running_long_meta_scene(self):
        now = datetime.now()
        job = {'status': 'running', 'cancel_requested': False,
               'updated_at': (now - timedelta(hours=7)).isoformat(),
               'long_video': LONG, 'video_generation_mode': 'meta_ai',
               'ai_status': 'ready', 'scene_count': 18,
               'generated_images': [f'generated/scene_{n:02d}.png' for n in range(1, 19)],
               'pipeline_stage': 'meta_ai'}
        self.assertFalse(interrupted_story_restart_candidate(job, now=now))
        self.assertTrue(interrupted_story_restart_candidate(job, now=now, owned_meta_receipt=True))
        self.assertFalse(interrupted_story_restart_candidate({**job, 'status': 'error'}, now=now, owned_meta_receipt=True))
        self.assertFalse(interrupted_story_restart_candidate({**job, 'cancel_requested': True}, now=now, owned_meta_receipt=True))
        self.assertFalse(interrupted_story_restart_candidate({**job, 'pipeline_stage': 'chatgpt'}, now=now, owned_meta_receipt=True))

    def test_disabled_capability_rejects_new_job_and_both_queue_paths(self):
        self.assertEqual(long_video_settings({**LONG, 'video_generation_mode': 'meta_ai'})['aspect_ratio'], '16:9')
        with patch('core.long_video.META_LANDSCAPE_GENERATION_VERIFIED', False), tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            queue = CreationQueue(temp)
            batch = StoryBatchQueue(temp)
            with self.assertRaisesRegex(ValueError, 'รอยืนยัน'):
                manager.create('เรื่องยาว', video_generation_mode='meta_ai', long_video=LONG)
            with self.assertRaisesRegex(ValueError, 'รอยืนยัน'):
                queue.enqueue('story', ['เรื่องยาว'], video_generation_mode='meta_ai', long_video=LONG)
            with self.assertRaisesRegex(ValueError, 'รอยืนยัน'):
                batch.enqueue_batch(['เรื่องยาว'], video_generation_mode='meta_ai', long_video=LONG)
            self.assertEqual(list(manager.root.glob('STORY-*')), [])

    def test_verified_capability_freezes_meta_mode_and_switch_keeps_old_flow(self):
        with patch('core.long_video.META_LANDSCAPE_GENERATION_VERIFIED', True), tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            job = manager.create('เรื่องใหม่', video_generation_mode='meta_ai', long_video=LONG)
            self.assertEqual(job['scene_count'], 18)
            self.assertEqual(job['aspect_ratio'], '16:9')
            self.assertEqual(job['long_video']['video_generation_mode'], 'meta_ai')
            self.assertEqual(job['scene_pipeline_version'], 0)
            self.assertEqual(job['video_source_type'], 'meta_ai_pending')
            wrong = io.BytesIO()
            Image.new('RGB', (400, 300), 'blue').save(wrong, format='PNG')
            with self.assertRaisesRegex(ValueError, '16:9'):
                manager.save_partial_image(job['id'], 1, base64.b64encode(wrong.getvalue()).decode())
            self.assertFalse((manager.root / job['id'] / 'generated' / 'scene_01.png').exists())
            five_three = io.BytesIO()
            Image.new('RGB', (500, 300), 'blue').save(five_three, format='PNG')
            with self.assertRaisesRegex(ValueError, '16:9'):
                manager.save_partial_image(job['id'], 1, base64.b64encode(five_three.getvalue()).decode())
            correct = io.BytesIO()
            Image.new('RGB', (640, 360), 'green').save(correct, format='PNG')
            manager.save_partial_image(job['id'], 1, base64.b64encode(correct.getvalue()).decode())
            fifty = manager.create('เรื่องยาวห้าสิบฉาก', video_generation_mode='meta_ai',
                                   long_video={**LONG, 'scene_count': 50})
            self.assertEqual(fifty['scene_count'], 50)
            queue = CreationQueue(temp)
            queued = queue.enqueue('story', ['เรื่องยาว'], video_generation_mode='meta_ai', long_video=LONG)['items'][0]
            self.assertEqual(queued['long_video']['video_generation_mode'], 'meta_ai')
            batch = StoryBatchQueue(temp)
            batch.enqueue_batch(['เรื่องยาว'], video_generation_mode='meta_ai', long_video=LONG)
            self.assertEqual(batch.snapshot()['items'][0]['long_video']['video_generation_mode'], 'meta_ai')

            old = manager.create('งาน Flow เดิม', video_generation_mode='google_flow', long_video=LONG)
            old['flow_clips'] = {'1': 'videos/flow_scene_01.mp4'}
            manager._save(old)
            changed = manager.set_video_generation_mode(old['id'], 'meta_ai', old['revision'])
            self.assertEqual(changed['video_generation_mode'], 'meta_ai')
            self.assertEqual(changed['long_video']['video_generation_mode'], 'meta_ai')
            self.assertEqual(changed['flow_clips'], old['flow_clips'])
            self.assertEqual(changed['video_source_type'], 'meta_ai_pending')
            with self.assertRaisesRegex(ValueError, 'งานเปลี่ยน'):
                manager.set_video_generation_mode(old['id'], 'google_flow', old['revision'])
            incompatible = manager.create('งาน Flow ภาพ 4:3', video_generation_mode='google_flow', long_video=LONG)
            landscape = io.BytesIO()
            Image.new('RGB', (400, 300), 'yellow').save(landscape, format='PNG')
            manager.save_partial_image(incompatible['id'], 1, base64.b64encode(landscape.getvalue()).decode())
            before = manager.get(incompatible['id'])
            with self.assertRaisesRegex(ValueError, 'ฉาก 1.*16:9'):
                manager.set_video_generation_mode(incompatible['id'], 'meta_ai', before['revision'])
            after = manager.get(incompatible['id'])
            self.assertEqual(after['video_generation_mode'], 'google_flow')
            self.assertEqual(after['revision'], before['revision'])
            interrupted = manager.create('Meta กำลังสร้างฉาก', video_generation_mode='meta_ai', long_video=LONG)
            receipt_file = manager.root / interrupted['id'] / 'prompts' / 'meta_video_receipts.json'
            AtomicJsonFile(receipt_file).write({'scenes': {'1': {'stage': 'send_intent', 'request_id': 'owned-1'}}})
            with self.assertRaisesRegex(ValueError, 'ยังไม่ยืนยัน'):
                manager.set_video_generation_mode(interrupted['id'], 'google_flow', interrupted['revision'])
            self.assertEqual(manager.get(interrupted['id'])['video_generation_mode'], 'meta_ai')

    def test_library_uses_selected_meta_provenance_not_archived_flow(self):
        job = {'video_generation_mode': 'meta_ai', 'video_source_type': 'meta_ai_story_composite',
               'scene_count': 18, 'long_video': LONG,
               'flow_clips': {'1': 'videos/old_flow_01.mp4'}, 'flow_clip_count': 1,
               'meta_clips': {'1': 'videos/meta_01.mp4', '2': 'videos/meta_02.mp4'},
               'meta_clip_count': 2,
               'render_plan': {'source_type': 'meta_ai_story_composite', 'meta_clip_count': 2}}
        source = VideoLibrary._video_source_summary('story', job)
        self.assertEqual(source['video_source_label'], 'Meta AI 2/18 ฉาก')
        self.assertEqual(source['source_remote_count'], 2)
        self.assertEqual(source['source_meta_count'], 2)
        self.assertEqual(source['source_local_count'], 0)

    def test_meta_chapters_have_separate_cache_and_full_voice_is_final_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            clips = []
            for index in range(18):
                clip = root / f'clip_{index+1:02d}.mp4'
                clip.write_bytes(bytes([index + 1]) * 2048)
                clips.append(clip)
            voice = root / 'narration.wav'
            voice.write_bytes(b'v' * 2048)
            chapter_calls, final_calls = [], []

            class FakeComposer:
                ffmpeg = Path('ffmpeg')

                def __init__(self, _path=''):
                    pass

                @staticmethod
                def media_info(_path):
                    return {'duration': 36.0}

                def compose(self, source, target, **options):
                    chapter_calls.append((len(source), str(options['voice_path'])))
                    Path(target).write_bytes(b'chapter' * 512)

            def fake_render(command, **_kwargs):
                final_calls.append(command)
                Path(command[-1]).write_bytes(b'final' * 512)
                return SimpleNamespace(returncode=0, stderr='')

            with (patch('core.long_video_render.MultiFlowComposer', FakeComposer),
                  patch('core.long_video_render.run_render', fake_render)):
                meta = LongMetaBatchComposer()
                output = root / 'working' / 'final.mp4'
                first = meta.compose(clips, output, [1] * 18, voice, width=640, height=360, fps=30)
                self.assertEqual(first['source_type'], 'meta_ai_story_composite')
                self.assertEqual(first['chapter_count'], 2)
                self.assertEqual([row[0] for row in chapter_calls], [10, 8])
                self.assertTrue(all('timing.wav' in row[1] for row in chapter_calls))
                self.assertEqual(final_calls[0].count(str(voice)), 1)
                self.assertTrue((output.parent / 'long_meta_chapters' / 'chapter_01.json').is_file())
                meta.compose(clips, output, [1] * 18, voice, width=640, height=360, fps=30)
                self.assertEqual(len(chapter_calls), 2)
                clips[12].write_bytes(b'changed' * 400)
                meta.compose(clips, output, [1] * 18, voice, width=640, height=360, fps=30)
                self.assertEqual([row[0] for row in chapter_calls], [10, 8, 8])

                flow = LongFlowBatchComposer()
                flow_result = flow.compose(clips, output, [1] * 18, voice, width=640, height=360, fps=30)
                self.assertEqual(flow_result['source_type'], 'google_flow_story_composite')
                self.assertEqual([row[0] for row in chapter_calls], [10, 8, 8, 10, 8])
                self.assertTrue((output.parent / 'long_flow_chapters' / 'chapter_01.json').is_file())

    @unittest.skipUnless(os.environ.get('SMARTFLOW_REAL_LONG_META_SMOKE') == '1', 'real FFmpeg smoke is opt-in')
    def test_real_ffmpeg_eighteen_clip_meta_chapters(self):
        from core.video_logo import locate_ffmpeg
        try:
            ffmpeg = locate_ffmpeg()
            ffprobe = ffmpeg.with_name('ffprobe.exe' if ffmpeg.suffix.lower() == '.exe' else 'ffprobe')
            if not ffprobe.is_file():
                self.skipTest('FFprobe unavailable')
        except Exception:
            self.skipTest('FFmpeg unavailable')
        with tempfile.TemporaryDirectory(prefix='smartflow-long-meta-smoke-') as temp:
            root = Path(temp)
            seed = root / 'seed.mp4'
            generated = subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-y',
                '-f', 'lavfi', '-i', 'color=c=blue:s=1152x648:r=24:d=1',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(seed)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            clips = []
            for index in range(18):
                clip = root / f'meta_{index+1:02d}.mp4'
                shutil.copyfile(seed, clip)
                clips.append(clip)
            voice = root / 'voice.wav'
            with wave.open(str(voice), 'wb') as output:
                output.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                output.writeframes(b'\0\0' * 8000 * 38)
            final = root / 'working' / 'final.mp4'
            result = LongMetaBatchComposer(str(ffmpeg)).compose(
                clips, final, [1] * 18, voice, width=1152, height=648, fps=24,
                crf=28, transition_sec=.1, audio_choices={'mode': 'api'})
            probe = subprocess.run([str(ffprobe), '-v', 'error', '-show_entries',
                'stream=codec_type,width,height,pix_fmt:format=duration', '-of', 'json', str(final)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            media = json.loads(probe.stdout)
            streams = media['streams']
            video = [stream for stream in streams if stream['codec_type'] == 'video']
            audio = [stream for stream in streams if stream['codec_type'] == 'audio']
            self.assertEqual((len(video), len(audio)), (1, 1))
            self.assertEqual((video[0]['width'], video[0]['height'], video[0]['pix_fmt']), (1152, 648, 'yuv420p'))
            self.assertAlmostEqual(float(media['format']['duration']), 38, delta=1.0)
            self.assertEqual(result['chapter_count'], 2)
            self.assertTrue((final.parent / 'long_meta_chapters' / 'chapter_02.json').is_file())


if __name__ == '__main__':
    unittest.main()
