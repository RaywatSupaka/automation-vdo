import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from core.creative_brief import PRODUCT_STYLES, STORY_STRUCTURES, public_catalog, story_structure_options, validate_brief
from core.creation_queue import CreationQueue
from core.product_script import product_script_options, authored_product_script
from core.story_manager import StoryManager


class CreativeControlsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager = StoryManager(Path(self.tmp.name))

    def result(self, job):
        count = job['scene_count']
        selected = (job.get('product_script_options') or {}).get('style') or job['story_structure_options']['structure']
        lines = ['เล่าเหตุการณ์ในห้องอย่างเป็นธรรมชาติ'] * count
        return dict(job_id=job['id'], video_title='เรื่องในห้อง', video_description='เรื่องสมมติ',
            narration_script=' '.join(lines), scene_narrations=lines,
            scene_prompts=['A room with a white lamp.'] * count, scene_durations=[5] * count,
            visual_bible={}, story_entities=[], scene_entities=[[] for _ in lines],
            scene_dialogue_turns=[[dict(speaker='ผู้บรรยาย', text=line)] for line in lines],
            creative_brief=dict(version=1, kind='product' if job.get('product_short') else 'story',
                                selection=selected, title='เหตุการณ์เล็กในห้อง', description='เล่าเหตุการณ์หนึ่งครั้งและจบอย่างเป็นธรรมชาติ'))

    def product(self, style, provider='chatgpt'):
        job = self.manager.create('โคมไฟ', scene_count=3, product_short=True,
            image_ai_provider=provider, video_generation_mode='google_flow',
            product_script_options={'version': 3, 'style': style})
        job.update(product_story={'name': 'โคมไฟ', 'description': 'สีขาว', 'reference_roles': ['product']},
                   audio_choices={'mode': 'api'})
        self.manager._save(job)
        return job

    def test_exact_catalog_and_strict_schema(self):
        self.assertEqual(len(PRODUCT_STYLES), 11)
        self.assertEqual(len(STORY_STRUCTURES), 10)
        self.assertEqual(len(public_catalog()['product']), 15)
        self.assertEqual(len(public_catalog()['story']), 12)
        self.assertEqual(len(set(row[0] for row in PRODUCT_STYLES)), 11)
        for value in ['auto', *(row[0] for row in PRODUCT_STYLES)]:
            self.assertEqual(product_script_options({'version': 3, 'style': value}), {'version': 3, 'style': value})
        for value in ['auto', *(row[0] for row in STORY_STRUCTURES)]:
            self.assertEqual(story_structure_options({'version': 1, 'structure': value})['structure'], value)
        for bad in [True, {}, {'version': True, 'structure': 'auto'}, {'version': 1, 'structure': 'narrator'},
                    {'version': 1, 'structure': 'auto', 'unexpected': 1}]:
            with self.assertRaises(ValueError):
                story_structure_options(bad)
        with self.assertRaises(ValueError):
            product_script_options({'version': 3, 'style': 'standard'})

    def test_product_all_styles_providers_persist_before_images_and_resume(self):
        for provider in ['chatgpt', 'gemini']:
            for style in ['auto', *(row[0] for row in PRODUCT_STYLES)]:
                with self.subTest(provider=provider, style=style):
                    job = self.product(style, provider)
                    package = self.manager.plugin_request(job['id'])
                    self.assertIn('PRODUCT CREATIVE SCRIPT v3', package['prompt'])
                    self.assertEqual(package['prompt'].count('CREATIVE BRIEF v1:'), 1)
                    self.assertIn('creative_brief', package['request']['required_fields'])
                    self.assertNotIn('แล้วต่อด้วยคำชวนแบบเป็นธรรมชาติให้ผู้ชมกดหัวใจ', package['prompt'])
                    self.assertTrue(authored_product_script(job))
                    result = self.result(job)
                    saved = self.manager.save_analysis_checkpoint(job['id'], result)
                    self.assertEqual(saved['creative_brief'], result['creative_brief'])
                    self.assertFalse(saved.get('partial_generated_images'))
                    restarted = StoryManager(Path(self.tmp.name))
                    checkpoint = restarted.load_analysis_checkpoint(job['id'])
                    self.assertEqual(checkpoint['creative_brief'], result['creative_brief'])
                    request = restarted.plugin_request(job['id'])['request']
                    self.assertEqual(request['creative_brief'], result['creative_brief'])
                    bad = copy.deepcopy(result);bad['creative_brief']['title'] = 'แนวที่เปลี่ยนเอง'
                    with self.assertRaisesRegex(ValueError, 'CREATIVE_BRIEF_REVIEW'):
                        restarted.save_analysis_checkpoint(job['id'], bad)

    def test_structure_is_independent_of_four_delivery_modes(self):
        for structure in ['auto', *(row[0] for row in STORY_STRUCTURES)]:
            for mode in ['narrator', 'solo', 'dialogue', 'visual']:
                with self.subTest(structure=structure, mode=mode):
                    job = self.manager.create('เรื่องของเพื่อน', scene_count=6, video_generation_mode='google_flow',
                        storytelling_options={'version': 1, 'mode': mode},
                        story_structure_options={'version': 1, 'structure': structure})
                    package = self.manager.plugin_request(job['id'])
                    self.assertEqual(package['request']['storytelling_options']['mode'], mode)
                    self.assertEqual(package['request']['creative_contract']['selection'], structure)
                    self.assertEqual(package['request']['image_count'], 6)
                    self.assertEqual(package['prompt'].count('CREATIVE BRIEF v1:'), 1)
        for extra in [{'product_short': True}, {'job_type': 'drama_episode'}, {'cast_creation': True}]:
            with self.assertRaises(ValueError):
                self.manager.create('เรื่อง', story_structure_options={'version': 1, 'structure': 'auto'}, **extra)

    def test_legacy_does_not_get_creative_metadata_or_instruction(self):
        for style in [None, {'version': 1, 'style': 'standard'}, {'version': 1, 'style': 'story_first_review'},
                      {'version': 2, 'style': 'short_film_ad'}]:
            job = self.manager.create('สินค้าเดิม', product_short=True, product_script_options=style)
            package = self.manager.plugin_request(job['id'])
            self.assertNotIn('creative_contract', package['request'])
            self.assertNotIn('CREATIVE BRIEF v1:', package['prompt'])
        job = self.manager.create('เรื่องเดิม')
        self.assertNotIn('story_structure_options', job)
        self.assertNotIn('CREATIVE BRIEF v1:', self.manager.plugin_request(job['id'])['prompt'])

    def test_bounded_brief_invalid_never_saves(self):
        job = self.product('auto');good = self.result(job)
        for patch in [{'title': 'x' * 101}, {'description': 'x' * 601}, {'selection': 'other'}, {'kind': 'story'},
                      {'description': '<script>'}, {'description': 'สอง\nบรรทัด'}, {'version': True}]:
            bad = copy.deepcopy(good);bad['creative_brief'].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.manager.save_analysis_checkpoint(job['id'], bad)
            self.assertNotIn('creative_brief', self.manager.get(job['id']))
        with self.assertRaises(ValueError):
            validate_brief(job, {})

    def test_queue_freeze_edit_clear_and_reopen(self):
        queue = CreationQueue(Path(self.tmp.name))
        options = {'story_structure_options': {'version': 1, 'structure': 'auto'}}
        row = queue.enqueue('story', ['เรื่องในห้อง'], scene_count=6, settings=options)['items'][0]
        options['story_structure_options']['structure'] = 'countdown'
        saved = queue.edit(row['queue_id'], 'เรื่องเดิม', settings={'provider': 'chatgpt'})
        self.assertEqual(saved['settings']['story_structure_options']['structure'], 'auto')
        changed = queue.edit(row['queue_id'], 'เรื่องเดิม', settings={'story_structure_options': {'version': 1, 'structure': 'countdown'}})
        self.assertEqual(changed['settings']['story_structure_options']['structure'], 'countdown')
        cleared = queue.edit(row['queue_id'], 'เรื่องเดิม', settings={'story_structure_options': None})
        self.assertIsNone(cleared['settings'].get('story_structure_options'))
        self.assertIsNone(CreationQueue(Path(self.tmp.name)).snapshot()['items'][0]['settings'].get('story_structure_options'))

    def test_product_rejects_early_repeated_cta_and_misaligned_script(self):
        job = self.product('auto');good = self.result(job)
        for lines in [['กดติดตาม', 'เล่าเรื่อง', 'จบเรื่อง'], ['เล่าเรื่อง', 'ต่อเหตุการณ์', 'กดติดตาม กดหัวใจ']]:
            bad = copy.deepcopy(good);bad.update(scene_narrations=lines, narration_script=' '.join(lines))
            with self.assertRaisesRegex(ValueError, 'PRODUCT_CREATIVE_REVIEW'):
                self.manager.save_analysis_checkpoint(job['id'], bad)
        bad = copy.deepcopy(good);bad['narration_script'] = 'บทที่ไม่ตรง'
        with self.assertRaisesRegex(ValueError, 'PRODUCT_CREATIVE_REVIEW'):
            self.manager.save_analysis_checkpoint(job['id'], bad)

    def test_actual_extension_and_native_ui(self):
        root = Path(__file__).resolve().parents[1]
        env = {**os.environ, 'SMARTFLOW_CREATIVE_CATALOG': json.dumps(public_catalog(), ensure_ascii=False)}
        env.setdefault('NODE_PATH', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        from core.cancellable_process import hidden_process_kwargs
        for script in ['creative_controls_extension.cjs', 'creative_controls_ui.cjs']:
            done = subprocess.run(['node', str(root / 'tests' / script)], cwd=root, env=env,
                                  capture_output=True, text=True, encoding='utf8', timeout=60, **hidden_process_kwargs())
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
