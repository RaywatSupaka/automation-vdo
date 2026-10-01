import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.story_content import StoryContentError, validate_story_content
from core.story_manager import StoryManager

ROOT = Path(__file__).resolve().parents[1]


class StoryNameBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = subprocess.run(['node', str(ROOT / 'tests/story_name_binding_harness.js'), '--emit'],
                             capture_output=True, text=True, encoding='utf-8', timeout=25)
        if run.returncode:
            raise AssertionError(run.stderr)
        cls.repaired = json.loads(run.stdout)
        cls.original = json.loads((ROOT / 'tests/fixtures/story_name_binding_2A16D8.json').read_text(encoding='utf-8'))
        cls.job = {'scene_count': 10, 'story_content_contract': {'version': 1}}

    def test_actual_extension_output_passes_desktop_validator(self):
        with self.assertRaises(StoryContentError):
            validate_story_content(self.job, self.original)
        result = validate_story_content(self.job, self.repaired)
        self.assertEqual(result['story_content_name_repair'], self.repaired['story_content_name_repair'])

    def test_invalid_audit_is_rejected(self):
        for field, value in [('after', 'rewritten scene'), ('phrase', 'not present'), ('name', 'wrong'),
                             ('scene_index', True), ('entity_id', 'missing')]:
            with self.subTest(field=field):
                result = copy.deepcopy(self.repaired)
                result['story_content_name_repair']['changes'][0][field] = value
                with self.assertRaises(StoryContentError):
                    validate_story_content(self.job, result)

    def test_reviewed_edit_after_binding_preserves_original_audit_and_resumes(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = StoryManager(folder)
            job = manager.create('เมื่อเอไอคุยกันเอง', 'ให้คิดเรื่องจากหัวข้อ', scene_count=10, visual_style='anime')
            result = copy.deepcopy(self.repaired)
            result['job_id'] = job['id']
            manager.save_analysis_checkpoint(job['id'], result)
            job = manager.mark_failed(job['id'], 'chatgpt', 'review scene')
            path = manager.root / job['id'] / 'prompts/ai_analysis_checkpoint.json'
            original_bytes = path.read_bytes()
            prompt = result['scene_prompts'][0] + ' แสงนุ่มขึ้น'
            saved = manager.save_scene_prompt(job['id'], 1, prompt, job['revision'])
            self.assertNotIn('story_content_name_repair', saved)
            self.assertEqual(saved['story_content_name_repair_history'], result['story_content_name_repair'])
            validate_story_content(saved, saved)
            checkpoint = manager.plugin_request(job['id'])['analysis_checkpoint']
            self.assertEqual(checkpoint['scene_prompts'][0], prompt)
            self.assertNotIn('story_content_name_repair', checkpoint)
            self.assertEqual(path.read_bytes(), original_bytes)
            manager.save_analysis_checkpoint(job['id'], checkpoint)

    def test_saved_checkpoint_preserves_audit_and_can_resume_without_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = StoryManager(folder)
            job = manager.create('เมื่อเอไอคุยกันเอง', 'ให้คิดเรื่องจากหัวข้อ', scene_count=10, visual_style='anime')
            result = copy.deepcopy(self.repaired)
            result['job_id'] = job['id']
            saved = manager.save_analysis_checkpoint(job['id'], result)
            self.assertEqual(saved['narration_script'], self.original['narration_script'])
            self.assertEqual(saved['story_content_name_repair'], result['story_content_name_repair'])
            checkpoint = manager.plugin_request(job['id'])['analysis_checkpoint']
            self.assertEqual(checkpoint['scene_prompts'], result['scene_prompts'])
            self.assertEqual(checkpoint['story_content_name_repair'], result['story_content_name_repair'])


if __name__ == '__main__':
    unittest.main()
