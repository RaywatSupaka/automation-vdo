import subprocess
import unittest
from pathlib import Path
from core.atomic_json import AtomicJsonFile
from core.scene_progress_view import scene_progress_view
import test_flow_scene_rebuild_388 as base


class FlowRepairResume400(base.FlowSceneRebuildTests):
    def test_actual_extension_resume(self):
        result = subprocess.run(['node', 'tests/flow_repair_resume_400.js'],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def manual(self, stage='proposal', error='ภาพทางเลือกต้องเปลี่ยนสาระหรือยังต้องตรวจ • new event'):
        self.body['rebuild_scene'] = True
        self.proof('1:fp'); self.act('begin')
        old = self.body['request_id']
        review = dict(request_id=old, phase='needs_review', digest='review1', run_id='RUN-1',
                      alternative=True, alternative_stage=stage, error=error,
                      failure_id='1:fp', fingerprint='fp', reason='timeout')
        store = AtomicJsonFile(self.folder/'prompts/flow_recovery.json')
        data = store.read({}); data['scenes']['1'].append(review); store.write(data)
        AtomicJsonFile(self.folder/'prompts/flow_manual_resume.json').write(dict(
            token='manual1', index=1, job_id=self.job['id'], request_id=old, event_digest='review1'))
        self.body.update(request_id='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', previous_request_id=old,
                         manual_resume_token='manual1')
        self.proof('1:fp')
        return old

    def test_explicit_preimage_resume_archives_once(self):
        old = self.manual()
        row = self.act('begin')['replacement']
        self.assertEqual(row['request_id'], self.body['request_id'])
        self.assertEqual(self.act('begin')['replacement'], row)
        ledger = AtomicJsonFile(self.folder/'prompts/flow_replacement.json').read({})
        self.assertEqual(ledger['history']['1'][0]['request_id'], old)
        self.assertEqual(len(ledger['history']['1']), 1)
        self.assertEqual(len(list((self.folder/'generated').glob('*.png'))), 1)

    def test_unknown_image_dispatch_cannot_rotate(self):
        self.manual(stage='image_sent')
        with self.assertRaises(ValueError): self.act('begin')

    def test_forged_manual_permit_cannot_rotate(self):
        self.manual(); self.body['manual_resume_token'] = 'wrong'
        with self.assertRaises(ValueError): self.act('begin')

    def test_wrong_digest_or_other_job_cannot_rotate(self):
        self.manual()
        store = AtomicJsonFile(self.folder/'prompts/flow_manual_resume.json')
        permit = store.read({})
        for field, value in [('event_digest', 'foreign'), ('job_id', 'OTHER'), ('index', 2), ('request_id', 'other')]:
            with self.subTest(field=field):
                store.write({**permit, field: value})
                with self.assertRaises(ValueError): self.act('begin')

    def test_newest_other_request_not_overridden_by_old_review(self):
        self.manual()
        AtomicJsonFile(self.folder/'prompts/scene_pipeline.json').write({'scenes': {'1': {'phase': 'video'}}})
        job = {**self.job, 'status': 'running', 'scene_pipeline_version': 1, 'scene_count': 3}
        view = scene_progress_view(job, self.folder, True,34)
        self.assertEqual(view['scene_phase'], 'repair')

    def test_new_audit_preserves_only_typed_proposal_flags(self):
        from core.story_prompt_recovery import record_recovery
        AtomicJsonFile(self.folder/'prompts/flow_recovery.json').write({'scenes': {}})
        record_recovery(self.folder, {**self.job, 'scene_count': 1}, {
            'index': 1, 'run_id': 'RUN-1', 'event': {
                'phase': 'needs_review', 'round': 1, 'request_id': self.body['request_id'],
                'alternative': True, 'alternative_stage': 'proposal',
                'proposal_review': {'needs_review': True, 'reference_compatible': False,
                                    'material_change': 'true', 'full_prompt': 'not a diagnostic'}}}, flow=True)
        row = AtomicJsonFile(self.folder/'prompts/flow_recovery.json').read({})['scenes']['1'][-1]
        self.assertEqual(row['alternative_stage'], 'proposal')
        self.assertEqual(row['proposal_review'], {'needs_review': True, 'reference_compatible': False})

    def test_real_review_not_reported_as_image_wait(self):
        self.manual()
        AtomicJsonFile(self.folder/'prompts/scene_pipeline.json').write({'scenes': {'1': {'phase': 'video'}}})
        # Only the terminal matching the replacement is authoritative.
        ledger = AtomicJsonFile(self.folder/'prompts/flow_recovery.json')
        data = ledger.read({}); data['scenes']['1'].pop(); ledger.write(data)
        job = {**self.job, 'status': 'running', 'scene_pipeline_version': 1, 'scene_count': 3}
        view = scene_progress_view(job, self.folder, True,34)
        self.assertNotIn('กำลังรับภาพ', view.get('message', ''))
        self.assertEqual(view['scene_phase'], 'repair_review')


if __name__ == '__main__':
    unittest.main()
