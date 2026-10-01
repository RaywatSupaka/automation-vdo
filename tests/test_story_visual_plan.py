import base64
import copy
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import subprocess

from PIL import Image
from core.atomic_json import AtomicJsonFile
from core.flow_motion_plan import motion_plan_action, plan_context, saved_motion_prompt
from core.story_visual_plan import repaired_image, SCENE_ACTION_RULE


class StoryVisualPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'generated').mkdir()
        self.image = self.root / 'generated/scene_01.png'
        Image.new('RGB', (288, 512), 'red').save(self.image)
        self.original = self.image.read_bytes()
        self.job = dict(id='STORY-TEST', image_ai_provider='chatgpt', scene_count=2,
                        scene_prompts=['Leave the city, rear view with city ahead', 'unchanged scene'],
                        scene_narrations=['He leaves the city without reward', 'He rests'],
                        generated_images=['generated/scene_01.png', 'generated/scene_02.png'])
        Image.new('RGB', (288, 512), 'green').save(self.root / 'generated/scene_02.png')
        self.context = plan_context(self.root, self.job, 1)
        other = plan_context(self.root, self.job, 2)
        self.store = AtomicJsonFile(self.root / 'prompts/flow_motion_plans.json')
        self.result = dict(job_id=self.job['id'], index=1, context_id=self.context['context_id'],
                           prompt='One vertical 9:16 video. The swordsman walks toward the city.',
                           needs_review=True, reference_compatible=False, material_change=True,
                           review_reason='Image faces the city, narration requires leaving it.')
        self.other = dict(phase='ready', context=other, prompt='preserved scene two')
        self.store.write({'schema': 1, 'plans': {self.context['context_id']:
            dict(phase='answered', context=self.context, request='old request', result=self.result,
                 content_recheck_attempt=1), other['context_id']: self.other}})

    def call(self, action='status', **extra):
        return motion_plan_action(self.root, self.job, dict(action=action, provider=self.job['image_ai_provider'],
            index=1, context_id=self.context['context_id'], **extra))

    def begin(self):
        self.call('story_visual_recheck')
        self.call('mark_sending')
        self.call('review', result=self.result)
        return self.call('story_visual_begin')['record']['story_visual_repair']

    def save_image(self, repair, color='blue'):
        self.call('story_visual_mark_image', request_id=repair['request_id'], conversation_url='https://chatgpt.com/c/fixture')
        buffer = io.BytesIO()
        Image.new('RGB', (288, 512), color).save(buffer, format='PNG')
        self.data = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
        return self.call('story_visual_image', request_id=repair['request_id'], image=self.data)['record']['story_visual_repair']

    def finish(self):
        repair = self.save_image(self.begin())
        repair = self.call('story_visual_prepare_motion', request_id=repair['request_id'])['record']['story_visual_repair']
        self.call('story_visual_mark_motion', request_id=repair['request_id'])
        answer = dict(job_id=self.job['id'], index=1, context_id=repair['candidate_context']['context_id'],
                      prompt='One vertical 9:16 video. The swordsman walks away from the city toward the camera.',
                      needs_review=False, reference_compatible=True, material_change=False)
        return repair, answer

    def test_legacy_answer_gets_new_action_request_not_flag_override(self):
        status = self.call()
        self.assertTrue(status['story_visual_repair_available'])
        result = self.call('story_visual_recheck')['record']
        self.assertEqual(result['prior_story_visual_answer'], self.result)
        self.assertIn('STARTING FRAME', result['request'])
        self.assertIn(self.result['review_reason'], result['request'])
        self.assertNotIn('ไม่ได้อธิบายเหตุผล', result['request'])
        self.assertEqual(result['content_recheck_attempt'], 1)
        with self.assertRaises(ValueError): self.call('story_visual_recheck')

    def test_bad_owner_schema_ratio_does_not_grant_repair(self):
        for patch in ({'index': 3}, {'context_id': 'wrong'}, {'needs_review': 'true'},
                      {'prompt': 'One 16:9 video of an entirely different place.'}):
            data = self.store.read({})
            data['plans'][self.context['context_id']]['result'] = {**self.result, **patch}
            self.store.write(data)
            self.assertFalse(self.call()['story_visual_repair_available'])
            with self.assertRaises(ValueError): self.call('story_visual_recheck')

    def test_unknown_request_never_grants_another_generation(self):
        repair = self.begin()
        self.call('story_visual_mark_image', request_id=repair['request_id'], conversation_url='https://chatgpt.com/c/fixture')
        again = self.call('story_visual_begin')['record']['story_visual_repair']
        self.assertEqual(repair['request_id'], again['request_id'])
        self.assertEqual(again['phase'], 'image_requested')
        with self.assertRaises(ValueError):
            self.call('story_visual_mark_image', request_id=repair['request_id'], conversation_url='https://chatgpt.com/c/fixture')

    def test_new_candidate_and_motion_commit_keep_originals_and_other_scene(self):
        repair, answer = self.finish()
        before = copy.deepcopy(self.job)
        self.call('story_visual_save', request_id=repair['request_id'], result=answer)
        self.assertEqual(self.image.read_bytes(), self.original)
        self.assertEqual(self.job, before)
        self.assertEqual(repaired_image(self.root, self.job, 1, 'generated/scene_01.png'), repair['image_file'])
        self.assertIn('away from the city', saved_motion_prompt(self.root, self.job, 1, 'generated/scene_01.png'))
        other = [r for r in self.store.read({})['plans'].values() if r['context']['index'] == 2][0]
        self.assertEqual(other, self.other)
        self.call('story_visual_save', request_id=repair['request_id'], result=answer)
        with self.assertRaises(ValueError): self.call('story_visual_save', request_id=repair['request_id'], result={**answer, 'prompt':answer['prompt']+' More.'})

    def test_candidate_not_selected_before_review_passes(self):
        repair, answer = self.finish()
        self.assertEqual(repaired_image(self.root, self.job, 1, 'generated/scene_01.png'), 'generated/scene_01.png')
        self.call('story_visual_save', request_id=repair['request_id'], result={**answer, 'material_change': True})
        self.assertEqual(self.call()['record']['story_visual_repair']['phase'], 'needs_review')
        self.assertEqual(repaired_image(self.root, self.job, 1, 'generated/scene_01.png'), 'generated/scene_01.png')
        with self.assertRaises(ValueError): self.call('story_visual_save', request_id=repair['request_id'], result=answer)

    def test_download_validation_and_wrong_request_keep_original(self):
        repair = self.begin()
        self.call('story_visual_mark_image', request_id=repair['request_id'], conversation_url='https://chatgpt.com/c/fixture')
        for extra in ({'request_id': 'other', 'image': 'bad'}, {'request_id': repair['request_id'], 'image': 'bad'}):
            with self.assertRaises(ValueError): self.call('story_visual_image', **extra)
        self.assertEqual(self.call()['record']['story_visual_repair']['phase'], 'image_requested')
        self.assertEqual(self.image.read_bytes(), self.original)

    def test_cancel_and_saved_video_block_new_repairs(self):
        for change in ({'cancel_requested': True}, {'video_path':'final.mp4'}, {'flow_clips':{'1':'clip.mp4'}}):
            old = copy.deepcopy(self.job); self.job.update(change)
            with self.assertRaises(ValueError): self.call('story_visual_recheck')
            self.job = old

    def test_candidate_hash_and_original_context_change_block_use(self):
        repair, answer = self.finish()
        self.call('story_visual_save', request_id=repair['request_id'], result=answer)
        (self.root / repair['image_file']).write_bytes(b'changed')
        with self.assertRaises(ValueError): repaired_image(self.root, self.job, 1, 'generated/scene_01.png')

    def test_fresh_request_separates_voiceover_from_visible_action(self):
        self.assertIn('audience calls to action are voiceover', self.call()['visual_request'])
        self.assertIn('scene_narrations, scene_prompts และ flow_shot_prompts', SCENE_ACTION_RULE)
        self.assertIn('ผู้ให้/ผู้รับ', SCENE_ACTION_RULE)

    def test_different_image_cannot_overwrite_saved_candidate(self):
        repair = self.save_image(self.begin())
        buffer = io.BytesIO(); Image.new('RGB', (288, 512), 'white').save(buffer, format='PNG')
        other = 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
        with self.assertRaises(ValueError): self.call('story_visual_image', request_id=repair['request_id'], image=other)

    def test_real_flow_package_uses_validated_image_and_motion_together(self):
        from core.story_manager import StoryManager
        repair, answer = self.finish()
        self.call('story_visual_save', request_id=repair['request_id'], result=answer)
        self.job['video_generation_mode'] = 'google_flow'
        manager = StoryManager(self.root / 'isolated-manager')
        with mock.patch.object(manager, '_folder', return_value=self.root), mock.patch.object(manager, 'get', return_value=self.job):
            package = manager.flow_package(self.job['id'], 1)
        self.assertEqual(package['image_files'], [repair['image_file']])
        self.assertIn('away from the city', package['video_prompt'])
        self.assertTrue(package['motion_prompt_ready'])
        self.assertEqual(self.image.read_bytes(), self.original)

    def test_scene_edit_during_pending_repair_does_not_reset_generation(self):
        repair = self.begin()
        self.call('story_visual_mark_image', request_id=repair['request_id'], conversation_url='https://chatgpt.com/c/fixture')
        self.job['scene_narrations'][0] = 'changed narration while generating'
        with self.assertRaisesRegex(ValueError, 'ไม่เริ่มซ้ำ'):
            self.call()

    def test_new_story_and_drama_requests_include_shared_action_contract(self):
        from core.story_manager import StoryManager
        manager = StoryManager(self.root / 'isolated-manager')
        job = manager.create('test story', scene_count=6, video_generation_mode='google_flow')
        request = (manager._folder(job['id']) / 'prompts/chatgpt_request.txt')
        self.assertIn(SCENE_ACTION_RULE, request.read_text(encoding='utf-8'))
        manager._write_drama_request(manager._folder(job['id']), job)
        self.assertIn(SCENE_ACTION_RULE, request.read_text(encoding='utf-8'))

    def test_extension_actual_source_recovery(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/story_visual_plan_harness.js'], cwd=root,
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__': unittest.main()
