"""Offline regressions for the approved Drama/Long audio overlap fixes."""
import array
import copy
import hashlib
import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.drama_options import drama_render_options
from core.generated_music import MARKER, freeze_plan
from core.media_audio import audio_choices
from core.story_performance import audio_instruction, validate_option


def drama_options(provider='google_flow', telling='dialogue', **audio):
    return {'video_generation_mode': provider, 'storytelling_options': {'version': 1, 'mode': telling},
            'audio_choices': {'mode': 'api', 'subtitle': False, 'keep_video_audio': True, **audio},
            'generated_music_options': {'version': 1, 'enabled': True, 'mood': 'warm', 'frequency': 'moderate'}}


def drama_job(provider='google_flow', telling='dialogue'):
    options = drama_options(provider, telling)
    job = {'id': 'STORY-AUDIO-OVERLAP', 'scene_count': 6, 'job_type': 'drama_episode',
           'actor_dialogue': True, 'actor_dialogue_version': 3,
           'video_generation_mode': provider, 'storytelling_options': options['storytelling_options'],
           'audio_choices': audio_choices(options['audio_choices'], provider),
           'generated_music_options': options['generated_music_options'],
           'scene_dialogue_turns': [[{'speaker': 'A', 'listener': 'B', 'text': 'วันนี้อากาศดีจัง'},
                                     {'speaker': 'B', 'listener': 'A', 'text': 'ไปเดินเล่นกันไหม'}]] * 6}
    freeze_plan(job)
    return job


