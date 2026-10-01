import array
import copy
import json
import logging
import math
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.generated_music import MARKER, apply_to_prompt, freeze_plan, normalize_options, selected, validate_options
from core.media_audio import audio_choices, flow_audio_instruction


def music_job(count=10, mode='api'):
    return {'id': 'STORY-MUSIC-TEST', 'scene_count': count, 'video_generation_mode': 'google_flow',
            'audio_choices': audio_choices({'mode': mode, 'keep_video_audio': mode == 'api'}),
            'scene_narrations': ['สวัสดีครับ'] * count,
            'generated_music_options': {'version': 1, 'enabled': True, 'mood': 'warm', 'frequency': 'moderate'}}


class GeneratedMusicTests(unittest.TestCase):
    def test_actual_extension_confirmed_repair_commits_music_before_ready(self):
        result = subprocess.run(['node', 'tests/generated_music_extension.cjs'],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_absent_and_disabled_do_not_change_job_or_prompt_bytes(self):
        for options in [None, {'version': 1, 'enabled': False}]:
            job = {'id': 'OLD', 'generated_music_options': options}
            original = copy.deepcopy(job)
            prompt = 'No background music.\nExisting saved prompt\n'
            self.assertIsNone(freeze_plan(job))
            self.assertEqual(job, original)
            self.assertEqual(apply_to_prompt(job, 1, prompt), prompt)
        self.assertNotIn('generated_music_version', audio_choices({'mode': 'api'}))

    def test_validate_explicit_audio_choices_without_mutation(self):
        opts = music_job()['generated_music_options']
        for provider, choices in [('image_motion', {'mode': 'api', 'keep_video_audio': True}),
                                  ('meta_ai', {'mode': 'none'}), ('google_flow', {'mode': 'api'}),
                                  ('meta_ai', {'mode': 'flow_original', 'music': True}),
                                  ('meta_ai', {'mode': 'flow_original', 'video_audio_volume': 0})]:
            before = copy.deepcopy(choices)
            with self.assertRaises(ValueError):
                validate_options(opts, provider, choices)
            self.assertEqual(choices, before)
        for value in [{'enabled': 'true'}, {'mood': []}, {'frequency': {}}, {'version': True}]:
            with self.assertRaises(ValueError):
                normalize_options(value)

    def test_plan_frozen_once_and_copied_across_restart(self):
        job = music_job()
        plan = freeze_plan(job)
        self.assertEqual(len(plan['scene_indices']), 3)
        self.assertTrue(all(b - a > 1 for a, b in zip(plan['scene_indices'], plan['scene_indices'][1:])))
        restarted = copy.deepcopy(job)
        with patch('core.generated_music.random.Random', side_effect=AssertionError('rerolled')):
            self.assertEqual(freeze_plan(restarted), plan)
            for index in range(1, 11):
                apply_to_prompt(restarted, index, 'Saved motion')
        self.assertEqual(job, restarted)
        restarted['generated_music_options']['mood'] = 'bright'
        with self.assertRaises(ValueError):
            freeze_plan(restarted)

    def test_single_and_many_scene_bounds_never_all_for_multiple_scenes(self):
        for count in range(1, 51):
            job = music_job(count)
            plan = freeze_plan(job)
            self.assertGreater(len(plan['scene_indices']), 0)
            self.assertLessEqual(len(plan['scene_indices']), max(1, count - 1))
            self.assertTrue(all(1 <= index <= count for index in plan['scene_indices']))
        self.assertEqual(freeze_plan(music_job(1))['scene_indices'], [1])

    def test_package_cannot_create_plan_or_accept_changed_count(self):
        job = music_job()
        with self.assertRaises(ValueError):
            apply_to_prompt(job, 1, 'Motion')
        self.assertNotIn('generated_music_plan', job)
        freeze_plan(job)
        job['scene_count'] = 11
        with self.assertRaises(ValueError):
            selected(job, 1)

    def test_selected_and_unselected_prompts_preserve_dialogue_without_music_conflicts(self):
        for mode in ['api', 'flow_original']:
            job = music_job(mode=mode)
            plan = freeze_plan(job)
            index = plan['scene_indices'][0]
            plain = next(i for i in range(1, 11) if i not in plan['scene_indices'])
            original = 'No extra dialogue, background music or burned-in captions. Spoken line: สวัสดีครับ'
            result = apply_to_prompt(job, index, original)
            self.assertIn('สวัสดีครับ', result)
            self.assertNotIn('No extra dialogue, background music', result)
            self.assertEqual(result.count(MARKER), 1)
            self.assertEqual(apply_to_prompt(job, index, result), result)
            self.assertEqual(apply_to_prompt(job, plain, original), original)
            self.assertEqual('No generated speech' in result, mode == 'api')
            self.assertIn(MARKER, flow_audio_instruction(job, index))
        job = music_job(1, 'flow_original')
        job['scene_narrations'] = ['No music, please']
        freeze_plan(job)
        self.assertIn('Spoken line: No music, please', flow_audio_instruction(job, 1))
        authored = 'The product is called No Music and ships in blue. "No background music." \'No music.\'\nAction: No music, please'
        self.assertTrue(apply_to_prompt(job, 1, authored).startswith(authored))

    def test_actor_native_and_dubbed_keep_saved_turns(self):
        from core.story_performance import audio_instruction, validate_option
        for mode in ['api', 'flow_original']:
            job = music_job(1, mode)
            job.update(actor_dialogue=True, job_type='drama_episode',
                       storytelling_options={'mode': 'solo'},
                       scene_dialogue_turns=[[{'speaker': 'A', 'listener': 'self', 'text': 'สวัสดีครับ'}]])
            freeze_plan(job)
            validate_option(True, 'google_flow', job['audio_choices'], job['storytelling_options'], drama=True, music_job=job)
            prompt = audio_instruction(job, 1)
            self.assertIn('สวัสดีครับ', prompt)
            self.assertIn(MARKER, prompt)
            self.assertNotIn('Do not add music', prompt)
            self.assertNotIn('No extra dialogue, background music', prompt)

    def test_meta_prompt_hash_legacy_and_frozen_new_music(self):
        from core.meta_video import MetaVideoManager
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'scene.png').write_bytes(b'test-image')
            job = music_job(1, 'flow_original')
            job.update(video_generation_mode='meta_ai', generated_images=['scene.png'], scene_prompts=['Calm action'])
            manager_stub = SimpleNamespace(root=root, get=lambda _: copy.deepcopy(job), _folder=lambda _: root)
            manager = MetaVideoManager(manager_stub, lambda _: {})
            job.pop('generated_music_options')
            legacy = manager.package(job['id'], 1)
            job['generated_music_options'] = {'enabled': False}
            self.assertEqual(manager.package(job['id'], 1), legacy)
            job['generated_music_options'] = music_job()['generated_music_options']
            freeze_plan(job)
            package = manager.package(job['id'], 1)
            self.assertEqual(package, manager.package(job['id'], 1))
            self.assertEqual(package['prompt'].count(MARKER), 1)
            self.assertNotIn('No background music', package['prompt'])
            self.assertIn('สวัสดีครับ', package['prompt'])
            self.assertNotEqual(package['context_id'], legacy['context_id'])

    def test_product_master_metadata_preserves_frozen_scene_music_and_manual_dispatch(self):
        from core.local_bridge import LocalBridge
        from core.product_manager import ProductManager
        for mode in ['api', 'flow_original']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                manager = ProductManager(Path(temp))
                job = music_job(3, mode)
                job.update(id='JOB-MUSIC-METADATA', product_name='Test product',
                           generated_images=['generated/one.png', 'generated/two.png', 'generated/three.png'],
                           flow_shot_prompts=['Scene one. No music.', 'Scene two. No music.', 'Scene three. No music.'])
                options = job.pop('generated_music_options')
                folder = manager.root / job['id']
                (folder / 'prompts').mkdir(parents=True)
                (folder / 'prompts/google_flow_prompt.txt').write_text('Ordinary product overview. No music.\n', encoding='utf-8')
                path = folder / 'job.json'

                def save():
                    path.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')

                save()
                legacy_master = manager.flow_package(job['id'])
                legacy_scenes = {index: manager.flow_package(job['id'], index) for index in range(1, 4)}
                job['generated_music_options'] = options
                save()
                # A manual metadata/preflight read cannot implicitly freeze a
                # plan, even if this opted-in job has not reached first Send.
                before_unfrozen = path.read_bytes()
                self.assertEqual(manager.flow_package(job['id']), legacy_master)
                self.assertEqual(path.read_bytes(), before_unfrozen)
                with self.assertRaisesRegex(ValueError, 'แผนดนตรี AI'):
                    manager.flow_package(job['id'], 1)

                plan = freeze_plan(job)
                save()
                before_frozen = path.read_bytes()
                with patch('core.generated_music.random.Random', side_effect=AssertionError('rerolled')):
                    master = manager.flow_package(job['id'])
                    self.assertEqual(master, legacy_master)
                    self.assertGreaterEqual(len(master['image_files']), 3)
                    self.assertEqual(master['shot_count'], 3)
                    self.assertNotIn(MARKER, master['video_prompt'])
                    for index in range(1, 4):
                        expected = copy.deepcopy(legacy_scenes[index])
                        expected['video_prompt'] = apply_to_prompt(job, index, expected['video_prompt'])
                        self.assertEqual(manager.flow_package(job['id'], index), expected)
                        self.assertEqual(MARKER in expected['video_prompt'], index in plan['scene_indices'])
                    # Same omitted-index command used by the manual AUTO FLOW
                    # control: no server/browser starts, and the queued request
                    # resolves scene 1 rather than sending the master package.
                    bridge = LocalBridge('127.0.0.1', 0, manager, logging.getLogger('music-metadata-test'))
                    with patch.object(manager, 'flow_package', wraps=manager.flow_package) as package:
                        command = bridge.queue_extension_command('open_flow', job['id'])
                    self.assertEqual(command['shot_index'], 1)
                    package.assert_called_once_with(job['id'], shot_index=1)
                self.assertEqual(path.read_bytes(), before_frozen)
                self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['generated_music_plan'], plan)


class GeneratedMusicRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.video_logo import locate_ffmpeg
        try:
            cls.ffmpeg = str(locate_ffmpeg())
        except Exception as error:
            raise unittest.SkipTest('FFmpeg unavailable') from error

    def run_media(self, *args):
        result = subprocess.run([self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', *map(str, args)],
                                capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace')[-1000:])
        return result

    def amplitude(self, path, frequency):
        raw = self.run_media('-i', path, '-map', '0:a:0', '-t', '1', '-f', 's16le', '-ar', '8000', '-ac', '1', 'pipe:1').stdout
        samples = array.array('h', raw)
        real = sum(value * math.cos(2 * math.pi * frequency * i / 8000) for i, value in enumerate(samples))
        imag = sum(value * math.sin(2 * math.pi * frequency * i / 8000) for i, value in enumerate(samples))
        return math.hypot(real, imag) / len(samples)

    def test_short_native_and_api_keep_actual_soundtrack_with_single_gain(self):
        from core.video_composer import MultiFlowComposer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            clip, voice = root / 'clip.mp4', root / 'voice.wav'
            self.run_media('-f', 'lavfi', '-i', 'color=c=blue:s=360x640:r=2', '-f', 'lavfi', '-i',
                           'sine=frequency=660:sample_rate=48000', '-t', '2', '-c:v', 'libx264',
                           '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', clip)
            self.run_media('-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=48000', '-t', '2', voice)
            composer = MultiFlowComposer(self.ffmpeg)
            native, mixed, full = root / 'native.mp4', root / 'mixed.mp4', root / 'full.mp4'
            composer.compose([clip], native, width=360, height=640, fps=24,
                             audio_choices={'mode': 'flow_original', 'video_audio_volume': 100, 'generated_music_version': 1})
            composer.compose([clip], mixed, voice, width=360, height=640, fps=24, tail_seconds=0,
                             transition_sec=0, audio_choices={'mode': 'api', 'keep_video_audio': True,
                                                             'video_audio_volume': 50, 'generated_music_version': 1})
            composer.compose([clip], full, voice, width=360, height=640, fps=24, tail_seconds=0,
                             transition_sec=0, audio_choices={'mode': 'api', 'keep_video_audio': True,
                                                             'video_audio_volume': 100, 'generated_music_version': 1})
            source = self.amplitude(native, 660)
            self.assertGreater(source, 500)
            self.assertGreater(self.amplitude(mixed, 330), 500)
            self.assertAlmostEqual(self.amplitude(mixed, 660) / self.amplitude(full, 660), .5, delta=.08)
            self.assertAlmostEqual(self.amplitude(mixed, 330) / self.amplitude(full, 330), 1, delta=.08)
            silent, spoken = root / 'silent.mp4', root / 'spoken.mp4'
            self.run_media('-i', clip, '-c:v', 'copy', '-an', silent)
            composer.compose([silent], spoken, voice, width=360, height=640, fps=24, tail_seconds=0,
                             transition_sec=0, audio_choices={'mode': 'api', 'keep_video_audio': True,
                                                             'video_audio_volume': 50, 'generated_music_version': 1})
            self.assertGreater(self.amplitude(spoken, 330), 500)
            self.assertLess(self.amplitude(spoken, 660), 20)
            with self.assertRaisesRegex(ValueError, 'ไม่มีเสียงวิดีโอ'):
                composer.compose([silent], root / 'legacy.mp4', voice, width=360, height=640, fps=24,
                                 audio_choices={'mode': 'api', 'keep_video_audio': True})
            with self.assertRaisesRegex(ValueError, 'ไม่มีแทร็กเสียง'):
                composer.compose([silent], root / 'required-dialogue.mp4', width=360, height=640, fps=24,
                                 audio_choices={'mode': 'flow_original', 'generated_music_version': 1})

    def test_long_flow_and_meta_keep_source_once_and_do_not_reuse_legacy_chapters(self):
        from core.long_video_render import LongFlowBatchComposer, LongMetaBatchComposer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            clips = []
            for index in range(18):
                path = root / f'{index}.mp4'
                path.write_bytes(bytes([index]) * 2048)
                clips.append(path)
            voice = root / 'voice.wav'
            self.run_media('-f', 'lavfi', '-i', 'sine=frequency=330:sample_rate=48000', '-t', '36', voice)
            for factory in [LongFlowBatchComposer, LongMetaBatchComposer]:
                composer = factory(self.ffmpeg)
                calls = []
                def chapter(source, target, **options):
                    calls.append(copy.deepcopy(options['audio_choices']))
                    tone = 'sine=frequency=660:sample_rate=48000' if options['audio_choices'].get('keep_video_audio') else 'anullsrc=r=48000:cl=mono'
                    self.run_media('-f', 'lavfi', '-i', 'color=c=green:s=640x360:r=2', '-f', 'lavfi', '-i', tone,
                                   '-t', 2 * len(source), '-c:v', 'libx264', '-preset', 'ultrafast',
                                   '-pix_fmt', 'yuv420p', '-c:a', 'aac', target)
                target = root / ('meta.mp4' if factory is LongMetaBatchComposer else 'flow.mp4')
                with patch.object(composer.flow, 'compose', chapter):
                    composer.compose(clips, target, [1] * 18, voice, width=640, height=360, fps=2,
                                     audio_choices={'mode': 'api'})
                    legacy = self.amplitude(target, 660)
                    choices = {'mode': 'api', 'keep_video_audio': True, 'video_audio_volume': 50, 'generated_music_version': 1}
                    composer.compose(clips, target, [1] * 18, voice, width=640, height=360, fps=2, audio_choices=choices)
                    self.assertEqual(len(calls), 4)
                    self.assertEqual(calls[-1]['video_audio_volume'], 100)
                    self.assertLess(legacy, 20)
                    self.assertGreater(self.amplitude(target, 660), 350)
                    self.assertGreater(self.amplitude(target, 330), 800)
                    self.assertAlmostEqual(self.amplitude(target, 660) / self.amplitude(target, 330), .5, delta=.12)
                    composer.compose(clips, target, [1] * 18, voice, width=640, height=360, fps=2, audio_choices=choices)
                    self.assertEqual(len(calls), 4)


if __name__ == '__main__':
    unittest.main()
