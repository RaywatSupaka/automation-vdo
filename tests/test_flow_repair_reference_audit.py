import copy
import json
import tempfile
import unittest
from pathlib import Path

from core.story_prompt_recovery import record_recovery


class FlowRepairReferenceAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.job = {'id': 'STORY-TEST', 'scene_count': 6,
                    'flow_clips': {'1': 'videos/flow_scene_01.mp4'},
                    'scene_narrations': ['Original narration']}
        self.body = {'index': 6, 'run_id': 'RUN-1', 'event': {
            'phase': 'ready', 'round': 1, 'request_id': 'repair-6',
            'original_prompt': 'Original prompt', 'prompt': 'Reviewed motion prompt',
            'reason': 'Current card rejected the public figure reference without charge',
            'fingerprint': 'current-card',
            'repair_reference': {'source': 'original',
                'image_url': 'http://127.0.0.1:8765/api/stories/STORY-TEST/files/generated/scene_06.png'}}}

    def rows(self):
        return json.loads((self.folder / 'prompts/flow_recovery.json').read_text())['scenes']

    def test_same_image_new_project_is_audited_without_replacement_or_media_changes(self):
        original_job = copy.deepcopy(self.job)
        source = self.folder / 'generated/scene_06.png'
        clip = self.folder / self.job['flow_clips']['1']
        for file, data in [(source, b'original image'), (clip, b'saved successful clip')]:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
        previous = copy.deepcopy(self.body)
        previous['index'] = 1
        previous['event'] = {'phase': 'completed', 'round': 1, 'request_id': 'previous'}
        record_recovery(self.folder, self.job, previous, flow=True)
        previous_row = self.rows()['1']
        record_recovery(self.folder, self.job, self.body, flow=True)
        record_recovery(self.folder, self.job, self.body, flow=True)
        self.assertEqual(len(self.rows()['6']), 1)
        event = self.body['event']
        event.update(phase='submitted', fresh_project={
            'source_path': '/project/failed', 'target_path': '/project/new',
            'phase': 'ready', 'click_claimed': True})
        record_recovery(self.folder, self.job, self.body, flow=True)
        rows = self.rows()['6']
        self.assertEqual([row['phase'] for row in rows], ['ready', 'submitted'])
        self.assertEqual(rows[1]['repair_reference'], event['repair_reference'])
        self.assertEqual(rows[1]['fresh_project'], event['fresh_project'])
        self.assertEqual(rows[1]['original_prompt'], 'Original prompt')
        self.assertEqual(rows[1]['reason'], event['reason'])
        self.assertEqual(self.rows()['1'], previous_row)
        self.assertEqual(self.job, original_job)
        self.assertEqual(source.read_bytes(), b'original image')
        self.assertEqual(clip.read_bytes(), b'saved successful clip')
        self.assertFalse((self.folder / 'prompts/flow_replacement.json').exists())
        self.assertFalse((self.folder / 'job.json').exists())

    def test_alternate_image_provenance_stays_distinct_for_product(self):
        self.job['id'] = 'JOB-TEST'
        reference = {'source': 'replacement',
            'image_url': 'http://localhost:8765/api/jobs/JOB-TEST/files/generated/recovery-06-r.png'}
        self.body['event']['repair_reference'] = reference
        record_recovery(self.folder, self.job, self.body, flow=True)
        self.assertEqual(self.rows()['6'][0]['repair_reference'], reference)

    def test_missing_reference_keeps_legacy_events_compatible(self):
        del self.body['event']['repair_reference']
        record_recovery(self.folder, self.job, self.body, flow=True)
        self.assertNotIn('repair_reference', self.rows()['6'][0])

    def test_invalid_or_cross_job_reference_is_rejected_before_audit(self):
        original = self.body['event']['repair_reference']['image_url']
        references = [None, {'source': 'unknown', 'image_url': original},
                      {'source': 'original', 'image_url': None}]
        for url in [original.replace('STORY-TEST', 'STORY-OTHER'),
                    original.replace('127.0.0.1', 'external.invalid'),
                    original.replace('generated/', '%2e%2e/'),
                    original.replace('generated/', 'generated%5c'),
                    original + '?secret=not-for-audit',
                    original.replace('127.0.0.1', 'user:password@127.0.0.1')]:
            references.append({'source': 'original', 'image_url': url})
        for reference in references:
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                self.body['event']['repair_reference'] = reference
                record_recovery(self.folder, self.job, self.body, flow=True)
        self.assertFalse((self.folder / 'prompts/flow_recovery.json').exists())
