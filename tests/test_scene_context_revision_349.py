import copy
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from core.atomic_json import AtomicJsonFile
from core.story_manager import StoryManager
from core.scene_context_revision import validate_revision, revised_story
from test_flow_replacement import FlowReplacementTests


class RevisionValidationTests(unittest.TestCase):
    def candidate(self):
        return dict(prompt='A vertical image of a vendor sharing breakfast with a visitor in a quiet garden.',
                    scene_narration='ผู้มาเยือนนั่งทานอาหารเช้าและพูดคุยกับเจ้าของร้านในสวน',
                    context_summary='เปลี่ยนเป็นการแบ่งปันอาหารเช้าในสวน', needs_review=False,
                    reference_compatible=True, material_change=True)

    def test_new_plot_allowed_but_duplicate_or_review_rejected(self):
        context={'story_beat':'Original narration'}
        row=validate_revision(self.candidate(),context,[])
        with self.assertRaises(ValueError):validate_revision(self.candidate(),context,[row])
        with self.assertRaises(ValueError):validate_revision({**self.candidate(),'needs_review':True},context,[])

    def test_derived_story_preserves_original_and_other_scenes(self):
        job={'scene_narrations':['Original narration','Next scene'],
             'dialogue_turns':[{'speaker':'A','text':'Original narration'},{'speaker':'B','text':'Next scene'}]}
        old=copy.deepcopy(job)
        revision=validate_revision(self.candidate(),{'story_beat':'Original narration'},[])
        effective=revised_story(job,{'1':{'phase':'ready','revision':revision}})
        self.assertEqual(job,old)
        self.assertEqual(effective['scene_narrations'][1],'Next scene')
        self.assertEqual(effective['dialogue_turns'][1],job['dialogue_turns'][1])
        self.assertEqual(effective['dialogue_turns'][0]['text'],revision['scene_narration'])
        job['dialogue_turns'][0]['text']='Unknown mapping'
        with self.assertRaises(ValueError):revised_story(job,{'1':{'phase':'ready','revision':revision}})

    def test_new_image_may_differ_from_old_reference_only_with_changed_event(self):
        candidate={**self.candidate(), 'reference_compatible':False}
        self.assertTrue(validate_revision(candidate,{'story_beat':'old'},[])['revision_hash'])
        for patch in [{'material_change':False}, {'needs_review':True},
                      {'reference_compatible':'false'}, {'material_change':'true'}]:
            with self.assertRaises(ValueError):
                validate_revision({**candidate,**patch},{'story_beat':'old'},[])

    def test_voice_revision_is_durable_idempotent_and_archives_audio(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);(folder/'audio').mkdir()
            (folder/'audio/narration.mp3').write_bytes(b'original paid audio')
            revision=validate_revision(self.candidate(),{'story_beat':'Original narration'},[])
            AtomicJsonFile(folder/'prompts/flow_replacement.json').write({'scenes':{'1':{'phase':'ready','revision':revision}}})
            manifest={'id':'STORY-TEST','scene_narrations':['Original narration'],
                      'voice_status':'ready','voice_path':'audio/narration.mp3','voice_job_id':'old-paid'}
            saved=[]
            def save(value):
                manifest.clear();manifest.update(copy.deepcopy(value));saved.append(copy.deepcopy(value))
            manager=SimpleNamespace(get=lambda _:copy.deepcopy(manifest),_folder=lambda _:folder,_save=save)
            result=StoryManager.activate_flow_story_revision(manager,'STORY-TEST')
            self.assertEqual(result['voice_status'],'needs_regeneration')
            self.assertEqual(result['voice_job_id'],'')
            self.assertEqual(manifest['scene_narrations'],['Original narration'])
            self.assertEqual(len(list((folder/'audio').glob('before-revision-*'))),1)
            StoryManager.activate_flow_story_revision(manager,'STORY-TEST')
            self.assertEqual(len(saved),1)


class RevisionTransactionTests(FlowReplacementTests):
    def test_duplicate_feedback_is_durable_and_does_not_approve_media(self):
        self.body['revise_story'] = True
        self.act('begin')
        candidate = RevisionValidationTests().candidate()
        duplicate = {**candidate, 'scene_narration': 'Original narration'}
        for _ in range(2):
            row = self.act('proposal_check', candidate=duplicate)['replacement']
            self.assertEqual(row['proposal_feedback']['code'], 'duplicate_story')
            self.assertEqual(row['phase'], 'requested')
            self.assertNotIn('revision', row)
            self.assertEqual(len(row['rejected_proposals']), 1)
        with self.assertRaises(ValueError):
            self.act('image', image=self.image())
        with self.assertRaises(ValueError):
            self.act('proposal_check', candidate={**duplicate, 'needs_review': True})
        with self.assertRaises(ValueError):
            self.act('proposal_check', candidate={**duplicate, 'reference_compatible': 'true'})
        row = self.act('proposal_check', candidate=candidate)['replacement']
        self.assertNotIn('proposal_feedback', row)
        self.assertIn('revision', row)
        self.assertEqual(len(row['rejected_proposals']), 1)
        self.assertEqual(self.job['scene_narrations'], ['Original narration'])
        self.act('image', image=self.image())
        with self.assertRaises(ValueError):
            self.act('proposal_check', candidate=duplicate)

    def test_new_context_transaction_and_history(self):
        self.body['revise_story']=True
        self.act('begin')
        candidate=RevisionValidationTests().candidate()
        candidate['reference_compatible']=False  # 489FDB: new composition, not old-frame motion.
        self.act('proposal',candidate=candidate)
        self.act('image',image=self.image())
        motion=dict(prompt='Vertical 9:16. The visitor shares breakfast in a quiet garden. All spoken dialogue must be in Thai only.',
                    needs_review=False,reference_compatible=True,material_change=False)
        for patch in [{'reference_compatible':False},{'needs_review':True},{'material_change':True}]:
            with self.assertRaises(ValueError):self.act('ready',candidate={**motion,**patch})
        self.act('ready',candidate=motion)
        self.body['request_id']='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
        result=self.act('begin')
        self.assertEqual(len(result['context']['previous_contexts']),1)
        with self.assertRaises(ValueError):self.act('proposal',candidate=candidate)
