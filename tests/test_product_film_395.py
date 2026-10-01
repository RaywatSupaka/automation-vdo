import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from core.atomic_json import AtomicJsonFile
from core.creation_queue import CreationQueue
from core.flow_motion_plan import plan_context
from core.flow_replacement import replacement_action
from core.media_audio import flow_audio_instruction
from core.product_script import product_script_options, validate_film_plan, film_instruction
from core.story_manager import StoryManager
from tests import test_product_script_394 as legacy

OPTIONS = dict(version=2, style='short_film_ad', genre='warm', ending_cta=True)


def film_result(job):
    count = job['scene_count']
    lines = ['พ่อซ่อนอะไรไว้น่ะ'] + ['ขยับโคมไฟหน่อย ยังวาดไม่เสร็จ'] * (count - 2) + ['วาดไม่สวย แต่ตั้งใจนะ']
    cta = 'ใครชอบของแบบในเรื่อง ดูที่ตะกร้าได้เลย' if job['product_script_options']['ending_cta'] else ''
    if cta:
        lines[-1] += ' ' + cta
    scenes = []
    for i, line in enumerate(lines):
        roles = ['hook', 'setup'] if i == 0 else ['payoff'] if i == count - 1 else ['bridge', 'product']
        if i == count - 1 and cta:
            roles += ['cta']
        scenes.append(dict(roles=roles, action='พ่อซ่อนกระดาษ' if i == 0 else 'วาดการ์ดข้างโคมไฟ',
                           product_visible=i > 0, speaker='ลูก' if i == 0 else 'พ่อ', listener='พ่อ' if i == 0 else 'ลูก',
                           spoken_text=line, facts_used=[] if i == 0 else ['สีขาว']))
    return dict(job_id=job['id'], video_title='สิ่งที่พ่อซ่อนไว้', video_description='เรื่องสมมติ',
                scene_prompts=['An adult hiding a card' if i == 0 else 'An adult drawing beside a white lamp' for i in range(count)],
                scene_narrations=lines, narration_script=' '.join(lines), scene_durations=[5]*count,
                scene_dialogue_turns=[[dict(speaker=s['speaker'], text=s['spoken_text'])] for s in scenes],
                visual_bible={'setting':'room'}, story_entities=[], scene_entities=[[] for _ in scenes],
                product_film_plan=dict(version=1, premise='พ่อซ่อนอะไร', product_connection='วาดการ์ดที่โต๊ะมีโคมไฟ',
                                       resolution='การ์ดวันเกิดลูก', ending_cta_text=cta, scenes=scenes))


