"""Explicit Continue and observed lost Meta tabs restart one unfinished scene."""
import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from core.meta_video import MetaVideoManager
from core.story_manager import StoryManager


class MetaFreshStartTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.stories = StoryManager(temporary.name)
        job = self.stories.create(topic='saved topic', scene_count=6, image_ai_provider='gemini',
                                  video_generation_mode='meta_ai')
        self.job_id = job['id']
        self.folder = self.stories._folder(self.job_id)
        (self.folder / 'generated' / 'scene.png').write_bytes(b'saved-source-image')
        job.update(scene_count=1, generated_images=['generated/scene.png'],
                   scene_prompts=['saved visual'], scene_narrations=['saved action'],
                   audio_choices={'mode': 'none'}, status='running')
        self.stories._save(job)
        self.manager = MetaVideoManager(self.stories, lambda _: dict(width=720, height=1280, duration=10))

    def advance(self, end='send_intent', index=1):
        receipt = self.manager.begin(self.job_id, index)
        body = {key: receipt[key] for key in ('job_id', 'index', 'request_id', 'context_id')}
        for stage in self.manager.STAGES[1:]:
            if stage == 'submitted':
                body['conversation_url'] = 'https://www.meta.ai/prompt/saved-conversation'
            if stage == 'downloading':
                body['download_id'] = 17
            self.manager.event({**body, 'stage': stage})
            if stage == end:
                break
        return body

    def missing(self, body, **changes):
        proof = dict(reason='tab_missing', tab_id=42, tab_missing=True, session_owned=True)
        proof.update(changes)
        return {**body, 'stage': 'fresh_start', 'fresh_start_evidence': proof}

    def assert_clean(self, receipt):
        self.assertEqual(receipt['stage'], 'prepared')
        for key in ('conversation_url', 'resume_stage', 'choice', 'download_id', 'send_diagnostic',
                    'route_recovery', 'redesign', 'retry_exhausted'):
            self.assertNotIn(key, receipt)

    def test_manual_unknown_send_has_clean_idempotent_successor_and_unchanged_job(self):
        old = self.advance()
        self.manager.event({**old, 'stage': 'needs_attention', 'message': 'unknown Send'})
        before = copy.deepcopy(self.stories.get(self.job_id))
        package = self.manager.package(self.job_id, 1)
        fresh = self.manager.restart_unfinished_on_continue(self.job_id)
        self.assert_clean(fresh)
        self.assertEqual(fresh['retry_previous_request_id'], old['request_id'])
        self.assertNotEqual(fresh['request_id'], old['request_id'])
        self.assertNotIn('fresh_start_not_before', fresh)
        self.assertEqual(self.manager.restart_unfinished_on_continue(self.job_id), fresh)
        restarted = MetaVideoManager(self.stories)
        self.assertEqual(restarted.restart_unfinished_on_continue(self.job_id), fresh)
        self.assertEqual(self.manager.package(self.job_id, 1), package)
        self.assertEqual(self.stories.get(self.job_id), before)
        self.assertEqual((self.folder / 'generated' / 'scene.png').read_bytes(), b'saved-source-image')
        self.assertEqual(len(self.manager._store(self.job_id).read()['attempt_history']['1']), 1)
        with self.assertRaises(ValueError):
            self.manager.event({**old, 'stage': 'submitted'})

    def test_manual_generating_discards_old_url_and_choice_but_preserves_archive(self):
        old = self.advance('generating')
        fresh = self.manager.restart_unfinished_on_continue(self.job_id)
        self.assert_clean(fresh)
        history = self.manager._store(self.job_id).read()['attempt_history']['1']
        self.assertEqual(history[0]['conversation_url'], old['conversation_url'])
        self.assertEqual(history[0]['stage'], 'generating')

    def test_missing_tab_lost_ack_and_competing_calls_create_one_successor(self):
        old = self.advance('generating')
        event = self.missing(old)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.manager.event(event), range(4)))
        self.assertTrue(all(row == results[0] for row in results))
        fresh = results[0]
        self.assert_clean(fresh)
        self.assertEqual(fresh['fresh_start_count'], 1)
        self.assertEqual(fresh['fresh_start_not_before'] - fresh['updated_at'], 5)
        resumed = MetaVideoManager(self.stories)
        self.assertEqual(resumed.event(event), fresh)
        self.assertEqual(len(self.manager._store(self.job_id).read()['attempt_history']['1']), 1)
        next_body = {key: fresh[key] for key in ('job_id', 'index', 'request_id', 'context_id')}
        advanced = self.manager.event({**next_body, 'stage': 'uploading'})
        self.assertEqual(self.manager.event(event), advanced)
        newer = self.manager.event(self.missing(next_body))
        self.assertEqual(newer['fresh_start_count'], 2)
        self.assertEqual(newer['fresh_start_not_before'] - newer['updated_at'], 10)
        with self.assertRaises(ValueError):
            self.manager.event(event)

    def test_stored_scene_and_clip_bytes_survive_restart_of_second_scene(self):
        job = self.stories.get(self.job_id)
        job.update(scene_count=2, generated_images=['generated/scene.png'] * 2,
                   scene_prompts=['saved visual', 'next visual'], scene_narrations=['saved action', 'next action'])
        self.stories._save(job)
        old = self.advance('downloading')
        result = self.folder / 'result.mp4'
        result.write_bytes(b'saved-video' * 200)
        stored = self.manager.event({**old, 'stage': 'stored', 'filename': str(result)})
        bytes_before = (self.folder / stored['path']).read_bytes()
        second = self.advance(index=2)
        before = copy.deepcopy(self.stories.get(self.job_id))
        fresh = self.manager.restart_unfinished_on_continue(self.job_id)
        self.assertEqual(fresh['index'], 2)
        self.assertEqual(fresh['retry_previous_request_id'], second['request_id'])
        self.assertEqual(self.manager.get(self.job_id, 1), stored)
        self.assertEqual((self.folder / stored['path']).read_bytes(), bytes_before)
        self.assertEqual(self.stories.get(self.job_id), before)
        with self.assertRaises(ValueError):
            self.manager.event(self.missing(old))

    def test_invalid_observation_stale_owner_inactive_and_cancelled_do_not_change_receipt(self):
        old = self.advance()
        before = self.manager._store(self.job_id).read()
        invalid = [dict(reason='other'), dict(reason=[]), dict(tab_id=True), dict(tab_id=-2),
                   dict(tab_missing=False), dict(session_owned='true'),
                   dict(reason='tab_not_owned', tab_missing=False, session_owned=True),
                   dict(reason='tab_left_meta', tab_missing=False, session_owned=False)]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manager.event(self.missing(old, **changes))
        for field in ('request_id', 'context_id'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.manager.event({**self.missing(old), field: 'stale'})
        for changes in (dict(status='failed'), dict(status='running', cancel_requested=True)):
            job = self.stories.get(self.job_id)
            job.update(changes)
            self.stories._save(job)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manager.event(self.missing(old))
        self.assertEqual(self.manager._store(self.job_id).read(), before)

    def test_unowned_and_left_meta_are_distinct_typed_observations(self):
        old = self.advance()
        fresh = self.manager.event(self.missing(old, reason='tab_not_owned', tab_missing=False, session_owned=False))
        new_body = {key: fresh[key] for key in ('job_id', 'index', 'request_id', 'context_id')}
        next_event = self.missing(new_body, reason='tab_left_meta', tab_missing=False, session_owned=True)
        self.assertEqual(self.manager.event(next_event), fresh)
        with patch('core.meta_video.time.time', return_value=fresh['fresh_start_not_before']):
            second = self.manager.event(next_event)
        self.assertEqual(second['fresh_start_reason'], 'tab_left_meta')
        self.assert_clean(second)

    def test_route_home_requires_stable_ready_empty_owned_page(self):
        old = self.advance('generating')
        route = dict(observed_url='https://www.meta.ai/', document_id='new-document', ready=True,
                     composer_empty=True, answer_empty=True, login=False, busy=False, stop=False,
                     dialog=False, composer_count=1, user_count=0, image_count=0, video_count=0,
                     message_count=0, samples=2, stable_ms=5000)
        event = {**self.missing(old, reason='route_home', tab_missing=False, session_owned=True),
                 'route_evidence': route}
        for change in (dict(ready=False), dict(busy=True), dict(composer_empty=False), dict(video_count=1),
                       dict(samples=1), dict(stable_ms=4999), dict(stable_ms=float('nan')),
                       dict(observed_url='https://www.meta.ai/prompt/foreign')):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.manager.event({**event, 'route_evidence': {**route, **change}})
        fresh = self.manager.event(event)
        self.assert_clean(fresh)
        self.assertEqual(fresh['fresh_start_reason'], 'route_home')
        self.assertEqual(fresh['fresh_start_route_evidence'], route)
        self.assertEqual(self.manager.event(event), fresh)

    def test_ordinary_worker_resume_keeps_unknown_send_owner(self):
        old = self.advance()
        self.manager.event({**old, 'stage': 'needs_attention'})
        resumed = self.manager.begin(self.job_id, 1, resume=True)
        self.assertEqual(resumed['request_id'], old['request_id'])
        self.assertEqual(resumed['stage'], 'send_intent')


if __name__ == '__main__':
    unittest.main()
