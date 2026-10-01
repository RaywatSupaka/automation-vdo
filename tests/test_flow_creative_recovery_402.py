"""Fresh, compliant replacement plans can change a failed scene, never old media."""
import copy
import subprocess
import unittest
from pathlib import Path

from core.scene_context_revision import validate_revision, revised_story
from core.flow_replacement import apply_replacement
from core.atomic_json import AtomicJsonFile
from core.story_performance import validate_plan
import test_scene_context_revision_349 as legacy
import test_flow_replacement as replacement_fixture
import test_story_performance as performance_fixture


class CreativeRevision402Tests(unittest.TestCase):
    def test_observed_false_false_proposal_is_valid_for_authorized_new_image(self):
        candidate = legacy.RevisionValidationTests().candidate()
        candidate.update(reference_compatible=False, material_change=False)
        context = {'story_beat': 'Old event', 'creative_revision_version': 1}
        clean = validate_revision(candidate, context, [])
        self.assertEqual(clean['scene_narration'], candidate['scene_narration'])
        with self.assertRaises(ValueError):
            validate_revision(candidate, {'story_beat': 'Old event'}, [])
        with self.assertRaises(ValueError):
            validate_revision({**candidate, 'needs_review': True}, context, [])

    def setUp(self):
        self.fixture = replacement_fixture.FlowReplacementTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture
        self.f.body.update(rebuild_scene=True, revise_story=True, creative_revision_version=1)
        AtomicJsonFile(self.f.folder/'prompts/flow_recovery.json').write({'scenes': {'1': [dict(
            run_id='RUN-1', request_id=self.f.body['request_id'], failure_id='failed-1',
            fingerprint='fp', reason='confirmed terminal')]}})
        self.candidate = legacy.RevisionValidationTests().candidate()
        self.candidate.update(reference_compatible=False, material_change=False)
        self.motion = dict(prompt='Vertical 9:16. The fictional friends look at a garden gate with a slow camera movement.',
                           needs_review=False, reference_compatible=True, material_change=False)

    def test_full_new_scene_path_preserves_source_and_failed_image_history(self):
        original = copy.deepcopy(self.f.job)
        source = (self.f.folder/'generated/scene_01.png').read_bytes()
        self.assertEqual(self.f.act('begin')['replacement']['creative_revision_version'], 1)
        checked = self.f.act('proposal_check', candidate=self.candidate)['replacement']
        self.assertNotIn('proposal_feedback', checked)
        self.assertEqual(checked['motion_context']['story_beat'], self.candidate['scene_narration'])
        first = self.f.act('image', image=self.f.image())['replacement']
        rejected = {**self.motion, 'reference_compatible': False}
        second = self.f.act('redesign', candidate=rejected)['replacement']
        self.assertEqual((second['phase'], second['creative_round']), ('requested', 1))
        self.assertEqual(self.f.act('redesign', candidate=rejected)['replacement'], second)  # Lost ACK replay.
        data = AtomicJsonFile(self.f.folder/'prompts/flow_replacement.json').read({})
        self.assertEqual(len(data['history']['1']), 1)
        self.assertEqual(data['history']['1'][0]['image_sha256'], first['image_sha256'])
        with self.assertRaisesRegex(ValueError, 'รอบซ่อมเก่า'):
            self.f.act('image', image=self.f.image())
        self.f.body['creative_round'] = 1
        new = {**self.candidate, 'scene_narration': 'เพื่อนพบทางเดินใหม่และตัดสินใจกลับบ้านด้วยกัน',
               'context_summary': 'A new safe walk along a different pathway.'}
        self.f.act('proposal_check', candidate=new)
        with self.assertRaises(ValueError):
            self.f.act('image', image=self.f.image())  # Old failed result not reused.
        final = self.f.act('image', image=self.f.image('green'))['replacement']
        self.assertNotEqual(first['image_file'], final['image_file'])
        self.assertTrue((self.f.folder/first['image_file']).is_file())
        self.f.act('ready', candidate=self.motion)
        package = {}
        apply_replacement(self.f.folder, self.f.job, 1, package)
        self.assertEqual(package['image_files'], [final['image_file']])
        self.assertEqual(self.f.job, original)
        self.assertEqual((self.f.folder/'generated/scene_01.png').read_bytes(), source)

    def test_no_rotation_for_unknown_image_approved_motion_or_finished_scene(self):
        self.f.act('begin')
        rejected = {**self.motion, 'needs_review': True}
        with self.assertRaises(ValueError): self.f.act('redesign', candidate=rejected)
        self.f.act('proposal_check', candidate=self.candidate)
        with self.assertRaises(ValueError): self.f.act('redesign', candidate=rejected)
        self.f.act('image', image=self.f.image())
        with self.assertRaises(ValueError): self.f.act('redesign', candidate=self.motion)
        self.f.job['flow_clips'] = {'1': 'saved.mp4'}
        with self.assertRaises(ValueError): self.f.act('redesign', candidate=rejected)
        self.f.job.pop('flow_clips')
        self.f.job['cancel_requested'] = True
        with self.assertRaises(ValueError): self.f.act('redesign', candidate=rejected)

    def test_invalid_revision_returns_feedback_without_approving_it(self):
        self.f.act('begin')
        for candidate in [{**self.candidate, 'needs_review': True}, {**self.candidate, 'scene_narration': ''}]:
            row = self.f.act('proposal_check', candidate=candidate)['replacement']
            self.assertEqual(row['proposal_feedback']['code'], 'revision_invalid')
            self.assertNotIn('revision', row)
            with self.assertRaises(ValueError): self.f.act('image', image=self.f.image())

    def actor_job(self):
        fixture = performance_fixture.StoryPerformanceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.f.job = {**fixture.job, **validate_plan(fixture.job, fixture.plan),
                      'generated_images': self.f.job['generated_images']}
        self.candidate['scene_dialogue_turns'] = [
            {'speaker': 'มะลิ', 'listener': 'ต้น', 'text': 'กลับบ้านกันไหม'},
            {'speaker': 'ต้น', 'listener': 'มะลิ', 'text': 'เดินไปด้วยกันนะ'}]

    def test_new_actor_dialogue_reaches_motion_package_and_render_not_original(self):
        self.actor_job()
        original = copy.deepcopy(self.f.job)
        self.f.act('begin')
        row = self.f.act('proposal_check', candidate=self.candidate)['replacement']
        self.assertNotIn('proposal_feedback', row)
        audio = row['motion_context']['audio_instruction']
        self.assertIn('ACTOR DIALOGUE:', audio)
        self.assertIn('กลับบ้านกันไหม', audio)
        self.assertNotIn('เห็นกุญแจไหม', audio)
        self.f.act('image', image=self.f.image())
        row = self.f.act('ready', candidate=self.motion)['replacement']
        self.assertIn('กลับบ้านกันไหม', row['effective_prompt'])
        self.assertNotIn('เห็นกุญแจไหม', row['effective_prompt'])
        self.assertEqual(self.f.act('ready', candidate=self.motion)['replacement'], row)
        effective = revised_story(self.f.job, {'1': row})
        self.assertEqual(effective['scene_dialogue_turns'][0], self.candidate['scene_dialogue_turns'])
        self.assertEqual(effective['scene_dialogue_turns'][1:], original['scene_dialogue_turns'][1:])
        self.assertIn('กลับบ้านกันไหม', effective['narration_script'])
        self.assertNotIn('เห็นกุญแจไหม', effective['narration_script'])
        package = {}
        apply_replacement(self.f.folder, self.f.job, 1, package)
        self.assertIn('กลับบ้านกันไหม', package['video_prompt'])
        self.assertEqual(self.f.job, original)

    def test_new_actor_dialogue_must_still_have_valid_speakers(self):
        self.actor_job()
        self.f.act('begin')
        self.candidate['scene_dialogue_turns'][0]['speaker'] = 'Unknown'
        row = self.f.act('proposal_check', candidate=self.candidate)['replacement']
        self.assertEqual(row['proposal_feedback']['code'], 'revision_invalid')
        self.assertNotIn('revision', row)
        with self.assertRaises(ValueError): self.f.act('image', image=self.f.image())

    def test_legacy_helper_is_not_migrated(self):
        self.f.body.pop('creative_revision_version')
        self.f.act('begin')
        row = self.f.act('begin', creative_revision_version=1)['replacement']
        self.assertNotIn('creative_revision_version', row)
        with self.assertRaises(ValueError): self.f.act('proposal_check', candidate=self.candidate)

    def test_actual_extension_creative_harness(self):
        result = subprocess.run(['node', 'tests/flow_creative_recovery_402.js'],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
