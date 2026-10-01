import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from core import product_editorial as editorial
from core.product_evidence import dimensions, snapshot
from core.story_manager import StoryManager


def job():
    return {'id': 'STORY-TEST', 'product_editorial_version': 1, 'scene_count': 3,
            'product_script_options': {'version': 1, 'style': 'story_first_review'},
            'product_short': True, 'product_story': {'name': 'ถุงใส 60x90 นิ้ว', 'description': '', 'price': '',
                'reference_roles': ['product']}, 'source_images': ['source/bag.png'],
            'video_generation_mode': 'meta_ai', 'audio_choices': {'mode': 'api'}}


def draft(j=None):
    j = j or job()
    lines = ['ของชิ้นใหญ่จะเก็บอย่างไรดี', 'ตัวถุงใสมองเห็นของด้านในได้', 'ก่อนเก็บลองเทียบขนาดให้พอดีก่อนนะครับ']
    return {'job_id': j['id'], 'video_title': 'เลือกเก็บให้พอดี', 'video_description': 'ตัวอย่างการเก็บของ',
            'narration_script': ' '.join(lines), 'scene_narrations': lines,
            'scene_prompts': ['A clear bag next to a chair', 'A hand points at a clear bag', 'Compare a clear bag with a chair'],
            'scene_durations': [5, 5, 5], 'visual_bible': {}, 'pronunciation_notes': {},
            'story_entities': [], 'scene_entities': [[], [], []],
            'product_editorial_review': {'image_observations': [], 'scenes': [
                {'index': i, 'purpose': purpose, 'evidence_ids': ['reference_1'], 'visual_anchor': 'clear bag'}
                for i, purpose in enumerate(['เปิดปัญหา', 'สาธิตความใส', 'เตือนเทียบขนาด'], 1)]}}


def bad(j=None):
    value = draft(j)
    value['scene_narrations'][1] = 'ชื่อสินค้าระบุว่าเป็นถุงหนาเหนียว สำหรับงานหนีน้ำ'
    value['narration_script'] = ' '.join(value['scene_narrations'])
    return value


def sending(j):
    state = j['product_editorial_state']
    editorial.mark_sending(j, state['request_id'], 'chatgpt', 'https://chatgpt.com/c/test')
    return state['request_id']


