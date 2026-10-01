"""Offline speech-repeat evidence and exact-scene retry ownership."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.flow_speech_quality import audit_native_scene_speech, RepeatedNativeSpeechError, retry_prompt
from core.atomic_json import AtomicJsonFile
from core.scene_pipeline import ScenePipeline
from core.story_manager import StoryManager
from core.story_finisher import finish_story_media
from ui.main_window import MainWindow


class FlowSpeechRetryTests(unittest.TestCase):
    def test_long_once_only_clause_repeated_inside_one_scene(self):
        script = ['วางของทั้งหมดบนโต๊ะก่อนนะ', 'หยิบรถเข็นมากางให้เรียบร้อย',
                  'พร้อมออกไปแล้ว ถ้าชอบไอเดียพาน้องเที่ยวแบบนี้ กดหัวใจนะ']
        transcript = {'source_sha256': 'source-one', 'segments': [
            {'start': 0, 'end': 5, 'text': script[0]},
            {'start': 8, 'end': 14, 'text': script[1]},
            {'start': 16, 'end': 19, 'text': 'พร้อมออกไปแล้ว ถ้าชอบไอเดียพาน้องเที่ยวแบบนี้'},
            {'start': 19, 'end': 23, 'text': 'ไอเดียพาน้องเที่ยวแบบนี้ กดหัวใจนะ'},
        ]}
        result = audit_native_scene_speech(transcript, script, [8, 8, 8])
        self.assertEqual(result['status'], 'repeat_confirmed')
        self.assertEqual([row['scene'] for row in result['findings']], [3])
        self.assertIn('ไอเดียพาน้องเที่ยว', result['findings'][0]['phrase'])

    def test_intended_repeat_and_cross_scene_phrase_are_not_false_positive(self):
        scripts = ['มาจัดของกัน มาจัดของกัน', 'มาจัดของกันนะ']
        transcript = {'segments': [
            {'start': 0, 'end': 7, 'text': scripts[0]},
            {'start': 8, 'end': 15, 'text': scripts[1]},
        ]}
        self.assertEqual(audit_native_scene_speech(transcript, scripts, [8, 8])['findings'], [])
        self.assertEqual(audit_native_scene_speech(transcript, scripts, [8])['status'], 'unverified')
        self.assertEqual(audit_native_scene_speech(transcript, scripts, [8, 8], composed_duration=20)['reason'],
                         'scene_boundaries_mismatch')

    def test_quality_gate_does_not_publish_bad_final_or_subtitle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'stories' / 'STORY-TEST'
            folder.mkdir(parents=True)
            job = {'id': 'STORY-TEST', 'scene_pipeline_version': 1, 'video_generation_mode': 'google_flow',
                   'scene_count': 2, 'scene_narrations': ['วางของบนโต๊ะก่อน', 'ชอบไอเดียพาน้องเที่ยวแบบนี้'],
                   'audio_choices': {'mode': 'flow_original', 'subtitle': True, 'music': False, 'sfx': False}}
            pipeline = ScenePipeline(folder)
            for index in (1, 2):
                row = pipeline.request(index, 2, {'scene': index})
                target = folder / f'scene_{index}.mp4'
                target.write_bytes(b'v' * 2048)
                pipeline.update(index, row['revision'], phase='complete', segment=target.name, duration=8)
            source = folder / 'combined.mp4'
            source.write_bytes(b's' * 2048)
            transcript = {'source_sha256': 'same-audio', 'segments': [
                {'start': 0, 'end': 7, 'text': job['scene_narrations'][0]},
                {'start': 8, 'end': 11, 'text': job['scene_narrations'][1]},
                {'start': 11, 'end': 15, 'text': job['scene_narrations'][1]},
            ]}
            class Mixer:
                def __init__(self, *_): pass
                def duration(self, *_): return 16
            manager = SimpleNamespace(root=root / 'stories', get=lambda _: job)
            with patch('core.story_finisher.AudioMixer', Mixer), patch('core.media_audio.native_transcript', return_value=transcript):
                with self.assertRaises(RepeatedNativeSpeechError):
                    finish_story_media(root, manager, job['id'], source,
                                       {'native_subtitle_credential': 'fixture'})
            self.assertFalse((folder / 'captions' / 'story_subtitle.srt').exists())
            self.assertFalse((folder / 'videos' / 'story_short_complete.mp4').exists())
            self.assertEqual(source.read_bytes(), b's' * 2048)
            self.assertTrue((folder / 'audio' / 'flow_speech_quality.json').is_file())

    def test_retry_prompt_is_one_suffix_not_second_spoken_line(self):
        prompt = 'Spoken line: ชอบไอเดียพาน้องเที่ยวแบบนี้'
        updated = retry_prompt(prompt)
        self.assertEqual(updated.count('Spoken line:'), 1)
        self.assertEqual(retry_prompt(updated), updated)

    def test_desktop_retry_collects_only_the_failed_scene(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'STORY-TEST'
            folder.mkdir()
            pipeline = ScenePipeline(folder)
            row = pipeline.request(1, 1, {'scene': 1})
            old = folder / 'old.mp4'
            old.write_bytes(b'o' * 2048)
            pipeline.update(1, row['revision'], phase='complete', segment='old.mp4', duration=8)
            state = {'retry_id': 'retry-one', 'segment_sha256': pipeline.get(1)['segment_sha256'], 'attempt': 1}
            new = folder / 'new.mp4'
            new.write_bytes(b'n' * 2048)
            job = {'id': 'STORY-TEST', 'scene_narrations': ['พาน้องเที่ยว'], 'render_snapshot': {
                'width': 720, 'height': 1280, 'fps': 30, 'crf': 18}}
            app = MainWindow.__new__(MainWindow)
            app.stories = SimpleNamespace(root=root, get=lambda _: job,
                                          complete_native_speech_retry=Mock())
            app._collect_story_flow_clips = Mock(return_value=[new])
            app._queue_story_phase = Mock()
            app._creation_settings = Mock(return_value={})
            app.cfg = {}
            with patch('core.scene_voice.render_scene_asset', return_value={
                    'segment': 'new.mp4', 'voice': '', 'duration': 8}):
                MainWindow._retry_story_native_speech_scene(app, 'STORY-TEST', 1, state, None)
            app._collect_story_flow_clips.assert_called_once_with(
                'STORY-TEST', None, only_scene=1, fresh_scene_attempt='retry-one')
            app.stories.complete_native_speech_retry.assert_called_once_with('STORY-TEST', 1, 'retry-one')
            self.assertEqual(pipeline.get(1)['phase'], 'complete')
            self.assertEqual(pipeline.segments(1), [new.resolve()])
            self.assertEqual(old.read_bytes(), b'o' * 2048)

    def test_fresh_attempt_never_inspects_old_flow_project(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'STORY-TEST'
            folder.mkdir()
            clip = folder / 'fresh.mp4'
            clip.write_bytes(b'v' * 2048)
            commands = []
            def command(action, *args, **kwargs):
                commands.append((action, args, kwargs))
                return {'run_id': kwargs.get('run_id') or 'RUN-FRESH'}
            app = MainWindow.__new__(MainWindow)
            app.stories = SimpleNamespace(root=root, get=lambda _: {'id': 'STORY-TEST', 'scene_count': 3},
                                          mark_running=Mock(), attach_flow_clip=lambda *_: {
                                              'flow_clips': {'3': 'fresh.mp4'}})
            app.bridge = SimpleNamespace(clear_flow_progress=Mock(), queue_extension_command=command,
                                         REQUIRED_EXTENSION_VERSION='0.15.430',
                                         extension_status=lambda: {'clients': [{
                                             'version': '0.15.430', 'speech_retry_protocol': 1}]})
            app._ensure_flow_extension = Mock()
            app._wait_flow_step = Mock()
            app._wait_download = Mock(return_value=clip)
            app._close_saved_flow_tab = Mock()
            app.events = Queue()
            app._write_console = Mock()
            result = MainWindow._collect_story_flow_clips(app, 'STORY-TEST', None,
                                                           only_scene=3, fresh_scene_attempt='attempt-one')
            self.assertEqual(result, [clip])
            self.assertEqual([row[0] for row in commands], ['open_flow', 'download_flow_result'])
            self.assertTrue(commands[0][2]['run_id'].startswith('RUN-'))
            self.assertEqual(app._wait_flow_step.call_args.kwargs['expected_run_id'], commands[0][2]['run_id'])
            self.assertEqual(app._wait_download.call_args.kwargs['expected_run_id'], commands[0][2]['run_id'])
            app.bridge.extension_status = lambda: {'clients': [{'version': '0.15.430'}]}
            commands.clear()
            with self.assertRaisesRegex(RuntimeError, 'FLOW_SPEECH_RETRY_UPDATE_REQUIRED'):
                MainWindow._collect_story_flow_clips(app, 'STORY-TEST', None,
                                                     only_scene=3, fresh_scene_attempt='attempt-two')
            self.assertEqual(commands, [])

    def test_retry_archives_old_clip_and_preserves_other_scenes(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(Path(temp))
            job = manager.create('พาน้องเที่ยว', scene_count=3, video_generation_mode='google_flow')
            folder = manager.root / job['id']
            job.update(scene_count=3, scene_pipeline_version=1, scene_narrations=['ฉากแรก', 'ฉากกลาง', 'ชอบไอเดียพาน้องเที่ยวแบบนี้'],
                       scene_prompts=['first', 'middle', 'last'], generated_images=[],
                       audio_choices={'mode': 'flow_original', 'subtitle': True})
            for index in range(1, 4):
                relative = f'generated/scene_{index:02d}.png'
                target = folder / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'png-' + bytes([index]))
                job['generated_images'].append(relative)
            old_flow = folder / 'videos' / 'flow_scene_03.mp4'
            old_flow.parent.mkdir(parents=True, exist_ok=True)
            old_flow.write_bytes(b'f' * 2048)
            job['flow_clips'] = {'3': 'videos/flow_scene_03.mp4'}
            manager._save(job)
            pipeline = ScenePipeline(folder)
            old_segments = []
            for index in range(1, 4):
                row = pipeline.request(index, 3, {'scene': index})
                relative = f'audio/scene_{index}.mp4'
                target = folder / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bytes([index]) * 2048)
                pipeline.update(index, row['revision'], phase='complete', segment=relative, duration=8)
                old_segments.append(target)
            evidence = {'scene': 3, 'phrase': 'ไอเดียพาน้องเที่ยวแบบนี้'}
            audit_store = AtomicJsonFile(folder / 'audio' / 'flow_speech_quality.json')
            def audit(source):
                audit_store.write({'status': 'repeat_confirmed', 'source_sha256': source,
                                   'scene_segments': {'3': pipeline.get(3)['segment_sha256']},
                                   'findings': [evidence]})
            audit('source-a')
            with self.assertRaisesRegex(ValueError, 'หลักฐานเสียงซ้ำ'):
                manager.begin_native_speech_retry(job['id'], evidence, 'stale-source')
            retry = manager.begin_native_speech_retry(job['id'], evidence, 'source-a')
            self.assertEqual(retry['attempt'], 1)
            self.assertEqual(manager.begin_native_speech_retry(job['id'], evidence, 'source-a')['retry_id'], retry['retry_id'])
            self.assertTrue((folder / retry['history'][0]['old_clip_backup']).is_file())
            self.assertNotIn('3', manager.get(job['id'])['flow_clips'])
            with patch('core.flow_motion_plan.saved_motion_prompt', return_value='Spoken line: ชอบไอเดียพาน้องเที่ยวแบบนี้'):
                package = manager.flow_package(job['id'], 3)
            self.assertEqual(package['speech_retry_id'], retry['retry_id'])
            self.assertEqual(package['video_prompt'].count('Spoken line:'), 1)
            self.assertIn('SPEECH DELIVERY CORRECTION', package['video_prompt'])
            pipeline.begin_speech_retry(3, retry['retry_id'], retry['segment_sha256'])
            self.assertEqual(pipeline.get(3)['phase'], 'speech_retry')
            self.assertTrue(all(path.is_file() for path in old_segments))
            self.assertEqual(pipeline.get(1)['phase'], 'complete')
            with self.assertRaises(ValueError):
                pipeline.begin_speech_retry(3, 'wrong', retry['segment_sha256'])
            new_segment = folder / 'audio' / 'scene_3_new.mp4'
            new_segment.write_bytes(b'n' * 2048)
            pipeline.update(3, pipeline.get(3)['revision'], phase='complete', segment='audio/scene_3_new.mp4')
            manager.complete_native_speech_retry(job['id'], 3, retry['retry_id'])
            self.assertEqual(manager.get(job['id'])['flow_speech_retries']['3']['status'], 'complete')
            self.assertEqual(pipeline.segments(3)[0], old_segments[0].resolve())
            audit('source-b')
            retry2 = manager.begin_native_speech_retry(job['id'], evidence, 'source-b')
            self.assertNotEqual(retry2['retry_id'], retry['retry_id'])
            self.assertEqual(retry2['attempt'], 2)
            audit('source-c')
            with self.assertRaisesRegex(ValueError, 'FLOW_SPEECH_REPEAT_REVIEW'):
                manager.begin_native_speech_retry(job['id'], evidence, 'source-c', max_attempts=2)


if __name__ == '__main__':
    unittest.main()