class ProductFilm395Tests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.ProductScript394Tests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.manager, self.root = self.fixture.manager, self.fixture.root

    def job(self, **kwargs):
        return self.fixture.job(style=copy.deepcopy(OPTIONS), **kwargs)

    def test_options_and_scope(self):
        self.assertEqual(product_script_options({'version':2, 'style':'short_film_ad'}), {**OPTIONS, 'genre':'auto'})
        for genre in ['auto', 'warm', 'comedy', 'twist']:
            self.assertEqual(product_script_options({**OPTIONS, 'genre':genre})['genre'], genre)
        for change in [dict(genre='unknown'), dict(ending_cta='false'), dict(ending_cta=0), dict(version=True), dict(style='standard')]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                product_script_options({**OPTIONS, **change})
        with self.assertRaises(ValueError):
            self.manager.create('ไม่ใช่สินค้า', product_script_options=OPTIONS)

    def test_request_provider_audio_count_and_video_matrix(self):
        for provider in ['chatgpt', 'gemini']:
            for audio in ['api', 'flow_original', 'none']:
                for count in [3, 6, 15]:
                    for video in ['google_flow', 'meta_ai']:
                        with self.subTest(provider=provider, audio=audio, count=count, video=video):
                            job = self.job(provider=provider, audio=audio, count=count, video=video)
                            package = self.manager.plugin_request(job['id'])
                            prompt = package['prompt']
                            self.assertIn('PRODUCT SHORT FILM AD v2', prompt)
                            self.assertNotIn('visible adult reviewer speaks directly to camera', prompt)
                            self.assertNotIn('แล้วต่อด้วยคำชวนแบบเป็นธรรมชาติให้ผู้ชมกดหัวใจ', prompt)
                            self.assertIn('product_film_plan', package['request']['required_fields'])
                            self.assertEqual(package['request']['product_script_options'], OPTIONS)
                            self.assertEqual(package['request']['product_script_instruction'], film_instruction(job))
                            self.assertEqual(package['job']['scene_count'], count)

    def test_valid_plan_and_structural_failures_before_images(self):
        job = self.job()
        good = film_result(job)
        self.assertIs(validate_film_plan(job, good), good)
        changes = [lambda r:r.pop('product_film_plan'),
                   lambda r:r['product_film_plan'].update(product_connection=''),
                   lambda r:r['product_film_plan']['scenes'][0].update(product_visible=True),
                   lambda r:r['product_film_plan']['scenes'][0].update(facts_used=['สีขาว']),
                   lambda r:r['product_film_plan']['scenes'][1].update(roles=['setup']),
                   lambda r:r['product_film_plan']['scenes'][-1].update(roles=['product']),
                   lambda r:r['product_film_plan']['scenes'][0].update(spoken_text='บทคนละเรื่อง'),
                   lambda r:r['product_film_plan']['scenes'][0].update(roles=['hook', 'cta']),
                   lambda r:r.update(narration_script='บทเต็มไม่ตรง'),
                   lambda r:r['product_film_plan'].update(ending_cta_text='ซื้อเลย'),
                   lambda r:r['product_film_plan']['scenes'].pop()]
        for change in changes:
            bad = copy.deepcopy(good)
            change(bad)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'PRODUCT_FILM_PLAN'):
                self.manager.save_analysis_checkpoint(job['id'], bad)
            self.assertFalse((self.manager.root/job['id']/'prompts/ai_analysis_checkpoint.json').exists())
        job['product_script_options']['ending_cta'] = False
        validate_film_plan(job, film_result(job))
        with self.assertRaisesRegex(ValueError, 'PRODUCT_FILM_PLAN'):
            validate_film_plan(job, good)

    def test_saved_plan_resume_result_audio_motion_and_edit(self):
        for audio in ['api', 'flow_original']:
            job = self.job(audio=audio)
            result = film_result(job)
            images = self.fixture.images(job)
            self.manager.save_analysis_checkpoint(job['id'], result)
            loaded = self.manager.load_analysis_checkpoint(job['id'])
            self.assertEqual(loaded['product_film_plan'], result['product_film_plan'])
            for index in [1, 3]:
                prepared = self.manager.prepare_scene_pipeline(job['id'], index)
                context = plan_context(self.manager.root/job['id'], prepared, index)
                self.assertEqual(context['product_film_scene'], result['product_film_plan']['scenes'][index-1])
                self.assertEqual(context['story_beat'], result['scene_narrations'][index-1])
                instruction = flow_audio_instruction(prepared, index)
                if audio == 'flow_original':
                    self.assertIn('SHORT FILM AUDIO:', instruction)
                    self.assertIn(result['scene_narrations'][index-1], instruction)
                    self.assertNotIn('AUDIO PERFORMANCE:', instruction)
                    self.assertEqual(flow_audio_instruction(prepared, index, instruction), '')
                else:
                    self.assertEqual(instruction, '')
            committed = self.manager.apply_ai_result({**result, 'generated_images':images})
            self.assertFalse(committed['engagement_cta_enabled'])
            self.assertEqual(committed['product_film_plan'], result['product_film_plan'])
            self.assertEqual(self.manager.repair_program_cta(job['id']), committed)
            lines = result['scene_narrations'][:]
            lines[0] = 'พ่อแอบทำอะไรอยู่'
            edited = self.manager.update_narration(job['id'], ' '.join(lines), lines)
            self.assertEqual(edited['product_film_plan']['scenes'][0]['spoken_text'], lines[0])
            self.assertEqual(edited['narration_script'].count(result['product_film_plan']['ending_cta_text']), 1)
            resumed = self.manager.prepare_scene_pipeline(job['id'], 1)
            self.assertEqual(resumed['scene_narrations'], lines)
            self.assertEqual(resumed['product_film_plan'], edited['product_film_plan'])

    def test_queue_and_desktop_frozen_options(self):
        queue = CreationQueue(self.root)
        options = copy.deepcopy(OPTIONS)
        settings = dict(creative_context=legacy.CONTEXT, product_script_options=options,
                        audio_choices=dict(mode='api', subtitle=True))
        first = queue.enqueue('story', ['โคมไฟ'], settings=settings, scene_count=3)['items'][0]
        options['genre'] = 'twist'
        second = queue.enqueue('story', ['โคมไฟ'], settings=settings, scene_count=3)['items'][0]
        self.assertNotEqual(first['queue_id'], second['queue_id'])
        rows = CreationQueue(self.root).snapshot()['items']
        self.assertEqual(rows[0]['settings']['product_script_options'], OPTIONS)
        self.assertTrue(rows[0]['settings']['audio_choices']['subtitle'])
        from ui.main_window import MainWindow
        app = SimpleNamespace(cfg={}, _product_pipeline_options=lambda **kw: {'provider':'gemini', 'subtitle_enabled':True})
        captured = MainWindow._creation_capture_settings(app, {**settings, 'product_script_options':OPTIONS})
        self.assertEqual(captured['product_script_options'], OPTIONS)
        window = Mock()
        window.membership = None
        window._story_pipeline_job_id = window._product_pipeline_job_id = ''
        window._story_audio_choices = {'mode':'api', 'subtitle':True}
        window._creation_settings.return_value = captured
        window._image_provider_key.return_value = 'gemini'
        window._ai_web_model_key.return_value = 'auto'
        window._story_video_mode_key.return_value = 'google_flow'
        window._compatible_extension.return_value = ({}, True)
        window.stories.create.side_effect = RuntimeError('TEST_STOP_AFTER_CAPTURE')
        MainWindow._create_story_and_run(window, queue_item_id='Q-TEST', creative_context=legacy.CONTEXT)
        self.assertEqual(window.stories.create.call_args.kwargs['product_script_options'], OPTIONS)
        window.bridge.queue_extension_command.assert_not_called()

    def test_repair_preserves_film_and_exact_dialogue(self):
        job = self.job(audio='flow_original')
        job.update(film_result(job))
        self.fixture.images(job)
        job['generated_images'] = [f'generated/scene_{i:02d}.png' for i in range(1, 4)]
        folder = self.manager.root/job['id']
        request = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        AtomicJsonFile(folder/'prompts/flow_recovery.json').write({'scenes':{'1':[
            dict(run_id='TEST', request_id=request, failure_id='failed-attempt-1', fingerprint='fp', reason='timeout')]}})
        result = replacement_action(folder, job, dict(index=1, request_id=request, run_id='TEST',
            replacement_action='begin', rebuild_scene=True, revise_story=True))
        self.assertFalse(result['replacement']['revise_story'])
        self.assertEqual(result['context']['product_film_scene'], job['product_film_plan']['scenes'][0])

    def test_actual_extension_validation_and_both_provider_repairs(self):
        job = self.job()
        run = subprocess.run(['node', 'tests/product_film_395.cjs'], input=json.dumps(film_result(job), ensure_ascii=False),
                             encoding='utf-8', capture_output=True, timeout=25)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('"ok":true', run.stdout)

    def test_flow_five_models_and_meta_native_packages(self):
        from core.meta_video import MetaVideoManager
        models = ['Omni 1.1 Flash', 'Veo 3.1 - Lite', 'Veo 3.1 - Fast',
                  'Veo 3.1 - Quality', 'Veo 3.1 - Lite [Lower Priority]']
        for model in models:
            job = self.job(audio='flow_original')
            job.update(film_result(job))
            self.fixture.images(job)
            job.update(generated_images=[f'generated/scene_{i:02d}.png' for i in range(1, 4)],
                       flow_settings={'model':model})
            self.manager._save(job)
            package = self.manager.flow_package(job['id'], 1)
            self.assertEqual(package['flow_settings']['model'], model)
            self.assertIn('SHORT FILM AUDIO:', package['video_prompt'])
            self.assertIn(job['scene_narrations'][0], package['video_prompt'])
        for audio in ['api', 'flow_original']:
            job = self.job(audio=audio, video='meta_ai')
            job.update(film_result(job))
            self.fixture.images(job)
            job['generated_images'] = [f'generated/scene_{i:02d}.png' for i in range(1, 4)]
            self.manager._save(job)
            prompt = MetaVideoManager(self.manager).package(job['id'], 1)['prompt']
            self.assertIn('SAVED SHORT FILM SCENE', prompt)
            self.assertIn('SHORT FILM AUDIO:' if audio == 'flow_original' else 'No music, speech or ambient audio', prompt)


if __name__ == '__main__':
    unittest.main()
