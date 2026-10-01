import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.analysis_json_transport import ANALYSIS_JSON_FORMAT, analysis_json_prompt
from core.product_manager import ProductManager
from core.story_manager import StoryManager


class AnalysisPromptTransport428Tests(unittest.TestCase):
    def test_rule_is_idempotent_and_preserves_quoted_facts(self):
        original = json.dumps({'name': 'เรื่องของ"น้ำพริก" ครบทุกรสชาติ'}, ensure_ascii=False)
        result = analysis_json_prompt(original)
        self.assertTrue(result.startswith(original))
        self.assertEqual(analysis_json_prompt(result), result)
        self.assertIn('```json', result)

    def test_story_product_and_drama_new_requests_use_persisted_format(self):
        for mode in ('story', 'product', 'drama'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                manager = StoryManager(Path(temp))
                job = manager.create('เรื่องของ"น้ำพริก" ครบทุกรสชาติ', scene_count=10,
                                     product_short=mode == 'product')
                if mode == 'product':
                    job.update(product_story={'name': job['topic'], 'description': '',
                                              'reference_roles': ['product', 'person']})
                elif mode == 'drama':
                    job.update(job_type='drama_episode', episode_no=1, episode_count=1)
                manager._save(job)
                package = manager.plugin_request(job['id'])
                self.assertTrue(package['prompt'].endswith(ANALYSIS_JSON_FORMAT))
                self.assertEqual(package['prompt'].count(ANALYSIS_JSON_FORMAT), 1)
                saved = manager._folder(job['id']) / package['request']['prompt_file']
                self.assertEqual(saved.read_text(encoding='utf-8'), package['prompt'])
                self.assertEqual(package['request']['image_count'], 10)

    def test_legacy_product_new_request_uses_same_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'prompts').mkdir()
            job = dict(id='JOB-TEST', product_name='เรื่องของ"น้ำพริก"', price='',
                       commission='', description='', source_images=[])
            ProductManager._write_ai_request(None, folder, job)
            prompt = (folder / 'prompts/chatgpt_request.txt').read_text(encoding='utf-8')
            self.assertTrue(prompt.endswith(ANALYSIS_JSON_FORMAT))
            self.assertNotIn('ห้ามมี Markdown', prompt)

    def test_owned_analysis_resume_keeps_original_prompt_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(Path(temp))
            job = manager.create('Existing owned analysis', scene_count=3)
            folder = manager._folder(job['id'])
            target = folder / 'prompts/chatgpt_request.txt'
            original = b'Previously submitted prompt; preserve exact request identity.'
            target.write_bytes(original)
            with patch('core.ai_web_resume.ai_web_resume_target', return_value={'stage': 'analysis'}):
                package = manager.plugin_request(job['id'])
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(package['prompt'], original.decode())

    def test_format_owner_or_ambiguity_guard_does_not_restart_whole_job(self):
        from core.story_pipeline import story_recovery_action
        from core.product_pipeline import product_ai_recovery_action, product_runtime_recovery_action
        job = dict(status='error', ai_status='waiting', automation_status='error', scene_count=10)
        for code in ('AI_ANALYSIS_FORMAT_REVIEW', 'AI_ANALYSIS_JSON_AMBIGUOUS'):
            for recover in (story_recovery_action, product_ai_recovery_action, product_runtime_recovery_action):
                with self.subTest(code=code, action=recover.__name__):
                    self.assertEqual(recover(job, code + ' • ต้องตรวจคำตอบเดิม'), '')


if __name__ == '__main__':
    unittest.main()
