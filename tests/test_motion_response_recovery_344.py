"""Real ledger coverage for partial/format-only motion responses; no provider calls."""
import copy
import json
import unittest

from core.flow_motion_plan import motion_format_request, motion_text_review, validate_motion_result
from tests import test_story_visual_plan as visual_fixture


class MotionResponseRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = visual_fixture.StoryVisualPlanTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.context = self.fixture.context
        self.job = self.fixture.job
        self.call = self.fixture.call

    def requested(self):
        self.call('story_visual_recheck')
        self.call('mark_sending')
        return self.call()['record']

    def valid(self, context=None):
        context = context or self.context
        return dict(job_id=context['job_id'], index=context['index'], context_id=context['context_id'],
                    prompt='One vertical 9:16 video. The swordsman turns and walks away from the city. All spoken dialogue must be in Thai only.',
                    needs_review=False, reference_compatible=True, material_change=False,
                    review_reason='A natural turn preserves the original departure.')

    def candidate(self):
        repair, _ = self.fixture.finish()
        return repair, self.valid(repair['candidate_context'])

    def assert_originals(self):
        self.assertEqual(self.fixture.image.read_bytes(), self.fixture.original)
        other = [r for r in self.fixture.store.read({})['plans'].values() if r['context']['index'] == 2][0]
        self.assertEqual(other, self.fixture.other)

    def test_legacy_prefix_passively_recovers_full_result_without_resetting_budgets(self):
        self.requested()
        raw = '{\n"job_id":_'
        review = self.call('review_text', answer_text=raw)
        self.assertFalse(review['validation']['repairable'])
        self.assertEqual(review['format_request'], '')
        self.assertEqual(self.call()['record']['answer_text'], raw)
        before = copy.deepcopy(self.job)
        recovered = self.call('review', result=self.valid())['record']
        self.assertEqual(recovered['prior_invalid_answer_text'], raw)
        self.assertEqual(recovered['prior_invalid_text_validation']['errors'], ['JSON อ่านไม่ได้'])
        self.assertEqual(recovered['content_recheck_attempt'], 1)
        self.assertEqual(recovered['story_visual_revision'], 1)
        self.assertNotIn('format_attempt', recovered)
        self.assertNotIn('story_visual_repair', recovered)
        self.assertEqual(self.call('save', result=self.valid())['record']['phase'], 'ready')
        self.assertEqual(self.job, before)
        self.assert_originals()

    def test_unclosed_prefix_with_complete_field_names_does_not_grant_format_send(self):
        self.requested()
        for prefix in ('{"prompt":"moving", "context_id":', '{"context_id":"fixture", "prompt":"unfinished',
                       '{"prompt":"literal } and escaped \\"", "context_id":"fixture"',
                       '{} followed by {"prompt":"same motion", "context_id":_'):
            with self.subTest(prefix=prefix):
                self.assertFalse(motion_text_review(prefix, 'chatgpt')['repairable'])
                self.call('review_text', answer_text=prefix)
                with self.assertRaises(ValueError): self.call('reformat', answer_text=prefix, request='arbitrary caller content')
                self.assertNotIn('format_attempt', self.call()['record'])

    def test_format_contract_is_server_bound_and_preserves_all_content_decisions(self):
        self.requested()
        malformed = '{"prompt":"some same-image motion", "context_id": broken}'
        first = self.call('review_text', answer_text=malformed)
        request = first['format_request']
        for field in ('job_id', 'index', 'context_id', 'prompt', 'needs_review', 'reference_compatible', 'material_change', 'review_reason'):
            self.assertIn(field, request)
        self.assertIn(self.context['context_id'], request)
        self.assertIn(self.context['image_sha256'], request)
        self.assertIn('Do not convert a review or incompatibility into approval', request)
        result = self.call('reformat', answer_text=malformed, request='CLIENT REWRITE MUST NOT BE USED')
        self.assertTrue(result['claimed'])
        self.assertEqual(result['record']['request'], request)
        self.assertEqual(result['format_request'], request)
        self.assertEqual(result['record']['format_attempt'], 1)
        self.assertEqual(self.call()['format_request'], request)
        self.assertNotIn('CLIENT REWRITE', request)
        self.assertFalse(self.call('reformat', answer_text=malformed)['claimed'])

    def test_main_content_flags_and_wrong_owner_never_grant_format_repair(self):
        self.requested()
        for changes in ({'needs_review': True}, {'material_change': True}, {'reference_compatible': False},
                        {'context_id': 'other'}, {'index': 2}, {'job_id': 'STORY-OTHER'}):
            answer = {**self.valid(), **changes}
            self.call('review', result=answer)
            self.assertEqual(self.call()['format_request'], '')
            with self.assertRaises(ValueError): self.call('reformat', answer_text=json.dumps(answer))
            with self.assertRaises(ValueError): self.call('save', result=answer)
        self.assert_originals()

    def test_main_cancel_and_changed_context_leave_raw_answer_untouched(self):
        self.requested()
        self.call('review_text', answer_text='{"job_id":_')
        prior = (self.fixture.root/'prompts/flow_motion_plans.json').read_bytes()
        self.job['cancel_requested'] = True
        with self.assertRaises(ValueError): self.call('review', result=self.valid())
        self.job.pop('cancel_requested')
        self.job['scene_narrations'][0] = 'Different event'
        with self.assertRaises(ValueError): self.call('review', result=self.valid())
        self.assertEqual((self.fixture.root/'prompts/flow_motion_plans.json').read_bytes(), prior)

    def test_candidate_prefix_is_durable_and_later_full_answer_commits_without_format(self):
        repair, answer = self.candidate()
        rid = repair['request_id']
        raw = '{\n"job_id":_'
        record = self.call('story_visual_review_text', request_id=rid, answer_text=raw)['record']['story_visual_repair']
        self.assertEqual(record['phase'], 'motion_answered_text')
        self.assertEqual(record['answer_text'], raw)
        self.assertFalse(record['validation']['repairable'])
        with self.assertRaises(ValueError): self.call('story_visual_reformat', request_id=rid)
        record = self.call('story_visual_save', request_id=rid, result=answer)['record']['story_visual_repair']
        self.assertEqual(record['phase'], 'ready')
        self.assertEqual(record['prior_invalid_answer_text'], raw)
        self.assertNotIn('format_attempt', record)
        self.assertEqual(record['image_sha256'], repair['image_sha256'])
        self.assert_originals()

    def test_candidate_format_has_claim_before_send_and_resumable_pending_phase(self):
        repair, answer = self.candidate()
        rid = repair['request_id']
        malformed = '{"prompt":"same motion", "context_id": broken}'
        first = self.call('story_visual_review_text', request_id=rid, answer_text=malformed)['record']['story_visual_repair']
        self.assertEqual(first['phase'], 'motion_answered_text')
        self.assertTrue(first['validation']['repairable'])
        formatted = self.call('story_visual_reformat', request_id=rid)
        self.assertTrue(formatted['claimed'])
        current = formatted['record']['story_visual_repair']
        self.assertEqual(current['phase'], 'preparing_motion_format')
        self.assertEqual(current['format_attempt'], 1)
        self.assertEqual(current['motion_request'], first['format_request'])
        self.assertEqual(current['original_motion_request'], repair['motion_request'])
        self.assertEqual(current['original_answer_text'], malformed)
        self.assertFalse(self.call('story_visual_reformat', request_id=rid)['claimed'])
        with self.assertRaises(ValueError): self.call('story_visual_save', request_id=rid, result=answer)
        self.call('story_visual_mark_format', request_id=rid)
        self.assertEqual(self.call()['record']['story_visual_repair']['phase'], 'motion_format_requested')
        with self.assertRaises(ValueError): self.call('story_visual_mark_format', request_id=rid)
        self.assertFalse(self.call('story_visual_reformat', request_id=rid)['claimed'])
        self.call('story_visual_save', request_id=rid, result=answer)
        saved = self.call()['record']['story_visual_repair']
        self.assertEqual(saved['phase'], 'ready')
        self.assertEqual(saved['format_attempt'], 1)
        self.assertEqual(saved['image_file'], repair['image_file'])
        self.assert_originals()

    def test_candidate_schema_only_result_can_format_with_exact_candidate_context(self):
        repair, answer = self.candidate()
        rid = repair['request_id']
        answer['needs_review'] = ''
        saved = self.call('story_visual_save', request_id=rid, result=answer)['record']['story_visual_repair']
        self.assertEqual(saved['phase'], 'motion_answered')
        self.assertTrue(saved['validation']['repairable'])
        self.assertIn(repair['candidate_context']['context_id'], saved['format_request'])
        self.assertNotEqual(repair['candidate_context']['context_id'], self.context['context_id'])
        formatted = self.call('story_visual_reformat', request_id=rid)['record']['story_visual_repair']
        self.assertEqual(formatted['prior_format_result'], answer)
        self.assertEqual(formatted['format_attempt'], 1)
        self.call('story_visual_mark_format', request_id=rid)
        answer['needs_review'] = False
        self.assertEqual(self.call('story_visual_save', request_id=rid, result=answer)['record']['phase'], 'ready')

    def test_candidate_terminal_content_decisions_remain_immutable(self):
        repair, answer = self.candidate()
        rid = repair['request_id']
        flagged = {**answer, 'needs_review': True, 'material_change': True}
        result = self.call('story_visual_save', request_id=rid, result=flagged)['record']['story_visual_repair']
        self.assertEqual(result['phase'], 'needs_review')
        with self.assertRaises(ValueError): self.call('story_visual_reformat', request_id=rid)
        with self.assertRaises(ValueError): self.call('story_visual_review_text', request_id=rid, answer_text=json.dumps(answer))
        with self.assertRaises(ValueError): self.call('story_visual_save', request_id=rid, result=answer)
        self.assertEqual(self.call('story_visual_save', request_id=rid, result=flagged)['record']['story_visual_repair'], result)
        self.assert_originals()

    def test_candidate_format_result_wrong_owner_cannot_commit_or_reset_budget(self):
        repair, answer = self.candidate()
        rid = repair['request_id']
        self.call('story_visual_review_text', request_id=rid, answer_text='{"prompt":"same action", "context_id": broken}')
        self.call('story_visual_reformat', request_id=rid)
        self.call('story_visual_mark_format', request_id=rid)
        bad = {**answer, 'context_id': self.context['context_id']}
        rejected = self.call('story_visual_save', request_id=rid, result=bad)['record']['story_visual_repair']
        self.assertEqual(rejected['phase'], 'needs_review')
        self.assertFalse(rejected['validation']['repairable'])
        self.assertEqual(rejected['format_attempt'], 1)
        self.assertFalse(self.call('story_visual_reformat', request_id=rid)['claimed'])
        with self.assertRaises(ValueError): self.call('story_visual_save', request_id=rid, result=answer)

    def test_candidate_cancel_or_changed_hash_or_request_blocks_format_send(self):
        repair, _ = self.candidate()
        rid = repair['request_id']
        self.call('story_visual_review_text', request_id=rid, answer_text='{"prompt":"same action", "context_id": broken}')
        self.call('story_visual_reformat', request_id=rid)
        self.job['cancel_requested'] = True
        with self.assertRaises(ValueError): self.call('story_visual_mark_format', request_id=rid)
        self.job.pop('cancel_requested')
        with self.assertRaises(ValueError): self.call('story_visual_mark_format', request_id='wrong-request')
        (self.fixture.root/repair['image_file']).write_bytes(b'changed image')
        with self.assertRaises(ValueError): self.call('story_visual_mark_format', request_id=rid)
        self.assertEqual(self.call()['record']['story_visual_repair']['phase'], 'preparing_motion_format')

    def test_candidate_second_malformed_answer_keeps_spent_budget(self):
        repair, _ = self.candidate()
        rid = repair['request_id']
        first = '{"prompt":"same action", "context_id": broken}'
        self.call('story_visual_review_text', request_id=rid, answer_text=first)
        self.call('story_visual_reformat', request_id=rid)
        self.call('story_visual_mark_format', request_id=rid)
        second = '{"context_id": broken, "prompt":"same action again"}'
        record = self.call('story_visual_review_text', request_id=rid, answer_text=second)['record']['story_visual_repair']
        self.assertEqual(record['original_answer_text'], first)
        self.assertEqual(record['answer_text'], second)
        self.assertEqual(record['format_attempt'], 1)
        self.assertFalse(self.call('story_visual_reformat', request_id=rid)['claimed'])

    def test_optional_review_reason_stays_valid_and_formatter_never_truncates_input(self):
        self.assertEqual(validate_motion_result(self.valid(), self.context)['errors'], [])
        request = motion_format_request(self.context, json.dumps(self.valid()), 'Saved same-image request')
        self.assertIn('review_reason', request)
        with self.assertRaises(ValueError): motion_format_request(self.context, 'x' * 16000, 'y' * 10000)

    def test_distinct_complete_motion_objects_are_ambiguity_not_formatting(self):
        first = self.valid()
        for patch in ({'context_id': 'OTHER'}, {'job_id': 'STORY-OTHER'}, {'index': 2},
                      {'needs_review': True}, {'reference_compatible': False}, {'material_change': True},
                      {'prompt': first['prompt'] + ' The actor stays still.'}):
            with self.subTest(patch=patch):
                second = {**first, **patch}
                raw = 'First:\n```json\n' + json.dumps(first) + '\n```\nSecond:\n' + json.dumps(second)
                for provider in ('chatgpt', 'gemini'):
                    validation = motion_text_review(raw, provider)
                    self.assertEqual(validation['repair_kind'], 'ambiguous_json')
                    self.assertFalse(validation['repairable'])
        duplicate = json.dumps(first) + '\n' + json.dumps(dict(reversed(list(first.items()))), indent=2)
        self.assertNotEqual(motion_text_review(duplicate, 'chatgpt')['repair_kind'], 'ambiguous_json')
        self.assertEqual(motion_text_review('{"prompt":"same action", "context_id": broken}', 'chatgpt')['repair_kind'], 'json_format')

    def test_main_ambiguous_raw_answer_is_durable_and_cannot_select_one(self):
        self.requested()
        answer = self.valid()
        raw = json.dumps(answer) + '\n' + json.dumps({**answer, 'needs_review': True})
        reviewed = self.call('review_text', answer_text=raw)
        self.assertEqual(reviewed['validation']['repair_kind'], 'ambiguous_json')
        self.assertEqual(reviewed['format_request'], '')
        with self.assertRaises(ValueError): self.call('reformat', answer_text=raw)
        with self.assertRaises(ValueError): self.call('review', result=answer)
        with self.assertRaises(ValueError): self.call('review_text', answer_text=json.dumps(answer))
        self.assertEqual(self.call('review_text', answer_text=raw)['record'], reviewed['record'])
        self.assertEqual(self.call()['record']['answer_text'], raw)
        self.assertNotIn('format_attempt', self.call()['record'])
        self.assert_originals()

    def test_candidate_ambiguous_raw_answer_keeps_image_and_blocks_formatter(self):
        repair, answer = self.candidate()
        rid = repair['request_id']
        raw = json.dumps(answer) + '\n' + json.dumps({**answer, 'context_id': self.context['context_id']})
        reviewed = self.call('story_visual_review_text', request_id=rid, answer_text=raw)['record']['story_visual_repair']
        self.assertEqual(reviewed['validation']['repair_kind'], 'ambiguous_json')
        with self.assertRaises(ValueError): self.call('story_visual_reformat', request_id=rid)
        with self.assertRaises(ValueError): self.call('story_visual_save', request_id=rid, result=answer)
        with self.assertRaises(ValueError): self.call('story_visual_review_text', request_id=rid, answer_text=json.dumps(answer))
        self.assertEqual(self.call('story_visual_review_text', request_id=rid, answer_text=raw)['record']['story_visual_repair'], reviewed)
        self.assertEqual(reviewed['answer_text'], raw)
        self.assertNotIn('format_attempt', reviewed)
        self.assertEqual(reviewed['image_sha256'], repair['image_sha256'])
        self.assert_originals()


if __name__ == '__main__': unittest.main()
