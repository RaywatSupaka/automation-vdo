"""A completed Meta apology redesigns one owned scene through its image provider."""
import unittest

from core.meta_video import MetaVideoManager, meta_reply_failure
from tests import test_meta_retry_381 as fixture
from tests.test_audit_fixes_426 import picture


ANSWER = 'ขออภัย ดูเหมือนว่าทางฝั่งของฉันจะเกิดปัญหาบางอย่าง โปรดลองอีกครั้ง'


class MetaTechnicalRedesign442(unittest.TestCase):
    setUp = fixture.MetaRetry381Tests.setUp
    advance = fixture.MetaRetry381Tests.advance

    def failure(self, body, **changes):
        proof = dict(matched_request=True, answer_complete=True, answer_truncated=False,
                     stop=False, busy=False, video_count=0, samples=2, stable_ms=6000,
                     answer_text=ANSWER)
        proof.update(changes)
        return {**body, 'stage': 'redesign_prepare', 'retry_evidence': proof}

    def test_exact_completed_reply_only_and_existing_server_retry_unchanged(self):
        self.assertEqual(meta_reply_failure(ANSWER), 'technical_redesign')
        self.assertEqual(meta_reply_failure(ANSWER + ' คำตอบอื่น'), '')
        self.assertEqual(meta_reply_failure('ข้อความอ้างอิง: ' + ANSWER), '')
        self.assertEqual(meta_reply_failure(ANSWER + ' นโยบายความปลอดภัย'), 'policy')
        self.assertEqual(meta_reply_failure(ANSWER + ' โควตาหมด'), 'quota')
        self.assertEqual(meta_reply_failure('Server error: could not generate a video.'),
                         'transient_service_error')

    def test_saved_image_prompt_redesign_new_context_and_ack_idempotence(self):
        body = self.advance()
        before = self.manager.package(self.job_id, 1)
        attempt = self.failure(body)
        repairing = self.manager.event(attempt)
        self.assertEqual(repairing['stage'], 'redesigning')
        self.assertEqual(repairing['redesign']['provider'], 'chatgpt')
        self.assertEqual(repairing['redesign']['failure_reason'], 'technical_redesign')
        self.assertIn('attached', repairing['redesign']['request'])
        self.assertIn('technical error', repairing['redesign']['request'])
        self.assertIn('Generate and show exactly one NEW', repairing['redesign']['request'])
        self.assertNotIn('Return one JSON object', repairing['redesign']['request'])
        self.assertEqual(self.manager.event(attempt)['redesign']['id'], repairing['redesign']['id'])
        self.assertEqual(self.manager.package(self.job_id, 1), before)

        claim = {**body, 'redesign_id': repairing['redesign']['id'], 'action': 'claim'}
        self.assertTrue(self.manager.redesign_event(claim)['send_authorized'])
        self.assertFalse(self.manager.redesign_event(claim)['send_authorized'])
        saved = self.manager.redesign_event({**claim, 'action': 'save_image', 'image': picture('orange')})
        self.assertEqual(saved['redesign']['phase'], 'image_saved')
        done = {**claim, 'action': 'save_prompt',
                'proposal': {'needs_review': False,
                             'video_prompt': 'Slow side camera track while the adult crosses the market.'}}
        next_scene = self.manager.redesign_event(done)
        self.assertEqual(next_scene['stage'], 'prepared')
        self.assertNotEqual(next_scene['request_id'], body['request_id'])
        self.assertNotEqual(next_scene['context_id'], body['context_id'])
        self.assertNotIn('conversation_url', next_scene)
        self.assertEqual(self.manager.redesign_event(done), next_scene)
        package = self.manager.package(self.job_id, 1)
        self.assertNotEqual(package['image_sha256'], before['image_sha256'])
        self.assertIn('technical error', package['prompt'])
        self.assertNotIn('rejected composition', package['prompt'])
        history = self.manager._store(self.job_id).read()['attempt_history']['1']
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['conversation_url'], body['conversation_url'])
        self.assertEqual(MetaVideoManager(self.stories).begin(self.job_id, 1)['request_id'],
                         next_scene['request_id'])

    def test_busy_unknown_late_video_policy_quota_and_wrong_owner_veto(self):
        body = self.advance()
        for changes in ({'busy': True}, {'answer_complete': False}, {'answer_truncated': True},
                        {'stop': True}, {'video_count': 1}, {'samples': 1},
                        {'stable_ms': 4999}, {'answer_text': ANSWER + ' นโยบายความปลอดภัย'},
                        {'answer_text': ANSWER + ' โควตาหมด'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manager.event(self.failure(body, **changes))
        for changes in ({'request_id': 'foreign'}, {'context_id': 'foreign'},
                        {'conversation_url': 'https://www.meta.ai/prompt/foreign'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manager.event({**self.failure(body), **changes})
        self.assertEqual(self.manager.get(self.job_id, 1)['stage'], 'generating')


if __name__ == '__main__':
    unittest.main()