class ProductEditorialTests(unittest.TestCase):
    def test_latest_bad_line_and_attribution_strip_not_accepted(self):
        j = job(); value = bad()
        codes = {x['code'] for x in editorial.inspect(j, value)}
        self.assertTrue({'SOURCE_PROCESS_LANGUAGE', 'UNSUPPORTED_CLAIM'} <= codes)
        value['scene_narrations'][1] = 'เป็นถุงหนาเหนียว สำหรับงานหนีน้ำ'
        value['narration_script'] = ' '.join(value['scene_narrations'])
        self.assertIn('UNSUPPORTED_CLAIM', {x['code'] for x in editorial.inspect(j, value)})

    def test_source_phrases_and_thai_spacing(self):
        for phrase in ('การใช้งานที่ระบุไว้ มีทั้งตู้และเตียง', 'ตาม ข้อมูล ที่ ให้มา',
                       'มีความยาวตามที่ระบุไว้ในสินค้า', 'รายละเอียดไม่ได้ระบุ',
                       'The product listing says this works', 'คลิปนี้ยาวสามนาที'):
            value = draft(); value['scene_narrations'][1] = phrase
            self.assertIn('SOURCE_PROCESS_LANGUAGE', {x['code'] for x in editorial.inspect(job(), value)})

    def test_useful_warning_not_global_blacklist(self):
        value = draft(); value['scene_narrations'][2] = 'ดูสัญลักษณ์ที่ระบุบนบรรจุภัณฑ์ก่อนใช้ครับ'
        value['narration_script'] = ' '.join(value['scene_narrations'])
        self.assertEqual(editorial.inspect(job(), value), [])

    def test_locked_quote_requires_saved_exact_scene_not_ai_claim(self):
        j = job(); value = bad()
        value['user_confirmed'] = True
        self.assertTrue(editorial.inspect(j, value))
        j['product_editorial_locked_quotes'] = {'2': value['scene_narrations'][1]}
        self.assertEqual(editorial.inspect(j, value), [])

    def test_legacy_and_other_modes_unchanged(self):
        for change in ({'product_editorial_version': None}, {'product_editorial_version': True},
                       {'product_story': {}}, {'long_video': {'version': 2}}, {'job_type': 'drama_episode'}):
            j = job(); j.update(change); before = copy.deepcopy(j)
            self.assertTrue(editorial.accept(j, bad())); editorial.assert_approved(j)
            self.assertEqual(j, before)

    def test_dimensions_convert_and_conflict_veto(self):
        self.assertEqual(dimensions('60×90นิ้ว'), [(152.4, 228.6)])
        j = job(); value = draft()
        value['scene_narrations'][1] = 'ขนาด 60 คูณ 90 นิ้ว'
        value['narration_script'] = ' '.join(value['scene_narrations'])
        self.assertEqual(editorial.inspect(j, value), [])
        value['product_editorial_review']['image_observations'] = [{'reference_id': 'reference_1', 'text': '2.25x3 เมตร'}]
        self.assertIn('UNSUPPORTED_NUMBER', {x['code'] for x in editorial.inspect(j, value)})

    def test_image_observation_cannot_authorize_new_number(self):
        value = draft(); value['scene_narrations'][1] = 'ราคานี้ 999 บาท'
        value['product_editorial_review']['image_observations'] = [{'reference_id': 'reference_1', 'text': '999 บาท'}]
        self.assertIn('UNSUPPORTED_NUMBER', {x['code'] for x in editorial.inspect(job(), value)})

    def test_same_number_different_unit_or_price_is_not_evidence(self):
        for line in ('ขนาด 60x90 เมตร', 'ราคา 90 บาท', 'น้ำหนัก 60 กิโลกรัม'):
            value = draft(); value['scene_narrations'][1] = line
            self.assertIn('UNSUPPORTED_NUMBER', {x['code'] for x in editorial.inspect(job(), value)})

    def test_promo_not_product_citation_and_missing_not_user_confirmed(self):
        j = job(); j['product_story']['reference_roles'] = ['promotion']
        self.assertIn('SCENE_EVIDENCE_ALIGNMENT', {x['code'] for x in editorial.inspect(j, draft())})
        saved = snapshot(j)
        self.assertEqual(saved['missing'], ['description', 'price'])
        self.assertNotIn('user_confirmed', json.dumps(saved))

    def test_no_approval_boolean_bypass(self):
        value = bad(); value['approved'] = True
        self.assertFalse(editorial.accept(job(), value))
        value = draft(); value.pop('product_editorial_review')
        self.assertTrue(editorial.inspect(job(), value))

    def test_wrong_visual_and_missing_scene_map(self):
        value = draft(); value['product_editorial_review']['scenes'][1]['visual_anchor'] = 'a red car'
        self.assertIn('SCENE_EVIDENCE_ALIGNMENT', {x['code'] for x in editorial.inspect(job(), value)})

    def test_repetition_and_turn_mismatch(self):
        value = draft(); value['scene_narrations'][2] = value['scene_narrations'][1]
        value['dialogue_turns'] = [{'speaker': 'พ่อ', 'text': 'ไม่ใช่บทนี้'}]
        codes = {x['code'] for x in editorial.inspect(job(), value)}
        self.assertTrue({'REPEATED_LINE', 'TURN_ALIGNMENT', 'SCRIPT_ALIGNMENT'} <= codes)

    def test_two_repairs_persist_even_when_answer_identical(self):
        j = job(); value = bad(); self.assertFalse(editorial.accept(j, value))
        for attempt in (1, 2):
            self.assertEqual(j['product_editorial_state']['attempts'], attempt)
            req = sending(j)
            # Simulated process restart: no in-memory counter needed.
            j = json.loads(json.dumps(j))
            self.assertFalse(editorial.accept(j, value, req))
        self.assertEqual(j['product_editorial_state']['status'], 'needs_review')
        self.assertTrue(editorial.queue_safe_failure(j, 'PRODUCT_EDITORIAL_REVIEW • budget'))
        self.assertFalse(editorial.queue_safe_failure(j, 'login quota error'))
        self.assertEqual(len(j['product_editorial_state']['history']), 3)

    def test_duplicate_ack_late_result_and_unknown_send(self):
        j = job(); value = bad(); editorial.accept(j, value)
        first = copy.deepcopy(j)
        editorial.accept(j, value); self.assertEqual(first, j)
        req = sending(j)
        with self.assertRaisesRegex(ValueError, 'OWNER_REVIEW'): sending(j)
        with self.assertRaisesRegex(ValueError, 'OWNER_REVIEW'): editorial.accept(j, draft(), 'foreign')
        self.assertTrue(editorial.accept(j, draft(), req))
        before = copy.deepcopy(j)
        editorial.accept(j, draft(), req); self.assertEqual(before, j)
        with self.assertRaisesRegex(ValueError, 'REVIEW'): editorial.accept(j, bad())

    def test_only_affected_scene_may_change(self):
        j = job(); editorial.accept(j, bad()); req = sending(j)
        value = draft(); value['scene_prompts'][0] = 'Another scene'
        with self.assertRaisesRegex(ValueError, 'นอกขอบเขต'): editorial.accept(j, value, req)

    def test_repair_preserves_cast(self):
        j = job(); editorial.accept(j, bad()); req = sending(j)
        value = draft(); value['character_bible'] = [{'name': 'stranger'}]
        with self.assertRaisesRegex(ValueError, 'ผู้พูด'): editorial.accept(j, value, req)

    def test_approval_hash_options_pronunciation_and_legacy_paid_identity(self):
        j = job(); value = draft(); self.assertTrue(editorial.accept(j, value)); j.update(value)
        editorial.assert_approved(j)
        for key, value in (('audio_choices', {'mode': 'none'}), ('pronunciation_notes', {'A': 'บี'}),
                           ('scene_narrations', ['changed'] * 3)):
            revised = copy.deepcopy(j); revised[key] = value
            with self.assertRaisesRegex(ValueError, 'REVIEW'): editorial.assert_approved(revised)

    def test_explicit_revision_rechecks_quality_without_mutating_original(self):
        from core.scene_context_revision import revised_story
        j = job(); value = draft(); editorial.accept(j, value); j.update(value)
        old = copy.deepcopy(j)
        new = revised_story(j, {'2': {'phase': 'ready', 'revision': {
            'scene_narration': 'ลองดูของด้านในผ่านตัวถุงครับ', 'revision_hash': 'r1'}}})
        editorial.assert_approved(new); self.assertEqual(j, old)
        with self.assertRaisesRegex(ValueError, 'REVIEW'):
            revised_story(j, {'2': {'phase': 'ready', 'revision': {
                'scene_narration': 'ชื่อสินค้าระบุว่าหนามาก', 'revision_hash': 'r2'}}})

    def test_queue_and_prepared_version_not_added_to_old(self):
        from core.creation_queue import clean_settings
        from core.product_prepare_options import freeze_product_options
        for func in (clean_settings, freeze_product_options):
            self.assertNotIn('product_editorial_version', func({}))
            self.assertEqual(func({'product_editorial_version': 1})['product_editorial_version'], 1)
            for invalid in (True, '1', 2):
                with self.assertRaises(ValueError): func({'product_editorial_version': invalid})

    def test_manager_checkpoint_restart_cancel_and_final_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = StoryManager(directory); j = manager.create('ถุงใส', scene_count=3, product_short=True)
            j.update({k: v for k, v in job().items() if k != 'id'}); manager._save(j)
            value = bad(j); saved = manager.save_analysis_checkpoint(j['id'], value)
            folder = manager._folder(j['id'])
            self.assertEqual(saved['analysis_status'], 'editorial_repair')
            self.assertFalse((folder / 'prompts/ai_analysis_checkpoint.json').exists())
            with self.assertRaisesRegex(ValueError, 'PRODUCT_EDITORIAL_REVIEW'):
                manager.save_partial_image(j['id'], 1, 'bad')
            state = saved['product_editorial_state']
            manager.mark_editorial_sending(j['id'], state['request_id'], 'chatgpt', 'https://chatgpt.com/c/test')
            manager = StoryManager(directory)
            package = manager.plugin_request(j['id'])
            self.assertEqual(package['ai_resume']['request'], state['request'])
            saved = manager.save_analysis_checkpoint(j['id'], draft(j), state['request_id'])
            self.assertEqual(saved['analysis_status'], 'ready'); editorial.assert_approved(saved)
            loaded = manager.load_analysis_checkpoint(j['id']); self.assertEqual(loaded['scene_narrations'], draft(j)['scene_narrations'])
            with self.assertRaisesRegex(ValueError, 'PRODUCT_EDITORIAL_REVIEW'):
                manager.apply_ai_result(bad(j))
            saved.update(cancel_requested=True); manager._save(saved)
            with self.assertRaisesRegex(ValueError, 'ยกเลิก'):
                manager.save_analysis_checkpoint(j['id'], draft(j))

    def test_final_import_does_not_add_cta_or_change_approved_words(self):
        import base64
        with tempfile.TemporaryDirectory() as directory:
            manager = StoryManager(directory); j = manager.create('ถุงใส', scene_count=3, product_short=True)
            j.update({k: v for k, v in job().items() if k != 'id'}); manager._save(j)
            value = draft(j); manager.save_analysis_checkpoint(j['id'], value)
            value['generated_images'] = [base64.b64encode(b'fixture-media-' * 20).decode()] * 3
            saved = manager.apply_ai_result(value)
            editorial.assert_approved(saved)
            self.assertEqual(saved['scene_narrations'], value['scene_narrations'])
            self.assertFalse(saved['engagement_cta_added_by_program'])

    def test_conflict_cannot_be_erased_by_repair(self):
        j = job(); value = bad()
        value['product_editorial_review']['image_observations'] = [{'reference_id': 'reference_1', 'text': '2.25x3 เมตร'}]
        editorial.accept(j, value); req = sending(j)
        value = draft(); value['scene_narrations'][1] = 'ขนาด 60 คูณ 90 นิ้ว'
        value['narration_script'] = ' '.join(value['scene_narrations'])
        self.assertFalse(editorial.accept(j, value, req))
        self.assertIn('UNSUPPORTED_NUMBER', {x['code'] for x in j['product_editorial_state']['issues']})

    def test_actual_queue_handler_skips_only_proven_text_exhaustion(self):
        import ast
        import types
        source = Path(__file__).resolve().parents[1] / 'ui/creation_queue.py'
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == '_creation_story_failure')
        scope = {}; exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), scope)
        j = job(); editorial.accept(j, bad())
        for _ in range(2): editorial.accept(j, bad(), sending(j))
        window = types.SimpleNamespace(stories=Mock(), story_queue=Mock(), _write_console=Mock(),
                                       _schedule_next_story_queue_item=Mock())
        window.stories.get.return_value = j
        item = {'queue_id': 'CQ-TEST', 'job_id': j['id']}
        scope['_creation_story_failure'](window, item, 'PRODUCT_EDITORIAL_REVIEW • exhausted')
        window.story_queue.pause.assert_not_called(); window._schedule_next_story_queue_item.assert_called_once()
        scope['_creation_story_failure'](window, item, 'META_VIDEO_REVIEW • unknown')
        window.story_queue.pause.assert_called_once()

    def test_actual_shared_extension_handshake(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', str(root / 'tests/product_editorial_465.cjs')], cwd=root,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_explicit_scene_provider_selection_rebinds_without_rewriting(self):
        from core.scene_video_plan import effective_job
        j = job(); value = draft(); editorial.accept(j, value); j.update(value)
        j['scene_video_plan'] = {'version': 1, 'revision': 1, 'scenes': {'1': {
            'provider': 'google_flow', 'flow_settings': {'model': 'test-model'},
            'selection_id': 'selection-one', 'revision': 1}}}
        before = copy.deepcopy(j)
        result = effective_job(j, 1); editorial.assert_approved(result)
        self.assertEqual(result['video_generation_mode'], 'google_flow')
        self.assertEqual(result['narration_script'], j['narration_script'])
        self.assertEqual(j, before)

    def test_standard_cta_is_required_before_approval_not_added_after(self):
        j = job(); j['product_script_options'] = {'version': 1, 'style': 'standard'}
        value = draft(); self.assertIn('CTA_MISSING', {x['code'] for x in editorial.inspect(j, value)})
        value['scene_narrations'][-1] += ' กดหัวใจแล้วคอมเมนต์คุยกันได้ครับ'
        value['narration_script'] = ' '.join(value['scene_narrations'])
        self.assertEqual(editorial.inspect(j, value), [])

    def test_flow_motion_preserves_approved_standard_ending(self):
        from core.flow_motion_plan import plan_context
        from PIL import Image
        j = job(); j['product_script_options'] = {'version': 1, 'style': 'standard'}
        j['image_ai_provider'] = 'chatgpt'
        value = draft(); value['scene_narrations'][-1] += ' กดหัวใจแล้วคอมเมนต์คุยกันได้ครับ'
        value['narration_script'] = ' '.join(value['scene_narrations'])
        editorial.accept(j, value); j.update(value)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); (folder / 'generated').mkdir()
            Image.new('RGB', (128, 256), 'navy').save(folder / 'generated/scene_03.png')
            with patch.object(StoryManager, '_ensure_engagement_cta', side_effect=AssertionError('late CTA')):
                result = plan_context(folder, j, 3)
            self.assertEqual(result['story_beat'], j['scene_narrations'][-1])

    def test_owned_resume_url_is_canonical_and_has_no_credentials(self):
        j = job(); editorial.accept(j, bad()); state = j['product_editorial_state']
        editorial.mark_sending(j, state['request_id'], 'chatgpt', 'https://chatgpt.com/c/test/?view=x#y')
        self.assertEqual(state['conversation_url'], 'https://chatgpt.com/c/test')
        j = job(); editorial.accept(j, bad()); state = j['product_editorial_state']
        with self.assertRaises(ValueError):
            editorial.mark_sending(j, state['request_id'], 'chatgpt', 'https://user:secret@chatgpt.com/c/test')

    def test_serial_prepare_keeps_standard_cta_and_approval(self):
        import base64
        import io
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            manager = StoryManager(directory)
            j = manager.create('ถุงใส', scene_count=3, product_short=True, video_generation_mode='google_flow')
            j.update({k: v for k, v in job().items() if k not in ('id', 'video_generation_mode')})
            j.update(scene_pipeline_version=1, product_script_options={'version': 1, 'style': 'standard'})
            manager._save(j)
            value = draft(j); value['scene_narrations'][-1] += ' กดหัวใจแล้วคอมเมนต์คุยกันได้ครับ'
            value['narration_script'] = ' '.join(value['scene_narrations'])
            manager.save_analysis_checkpoint(j['id'], value)
            image = io.BytesIO(); Image.new('RGB', (128, 256), 'navy').save(image, format='PNG')
            manager.save_partial_image(j['id'], 1, base64.b64encode(image.getvalue()).decode())
            with patch.object(StoryManager, '_ensure_engagement_cta', side_effect=AssertionError('late CTA')):
                manager.prepare_scene_pipeline(j['id'], 1)
            saved = manager.get(j['id']); editorial.assert_approved(saved)
            self.assertEqual(saved['narration_script'], value['narration_script'])

    def test_desktop_rejects_late_owner_even_with_correct_editorial_request_id(self):
        import logging
        from core.local_bridge import LocalBridge
        from core.product_manager import ProductManager
        with tempfile.TemporaryDirectory() as directory:
            manager = StoryManager(directory); j = manager.create('ถุงใส', scene_count=3, product_short=True)
            j.update({k: v for k, v in job().items() if k != 'id'}); manager._save(j)
            saved = manager.save_analysis_checkpoint(j['id'], bad(j))
            req = saved['product_editorial_state']['request_id']
            manager.mark_editorial_sending(j['id'], req, 'chatgpt', 'https://chatgpt.com/c/test')
            bridge = LocalBridge('127.0.0.1', 0, ProductManager(directory), logging.getLogger('editorial-test'), stories=manager)
            bridge._extension_runs[('ai', j['id'], 0)] = {'run_id': 'RUN-CURRENT'}
            body = {'job_id': j['id'], 'run_id': 'RUN-OLD', 'result': draft(j), 'editorial_request_id': req}
            with self.assertRaises(ValueError): bridge._accept_story_checkpoint(body, analysis=True)
            self.assertEqual(manager.get(j['id'])['product_editorial_state']['status'], 'needs_repair')
            body['run_id'] = 'RUN-CURRENT'
            self.assertEqual(bridge._accept_story_checkpoint(body, analysis=True)['analysis_status'], 'ready')


if __name__ == '__main__': unittest.main()
