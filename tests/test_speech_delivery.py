import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from core.speech_delivery import (attach_request, effective_text, enabled, freeze_plan,
    native_instruction, scene_delivery, version, writing_instruction, validate_speakers)
from core.media_audio import flow_audio_instruction
from core.creation_queue import clean_settings, CreationQueue
from core.scene_context_revision import revised_story
from core.story_finisher import _subtitle_script
from core.story_manager import StoryManager


def sample(mode='flow_original'):
    return {'id': 'STORY-TEST', 'speech_delivery_version': 1, 'scene_count': 2,
        'scene_narrations': ['พ่อทักทายลูกอย่างอ่อนโยน', 'ทุกคนเดินเข้าบ้าน'],
        'narration_script': 'พ่อทักทายลูกอย่างอ่อนโยน ทุกคนเดินเข้าบ้าน',
        'audio_choices': {'mode': mode}, 'video_generation_mode': 'meta_ai'}


class SpeechDeliveryTests(unittest.TestCase):
    def test_legacy_no_opt_in_or_mutation(self):
        job = sample(); job.pop('speech_delivery_version')
        before = copy.deepcopy(job)
        freeze_plan(job)
        self.assertEqual(before, job)
        self.assertIsNone(native_instruction(job, 1))
        self.assertEqual(writing_instruction(job), '')
        self.assertNotIn('speech_delivery_version', clean_settings({}))

    def test_strict_versions(self):
        for value in (True, False, '1', None, 2):
            with self.subTest(value=value), self.assertRaises(ValueError): version(value)
        self.assertEqual(clean_settings({'speech_delivery_version': 1}), {'speech_delivery_version': 1})

    def test_unknown_speaker_never_becomes_narrator(self):
        job = sample(); job['character_bible'] = [{'name': 'พ่อ'}]
        result = {'dialogue_turns': [{'speaker': 'แม่', 'text': 'สวัสดี'}]}
        with self.assertRaisesRegex(ValueError, 'SPEECH_DELIVERY_REVIEW'):
            validate_speakers(job, result)
        self.assertEqual(result['dialogue_turns'][0]['speaker'], 'แม่')
        result['dialogue_turns'][0]['speaker'] = 'พ่อ'
        validate_speakers(job, result)

    def test_script_rule_not_rewrite(self):
        job = sample(); job['scene_narrations'][0] = 'มีความยาวตามที่ระบุไว้ในสินค้า'
        before = copy.deepcopy(job)
        instruction = writing_instruction(job)
        for phrase in ('selected product/variant', 'missing', 'conflicting', 'warnings only',
                       'Explicit user-approved quotations remain exact', 'มีความยาวตามที่ระบุไว้ในสินค้า',
                       'real product measurement is not a clip duration'):
            self.assertIn(phrase, instruction)
        self.assertEqual(job, before)  # style quality never edits an approved quote or pauses a queue

    def test_attach_once_and_legacy_request_bytes(self):
        job = sample(); req = {'required_fields': ['scene_narrations']}
        text, req = attach_request(job, 'ORIGINAL', req)
        text2, _ = attach_request(job, text, req)
        self.assertEqual(text, text2)
        self.assertEqual(req['required_fields'], ['scene_narrations'])
        self.assertEqual(attach_request({}, 'ORIGINAL', {}), ('ORIGINAL', {}))

    def test_narrator_does_not_turn_quotes_into_actor(self):
        job = sample(); job['scene_narrations'][0] = 'พ่อพูดว่า สวัสดีจ้า'
        d = scene_delivery(job, 1)
        self.assertEqual(d['placement'], 'off_screen')
        self.assertEqual(d['turns'][0]['speaker'], 'ผู้บรรยาย')
        self.assertIn('all visible characters stay silent', flow_audio_instruction(job, 1))

    def test_actor_exact_turn_order_tags_not_speech(self):
        job = sample()
        job.update(actor_dialogue=True, storytelling_options={'mode': 'dialogue'},
            scene_dialogue_turns=[[{'speaker': 'พ่อ', 'listener': 'ลูก', 'text': 'สวัสดีจ้า'},
                                   {'speaker': 'ลูก', 'listener': 'พ่อ', 'text': 'สวัสดีค่ะ'}], []])
        d = scene_delivery(job, 1)
        self.assertEqual([x['speaker_tag'] for x in d['turns']], ['@พ่อ', '@ลูก'])
        self.assertEqual([x['text'] for x in d['turns']], ['สวัสดีจ้า', 'สวัสดีค่ะ'])
        text = flow_audio_instruction(job, 1)
        self.assertEqual(text.count('สวัสดีจ้า'), 1)
        self.assertIn('listener remains silent', text)
        self.assertIn('No generated speech', flow_audio_instruction(job, 2))

    def test_pointing_remains_behind_camera(self):
        job = sample(); job.update(product_short=True, product_presentation_version=1,
            product_script_options={'version': 3, 'style': 'pointing_review'})
        text = flow_audio_instruction(job, 1)
        self.assertIn('behind it', text)
        self.assertIn('No visible speaking face', text)
        self.assertNotIn('assigned visible speaker', text)

    def test_api_and_silent_do_not_compete(self):
        for mode in ('api', 'none'):
            text = flow_audio_instruction(sample(mode), 1)
            self.assertIn('No generated speech', text)
            self.assertNotIn('Ordered dialogue DATA', text)

    def test_native_idempotent_not_truncated(self):
        job = sample(); job['scene_narrations'][0] = 'สวัสดีจ้า ' * 200
        block = flow_audio_instruction(job, 1)
        self.assertIn('END SPEECH SCENE v1', block)
        self.assertEqual(flow_audio_instruction(job, 1, 'motion' + block), '')
        self.assertEqual(block.count('สวัสดีจ้า'), 200)

    def test_native_profile_frozen(self):
        job = sample(); job['storytelling_options'] = {'mode': 'narrator', 'tone': 'warm'}
        freeze_plan(job); old = copy.deepcopy(job['speech_delivery_plan'])
        job['storytelling_options']['tone'] = 'drama'
        freeze_plan(job)
        self.assertEqual(old, job['speech_delivery_plan'])

    def test_pronunciation_same_as_subtitles(self):
        job = sample('api'); job.update(narration_script='ใช้ Acme ได้เลย',
            scene_narrations=['ใช้ Acme ได้เลย', 'กลับบ้าน'], pronunciation_notes={'Acme': 'แอคมี่'})
        actual, issues = effective_text(job, 'ใช้ Acme ได้เลย')
        self.assertFalse(issues)
        self.assertIn('แอคมี่', actual)
        self.assertEqual(actual, _subtitle_script(job)[0])
        self.assertEqual(actual, scene_delivery(job, 1)['turns'][0]['effective_text'])

    def test_scene_preview_matches_actual_turn_boundaries(self):
        from core.studio_review import voice_review
        job = sample('api'); job.update(scene_pipeline_version=1,
            scene_narrations=['Acme', 'World'], narration_script='Acme World',
            pronunciation_notes={'Acme World': 'ห้ามอ่านข้ามฉาก', 'Acme': 'แอคมี่'})
        expected = ' '.join(effective_text(job, text)[0] for text in job['scene_narrations'])
        self.assertEqual(voice_review(job)['script'], expected)
        self.assertEqual(_subtitle_script(job)[0], expected)

    def test_revision_rebinds_only_changed_scene(self):
        job = sample(); freeze_plan(job)
        old = copy.deepcopy(job)
        changed = revised_story(job, {'1': {'phase': 'ready', 'revision': {
            'scene_narration': 'พ่อชวนลูกกลับบ้านด้วยกัน', 'revision_hash': 'approved'}}})
        self.assertEqual(job, old)
        before = job['speech_delivery_plan']['scenes']; after = changed['speech_delivery_plan']['scenes']
        self.assertNotEqual(before[0]['content_hash'], after[0]['content_hash'])
        self.assertEqual(before[1], after[1])

    def test_save_and_requests_across_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = StoryManager(directory)
            for kwargs in ({}, {'product_short': True, 'scene_count': 3},
                           {'storytelling_options': {'version': 1, 'mode': 'narrator', 'tone': 'warm', 'cta_enabled': False}}):
                job = manager.create('บ้าน', **kwargs)
                folder = manager._folder(job['id'])
                original = (folder / 'prompts/chatgpt_request.txt').read_text(encoding='utf-8')
                self.assertNotIn('SPEECH DELIVERY v1:', original)
                job['speech_delivery_version'] = 1
                manager._write_request(folder, job)
                request = json.loads((folder / 'ai_request.json').read_text(encoding='utf-8'))
                self.assertEqual(request['speech_delivery_version'], 1)
                self.assertEqual((folder / 'prompts/chatgpt_request.txt').read_text(encoding='utf-8').count('SPEECH DELIVERY v1:'), 1)
                job.update(scene_narrations=['สวัสดีจ้า'] * job['scene_count'])
                manager._save(job)
                self.assertEqual(manager.get(job['id'])['speech_delivery_plan']['version'], 1)

    def test_edit_old_queue_cannot_migrate_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = CreationQueue(directory)
            result = queue.enqueue('story', ['บ้าน'], settings={}, queue_only=True)
            ident = result['items'][0]['queue_id']
            queue.edit(ident, 'บ้านใหม่', settings={'speech_delivery_version': 1})
            self.assertNotIn('speech_delivery_version', queue.snapshot()['items'][0]['settings'])

    def test_extension_repair_contract(self):
        result = subprocess.run(['node', 'tests/speech_delivery_contract.cjs'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_current_provider_packages_and_recovery(self):
        from test_pointing_review_463 import PointingReview463Tests
        # Reuse synthetic images and actual package/recovery transactions from
        # the previous regression, with the new opt-in contract enabled.
        for method in ('test_flow_final_package_keeps_visual_after_saved_motion_and_resume',
                       'test_meta_package_audio_silent_external_and_immutable_receipts',
                       'test_meta_two_stage_redesign_preserves_pov_and_speech'):
            fixture = PointingReview463Tests(method)
            fixture.setUp()
            try:
                fixture.job['speech_delivery_version'] = 1
                fixture.stories._save(fixture.job)
                getattr(fixture, method)()
            finally:
                fixture.doCleanups()

    def test_voice_normal_speed_and_effective_text_request_identity(self):
        from core.scene_voice import render_scene_asset
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); video = root / 'video.mp4'; video.write_bytes(b'fixture')
            job = sample('api'); job['scene_narrations'][0] = 'ใช้ Acme ได้เลย'
            job['pronunciation_notes'] = {'Acme': 'แอคมี่'}
            render = dict(width=720, height=1280, fps=30, crf=20)
            def concat(args, **kwargs):
                Path(args[-1]).write_bytes(b'fixture-wav'); return Mock(returncode=0)
            with patch('core.scene_voice.render_chunked_voice') as tts, \
                 patch('core.cancellable_process.run_cancellable', side_effect=concat), \
                 patch('core.video_composer.MultiFlowComposer') as composer, \
                 patch('core.video_logo.locate_ffmpeg', return_value=Path('ffmpeg')):
                composer.return_value.compose.return_value = {'duration': 6}
                first = render_scene_asset.__wrapped__(root, job, 1, video, Mock(), 'voice-a', render, '', None, lambda *a: None)
                self.assertEqual(tts.call_args.args[1], effective_text(job, 'ใช้ Acme ได้เลย')[0])
                self.assertEqual(tts.call_args.kwargs['options']['speed'], 1.0)
                self.assertEqual(tts.call_args.kwargs['options']['emotion_id'], 'normal')
                old_scope = tts.call_args.kwargs['scope']
                job['speech_delivery_plan'] = {'version': 1, 'profile': 'comedy'}
                again = render_scene_asset.__wrapped__(root, job, 1, video, Mock(), 'voice-a', render, '', None, lambda *a: None)
                self.assertEqual(first, again)
                self.assertEqual(old_scope, tts.call_args.kwargs['scope'])
                job['pronunciation_notes'] = {'Acme': 'แอคเม่'}
                render_scene_asset.__wrapped__(root, job, 1, video, Mock(), 'voice-a', render, '', None, lambda *a: None)
                self.assertNotEqual(old_scope, tts.call_args.kwargs['scope'])

    def test_saved_product_and_drama_versions_survive(self):
        from core.product_prepare_options import freeze_product_options
        from core.drama_options import drama_render_options
        from core.product_runtime_snapshot import prepared_product_runtime
        from test_product_runtime_snapshot_451 import products, RUNTIME, CONTEXT
        for flag in (None, 1):
            runtime = copy.deepcopy(RUNTIME)
            if flag: runtime['speech_delivery_version'] = flag
            saved = freeze_product_options({'product_runtime_snapshot': runtime})
            manager, _ = products(saved)
            result = prepared_product_runtime(manager, {'creative_context': CONTEXT})
            self.assertEqual(result.get('speech_delivery_version'), flag)
            options = drama_render_options({'speech_delivery_version': flag} if flag else {})
            self.assertEqual(options.get('speech_delivery_version'), flag)


if __name__ == '__main__': unittest.main()
