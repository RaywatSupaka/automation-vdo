import tempfile
import unittest
from pathlib import Path

from core.story_manager import StoryManager


class ProductPromptCompact421Tests(unittest.TestCase):
    def test_product_first_prompt_is_fact_bounded_and_short(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(Path(temp))
            job = manager.create('ชุดน้ำพริกข้าวซอย', scene_count=5, product_short=True,
                                 product_script_options={'version': 1, 'style': 'story_first_review'},
                                 video_generation_mode='meta_ai')
            job.update(product_story={'name': 'ชุดน้ำพริกข้าวซอย', 'description': '', 'price': '',
                                      'reference_roles': ['product', 'person'],
                                      'url': 'https://shopee.co.th/item/123'},
                       source_images=['source/product.jpg', 'source/person.jpg'])
            manager._save(job)
            package = manager.plugin_request(job['id'])
            prompt = package['prompt']
            self.assertLess(len(prompt), 4000)
            self.assertIn('ชุดน้ำพริกข้าวซอย', prompt)
            self.assertIn('PRODUCT STORY-FIRST REVIEW v1', prompt)
            self.assertIn('ถ้ารายละเอียดว่าง', prompt)
            self.assertIn('จำนวนฉาก: 5', prompt)
            self.assertNotIn('สร้างแพ็กเกจคลิปเรื่องเล่า Shorts', prompt)
            self.assertNotIn('https://shopee.co.th/item/123', prompt)
            self.assertEqual(package['request']['image_count'], 5)
            self.assertEqual(package['request']['image_files'], job['source_images'])

    def test_verified_description_and_price_pass_without_internal_commission(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(Path(temp))
            job = manager.create('โคมไฟ', scene_count=3, product_short=True)
            job.update(product_story={'name': 'โคมไฟ', 'description': 'สีขาว ปรับระดับได้',
                                      'price': '199', 'commission': '25%',
                                      'reference_roles': ['product']})
            manager._save(job)
            prompt = manager.plugin_request(job['id'])['prompt']
            self.assertIn('สีขาว ปรับระดับได้', prompt)
            self.assertIn('199', prompt)
            self.assertNotIn('25%', prompt)
            self.assertIn('PRODUCT STORY SHORTS', prompt)

    def test_short_film_preserves_its_validated_plan_without_generic_story_stack(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = StoryManager(Path(temp))
            job = manager.create('โคมไฟ', scene_count=5, product_short=True,
                                 product_script_options={'version': 2, 'style': 'short_film_ad',
                                                         'genre': 'auto', 'ending_cta': True})
            job.update(product_story={'name': 'โคมไฟ', 'description': 'สีขาว',
                                      'reference_roles': ['product']})
            manager._save(job)
            package = manager.plugin_request(job['id'])
            self.assertLess(len(package['prompt']), 6500)
            self.assertIn('PRODUCT SHORT FILM AD v2', package['prompt'])
            self.assertNotIn('สร้างแพ็กเกจคลิปเรื่องเล่า Shorts', package['prompt'])
            self.assertIn('product_film_plan', package['request']['required_fields'])


if __name__ == '__main__':
    unittest.main()
