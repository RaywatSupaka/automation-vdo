import ast
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.creation_queue import CreationQueue
from core.meta_prompt import SINGLE_VIDEO_INSTRUCTION, COMPLIANT_VIDEO_INSTRUCTION, meta_prompt_version
from core.meta_video import MetaVideoManager
from core.story_manager import StoryManager

ROOT = Path(__file__).resolve().parents[1]


class MetaSingleVideoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stories = StoryManager(self.temp.name)
        self.manager = MetaVideoManager(self.stories)

    def job(self, **kwargs):
        job = self.stories.create('market video', video_generation_mode='meta_ai', **kwargs)
        (self.stories._folder(job['id']) / 'generated/scene_01.png').write_bytes(b'image')
        job.update(generated_images=['generated/scene_01.png'], scene_prompts=['Lift the fallen structure'],
                   scene_narrations=['Open the path'], audio_choices={'mode': 'none'})
        self.stories._save(job)
        return job

    def test_new_job_requests_one_playable_video_not_one_text_answer(self):
        job = self.job()
        self.assertEqual(job['meta_prompt_version'], 5)
        prompt = self.manager.package(job['id'], 1)['prompt']
        self.assertNotIn(SINGLE_VIDEO_INSTRUCTION, prompt)
        self.assertLess(len(prompt), 1600)
        for part in ('exactly one playable', 'not options or an explanation',
                     'report that truthfully',
                     'No music, speech or ambient audio'):
            self.assertIn(part, prompt)
        self.assertIn(COMPLIANT_VIDEO_INSTRUCTION, prompt)

    def test_existing_version_three_prompt_and_receipt_are_unchanged(self):
        job = self.job(meta_prompt_version=3)
        prompt = self.manager.package(job['id'], 1)['prompt']
        self.assertNotIn(COMPLIANT_VIDEO_INSTRUCTION, prompt)
        self.assertIn('Return the actual video, not options or an explanation.', prompt)
        first = self.manager.begin(job['id'], 1)
        self.assertEqual(self.manager.begin(job['id'], 1, resume=True)['request_id'], first['request_id'])
        self.assertEqual(self.manager.begin(job['id'], 1, resume=True)['context_id'], first['context_id'])

    def test_existing_version_two_prompt_is_unchanged(self):
        job = self.job(meta_prompt_version=2)
        old = self.job(meta_prompt_version=1)
        self.assertEqual(self.manager.package(job['id'], 1)['prompt'],
                         self.manager.package(old['id'], 1)['prompt']
                         + '\nGeneration instruction: ' + SINGLE_VIDEO_INSTRUCTION)

    def test_legacy_job_hash_and_resume_remain_byte_identical(self):
        job = self.job(meta_prompt_version=1)
        expected = ('Create one actual playable vertical 9:16 video from the attached image, not a still image or explanation. '
                    'Use the image as the starting frame. Preserve the characters, product and scene continuity. '
                    'Add natural visible action, subtle environmental motion and one smooth camera move. '
                    'No text, captions or watermark. No music, speech or ambient audio; narration is added separately.'
                    '\nScene: Lift the fallen structure\nStory action: Open the path')
        first = self.manager.begin(job['id'], 1)
        self.assertEqual(first['prompt'], expected)
        expected_hash = hashlib.sha256((job['id'] + ':1:' + hashlib.sha256(b'image').hexdigest() + ':' + expected).encode()).hexdigest()
        self.assertEqual(first['context_id'], expected_hash)
        self.manager.event({**first, 'stage': 'uploading'})
        job.pop('meta_prompt_version')  # Pre-update persisted jobs have no field.
        self.stories._save(job)
        resumed = MetaVideoManager(StoryManager(self.temp.name)).begin(job['id'], 1, resume=True)
        self.assertEqual(resumed['prompt'], expected)
        self.assertEqual(resumed['context_id'], first['context_id'])
        self.assertEqual(resumed['request_id'], first['request_id'])
        self.assertEqual(resumed['stage'], 'uploading')

    def test_version_and_scene_mutation_cannot_reset_owned_receipt(self):
        job = self.job()
        self.manager.begin(job['id'], 1)
        job['meta_prompt_version'] = 1
        self.stories._save(job)
        with self.assertRaisesRegex(ValueError, 'เปลี่ยนหลังเริ่มงาน'):
            self.manager.begin(job['id'], 1, resume=True)
        for value in (True, None, '2', 0, 6):
            with self.assertRaises(ValueError): meta_prompt_version(value)

    def test_audio_and_dialogue_kept_for_all_modes(self):
        job = self.job()
        for mode, keep, expected in [('api', False, 'No music, speech or ambient audio'),
                                      ('none', False, 'No music, speech or ambient audio'),
                                      ('api', True, 'Include natural ambient sounds only'),
                                      ('flow_original', False, 'All spoken dialogue must be in Thai only')]:
            job.update(audio_choices={'mode': mode, 'keep_video_audio': keep}, product_presentation_version=1,
                       scene_narrations=['ลองนั่งเก้าอี้ตัวนี้กันค่ะ'])
            self.stories._save(job)
            prompt = self.manager.package(job['id'], 1)['prompt']
            self.assertIn(expected, prompt)
            if mode == 'flow_original':
                self.assertIn('ลองนั่งเก้าอี้ตัวนี้กันค่ะ', prompt)
            else:
                self.assertNotIn('ลองนั่งเก้าอี้ตัวนี้กันค่ะ', prompt)
            self.assertNotIn(SINGLE_VIDEO_INSTRUCTION, prompt)
            if mode == 'flow_original': self.assertIn('on-camera dialogue', prompt)

    def test_queue_freezes_version_and_old_ui_queue_defaults_to_legacy(self):
        queue = CreationQueue(self.temp.name)
        item = queue.enqueue('story', ['new'], video_generation_mode='meta_ai')['items'][0]
        self.assertEqual(CreationQueue(self.temp.name).get_item(item['queue_id'])['settings']['meta_prompt_version'], 5)
        old = queue.enqueue('story', ['old'], video_generation_mode='meta_ai', settings={'meta_prompt_version': 1})['items'][0]
        self.assertEqual(old['settings']['meta_prompt_version'], 1)
        tree = ast.parse((ROOT / 'ui/main_window.py').read_text(encoding='utf-8'))
        expr = next(k.value for n in ast.walk(tree) if isinstance(n, ast.Call)
                    for k in n.keywords if k.arg == 'meta_prompt_version')
        class Window:
            def _creation_settings(self): return self.settings
        window = Window()
        for queued, settings, expected in [(True, {}, 1), (True, {'meta_prompt_version': 2}, 2), (False, {}, None)]:
            window.settings = settings
            self.assertEqual(eval(compile(ast.Expression(expr), '<actual-ui>', 'eval'), {'self': window, 'queue_item_id': queued}), expected)

    def test_actual_extension_controller_handles_new_prompt_without_changes(self):
        job = self.job()
        package = self.manager.package(job['id'], 1)
        result = subprocess.run(['node', str(ROOT / 'tests/meta_video_harness.cjs'), '--package'],
                                input=json.dumps(package), capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__': unittest.main()