class DramaMusicContractTests(unittest.TestCase):
    def test_creation_accepts_validated_music_dubbing_without_client_marker(self):
        for provider in ('google_flow', 'meta_ai'):
            for telling in ('solo', 'dialogue'):
                with self.subTest(provider=provider, telling=telling):
                    options = drama_options(provider, telling)
                    before = copy.deepcopy(options)
                    saved = drama_render_options(options)
                    self.assertTrue(saved['audio_choices']['keep_video_audio'])
                    self.assertEqual(saved['storytelling_options']['mode'], telling)
                    self.assertNotIn('generated_music_version', saved['audio_choices'])
                    self.assertEqual(options, before)

    def test_invalid_combinations_still_fail_at_creation(self):
        changes = [({'keep_video_audio': False}, {}), ({'video_audio_volume': 0}, {}),
                   ({'music': True}, {}), ({}, {'enabled': False}),
                   ({'mode': 'none'}, {}), ({'generated_music_version': 1}, {'enabled': False})]
        for audio, music in changes:
            with self.subTest(audio=audio, music=music), self.assertRaises(ValueError):
                options = drama_options(**audio)
                options['generated_music_options'].update(music)
                drama_render_options(options)
        options = drama_options(generated_music_version=1)
        options.pop('generated_music_options')
        with self.assertRaises(ValueError):
            drama_render_options(options)

    def test_native_defaults_and_non_music_dubbing_remain_supported(self):
        native = drama_options(mode='flow_original', keep_video_audio=False)
        self.assertEqual(drama_render_options(native)['audio_choices']['mode'], 'flow_original')
        native.pop('audio_choices')
        self.assertEqual(drama_render_options(native)['audio_choices']['mode'], 'flow_original')
        plain = drama_options(keep_video_audio=False)
        plain['generated_music_options']['enabled'] = False
        self.assertEqual(drama_render_options(plain)['audio_choices']['mode'], 'api')
        self.assertTrue(validate_option(True, 'google_flow', {'mode': 'flow_original'}))
        self.assertTrue(validate_option(True, 'meta_ai', {'mode': 'none'}, {'version': 1, 'mode': 'visual'}))
        # A Shorts actor may not acquire the Drama API exception.
        from core.storytelling import validate_settings
        with self.assertRaises(ValueError):
            validate_settings(plain['storytelling_options'], 'google_flow', plain['audio_choices'],
                              generated_music_options=plain['generated_music_options'])

    def test_render_requires_the_frozen_music_plan_not_only_marker(self):
        job = drama_job()
        self.assertTrue(validate_option(True, 'google_flow', job['audio_choices'],
            job['storytelling_options'], drama=True, music_job=job))
        for change in ('no_plan', 'no_options', 'changed_options', 'changed_count'):
            candidate = copy.deepcopy(job)
            if change == 'no_plan': candidate.pop('generated_music_plan')
            if change == 'no_options': candidate.pop('generated_music_options')
            if change == 'changed_options': candidate['generated_music_options']['mood'] = 'bright'
            if change == 'changed_count': candidate['scene_count'] = 7
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_option(True, 'google_flow', candidate['audio_choices'],
                    candidate['storytelling_options'], drama=True, music_job=candidate)
        with self.assertRaises(ValueError):
            validate_option(True, 'google_flow', job['audio_choices'], job['storytelling_options'], drama=True)

    def test_invalid_plan_stops_before_scene_voice_requests_or_output_writes(self):
        from core.scene_voice import render_scene_asset
        from core.video_logo import locate_ffmpeg
        try:
            ffmpeg = str(locate_ffmpeg())
        except Exception as error:
            self.skipTest(str(error))
        job = drama_job()
        job.pop('generated_music_plan')
        with tempfile.TemporaryDirectory() as temp, patch('core.scene_voice.render_chunked_voice') as voice:
            folder = Path(temp)
            with self.assertRaisesRegex(ValueError, 'แผนดนตรี AI'):
                render_scene_asset(folder, job, 1, folder / 'not-read.mp4', object(), 'fixture-reference',
                                   {}, ffmpeg, None, None)
            voice.assert_not_called()
            self.assertEqual(list(folder.iterdir()), [])

    def test_creation_to_frozen_series_and_episode_render(self):
        from core.drama_series import DramaSeriesManager
        with tempfile.TemporaryDirectory() as temp:
            manager = DramaSeriesManager(temp)
            series = manager.create('ละครเสียงทดสอบ', characters=[{'name': 'A'}, {'name': 'B'}],
                                    render_options=drama_options())
            context = DramaSeriesManager(temp).episode_context(series['id'], 1)
            saved = context['render_options']
            job = drama_job()
            job.update(audio_choices=copy.deepcopy(saved['audio_choices']),
                       generated_music_options=copy.deepcopy(saved['generated_music_options']))
            freeze_plan(job)
            self.assertTrue(validate_option(True, 'google_flow', job['audio_choices'],
                job['storytelling_options'], drama=True, music_job=job))

    def test_prompt_keeps_one_saved_dialogue_and_no_generated_speech_every_scene(self):
        for provider in ('google_flow', 'meta_ai'):
            job = drama_job(provider)
            original = copy.deepcopy(job)
            with patch('core.generated_music.random.Random', side_effect=AssertionError('rerolled')):
                for index in range(1, 7):
                    prompt = audio_instruction(job, index)
                    self.assertIn('WITHOUT generated speech or vocals', prompt)
                    self.assertNotIn('All spoken dialogue must be in Thai', prompt)
                    self.assertEqual(prompt.count('วันนี้อากาศดีจัง'), 1)
                    self.assertEqual(prompt.count('ไปเดินเล่นกันไหม'), 1)
                    self.assertEqual(MARKER in prompt, index in job['generated_music_plan']['scene_indices'])
            self.assertEqual(job, original)


