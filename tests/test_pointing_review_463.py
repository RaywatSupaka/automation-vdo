"""Offline POV preset through real saved-job and provider-package paths."""
import base64
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from PIL import Image
from core.creation_queue import CreationQueue, clean_settings
from core.creative_brief import instruction, public_catalog
from core.flow_motion_plan import plan_context, motion_plan_action
from core.media_audio import flow_audio_instruction
from core.meta_video import MetaVideoManager
from core.product_pointing import VISUAL_INSTRUCTION, enabled, apply_visual
from core.product_prepare_options import freeze_product_options
from core.product_script import creative_product_instruction, product_script_options
from core.product_story import outfit_instruction, story_brief
from core.story_manager import StoryManager
from core.story_visual_plan import motion_request

OPTIONS = {'version': 3, 'style': 'pointing_review'}
LINE = 'ตรงนี้เป็นขอบแก้วสีขาว มองเห็นลวดลายได้ชัด'
MOTION = 'The index finger points at the rim, then rests. Gentle handheld push toward the cup.'


class PointingReview463Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stories = StoryManager(self.tmp.name)
        self.job = self.stories.create('แก้วสีขาว', scene_count=3, product_short=True,
            product_script_options=OPTIONS, video_generation_mode='meta_ai')
        self.folder = self.stories._folder(self.job['id'])
        self.job.update(product_story={'name': 'แก้วสีขาว', 'description': 'สีขาว',
                'reference_roles': ['product'], 'outfit_mode': 'auto'},
            scene_prompts=['A white cup on a table, one hand pointing at the rim.'] * 3,
            scene_narrations=[LINE] * 3, narration_script=' '.join([LINE] * 3), video_title='แก้วสีขาว',
            story_entities=[], scene_entities=[[], [], []],
            flow_shot_prompts=[MOTION] * 3, audio_choices={'mode': 'flow_original'},
            creative_brief={'version': 1, 'kind': 'product', 'selection': 'pointing_review',
                'title': 'นิ้วชี้', 'description': 'พาดูรายละเอียดของแก้วทีละจุด'}, generated_images=[])
        for i in range(1, 4):
            relative = f'generated/scene_{i:02d}.png'
            Image.new('RGB', (360, 640), ('blue', 'red', 'green')[i-1]).save(self.folder / relative)
            self.job['generated_images'].append(relative)
        self.stories._save(self.job)
        self.meta = MetaVideoManager(self.stories, lambda _: {})

    def test_opt_in_catalog_and_exact_selection(self):
        row = next(x for x in public_catalog()['product'] if x['value'] == 'pointing_review')
        self.assertEqual(row['label'], 'นิ้วชี้')
        self.assertIn('ไม่ต้องเห็นหน้า', row['description'])
        self.assertEqual(product_script_options(OPTIONS), OPTIONS)
        self.assertTrue(enabled(self.job))
        for change in ({'product_short': False}, {'product_script_options': None},
                       {'product_script_options': {'version': 1, 'style': 'pointing_review'}},
                       {'product_script_options': {'version': 3, 'style': 'object_pov'}}):
            job = {**self.job, **change}
            self.assertFalse(enabled(job))
            self.assertEqual(apply_visual(job, 'unchanged'), 'unchanged')

    def test_product_capture_queue_freezes_and_survives_restart_edit(self):
        original = {'product_script_options': copy.deepcopy(OPTIONS), 'audio_choices': {'mode': 'none'}}
        frozen = freeze_product_options(original)
        queue = CreationQueue(self.tmp.name)
        settings = {**clean_settings(frozen), 'creative_context': {'kind': 'product_story', 'product_short': True}}
        row = queue.enqueue('story', ['แก้วสีขาว'], settings=settings, scene_count=3)['items'][0]
        original['product_script_options']['style'] = 'auto'
        changed = queue.edit(row['queue_id'], 'แก้วสีขาว', settings={'provider': 'gemini'})
        self.assertEqual(changed['settings']['product_script_options'], OPTIONS)
        self.assertEqual(CreationQueue(self.tmp.name).snapshot()['items'][0]['settings']['product_script_options'], OPTIONS)
        self.assertEqual(frozen['product_script_options'], OPTIONS)

    def test_request_resume_keeps_visual_directive_even_with_saved_brief(self):
        for provider in ('chatgpt', 'gemini'):
            self.job['image_ai_provider'] = provider
            self.stories._save(self.job)
            package = StoryManager(self.tmp.name).plugin_request(self.job['id'])
            self.assertEqual(package['request']['product_script_options'], OPTIONS)
            self.assertEqual(package['request']['product_visual_instruction'], VISUAL_INSTRUCTION)
            self.assertEqual(package['request']['creative_brief'], self.job['creative_brief'])
            self.assertIn(VISUAL_INSTRUCTION, package['prompt'])
            self.assertNotIn('Use the saved visible reviewer/cast', package['prompt'])
            self.assertNotIn('ถ้ารายละเอียดว่าง ให้เล่าเหตุการณ์สมมติ', package['prompt'])
        self.assertIn(VISUAL_INSTRUCTION, instruction(self.job))

    def test_script_audio_modes_and_clothing_are_not_on_camera(self):
        for mode, marker in [('none', 'SILENT VIDEO'), ('api', 'VOICEOVER'), ('flow_original', 'NATIVE AUDIO')]:
            job = {**self.job, 'audio_choices': {'mode': mode}}
            text = creative_product_instruction(job)
            self.assertIn(marker, text)
            self.assertNotIn('Use the saved visible reviewer/cast', text)
            for wardrobe in ('auto', 'saved', 'product'):
                job['product_story'] = {**self.job['product_story'], 'outfit_mode': wardrobe}
                text = story_brief(job)
                self.assertIn('POV wardrobe:', text)
                self.assertNotIn('ให้ตัวละครสวมสินค้านั้นจริง', text)
                self.assertNotIn('ใช้รูป person สำหรับตัวตนและใบหน้า', text)
        self.assertIn('ให้ตัวละครสวมสินค้านั้นจริง', outfit_instruction({'outfit_mode': 'product'}))

    def test_native_audio_once_no_face_and_preserves_missing_line(self):
        audio = flow_audio_instruction(self.job, 1)
        self.assertEqual(audio.count(LINE), 1)
        self.assertIn('from behind the camera', audio)
        self.assertNotIn('visible reviewer speaks', audio)
        self.assertEqual(flow_audio_instruction(self.job, 1, audio), '')
        self.assertIn('No speech is saved', flow_audio_instruction(self.job, 99))
        for mode in ('none', 'api'):
            self.assertEqual(flow_audio_instruction({**self.job, 'audio_choices': {'mode': mode}}, 1), '')

    def test_motion_context_binds_visual_preset_and_format_repair(self):
        context = plan_context(self.folder, self.job, 1)
        self.assertEqual(context['product_visual_instruction'], VISUAL_INSTRUCTION)
        self.assertIn(VISUAL_INSTRUCTION, motion_request(context))
        self.assertIn('Do not include spoken text', motion_request(context).replace('do not include', 'Do not include'))
        from core.flow_motion_plan import motion_format_request
        self.assertIn(VISUAL_INSTRUCTION, motion_format_request(context, '{}'))
        old = {**self.job, 'product_script_options': {'version': 3, 'style': 'auto'}, 'creative_brief': None}
        self.assertNotIn('product_visual_instruction', plan_context(self.folder, old, 1))
        self.assertNotEqual(context['context_id'], plan_context(self.folder, old, 1)['context_id'])

    def test_flow_final_package_keeps_visual_after_saved_motion_and_resume(self):
        self.job['video_generation_mode'] = 'google_flow'
        self.stories._save(self.job)
        context = plan_context(self.folder, self.job, 1)
        body = {'index': 1, 'provider': self.job['image_ai_provider'], 'context_id': context['context_id']}
        motion_plan_action(self.folder, self.job, {**body, 'action': 'claim', 'request': motion_request(context)})
        result = {'job_id': self.job['id'], 'index': 1, 'context_id': context['context_id'],
            'needs_review': False, 'reference_compatible': True, 'material_change': False,
            'prompt': 'Create one vertical 9:16 video. ' + MOTION}
        motion_plan_action(self.folder, self.job, {**body, 'action': 'save', 'result': result})
        first = self.stories.flow_package(self.job['id'], 1)
        self.assertIn(VISUAL_INSTRUCTION, first['video_prompt'])
        self.assertEqual(first['video_prompt'].count(LINE), 1)
        self.assertEqual(StoryManager(self.tmp.name).flow_package(self.job['id'], 1), first)

    def test_meta_package_audio_silent_external_and_immutable_receipts(self):
        for mode in ('none', 'api', 'flow_original'):
            self.job['audio_choices'] = {'mode': mode}
            self.stories._save(self.job)
            package = self.meta.package(self.job['id'], 1)
            self.assertIn(VISUAL_INSTRUCTION, package['prompt'])
            self.assertIn(VISUAL_INSTRUCTION, package['continuity_instruction'])
            self.assertNotIn('Clothing continuity: animate the adult character', package['prompt'])
            self.assertEqual(package['prompt'].count(LINE), 1 if mode == 'flow_original' else 0)
            self.assertEqual(package['scene_value'], MOTION)
        before = [(self.folder / f).read_bytes() for f in self.job['generated_images']]
        receipt = self.meta.begin(self.job['id'], 1)
        self.assertEqual(self.meta.begin(self.job['id'], 1), receipt)
        self.assertEqual([(self.folder / f).read_bytes() for f in self.job['generated_images']], before)

    def test_meta_two_stage_redesign_preserves_pov_and_speech(self):
        package = self.meta.package(self.job['id'], 1)
        self.assertIn(VISUAL_INSTRUCTION, self.meta._redesign_image_request(package, 'technical_redesign'))
        self.assertIn(VISUAL_INSTRUCTION, self.meta._redesign_prompt_request(package, {'image_sha256': 'a'*64}))
        receipt = self.meta.begin(self.job['id'], 1)
        body = dict(job_id=self.job['id'], index=1, request_id=receipt['request_id'], context_id=receipt['context_id'])
        for stage in self.meta.STAGES[1:]:
            if stage == 'submitted':
                body['conversation_url'] = 'https://www.meta.ai/prompt/pointing-fixture'
            self.meta.event({**body, 'stage': stage})
            if stage == 'generating':
                break
        receipt = self.meta.event({**body, 'stage': 'redesign_prepare', 'retry_evidence': {
            'matched_request': True, 'answer_complete': True, 'answer_truncated': False,
            'stop': False, 'busy': False, 'video_count': 0, 'samples': 2, 'stable_ms': 6000,
            'answer_text': 'ขออภัย ดูเหมือนว่าทางฝั่งของฉันจะเกิดปัญหาบางอย่าง โปรดลองอีกครั้ง'}})
        body['redesign_id'] = receipt['redesign']['id']
        self.meta.redesign_event({**body, 'action': 'claim'})
        buffer = io.BytesIO(); Image.new('RGB', (360, 640), 'yellow').save(buffer, format='PNG')
        self.meta.redesign_event({**body, 'action': 'save_image',
            'image': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()})
        with self.assertRaises(ValueError):
            self.meta.redesign_event({**body, 'action': 'save_prompt', 'proposal': {'needs_review': False, 'video_prompt': LINE}})
        proposal = {'needs_review': False, 'video_prompt': MOTION}
        successor = self.meta.redesign_event({**body, 'action': 'save_prompt', 'proposal': proposal})
        next_package = self.meta.package(self.job['id'], 1)
        self.assertIn(VISUAL_INSTRUCTION, next_package['prompt'])
        self.assertEqual(next_package['prompt'].count(LINE), 1)
        self.assertEqual(self.meta.redesign_event({**body, 'action': 'save_prompt', 'proposal': proposal}), successor)

    def test_actual_extension_image_context_and_repair(self):
        from core.cancellable_process import hidden_process_kwargs
        root = Path(__file__).resolve().parents[1]
        package = self.stories.plugin_request(self.job['id'])
        run = subprocess.run(['node', 'tests/pointing_review_463.cjs'], cwd=root, input=json.dumps(package),
            capture_output=True, text=True, encoding='utf-8', timeout=30, **hidden_process_kwargs())
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
