"""Saved Meta route redirected to a ready Home: no provider calls or user Job writes."""
import copy
import unittest
import subprocess
from unittest.mock import patch
from tests import test_meta_video as fixtures


class MetaRouteRecoveryTests(unittest.TestCase):
    setUp = fixtures.MetaVideoTests.setUp
    advance = fixtures.MetaVideoTests.advance

    def test_actual_extension_and_ui(self):
        result = subprocess.run(['node', str(fixtures.ROOT / 'tests/meta_route_recovery.cjs')],
            cwd=fixtures.ROOT, capture_output=True, text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def proof(self, document='before'):
        return dict(observed_url='https://www.meta.ai/', document_id=document,
                    ready=True, login=False, composer_count=1, composer_empty=True,
                    user_count=0, image_count=0, video_count=0, message_count=0, busy=False, stop=False,
                    answer_empty=True, dialog=False)

    def check(self, body):
        with patch('core.meta_route_recovery.time.time', return_value=100):
            return self.manager.event({**body, 'stage':'route_recheck', 'route_evidence':self.proof()})

    def retry(self, body, check, **proof):
        return self.manager.event({**body, 'stage':'route_retry',
            'route_check_id':check['route_recovery']['check_id'],
            'route_evidence':{**self.proof('after'), 'samples':2, 'stable_ms':6000, **proof}})

    def test_recheck_then_single_successor_preserves_context_and_history(self):
        body = self.advance('generating')
        before = copy.deepcopy(self.stories.get(self.job_id))
        checked = self.check(body)
        self.assertEqual(checked['stage'], 'generating')
        self.assertEqual(self.check(body)['route_recovery'], checked['route_recovery'])
        with patch('core.meta_route_recovery.time.time', return_value=116):
            next_row = self.retry(body, checked)
            self.assertEqual(self.retry(body, checked), next_row, 'lost ACK must return the same successor')
        self.assertEqual(next_row['stage'], 'prepared')
        self.assertNotEqual(next_row['request_id'], body['request_id'])
        self.assertEqual(next_row['context_id'], body['context_id'])
        self.assertNotIn('conversation_url', next_row)
        history = self.manager._store(self.job_id).read()['attempt_history']['1']
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['conversation_url'], body['conversation_url'])
        self.assertEqual(self.stories.get(self.job_id), before)

    def test_incomplete_or_active_or_wrong_page_never_authorizes_replay(self):
        body = self.advance('generating'); checked = self.check(body)
        for changes in [dict(document_id='before'), dict(ready=False), dict(login=True),
                        dict(composer_count=2), dict(composer_empty=False), dict(user_count=1),
                        dict(image_count=1), dict(video_count=1), dict(busy=True), dict(stop=True),
                        dict(answer_empty=False), dict(dialog=True), dict(samples=1), dict(message_count=1),
                        dict(observed_url='https://www.meta.ai/prompt/other'),
                        dict(observed_url='https://evil.test/'), dict(stable_ms=0)]:
            with self.subTest(changes=changes), patch('core.meta_route_recovery.time.time', return_value=116):
                with self.assertRaises(ValueError): self.retry(body, checked, **changes)
        self.assertEqual(self.manager.get(self.job_id, 1)['request_id'], body['request_id'])

    def test_waits_for_durable_cooldown_then_requires_fresh_proof(self):
        body = self.advance('generating'); checked = self.check(body)
        with patch('core.meta_route_recovery.time.time', return_value=110):
            self.assertEqual(self.retry(body, checked)['request_id'], body['request_id'])

    def test_no_recovery_of_unknown_send_or_download(self):
        for stage in ['send_intent', 'downloading']:
            with self.subTest(stage=stage):
                self.setUp(); body = self.advance(stage)
                with self.assertRaises(ValueError): self.check(body)

    def test_cancel_and_stale_owner_block_retry(self):
        body = self.advance('generating'); checked = self.check(body)
        with self.assertRaises(ValueError): self.retry({**body, 'request_id':'another'}, checked)
        job = self.stories.get(self.job_id); job['cancel_requested'] = True; self.stories._save(job)
        with self.assertRaises(ValueError): self.retry(body, checked)

    def test_returned_owned_conversation_clears_old_recheck(self):
        body = self.advance('generating'); checked = self.check(body)
        result = self.manager.event({**body, 'stage':'route_restored',
            'route_check_id':checked['route_recovery']['check_id']})
        self.assertNotIn('route_recovery', result)

    def test_diagnostic_reads_exact_failed_scene_not_stored_predecessor(self):
        from core.meta_error_report import read_meta_error, safe_meta_url
        body = self.advance('generating')
        self.manager.event({**body, 'stage':'needs_attention', 'message':'route mismatch',
            'page_diagnostic':{'observed_url':'https://www.meta.ai/?secret=drop'}})
        data = read_meta_error(self.stories, self.job_id, 'META_VIDEO_REVIEW • route mismatch')
        self.assertEqual(data['index'], 1)
        self.assertEqual(data['observed_url'], 'https://www.meta.ai/')
        self.assertEqual(data['expected_url'], body['conversation_url'])
        self.assertEqual(read_meta_error(self.stories, self.job_id, 'unrelated failure'), {})
        self.assertEqual(safe_meta_url('https://evil.test/prompt/foo'), '')
        self.assertEqual(safe_meta_url('https://www.meta.ai.evil.test/'), '')

if __name__ == '__main__': unittest.main()
