import base64
import copy
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace

from PIL import Image
from core.atomic_json import AtomicJsonFile
from core.creation_queue import CreationQueue, clean_settings
from core.flow_motion_plan import plan_context
from core.flow_replacement import replacement_action
from core.product_script import product_script_options, story_first_review, review_instruction
from core.story_manager import StoryManager

OPTIONS = {'version': 1, 'style': 'story_first_review'}
CONTEXT = {'kind': 'product_story', 'product_short': True}


class ProductScript394Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.manager = StoryManager(self.root)

    def job(self, provider='chatgpt', count=3, audio='api', style=OPTIONS, video='google_flow'):
        job = self.manager.create('โคมไฟ', scene_count=count, product_short=True,
                                  image_ai_provider=provider, video_generation_mode=video,
                                  product_script_options=copy.deepcopy(style))
        job.update(product_story={'name': 'โคมไฟ', 'description': 'สีขาว', 'reference_roles': ['product']},
                   audio_choices={'mode': audio})
        self.manager._save(job)
        return job

    def analysis(self, job):
        count = job['scene_count']
        lines = ['ว่าจะอ่านอีกหน้าเดียว', 'ขยับโคมไฟมาทางนี้หน่อย', 'ได้มุมอ่านหนังสือแล้ว']
        lines = [lines[i % 3] for i in range(count)]
        return dict(job_id=job['id'], video_title='มุมอ่านหนังสือ', video_description='เรื่องสมมติ',
                    narration_script=' '.join(lines), scene_narrations=lines,
                    scene_prompts=[f'A white lamp and an adult reading, angle {i}' for i in range(count)],
                    scene_durations=[5]*count, visual_bible={'setting': 'reading room'},
                    story_entities=[], scene_entities=[[] for _ in lines],
                    scene_dialogue_turns=[[dict(speaker='ผู้บรรยาย', text=line)] for line in lines])

    def images(self, job):
        folder = self.manager.root / job['id']
        result = []
        for i in range(job['scene_count']):
            buffer = io.BytesIO()
            Image.new('RGB', (288, 512), (30+i*20, 70, 100)).save(buffer, format='PNG')
            (folder/f'generated/scene_{i+1:02d}.png').write_bytes(buffer.getvalue())
            result.append(base64.b64encode(buffer.getvalue()).decode())
        return result

    def test_normalize_strict_scope_and_legacy(self):
        self.assertIsNone(product_script_options())
        self.assertEqual(product_script_options(OPTIONS, product=True), OPTIONS)
        for bad in [True, [], {}, {'version': True, 'style':'standard'}, {'version':2, 'style':'standard'}, {'version':1, 'style':'unknown'}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                product_script_options(bad)
        with self.assertRaises(ValueError):
            self.manager.create('เรื่องธรรมดา', product_script_options=OPTIONS)
        self.assertFalse(story_first_review({'product_script_options':OPTIONS}))
        self.assertEqual(review_instruction({}), '')

    def test_provider_audio_count_matrix_and_legacy_prompt(self):
        for provider in ['chatgpt', 'gemini']:
            for audio in ['api', 'flow_original']:
                for count in [3, 6, 15]:
                    with self.subTest(provider=provider, audio=audio, count=count):
                        job = self.job(provider, count, audio)
                        package = self.manager.plugin_request(job['id'])
                        prompt = package['prompt']
                        self.assertIn('PRODUCT STORY-FIRST REVIEW v1', prompt)
                        self.assertIn('NATIVE AUDIO:' if audio == 'flow_original' else 'VOICEOVER:', prompt)
                        self.assertNotIn('แล้วต่อด้วยคำชวนแบบเป็นธรรมชาติให้ผู้ชมกดหัวใจ', prompt)
                        self.assertNotIn('รายการสุดท้ายต้องรวมประโยคปิดเรื่องและคำชวน', prompt)
                        self.assertIn('สีขาว', prompt)
                        self.assertEqual(package['request']['image_count'], count)
                        self.assertEqual(package['request']['product_script_options'], OPTIONS)
                        self.assertEqual(package['request']['product_script_instruction'], review_instruction(job))
                        self.assertEqual(package['job']['image_ai_provider'], provider)
        for style in [None, {'version':1, 'style':'standard'}]:
            job = self.job(style=style)
            prompt = self.manager.plugin_request(job['id'])['prompt']
            self.assertNotIn('PRODUCT STORY-FIRST REVIEW v1', prompt)
            self.assertIn('แล้วต่อด้วยคำชวนแบบเป็นธรรมชาติให้ผู้ชมกดหัวใจ', prompt)
        legacy = self.manager.create('เรื่องเดิม')
        self.assertNotIn('product_script_options', legacy)

    def test_queue_persistence_fingerprint_and_new_job_scope(self):
        queue = CreationQueue(self.root)
        settings = dict(creative_context=CONTEXT, product_script_options=copy.deepcopy(OPTIONS))
        first = queue.enqueue('story', ['โคมไฟ'], settings=settings, scene_count=3)['items'][0]
        settings['product_script_options']['style'] = 'standard'
        second = queue.enqueue('story', ['โคมไฟ'], settings=settings, scene_count=3)['items'][0]
        rows = CreationQueue(self.root).snapshot()['items']
        self.assertEqual(rows[0]['settings']['product_script_options'], OPTIONS)
        self.assertNotEqual(first['queue_id'], second['queue_id'])
        edited = queue.edit(first['queue_id'], 'เรื่องปรับใหม่', settings={'provider':'gemini'})
        self.assertEqual(edited['settings']['product_script_options'], OPTIONS)
        self.assertEqual(edited['settings']['creative_context'], CONTEXT)
        self.assertEqual(clean_settings({'product_script_options':OPTIONS})['product_script_options'], OPTIONS)
        with self.assertRaises(ValueError):
            queue.enqueue('story', ['ไม่ใช่สินค้า'], settings={'product_script_options':OPTIONS}, scene_count=6)

    def test_apply_edit_resume_and_motion_never_append_cta(self):
        for provider in ['chatgpt', 'gemini']:
            job = self.job(provider)
            analysis = self.analysis(job)
            images = self.images(job)
            self.manager.save_analysis_checkpoint(job['id'], analysis)
            prepared = self.manager.prepare_scene_pipeline(job['id'], 3)
            self.assertEqual(prepared['scene_narrations'], analysis['scene_narrations'])
            context = plan_context(self.manager.root/job['id'], prepared, 3)
            self.assertEqual(context['story_beat'], analysis['scene_narrations'][-1])
            result = self.manager.apply_ai_result({**analysis, 'generated_images':images})
            self.assertEqual(result['narration_script'], analysis['narration_script'])
            self.assertFalse(result['engagement_cta_added_by_program'])
            self.assertFalse(result['engagement_cta_enabled'])
            edited = self.manager.update_narration(job['id'], 'บทแก้เอง', ['หนึ่ง', 'สอง', 'จบ'])
            self.assertEqual(edited['scene_narrations'][-1], 'จบ')
            self.assertFalse(edited['engagement_cta_enabled'])
            self.assertEqual(self.manager.repair_program_cta(job['id']), edited)

    def test_desktop_captures_and_dispatches_frozen_style_without_form_state(self):
        from ui.main_window import MainWindow
        app = SimpleNamespace(cfg={}, _product_pipeline_options=lambda **kw: {
            'provider':'gemini', 'subtitle_enabled':False})
        captured = MainWindow._creation_capture_settings(app, dict(creative_context=CONTEXT,
            product_script_options=OPTIONS, provider='gemini', video_generation_mode='google_flow'))
        self.assertEqual(captured['product_script_options'], OPTIONS)
        self.assertNotIn('product_script_options', MainWindow._creation_capture_settings(app, {}))
        for queued in [False, True]:
            window = Mock()
            window.membership = None
            window._story_pipeline_job_id = window._product_pipeline_job_id = ''
            window._story_audio_choices = {'mode':'flow_original'}
            window._creation_settings.return_value = {**captured, 'audio_choices': {'mode':'flow_original'}}
            window._image_provider_key.return_value = 'gemini'
            window._ai_web_model_key.return_value = 'auto'
            window._story_video_mode_key.return_value = 'google_flow'
            window._compatible_extension.return_value = ({}, True)
            # Stop at the real create boundary, before any worker/dispatch/UI.
            window.stories.create.side_effect = RuntimeError('TEST_STOP_AFTER_CAPTURE')
            MainWindow._create_story_and_run(window, queue_item_id='Q-TEST' if queued else '',
                creative_context=CONTEXT, product_script_options=None if queued else OPTIONS)
            self.assertEqual(window.stories.create.call_args.kwargs['product_script_options'], OPTIONS)
            self.assertTrue(window.stories.create.call_args.kwargs['product_short'])
            window.bridge.queue_extension_command.assert_not_called()

    def test_failed_video_rebuild_preserves_review_dialogue(self):
        job = self.job()
        self.images(job)
        job.update(generated_images=['generated/scene_01.png'], scene_narrations=['บทที่อนุมัติ'],
                   scene_prompts=['An adult reading beside a lamp.'])
        folder = self.manager.root/job['id']
        request = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        AtomicJsonFile(folder/'prompts/flow_recovery.json').write({'scenes':{'1':[
            dict(run_id='TEST', request_id=request, failure_id='failed-attempt-1', fingerprint='fp', reason='timeout')]}})
        result = replacement_action(folder, job, dict(index=1, request_id=request, run_id='TEST',
            replacement_action='begin', rebuild_scene=True, revise_story=True))
        self.assertTrue(result['replacement']['rebuild_scene'])
        self.assertFalse(result['replacement']['revise_story'])
        self.assertEqual(result['context']['story_beat'], 'บทที่อนุมัติ')

    def test_extension_actual_source_repair_contract(self):
        result = subprocess.run(['node', 'tests/product_script_394.cjs'], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding='utf8', timeout=25)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
