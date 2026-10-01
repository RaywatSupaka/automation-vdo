"""Explicit Meta helper Continue preserves completed image/prompt checkpoints."""
import tempfile
import unittest
from pathlib import Path

from core.meta_video import MetaVideoManager
from core.story_manager import StoryManager
from tests.test_audit_fixes_426 import picture


ANSWER = 'ขออภัย ดูเหมือนว่าทางฝั่งของฉันจะเกิดปัญหาบางอย่าง โปรดลองอีกครั้ง'


class MetaContinueFreshTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.stories = StoryManager(temporary.name)
        job = self.stories.create(topic='test', scene_count=6, video_generation_mode='meta_ai')
        self.job_id = job['id']
        folder = self.stories._folder(self.job_id)
        image = folder / 'generated' / 'scene.png'
        image.write_bytes(b'original-image')
        job.update(scene_count=1, generated_images=['generated/scene.png'],
                   scene_prompts=['one saved scene'], scene_narrations=['saved action'])
        self.stories._save(job)
        self.manager = MetaVideoManager(self.stories)
        self.image = image

    def _advance(self, end='generating', index=1):
        receipt = self.manager.begin(self.job_id, index)
        body = {key: receipt[key] for key in ('job_id', 'index', 'request_id', 'context_id')}
        for stage in self.manager.STAGES[1:]:
            if stage == 'submitted':
                body['conversation_url'] = 'https://www.meta.ai/prompt/' + receipt['request_id']
            if stage == 'downloading':
                body['download_id'] = 9
            self.manager.event({**body, 'stage': stage})
            if stage == end:
                break
        return body

    def _redesign(self, body):
        return self.manager.event({**body, 'stage': 'redesign_prepare', 'retry_evidence': dict(
            matched_request=True, answer_complete=True, answer_truncated=False,
            stop=False, busy=False, video_count=0, samples=2, stable_ms=6000,
            answer_text=ANSWER)})

    def test_manual_continue_allocates_new_helper_then_new_meta_home_context(self):
        before_image = self.image.read_bytes()
        old_body = self._advance()
        old = self._redesign(old_body)
        claimed = self.manager.redesign_event({**old_body, 'redesign_id': old['redesign']['id'], 'action': 'claim'})
        self.assertTrue(claimed['send_authorized'])

        fresh = self.manager.restart_unfinished_on_continue(self.job_id)
        self.assertEqual(fresh['stage'], 'redesigning')
        self.assertEqual(fresh['redesign']['phase'], 'prepared')
        self.assertNotEqual(fresh['request_id'], old['request_id'])
        self.assertNotEqual(fresh['redesign']['id'], old['redesign']['id'])
        self.assertEqual(fresh['fresh_start_reason'], 'manual_redesign_continue')
        self.assertEqual(fresh['redesign_previous_request_id'], old['request_id'])
        self.assertEqual(fresh['superseded_redesign_id'], old['redesign']['id'])
        self.assertNotIn('conversation_url', fresh)
        self.assertEqual(self.image.read_bytes(), before_image)
        self.assertEqual(self.manager.begin(self.job_id, 1, resume=True)['request_id'], fresh['request_id'])
        repeated = self.manager.restart_unfinished_redesign_on_continue(self.job_id)
        self.assertEqual(repeated['request_id'], fresh['request_id'])
        self.assertEqual(repeated['redesign']['id'], fresh['redesign']['id'])
        self.assertEqual(repeated['redesign']['request'], fresh['redesign']['request'])
        self.assertEqual(repeated['redesign']['base_request'], fresh['redesign']['request'])
        self.assertIn('Generate and show exactly one NEW', repeated['redesign']['request'])
        self.assertNotIn('Return one JSON object', repeated['redesign']['request'])
        self.assertEqual(self.manager._store(self.job_id).read()['attempt_history']['1'][0]['conversation_url'],
                         old_body['conversation_url'])
        with self.assertRaises(ValueError):
            self.manager.redesign_event({**old_body, 'redesign_id':old['redesign']['id'], 'action':'claim'})

        next_body = {key: repeated[key] for key in ('job_id', 'index', 'request_id', 'context_id')}
        self.assertTrue(self.manager.redesign_event({**next_body, 'redesign_id':repeated['redesign']['id'],
                                                     'action':'claim'})['send_authorized'])
        self.manager.redesign_event({**next_body, 'redesign_id':repeated['redesign']['id'],
                                     'action':'save_image', 'image':picture('orange')})
        prepared = self.manager.redesign_event({**next_body, 'redesign_id':repeated['redesign']['id'],
                                                'action':'save_prompt',
                                                'proposal':{'needs_review':False,
                                                            'video_prompt':'Track slowly as the adult crosses the market.'}})
        self.assertEqual(prepared['stage'], 'prepared')
        self.assertNotEqual(prepared['context_id'], old['context_id'])
        self.assertNotIn('conversation_url', prepared)
        self.assertNotEqual(self.manager.package(self.job_id, 1)['image_path'], str(self.image))

    def test_image_is_saved_before_prompt_and_resume_keeps_it(self):
        original_bytes = self.image.read_bytes()
        body = self._advance()
        receipt = self._redesign(body)
        event = {**body, 'redesign_id': receipt['redesign']['id']}
        self.manager.redesign_event({**event, 'action': 'claim'})
        image_event = {**event, 'action': 'save_image', 'image': picture('orange')}
        saved = self.manager.redesign_event(image_event)
        saved_image = saved['redesign']['saved_image']
        self.assertEqual(saved['redesign']['phase'], 'image_saved')
        self.assertTrue(Path(saved_image['image_path']).is_file())
        self.assertIn('video_prompt', saved['redesign']['prompt_request'])
        self.assertEqual(self.manager.package(self.job_id, 1)['image_path'], str(self.image))
        self.assertNotIn('overrides', self.manager._store(self.job_id).read())
        self.assertEqual(self.image.read_bytes(), original_bytes)
        self.assertEqual(self.manager.redesign_event(image_event), saved)
        for field in ('request_id', 'context_id', 'redesign_id'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.manager.redesign_event({**image_event, field: 'foreign'})
        with self.assertRaises(ValueError):
            self.manager.redesign_event({**event, 'action': 'save_image', 'image': picture('green')})
        with self.assertRaises(ValueError):
            self.manager.redesign_event({**event, 'action': 'save_prompt',
                                         'proposal': {'needs_review': True,
                                                      'video_prompt': 'Move the camera slowly through this scene.'}})
        self.assertEqual(self.manager.get(self.job_id, 1)['redesign']['phase'], 'image_saved')

        self.manager.event({**body, 'stage': 'needs_attention', 'message': 'Prompt needs review'})
        continued = self.manager.restart_unfinished_on_continue(self.job_id)
        self.assertEqual(continued['stage'], 'redesigning')
        self.assertEqual(continued['request_id'], receipt['request_id'])
        self.assertEqual(continued['redesign']['id'], receipt['redesign']['id'])
        self.assertEqual(continued['redesign']['saved_image'], saved_image)
        self.assertEqual(continued['redesign']['prompt_attempt'], 1)
        self.assertEqual(self.manager.restart_unfinished_redesign_on_continue(self.job_id)['redesign']['prompt_attempt'], 1)

        prompt_event = {**event, 'action': 'save_prompt',
                        'proposal': {'needs_review': False,
                                     'video_prompt': 'Track slowly as the adult crosses the market.'}}
        restarted = MetaVideoManager(self.stories)
        next_scene = restarted.redesign_event(prompt_event)
        self.assertEqual(next_scene['stage'], 'prepared')
        self.assertEqual(restarted.redesign_event(prompt_event), next_scene)
        self.assertEqual(restarted.redesign_event(image_event), next_scene)
        for field in ('request_id', 'context_id', 'redesign_id'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                restarted.redesign_event({**prompt_event, field: 'foreign'})
        self.assertEqual(self.image.read_bytes(), original_bytes)
        self.assertEqual(restarted.package(self.job_id, 1)['image_path'], saved_image['image_path'])
        history = restarted._store(self.job_id).read()['attempt_history']['1']
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['redesign']['phase'], 'prompt_saved')

    def test_legacy_json_first_receipt_continue_requests_an_actual_image(self):
        body = self._advance()
        old = self._redesign(body)
        store = self.manager._store(self.job_id)
        with store.locked():
            data = store.read_unlocked({'scenes': {}})
            data['scenes']['1']['redesign']['request'] = (
                'Return one JSON object only: image_prompt, video_prompt, needs_review. Do not generate media yet.')
            data['scenes']['1']['redesign'].pop('image_request', None)
            store.write_unlocked(data)
        fresh = self.manager.restart_unfinished_redesign_on_continue(self.job_id)
        self.assertNotEqual(fresh['request_id'], old['request_id'])
        self.assertIn('Generate and show exactly one NEW', fresh['redesign']['request'])
        self.assertNotIn('Return one JSON object only', fresh['redesign']['request'])
        self.assertEqual(fresh['redesign']['image_request'], fresh['redesign']['request'])

    def test_continue_restarts_image_step_if_saved_image_is_corrupt(self):
        body = self._advance()
        receipt = self._redesign(body)
        event = {**body, 'redesign_id': receipt['redesign']['id']}
        self.manager.redesign_event({**event, 'action': 'claim'})
        saved = self.manager.redesign_event({**event, 'action': 'save_image', 'image': picture('orange')})
        Path(saved['redesign']['saved_image']['image_path']).write_bytes(b'corrupt-test-fixture')
        self.manager.event({**body, 'stage': 'needs_attention', 'message': 'Prompt needs review'})

        fresh = self.manager.restart_unfinished_redesign_on_continue(self.job_id)
        self.assertNotEqual(fresh['request_id'], receipt['request_id'])
        self.assertEqual(fresh['redesign']['phase'], 'prepared')
        self.assertNotIn('saved_image', fresh['redesign'])
        self.assertNotIn('prompt_request', fresh['redesign'])
        self.assertIn('Generate and show exactly one NEW', fresh['redesign']['request'])
        self.assertEqual(self.image.read_bytes(), b'original-image')

    def test_unknown_send_and_unproven_render_do_not_restart(self):
        body = self._advance('send_intent')
        self.assertIsNone(self.manager.restart_unfinished_redesign_on_continue(self.job_id))
        self.manager.event({**body, 'stage':'needs_attention', 'message':'Unknown send'})
        self.assertIsNone(self.manager.restart_unfinished_redesign_on_continue(self.job_id))
        self.assertEqual(self.manager.get(self.job_id, 1)['request_id'], body['request_id'])
        self.assertNotIn('attempt_history', self.manager._store(self.job_id).read())

    def test_continue_preserves_finished_scene_and_restarts_only_next_failed_scene(self):
        folder = self.stories._folder(self.job_id)
        for index in (2, 3):
            (folder / 'generated' / f'scene_{index}.png').write_bytes(f'image-{index}'.encode())
        job = self.stories.get(self.job_id)
        job.update(scene_count=3,
                   generated_images=['generated/scene.png', 'generated/scene_2.png', 'generated/scene_3.png'],
                   scene_prompts=['one', 'two', 'three'], scene_narrations=['one', 'two', 'three'])
        self.stories._save(job)
        finished = self.manager.begin(self.job_id, 1)
        store = self.manager._store(self.job_id)
        with store.locked():
            data = store.read_unlocked({'scenes': {}})
            data['scenes']['1']['stage'] = 'stored'
            store.write_unlocked(data)
        second_body = self._advance(index=2)
        old_second = self._redesign(second_body)
        fresh = self.manager.restart_unfinished_redesign_on_continue(self.job_id)
        self.assertEqual(fresh['index'], 2)
        self.assertEqual(self.manager.get(self.job_id, 1)['request_id'], finished['request_id'])
        self.assertEqual(self.manager.get(self.job_id, 1)['stage'], 'stored')
        self.assertNotEqual(fresh['request_id'], old_second['request_id'])
        self.assertEqual(self.manager.get(self.job_id, 3), {})


if __name__ == '__main__':
    unittest.main()
