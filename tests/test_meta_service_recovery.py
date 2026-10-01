"""Offline regression for the observed completed Meta server-error reply."""
import json
import subprocess
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from core.meta_video import MetaVideoManager, meta_reply_failure
from tests import test_meta_retry_381 as fixture


CASES = json.loads((fixture.ROOT / 'tests/meta_service_recovery_cases.json').read_text(encoding='utf-8'))
ANSWER = CASES[0][0]


class MetaServiceRecoveryTests(unittest.TestCase):
    setUp = fixture.MetaRetry381Tests.setUp
    advance = fixture.MetaRetry381Tests.advance
    retry = fixture.MetaRetry381Tests.retry

    def technical(self, body, **proof):
        return self.retry(body, **dict(answer_text=ANSWER, **proof))

    def test_classifier_shared_with_extension_and_priority_guards(self):
        for text, expected in CASES:
            with self.subTest(text=text):
                self.assertEqual(meta_reply_failure(text), expected)

    def test_schedule_is_durable_nonterminal_and_does_not_allocate_or_edit_package(self):
        package = self.manager.package(self.job_id, 1)
        body = self.advance()
        with patch('core.meta_video.time.time', return_value=1000):
            waiting = self.manager.event(self.technical(body))
        self.assertEqual(waiting['stage'], 'generating')
        self.assertEqual(waiting['request_id'], body['request_id'])
        self.assertEqual(waiting['conversation_url'], body['conversation_url'])
        self.assertEqual(waiting['recovery']['next_retry_at'], 1015)
        self.assertEqual(waiting['recovery']['attempt'], 1)
        self.assertNotIn('attempt_history', self.manager._store(self.job_id).read())
        restarted = MetaVideoManager(self.stories)
        with patch('core.meta_video.time.time', return_value=1014):
            self.assertEqual(restarted.event(self.technical(body)), waiting)
        self.assertEqual(restarted.package(self.job_id, 1), package)

    def test_technical_loop_has_capped_backoff_not_a_two_attempt_lifetime_stop(self):
        package = self.manager.package(self.job_id, 1)
        now = 1000
        previous_request = None
        for attempt, delay in enumerate((15, 30, 60, 120, 300, 300, 300), 1):
            body = self.advance()
            if previous_request:
                self.assertEqual(body['request_id'], previous_request)
            with patch('core.meta_video.time.time', return_value=now):
                waiting = self.manager.event(self.technical(body))
            self.assertEqual(waiting['recovery']['next_retry_at'], now + delay)
            self.manager = MetaVideoManager(self.stories)
            now += delay
            with patch('core.meta_video.time.time', return_value=now):
                fresh = self.manager.event(self.technical(body))
            self.assertEqual(fresh['stage'], 'prepared')
            self.assertEqual(fresh['service_retry_count'], attempt)
            self.assertEqual(fresh['retry_count'], 0)
            self.assertEqual(fresh['context_id'], body['context_id'])
            self.assertNotEqual(fresh['request_id'], body['request_id'])
            self.assertNotIn('conversation_url', fresh)
            self.assertNotIn('recovery', fresh)
            self.assertNotIn('choice', fresh)
            previous_request = fresh['request_id']
            history = self.manager._store(self.job_id).read()['attempt_history']['1']
            self.assertEqual(len(history), attempt)
            self.assertEqual(history[-1]['failure_reason'], 'transient_service_error')
            self.assertEqual(history[-1]['conversation_url'], body['conversation_url'])
            self.assertEqual(self.manager.package(self.job_id, 1), package)

    def test_lost_ack_and_concurrent_due_events_return_exactly_one_successor(self):
        body = self.advance()
        with patch('core.meta_video.time.time', return_value=1000):
            self.manager.event(self.technical(body))
        with patch('core.meta_video.time.time', return_value=1015), ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.manager.event(self.technical(body)), range(2)))
        self.assertEqual(results[0], results[1])
        fresh = results[0]
        next_body = {key: fresh[key] for key in ('job_id', 'index', 'request_id', 'context_id')}
        advanced = self.manager.event(dict(next_body, stage='uploading'))
        self.assertEqual(MetaVideoManager(self.stories).event(self.technical(body)), advanced)
        self.assertEqual(len(self.manager._store(self.job_id).read()['attempt_history']['1']), 1)

    def test_due_time_does_not_override_owner_busy_video_choice_or_complete_proof(self):
        body = self.advance()
        with patch('core.meta_video.time.time', return_value=1000):
            original = self.manager.event(self.technical(body))
        changes = ({'matched_request': False}, {'answer_complete': False}, {'answer_truncated': True},
                   {'stop': True}, {'busy': True}, {'video_count': 1}, {'video_count': False},
                   {'samples': 1}, {'stable_ms': 4999}, {'stable_ms': float('inf')},
                   {'stable_ms': float('nan')})
        for change in changes:
            with self.subTest(change=change), patch('core.meta_video.time.time', return_value=9999), self.assertRaises(ValueError):
                self.manager.event(self.technical(body, **change))
            self.assertEqual(self.manager.get(self.job_id, 1), original)
        for change in ({'request_id': 'foreign'}, {'context_id': 'foreign'},
                       {'conversation_url': 'https://www.meta.ai/prompt/foreign'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.manager.event(dict(self.technical(body), **change))
        for answer in (CASES[4][0], CASES[5][0], 'Generating your video now.'):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                self.manager.event(self.retry(body, answer_text=answer))

    def test_changed_completed_service_reply_starts_new_cooldown_not_instant_send(self):
        body = self.advance()
        with patch('core.meta_video.time.time', return_value=1000):
            self.manager.event(self.technical(body))
        with patch('core.meta_video.time.time', return_value=1015):
            waiting = self.manager.event(self.retry(body, answer_text=CASES[1][0]))
        self.assertEqual(waiting['request_id'], body['request_id'])
        self.assertEqual(waiting['recovery']['attempt'], 1)
        self.assertEqual(waiting['recovery']['next_retry_at'], 1030)

    def test_late_video_advances_download_and_cannot_retry(self):
        body = self.advance()
        with patch('core.meta_video.time.time', return_value=1000):
            self.manager.event(self.technical(body))
        result = self.manager.event(dict(body, stage='download_intent'))
        self.assertEqual(result['stage'], 'download_intent')
        self.assertNotIn('recovery', result)
        with self.assertRaises(ValueError):
            self.manager.event(self.technical(body))
        self.assertNotIn('attempt_history', self.manager._store(self.job_id).read())

    def test_cancel_and_unknown_send_never_become_technical_retry(self):
        body = self.advance('send_intent')
        with self.assertRaises(ValueError):
            self.manager.event(self.technical(body))
        body['conversation_url'] = 'https://www.meta.ai/prompt/owned'
        for stage in ('submitted', 'generating'):
            self.manager.event(dict(body, stage=stage))
        with patch('core.meta_video.time.time', return_value=1000):
            self.manager.event(self.technical(body))
        job = self.stories.get(self.job_id)
        job['cancel_requested'] = True
        self.stories._save(job)
        with self.assertRaises(ValueError):
            self.manager.event(self.technical(body))

    def test_saved_scene_and_original_image_are_untouched(self):
        body = self.advance()
        store = self.manager._store(self.job_id)
        data = store.read()
        data['scenes']['2'] = dict(stage='stored', path='kept.mp4', sha256='keep')
        store.write(data)
        with patch('core.meta_video.time.time', return_value=1000):
            self.manager.event(self.technical(body))
        with patch('core.meta_video.time.time', return_value=1015):
            self.manager.event(self.technical(body))
        self.assertEqual(store.read()['scenes']['2'], data['scenes']['2'])
        self.assertEqual((self.stories._folder(self.job_id) / 'generated/scene.png').read_bytes(), b'original-image')

    def test_actual_extension_service_controller(self):
        result = subprocess.run(['node', str(fixture.ROOT / 'tests/meta_service_recovery.cjs')],
                                capture_output=True, text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
