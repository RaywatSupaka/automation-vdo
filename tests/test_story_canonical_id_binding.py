"""Exact scene-ID binding avoids a provider question and retains verifiable proof."""
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs
from core.story_content import (
    StoryContentError, _story_canonical_id_binding_phrase, validate_story_content,
)
from core.story_manager import StoryManager

ROOT = Path(__file__).resolve().parents[1]


class StoryCanonicalIdBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = subprocess.run(['node', str(ROOT / 'tests/story_canonical_id_binding_harness.js'), '--emit'],
                             capture_output=True, text=True, encoding='utf-8', timeout=25,
                             **hidden_process_kwargs())
        if run.returncode:
            raise AssertionError(run.stdout + run.stderr)
        cls.fixture = json.loads(run.stdout)
        cls.job = {'scene_count': 10, 'story_content_contract': {'version': 1}}

    def test_actual_extension_ten_scene_output_preserves_story_and_passes_desktop(self):
        original, repaired = self.fixture['original'], self.fixture['repaired']
        with self.assertRaises(StoryContentError):
            validate_story_content(self.job, original)
        before = copy.deepcopy(repaired)
        clean = validate_story_content(self.job, repaired)
        self.assertEqual(clean['story_content_name_repair'], repaired['story_content_name_repair'])
        self.assertEqual(len(clean['story_content_name_repair']['changes']), 10)
        self.assertEqual(repaired, before)
        for field, value in original.items():
            if field != 'scene_prompts':
                self.assertEqual(repaired[field], value, field)

    def test_canonical_method_and_before_after_cannot_be_forged(self):
        for field, value in [('method', 'guess'), ('method', None), ('phrase', 'woodcutter'),
                             ('entity_id', 'unknown_person'), ('name', 'Different name'),
                             ('before', 'A different scene'), ('after', 'Rewritten scene')]:
            with self.subTest(field=field, value=value):
                result = copy.deepcopy(self.fixture['repaired'])
                result['story_content_name_repair']['changes'][0][field] = value
                with self.assertRaises(StoryContentError):
                    validate_story_content(self.job, result)

    def test_mirrored_negative_substring_and_undeclared_guards(self):
        texts = [
            'A taller_woodcutter_man stands nearby.', 'woodcutter_man_extra stands nearby.',
            'woodcutter_man-child stands nearby.', 'ก่อนwoodcutter_man walks.', 'woodcutter_manก่อน walks.',
            'woodcutter_man and woodcutter_man stand nearby.', 'No woodcutter_man in this scene.',
            'Do not depict woodcutter_man in the forest.', 'The frame excludes woodcutter_man.',
            'Negative prompt: woodcutter_man.', 'woodcutter_man is not present.',
            'woodcutter_man should not appear.', 'woodcutter_man, absent from the scene.',
            'ห้ามแสดง woodcutter_man ในฉากนี้', 'woodcutter_man ไม่ปรากฏในภาพ',
            'Foreground shows woodcutter_man with unknown_person.',
        ]
        entities = self.fixture['original']['story_entities']
        for text in texts:
            with self.subTest(text=text):
                self.assertIsNone(_story_canonical_id_binding_phrase(text, 'woodcutter_man', entities, ['woodcutter_man']))
                result = copy.deepcopy(self.fixture['repaired'])
                change = result['story_content_name_repair']['changes'][0]
                change['before'] = text
                change['after'] = text.replace('woodcutter_man', 'woodcutter_man (ไอ่หนุ่มตัดฟืน)', 1)
                result['scene_prompts'][0] = change['after']
                with self.assertRaises(StoryContentError):
                    validate_story_content(self.job, result)
        self.assertIsNone(_story_canonical_id_binding_phrase(
            self.fixture['original']['scene_prompts'][0], 'woodcutter_man', entities, []))

    def test_mirrored_registry_collisions_and_other_character_guards(self):
        for other in [
            {'id': 'woodcutter-man', 'name': 'อีกคน', 'aliases': []},
            {'id': 'other_person', 'name': 'woodcutter man', 'aliases': []},
            {'id': 'other_person', 'name': 'อีกคน', 'aliases': ['woodcutter man']},
            {'id': 'other_person', 'name': 'ไอ่หนุ่มตัดฟืน', 'aliases': []},
        ]:
            with self.subTest(other=other):
                result = copy.deepcopy(self.fixture['repaired'])
                result['story_entities'].append({**other, 'visual_identity': 'A different person.'})
                with self.assertRaises(StoryContentError):
                    validate_story_content(self.job, result)
        result = copy.deepcopy(self.fixture['repaired'])
        result['story_entities'].append({'id': 'other_person', 'name': 'Somchai', 'aliases': [], 'visual_identity': 'A different person.'})
        result['scene_entities'][0].append('other_person')
        change = result['story_content_name_repair']['changes'][0]
        change['before'] = 'Foreground shows woodcutter_man beside Somchai.'
        change['after'] = change['before'].replace('woodcutter_man', 'woodcutter_man (ไอ่หนุ่มตัดฟืน)')
        result['scene_prompts'][0] = change['after']
        with self.assertRaises(StoryContentError):
            validate_story_content(self.job, result)

    def test_explicit_user_anchor_cannot_use_generated_id_repair(self):
        job = {**self.job, 'character_bible': [{'name': 'ไอ่หนุ่มตัดฟืน'}]}
        with self.assertRaises(StoryContentError):
            validate_story_content(job, self.fixture['repaired'])

    def test_short_internal_id_requires_canonical_method(self):
        result = {'story_entities': [{'id': 'hero_id', 'name': 'พระเอก', 'aliases': [], 'visual_identity': 'A masked hero.'}],
                  'scene_entities': [['hero_id']], 'scene_prompts': ['hero_id (พระเอก) stands in the forest.'],
                  'story_content_name_repair': {'version': 1, 'changes': [{
                      'scene_index': 1, 'entity_id': 'hero_id', 'name': 'พระเอก', 'phrase': 'hero_id',
                      'before': 'hero_id stands in the forest.', 'after': 'hero_id (พระเอก) stands in the forest.',
                      'method': 'canonical_entity_id'}]}}
        job = {'scene_count': 1, 'story_content_contract': {'version': 1}}
        validate_story_content(job, result)
        del result['story_content_name_repair']['changes'][0]['method']
        with self.assertRaises(StoryContentError):
            validate_story_content(job, result)

    def test_checkpoint_resume_retains_proof_without_media_generation(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = StoryManager(folder)
            job = manager.create('เรื่องคนตัดฟืน', 'ให้เล่าเรื่องคนตัดฟืน', scene_count=10)
            result = copy.deepcopy(self.fixture['repaired'])
            result['job_id'] = job['id']
            saved = manager.save_analysis_checkpoint(job['id'], result)
            checkpoint = manager.plugin_request(job['id'])['analysis_checkpoint']
            for field in ['scene_prompts', 'narration_script', 'story_entities', 'scene_entities', 'story_content_name_repair']:
                self.assertEqual(saved[field], result[field], field)
                self.assertEqual(checkpoint[field], result[field], field)
            self.assertEqual(list((manager.root / job['id'] / 'generated').iterdir()), [])


if __name__ == '__main__':
    unittest.main()
