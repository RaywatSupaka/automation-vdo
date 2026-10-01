"""Completed incomplete text repair must retain the desktop's name proof contract."""
import copy
import json
import subprocess
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs
from core.story_content import StoryContentError, validate_story_content

ROOT = Path(__file__).resolve().parents[1]


class StoryNameBindingRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = subprocess.run(['node', str(ROOT / 'tests/story_name_binding_recovery_harness.js'), '--emit'],
                             capture_output=True, text=True, encoding='utf-8', timeout=30,
                             **hidden_process_kwargs())
        if run.returncode:
            raise AssertionError(run.stdout + run.stderr)
        cls.fixture = json.loads(run.stdout)

    def test_actual_source_recovery_guards_both_providers(self):
        self.assertTrue(self.fixture['ok'])
        self.assertGreaterEqual(self.fixture['cases'], 40)

    def test_partial_repair_keeps_original_story_and_desktop_proof(self):
        original, repaired = self.fixture['original'], self.fixture['repaired']
        job = {'scene_count': 10, 'story_content_contract': {'version': 1}}
        validate_story_content(job, repaired)
        self.assertEqual(len(repaired['story_content_name_repair']['changes']), 2)
        for key, value in original.items():
            if key != 'scene_prompts':
                self.assertEqual(repaired[key], value, key)
        changed = copy.deepcopy(repaired)
        changed['story_content_name_repair']['changes'][1]['after'] += ' fabricated'
        with self.assertRaises(StoryContentError):
            validate_story_content(job, changed)


if __name__ == '__main__':
    unittest.main()
