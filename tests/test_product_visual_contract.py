import copy
import json
import tempfile
import unittest
import os
import subprocess
import sys
from pathlib import Path
from core.atomic_json import AtomicJsonFile
from core.flow_motion_plan import motion_plan_action, plan_context, saved_motion_prompt


class ProductVisualContractTests(unittest.TestCase):
    def test_real_extension_desktop_contract(self):
        result = subprocess.run(['node', 'tests/product_visual_contract_harness.js'],
                                cwd=Path(__file__).resolve().parents[1],
                                env={**os.environ, 'SMARTFLOW_TEST_PYTHON': sys.executable},
                                capture_output=True, text=True, encoding='utf-8', timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'JOB-TEST'
        self.root.mkdir()
        (self.root / 'generated').mkdir()
        self.image = self.root / 'generated/selling_image_02.png'
        self.image.write_bytes(b'unchanged saved studio product image')
        self.job = {'id': 'JOB-TEST', 'image_ai_provider': 'chatgpt', 'product_name': 'HMS device',
                    'description': 'Device supports split screen on a compatible car display.',
                    'image_prompts': ['hero', 'Close-up of the device on a plain white studio background'],
                    'flow_shot_prompts': ['hero', {'scene_index': 2, 'prompt': 'DRAFT_CUT_TO_FACTORY_CARPLAY_DISPLAY'}],
                    'spoken_script_segments': [{'text': 'intro'}, {'text': 'รองรับการแบ่งหน้าจอ'}]}
        self.store = AtomicJsonFile(self.root / 'prompts/flow_motion_plans.json')
        self.base = plan_context(self.root, self.job, 2)
        self.answer = {key: self.base[key] for key in ('job_id', 'index', 'context_id')}
        self.answer.update(prompt='Create one continuous vertical 9:16 video of the same product in the white-gray studio setting with a slow subtle push-in.',
                           needs_review=True, reference_compatible=True, material_change=True,
                           review_reason='The attached reference shows only the standalone product on a plain studio background; removing the split-screen demonstration materially changes the original story beat, so review is still required.')

    def call(self, action='status', **extra):
        return motion_plan_action(self.root, self.job, {'action': action, 'index': 2, 'provider': self.job['image_ai_provider'], **extra})

    def legacy(self, phase='answered', **changes):
        row = {'phase': phase, 'context': self.base, 'request': 'DRAFT_CUT_TO_FACTORY_CARPLAY_DISPLAY',
               'result': {**self.answer, **changes}, 'content_recheck_attempt': 1}
        self.store.write({'schema': 1, 'plans': {self.base['context_id']: row}})
        return row

    def test_real_second_response_gets_new_bound_brief_without_old_cut(self):
        original = self.legacy()
        self.assertTrue(self.call()['revision_available'])
        revised = self.call('revise_visual', context_id=self.base['context_id'])
        ctx = revised['context']
        self.assertNotEqual(ctx['context_id'], self.base['context_id'])
        self.assertEqual(ctx['image_sha256'], self.base['image_sha256'])
        self.assertEqual(ctx['story_beat'], self.job['image_prompts'][1])
        self.assertIn('รองรับการแบ่งหน้าจอ', revised['record']['request'])
        self.assertIn(self.job['description'], revised['record']['request'])
        self.assertNotIn('DRAFT_CUT_TO_FACTORY_CARPLAY_DISPLAY', revised['record']['request'])
        self.assertEqual(self.store.read()['plans'][self.base['context_id']], original)
        # Restart during preparation: same exact request, not another revision.
        self.assertEqual(self.call()['record'], revised['record'])
        prepared = self.call('prepare', context_id=ctx['context_id'], request='do not replace request')
        self.assertEqual(prepared['record']['request'], revised['record']['request'])
        self.call('mark_sending', context_id=ctx['context_id'])
        self.assertFalse(self.call('prepare', context_id=ctx['context_id'], request='do not resend')['claimed'])
        with self.assertRaises(ValueError): self.call('revise_visual', context_id=ctx['context_id'])
        with self.assertRaises(ValueError): self.call('save', context_id=ctx['context_id'], result=self.answer)
        valid = {**self.answer, 'context_id': ctx['context_id'], 'needs_review': False, 'material_change': False}
        self.call('review', context_id=ctx['context_id'], result=valid)
        self.call('save', context_id=ctx['context_id'], result=valid)
        self.assertIn('vertical 9:16', saved_motion_prompt(self.root, self.job, 2, 'generated/selling_image_02.png'))
        self.assertFalse(self.call()['revision_available'])
        self.assertEqual(self.store.read()['plans'][self.base['context_id']], original)
        self.assertEqual(self.image.read_bytes(), b'unchanged saved studio product image')

    def test_fresh_request_uses_image_brief_not_ai_motion_draft(self):
        status = self.call()
        self.assertIn('product_visual_contract', status['context'])
        self.assertNotIn('DRAFT_CUT_TO_FACTORY_CARPLAY_DISPLAY', status['visual_request'])
        self.assertEqual(status['context']['product_visual_contract']['saved_narration'], 'รองรับการแบ่งหน้าจอ')
        prepared = self.call('prepare', context_id=status['context']['context_id'], request='wrong client request')
        self.assertEqual(prepared['record']['request'], status['visual_request'])

    def test_revision_cannot_loop_or_force_still_flagged_answer(self):
        self.legacy()
        ctx = self.call('revise_visual', context_id=self.base['context_id'])['context']
        key = ctx['context_id']
        self.call('mark_sending', context_id=key)
        still_bad = {**self.answer, 'context_id': key}
        review = self.call('review', context_id=key, result=still_bad)
        self.assertFalse(review['revision_available'])
        for action in ('save', 'revise_visual', 'recheck_content'):
            with self.assertRaises(ValueError): self.call(action, context_id=key, result=still_bad, request='No further retry')
        self.assertEqual(len(self.store.read()['plans']), 2)

    def test_ambiguous_wrong_owner_and_non_boolean_do_not_revise(self):
        for phase, changes in [('requested', {}), ('preparing', {}), ('answered_text', {}),
                               ('answered', {'job_id': 'OTHER'}), ('answered', {'reference_compatible': False}),
                               ('answered', {'needs_review': 'true'}), ('answered', {'prompt': self.answer['prompt']+' 16:9'})]:
            with self.subTest(phase=phase, changes=changes):
                self.legacy(phase, **changes)
                self.assertFalse(self.call()['revision_available'])
                with self.assertRaises(ValueError): self.call('revise_visual', context_id=self.base['context_id'])
                self.assertEqual(len(self.store.read()['plans']), 1)

    def test_ready_legacy_preserved(self):
        row = self.legacy('ready', needs_review=False, material_change=False)
        row['prompt'] = self.answer['prompt']
        self.store.write({'schema': 1, 'plans': {self.base['context_id']: row}})
        self.assertEqual(self.call()['record'], row)
        self.assertEqual(self.call()['context'], self.base)

    def test_changed_facts_do_not_reset_revision(self):
        self.legacy()
        self.call('revise_visual', context_id=self.base['context_id'])
        self.job['description'] += ' changed requirement'
        with self.assertRaisesRegex(ValueError, 'ข้อมูลสินค้าเปลี่ยน'): self.call()

    def test_changed_image_with_pending_revision_does_not_resend(self):
        self.legacy()
        self.call('revise_visual', context_id=self.base['context_id'])
        self.image.write_bytes(b'different image')
        with self.assertRaisesRegex(ValueError, 'ไม่รู้ผล'): self.call()

    def test_both_provider_contexts_and_wrong_provider(self):
        self.job['image_ai_provider'] = 'gemini'
        status = self.call()
        self.assertEqual(status['context']['provider'], 'gemini')
        with self.assertRaisesRegex(ValueError, 'ผู้เขียนพรอมต์'):
            motion_plan_action(self.root, self.job, {'provider': 'chatgpt', 'index': 2})

    def test_flow_package_uses_revised_image_prompt_pair_after_import(self):
        from core.product_manager import ProductManager
        from core.product_visual_contract import product_motion_progress
        analysis = {key: copy.deepcopy(self.job[key]) for key in ('image_prompts','flow_shot_prompts','spoken_script_segments')}
        AtomicJsonFile(self.root / 'prompts/image_recovery.json').write({'analysis': analysis})
        self.legacy()
        key = self.call('revise_visual', context_id=self.base['context_id'])['context']['context_id']
        self.call('mark_sending', context_id=key)
        valid = {**self.answer, 'context_id': key, 'needs_review': False, 'material_change': False}
        self.call('save', context_id=key, result=valid)
        # Importer can normalize TTS/title, without replacing the saved analysis.
        self.job['spoken_script_segments'][1]['text'] = 'normalized TTS'
        self.job['video_title'] = 'new display title'
        self.job['generated_images'] = ['generated/selling_image_01.png','generated/selling_image_02.png']
        AtomicJsonFile(self.root / 'job.json').write(self.job)
        manager = ProductManager(Path(self.temp.name))
        manager.root = self.root.parent
        packet = manager.flow_package(self.job['id'], 2)
        self.assertTrue(packet['motion_prompt_ready'])
        self.assertEqual(packet['image_files'], ['generated/selling_image_02.png'])
        self.assertEqual(packet['video_prompt'], valid['prompt'])
        self.assertNotIn('DRAFT_CUT_TO_FACTORY_CARPLAY_DISPLAY', packet['video_prompt'])
        before = self.store.path.read_bytes() if hasattr(self.store, 'path') else None
        summary = product_motion_progress(self.root, self.job)
        self.assertIn('ภาพบันทึกแล้ว 1/3', summary)
        self.assertIn('แผนวิดีโอพร้อม 1/3', summary)
        if before is not None: self.assertEqual(before, self.store.path.read_bytes())

    def test_cancel_prevents_new_revision(self):
        self.legacy()
        self.job['cancel_requested'] = True
        with self.assertRaisesRegex(ValueError, 'ยกเลิก'): self.call('revise_visual', context_id=self.base['context_id'])
        self.assertEqual(len(self.store.read()['plans']), 1)


if __name__ == '__main__': unittest.main()