class LongAudioContractTests(unittest.TestCase):
    def test_new_jobs_and_queue_capture_version_but_legacy_dispatch_does_not(self):
        from core.creation_queue import CreationQueue
        from core.story_manager import StoryManager
        for provider in ('google_flow', 'meta_ai'):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as temp:
                options = {'version': 2, 'scene_count': 18}
                manager, queue = StoryManager(temp), CreationQueue(temp)
                new = manager.create('คลิปยาวใหม่', long_video=options, video_generation_mode=provider)
                self.assertEqual(new.get('long_source_audio_version'), 1)
                old = manager.create('คิวเก่า', long_video=options, video_generation_mode=provider,
                                     long_source_audio_version=0)
                self.assertNotIn('long_source_audio_version', old)
                before = (manager.root / old['id'] / 'job.json').read_bytes()
                manager.get(old['id'])
                self.assertEqual((manager.root / old['id'] / 'job.json').read_bytes(), before)
                row = queue.enqueue('story', ['ยาวเข้าคิว'], long_video=options,
                                    video_generation_mode=provider)['items'][0]
                self.assertEqual(row['settings'].get('long_source_audio_version'), 1)
                queue.edit(row['queue_id'], 'แก้ชื่อเท่านั้น', settings={})
                self.assertEqual(queue.get_item(row['queue_id'])['settings'].get('long_source_audio_version'), 1)

    def test_short_local_and_legacy_rows_do_not_gain_new_contract(self):
        from core.creation_queue import CreationQueue, clean_settings
        from core.story_manager import StoryManager
        self.assertNotIn('long_source_audio_version', clean_settings({'audio_choices': {'mode': 'api'}}))
        with tempfile.TemporaryDirectory() as temp:
            manager, queue = StoryManager(temp), CreationQueue(temp)
            for settings in ({}, {'long_video': {'version': 2, 'scene_count': 18}},
                             {'long_video': {'version': 1, 'scene_count': 18}, 'video_generation_mode': 'google_flow'}):
                job = manager.create('ไม่เปลี่ยนสัญญาเสียง', **settings)
                self.assertNotIn('long_source_audio_version', job)
            row = queue.enqueue('story', ['รายการเดิม'], long_video={'version': 2, 'scene_count': 18},
                                video_generation_mode='google_flow', settings={'long_source_audio_version': 0})['items'][0]
            queue.edit(row['queue_id'], 'แก้ชื่อ', settings={})
            self.assertEqual(queue.get_item(row['queue_id'])['settings'].get('long_source_audio_version', 0), 0)
        for value in (True, 2, '1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                clean_settings({'long_source_audio_version': value})

    def test_long_contract_is_not_added_to_audio_or_prompt_fields(self):
        from core.story_manager import StoryManager
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(temp)
            with patch('core.story_manager.uuid.uuid4', return_value=SimpleNamespace(hex='ab1234' * 6)):
                old = manager.create('ข้อความเดิม', long_video={'version': 2, 'scene_count': 18},
                                     video_generation_mode='google_flow', long_source_audio_version=0)
                request = manager.plugin_request(old['id'])
                manager.create('ข้อความเดิม', long_video={'version': 2, 'scene_count': 18},
                               video_generation_mode='google_flow')
                current = manager.plugin_request(old['id'])
                for field in ('request', 'prompt', 'ai_resume', 'long_video_plan'):
                    self.assertEqual(current[field], request[field])
                self.assertEqual(current['job'].get('audio_choices'), request['job'].get('audio_choices'))


class LongAudioSyntheticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.video_logo import locate_ffmpeg
        try:
            cls.ffmpeg = str(locate_ffmpeg())
        except Exception as error:
            raise unittest.SkipTest('FFmpeg unavailable') from error

    def media(self, *args):
        from core.cancellable_process import hidden_process_kwargs
        result = subprocess.run([self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', *map(str, args)],
                                capture_output=True, timeout=120, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace')[-2000:])
        return result.stdout

    def amplitudes(self, path, start=1):
        raw = self.media('-ss', start, '-i', path, '-map', '0:a:0', '-t', 1,
                         '-f', 's16le', '-ar', '8000', '-ac', '1', 'pipe:1')
        samples = array.array('h', raw)
        return {frequency: math.hypot(
            sum(value * math.cos(2 * math.pi * frequency * i / 8000) for i, value in enumerate(samples)),
            sum(value * math.sin(2 * math.pi * frequency * i / 8000) for i, value in enumerate(samples))) / len(samples)
                for frequency in (330, 660, 880)}

    def test_real_chapters_keep_source_gain_once_silence_and_voice_across_boundary(self):
        from core.long_video_render import LongFlowBatchComposer, LongMetaBatchComposer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tone, later, quiet, voice = [root / name for name in ('tone.mp4', 'later.mp4', 'quiet.mp4', 'voice.wav')]
            for path, frequency in ((tone, 660), (later, 880)):
                self.media('-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=2', '-f', 'lavfi', '-i',
                           f'sine=frequency={frequency}:sample_rate=48000', '-t', 2, '-c:v', 'libx264',
                           '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ac', 2, path)
            self.media('-i', tone, '-c:v', 'copy', '-an', quiet)
            self.media('-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=48000', '-t', 36, '-ac', 2, voice)
            clips = [tone] * 9 + [quiet] + [later] * 8
            originals = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (tone, later, quiet, voice)}
            voice_amp = self.amplitudes(voice)[330]
            for factory in (LongFlowBatchComposer, LongMetaBatchComposer):
                composer = factory(self.ffmpeg)
                output = root / factory.__name__ / 'final.mp4'
                options = dict(width=1152, height=648, fps=24, transition_sec=0, crf=28)
                levels = {}
                for gain in (0, 35, 100):
                    choices = {'mode': 'api', 'keep_video_audio': True, 'allow_silent': True, 'video_audio_volume': gain}
                    with patch.object(composer.flow, 'compose', wraps=composer.flow.compose) as chapters:
                        composer.compose(clips, output, [1] * 18, voice, audio_choices=choices,
                                         source_audio_version=1, **options)
                    self.assertEqual(chapters.call_count, 2)
                    self.assertEqual(chapters.call_args.kwargs['audio_choices']['video_audio_volume'], 100)
                    levels[gain] = self.amplitudes(output)
                    self.assertAlmostEqual(levels[gain][330] / voice_amp, 1, delta=.1)
                self.assertLess(levels[0][660], 20)
                self.assertAlmostEqual(levels[35][660] / levels[100][660], .35, delta=.05)
                # No narration duplication and no source gain applied a second time in chapters.
                self.assertAlmostEqual(levels[100][660] / self.amplitudes(tone)[660], 1, delta=.12)
                for start, audible in ((17, 660), (18.5, None), (20.5, 880), (34, 880)):
                    measured = self.amplitudes(output, start)
                    self.assertAlmostEqual(measured[330] / voice_amp, 1, delta=.1)
                    if audible:
                        self.assertGreater(measured[audible], 600)
                    else:
                        self.assertLess(measured[660] + measured[880], 30)
                choices = {'mode': 'api', 'keep_video_audio': True, 'allow_silent': True, 'video_audio_volume': 100}
                with patch.object(composer.flow, 'compose', wraps=composer.flow.compose) as chapters:
                    result = composer.compose(clips, output, [1] * 18, voice, audio_choices=choices,
                                              source_audio_version=1, **options)
                self.assertEqual(chapters.call_count, 0, 'same saved contract reuses both chapters')
                self.assertAlmostEqual(result['duration'], 36, delta=.5)
                chapter_dir = output.parent / ('long_meta_chapters' if factory is LongMetaBatchComposer else 'long_flow_chapters')
                saved = json.loads((chapter_dir / 'chapter_01.json').read_text())['identity']
                self.assertEqual(saved['source_audio_version'], 1)
                # Legacy without music continues to discard source, even with keep=True.
                with patch.object(composer.flow, 'compose', wraps=composer.flow.compose) as chapters:
                    composer.compose(clips, output, [1] * 18, voice, audio_choices=choices, **options)
                self.assertEqual(chapters.call_count, 2, 'new audio chapter cannot masquerade as legacy')
                self.assertLess(self.amplitudes(output)[660], 20)
                saved = json.loads((chapter_dir / 'chapter_01.json').read_text())['identity']
                self.assertNotIn('source_audio_version', saved)
                ledger_bytes = (chapter_dir / 'chapter_01.json').read_bytes()
                with patch.object(composer.flow, 'compose', wraps=composer.flow.compose) as chapters:
                    composer.compose(clips, output, [1] * 18, voice, audio_choices=choices, **options)
                self.assertEqual(chapters.call_count, 0, 'legacy cache remains reusable without new identity fields')
                self.assertEqual((chapter_dir / 'chapter_01.json').read_bytes(), ledger_bytes)
                # The already-shipped opt-in music contract retains its original mixing behavior.
                composer.compose(clips, output, [1] * 18, voice,
                                 audio_choices={**choices, 'generated_music_version': 1}, **options)
                self.assertGreater(self.amplitudes(output)[660], 600)
                composer.compose(clips, output, [1] * 18, voice,
                                 audio_choices={**choices, 'generated_music_version': 1}, source_audio_version=1, **options)
                self.assertAlmostEqual(self.amplitudes(output)[660] / levels[100][660], 1, delta=.03)
                composer.compose(clips, output, [1] * 18, voice,
                                 audio_choices={**choices, 'keep_video_audio': False}, source_audio_version=1, **options)
                self.assertLess(self.amplitudes(output)[660], 20)
            self.assertEqual({path: hashlib.sha256(path.read_bytes()).hexdigest() for path in originals}, originals)


if __name__ == '__main__':
    unittest.main()
