import json
import logging
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path

from core.meta_video import MetaVideoManager, meta_reply_failure
from core.story_manager import StoryManager

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'tests/meta_retry_cases_381.json').read_text(encoding='utf-8'))


class MetaRetry381Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stories = StoryManager(self.temp.name)
        job = self.stories.create(topic='test', scene_count=6, video_generation_mode='meta_ai')
        self.job_id = job['id']
        folder = self.stories._folder(self.job_id)
        (folder / 'generated/scene.png').write_bytes(b'original-image')
        job.update(scene_count=1, generated_images=['generated/scene.png'],
                   scene_prompts=['scene'], scene_narrations=['action'])
        self.stories._save(job)
        self.manager = MetaVideoManager(self.stories)

    def advance(self, end='generating'):
        receipt = self.manager.begin(self.job_id, 1)
        body = {key: receipt[key] for key in ('job_id', 'index', 'request_id', 'context_id')}
        for stage in self.manager.STAGES[1:]:
            if stage == 'submitted':
                body['conversation_url'] = 'https://www.meta.ai/prompt/' + receipt['request_id']
            if stage == 'downloading': body['download_id'] = 9
            self.manager.event({**body, 'stage': stage})
            if stage == end: break
        return body

    def retry(self, body, **proof):
        return {**body, 'stage': 'retry_prepared', 'retry_evidence': dict(
            matched_request=True, answer_complete=True, answer_truncated=False, stop=False, busy=False,
            video_count=0, stable_ms=5000, samples=2, answer_text=CASES[0][0]) | proof}

    def test_classifier_same_cases_as_extension(self):
        for answer, expected in CASES:
            with self.subTest(answer=answer): self.assertEqual(meta_reply_failure(answer), expected)

    def test_original_package_preserved_and_failed_attempt_archived(self):
        before = self.manager.package(self.job_id, 1)
        body = self.advance()
        result = self.manager.event(self.retry(body))
        self.assertNotEqual(result['request_id'], body['request_id'])
        self.assertEqual(result['stage'], 'prepared')
        self.assertEqual(result['retry_count'], 1)
        self.assertNotIn('conversation_url', result)
        self.assertEqual(before, self.manager.package(self.job_id, 1))
        history = self.manager._store(self.job_id).read()['attempt_history']['1']
        self.assertEqual(history[0]['request_id'], body['request_id'])
        self.assertEqual(history[0]['conversation_url'], body['conversation_url'])
        self.assertEqual(history[0]['failure_reason'], 'completed_no_video')

    def test_lost_ack_replay_does_not_spend_another_retry_or_reset_successor(self):
        body = self.advance()
        retry = self.retry(body)
        result = self.manager.event(retry)
        new_body = {key: result[key] for key in ('job_id', 'index', 'request_id', 'context_id')}
        updated = self.manager.event({**new_body, 'stage': 'uploading'})
        restarted = MetaVideoManager(self.stories)
        self.assertEqual(restarted.event(retry), updated)
        self.assertEqual(len(restarted._store(self.job_id).read()['attempt_history']['1']), 1)
        with self.assertRaises(ValueError): self.manager.event({**body, 'stage': 'generating'})

    def test_two_retries_are_durable_and_explicit_continue_starts_fresh_after_failure(self):
        for count in (1, 2):
            result = self.manager.event(self.retry(self.advance()))
            self.assertEqual(result['retry_count'], count)
            self.manager = MetaVideoManager(self.stories)
        body = self.advance()
        result = self.manager.event(self.retry(body))
        self.assertEqual(result['stage'], 'needs_attention')
        self.assertTrue(result['retry_exhausted'])
        self.assertEqual(result['request_id'], body['request_id'])
        self.assertEqual(self.manager.begin(self.job_id, 1)['stage'], 'needs_attention')
        fresh = self.manager.begin(self.job_id, 1, resume=True)
        self.assertEqual(fresh['stage'], 'prepared')
        self.assertEqual(fresh['retry_count'], 0)
        self.assertEqual(fresh['manual_restart_count'], 1)
        self.assertNotEqual(fresh['request_id'], body['request_id'])
        self.assertNotIn('conversation_url', fresh)
        self.assertEqual(self.manager.begin(self.job_id, 1, resume=True)['request_id'], fresh['request_id'])
        self.assertEqual(self.manager.event(self.retry(body))['request_id'], fresh['request_id'])
        self.assertEqual(len(self.manager._store(self.job_id).read()['attempt_history']['1']), 3)

    def test_unavailable_file_retries_with_fresh_owned_attempt(self):
        body = self.advance()
        fresh = self.manager.event(self.retry(body, answer_text='Response 1: video (file unavailable). Response 2: video (file unavailable).'))
        self.assertNotEqual(fresh['request_id'], body['request_id'])
        self.assertNotIn('conversation_url', fresh)
        self.assertEqual(fresh['stage'], 'prepared')

    def test_resume_does_not_restart_unknown_send(self):
        body = self.advance('send_intent')
        self.manager.event({**body, 'stage': 'needs_attention', 'message': 'Unknown send'})
        fresh = self.manager.begin(self.job_id, 1, resume=True)
        self.assertEqual(fresh['request_id'], body['request_id'])
        self.assertEqual(fresh['stage'], 'send_intent')

    def test_explicit_continue_after_presend_failure_has_no_old_url_or_intents(self):
        body = self.advance('ready_to_send')
        self.manager.event({**body, 'stage': 'needs_attention', 'message': 'Preparation failed'})
        fresh = self.manager.begin(self.job_id, 1, resume=True)
        self.assertNotEqual(fresh['request_id'], body['request_id'])
        self.assertEqual(fresh['stage'], 'prepared')
        self.assertNotIn('conversation_url', fresh)

    def test_native_comparison_dom_regression(self):
        result = subprocess.run(['node', 'tests/meta_comparison_412.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_incomplete_wrong_busy_and_policy_evidence_never_retry(self):
        body = self.advance()
        original = self.manager.get(self.job_id, 1)
        for changes in ({'matched_request': False}, {'answer_complete': False}, {'answer_truncated': True},
                        {'stop': True}, {'busy': True}, {'video_count': 1}, {'video_count': False},
                        {'samples': 1}, {'stable_ms': 4999}, {'answer_text': ''},
                        {'answer_text': CASES[7][0]}, {'answer_text': CASES[9][0]},
                        {'answer_text': "I couldn't create it." + 'x' * 12000}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manager.event(self.retry(body, **changes))
            self.assertEqual(self.manager.get(self.job_id, 1), original)
        for key in ('matched_request', 'answer_complete', 'answer_truncated', 'stop', 'busy', 'video_count', 'samples', 'stable_ms'):
            invalid = self.retry(body)
            del invalid['retry_evidence'][key]
            with self.subTest(missing=key), self.assertRaises(ValueError): self.manager.event(invalid)

    def test_unknown_send_and_download_cannot_restart(self):
        body = self.advance('send_intent')
        with self.assertRaises(ValueError): self.manager.event(self.retry(body))
        body['conversation_url'] = 'https://www.meta.ai/prompt/test'
        for stage in ('submitted', 'generating', 'download_intent', 'downloading'):
            self.manager.event({**body, 'stage': stage, 'download_id': 9})
        with self.assertRaises(ValueError): self.manager.event(self.retry(body))

    def test_cancel_context_and_wrong_conversation_block_retry(self):
        body = self.advance()
        with self.assertRaises(ValueError):
            self.manager.event({**self.retry(body), 'conversation_url': 'https://www.meta.ai/prompt/other'})
        with self.assertRaises(ValueError):
            self.manager.event({**self.retry(body), 'context_id': 'wrong'})
        job = self.stories.get(self.job_id)
        job['cancel_requested'] = True
        self.stories._save(job)
        with self.assertRaises(ValueError): self.manager.event(self.retry(body))

    def test_existing_stored_scenes_and_files_are_untouched(self):
        body = self.advance()
        store = self.manager._store(self.job_id)
        data = store.read()
        data['scenes']['2'] = {'stage': 'stored', 'path': 'kept.mp4', 'sha256': 'keep'}
        store.write(data)
        self.manager.event(self.retry(body))
        self.assertEqual(store.read()['scenes']['2'], data['scenes']['2'])
        self.assertEqual((self.stories._folder(self.job_id) / 'generated/scene.png').read_bytes(), b'original-image')

    def test_actual_extension_dom_and_retry_controller(self):
        result = subprocess.run(['node', str(ROOT / 'tests/meta_retry_381.cjs')],
                                capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_retry_through_paired_authenticated_bridge_and_new_package(self):
        from core.local_bridge import LocalBridge
        from core.product_manager import ProductManager
        body = self.advance()
        bridge = LocalBridge('127.0.0.1', 0, ProductManager(self.temp.name),
                             logging.getLogger('meta-retry-test'), stories=self.stories).start()
        try:
            base = f'http://127.0.0.1:{bridge.server.server_address[1]}'
            from tests.extension_identity_fixture import pair_fixture
            headers = {'Origin': pair_fixture(bridge), 'X-SmartFlow-Token': bridge._extension_token,
                       'Content-Type': 'application/json'}
            event = {**self.retry(body), 'version': LocalBridge.REQUIRED_EXTENSION_VERSION}
            request = urllib.request.Request(base + '/api/meta-video/event',
                data=json.dumps(event).encode(), headers=headers)
            with urllib.request.urlopen(request, timeout=5) as response:
                receipt = json.load(response)['receipt']
            request = urllib.request.Request(base + f'/api/meta-video/package?job_id={self.job_id}&index=1', headers=headers)
            with urllib.request.urlopen(request, timeout=5) as response:
                package = json.load(response)['package']
            self.assertEqual(package['stage'], 'prepared')
            self.assertEqual(package['request_id'], receipt['request_id'])
            self.assertEqual(package['image_sha256'], self.manager.package(self.job_id, 1)['image_sha256'])
            self.assertEqual(package['prompt'], self.manager.package(self.job_id, 1)['prompt'])
        finally:
            bridge.stop()


if __name__ == '__main__': unittest.main()
