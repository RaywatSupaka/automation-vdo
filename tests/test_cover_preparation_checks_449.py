"""Bounded preparation diagnostics must not grant cover dispatch authority."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from core.ai_cover import AICovers
from core.atomic_json import AtomicJsonFile


class CoverPreparationChecks449Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.job = 'STORY-COVER-CHECKS'
        stories = SimpleNamespace(root=self.root / 'stories')
        self.folder = stories.root / self.job
        self.folder.mkdir(parents=True)
        self.video = self.folder / 'final.mp4'
        self.video.write_bytes(b'preserve final')
        Image.new('RGB', (576, 1024), 'blue').save(self.folder / 'scene.jpg')
        self.manifest = AtomicJsonFile(self.folder / 'job.json')
        self.manifest.write(dict(id=self.job, job_type='story_short', status='ready',
            video_path='final.mp4', generated_images=['scene.jpg'],
            image_ai_provider='chatgpt', ai_cover_options={'enabled': True}))
        self.service = AICovers(SimpleNamespace(root=self.root / 'products'), stories)
        self.rid = self.service.request(self.job)['request_id']
        self.service.event(self.rid, {'phase': 'claimed'})

    def checks(self, **changes):
        return dict(owner_current=True, composer_ready=True, draft_present=False,
            attachment_busy=False, attachment_failed=False, response_active=False,
            user_turns=0, assistant_turns=0, attachment_count=0) | changes

    def proof(self, **changes):
        return dict(stage='image_tool', reason='opener_missing', attempt=1,
            not_dispatched=True, request_id=self.rid, checks=self.checks()) | changes

    def prepare(self, proof=None, **event):
        return self.service.event(self.rid, dict(phase='preparing',
            preparation_state=self.proof() if proof is None else proof) | event)

    def disk_snapshot(self):
        return (self.service.store.path.read_bytes(),
                (self.folder / 'job.json').read_bytes(), self.video.read_bytes())

    def reject_atomically(self, proof, **event):
        before = self.disk_snapshot()
        with self.assertRaises(ValueError):
            self.prepare(proof, **event)
        self.assertEqual(self.disk_snapshot(), before)

    def test_new_reasons_and_checks_round_trip_to_ledger_and_manifest(self):
        observations = {
            'tool_pending': self.checks(),
            'conversation_not_empty': self.checks(user_turns=1, assistant_turns=2),
            'attachment_present': self.checks(attachment_count=2),
            'upload_busy': self.checks(attachment_busy=True, attachment_count=1),
            'upload_failed': self.checks(attachment_failed=True, attachment_count=1),
        }
        for reason, checks in observations.items():
            with self.subTest(reason=reason):
                proof = self.proof(reason=reason, checks=checks)
                row = self.prepare(proof)
                self.assertEqual(row['preparation_state'], proof)
                self.assertEqual(self.service.get(self.rid)['preparation_state'], proof)
                self.assertEqual(self.manifest.read()['ai_cover_state']['preparation_state'], proof)
                self.assertTrue(self.service.completion(self.job)['waiting'])
                self.assertFalse(self.service.completion(self.job)['ready'])
                self.assertNotIn('cover_path', self.manifest.read())
        self.assertEqual(self.video.read_bytes(), b'preserve final')

    def test_legacy_448_proof_without_checks_is_still_accepted(self):
        proof = self.proof()
        del proof['checks']
        row = self.prepare(proof)
        self.assertEqual(row['preparation_state'], proof)
        self.assertTrue(self.service._not_dispatched(row))
        self.assertNotIn('checks', self.manifest.read()['ai_cover_state']['preparation_state'])

    def test_boolean_checks_require_exact_bool(self):
        self.prepare()
        for key in ('owner_current', 'composer_ready', 'draft_present',
                    'attachment_busy', 'attachment_failed', 'response_active'):
            for value in (0, 1, None, 'true', [], {}):
                with self.subTest(key=key, value=value):
                    self.reject_atomically(self.proof(checks=self.checks(**{key: value})))

    def test_count_checks_require_bounded_exact_int(self):
        self.prepare()
        for key in ('user_turns', 'assistant_turns', 'attachment_count'):
            for value in (-1, 1001, True, False, 1.0, '1', None):
                with self.subTest(key=key, value=value):
                    self.reject_atomically(self.proof(checks=self.checks(**{key: value})))
            for value in (0, 1000):
                with self.subTest(key=key, boundary=value):
                    row = self.prepare(self.proof(checks=self.checks(**{key: value})))
                    self.assertEqual(row['preparation_state']['checks'][key], value)

    def test_all_nine_checks_required_when_object_is_present(self):
        for key in self.checks():
            checks = self.checks()
            del checks[key]
            with self.subTest(missing=key):
                self.reject_atomically(self.proof(checks=checks))
        for value in (None, False, [], '', 0, {}):
            with self.subTest(checks=value):
                self.reject_atomically(self.proof(checks=value))

    def test_foreign_fields_reject_without_partial_writes_or_prompt_bytes(self):
        marker = 'PRIVATE-PROMPT-IMAGE-DATA-MUST-NOT-PERSIST'
        for key in ('prompt', 'image', 'url', 'request_id', 'dispatch_completed'):
            with self.subTest(key=key):
                self.reject_atomically(self.proof(checks=self.checks(**{key: marker})),
                    send_diagnostics={'target_stable_before_press': True})
        proof = self.proof(prompt=marker, image=marker)
        self.prepare(proof, prompt=marker)
        for data in self.disk_snapshot():
            self.assertNotIn(marker.encode(), data)
        self.assertEqual(self.service.get(self.rid)['preparation_state'], self.proof())

    def test_checks_cannot_replace_request_bound_never_sent_authority(self):
        for changes in ({'request_id': 'foreign'}, {'not_dispatched': False},
                        {'not_dispatched': 'true'}, {'stage': 'send'}, {'attempt': 0.5}):
            with self.subTest(changes=changes):
                self.reject_atomically(self.proof(**changes))
        for event in ({'phase': 'preparing', 'checks': self.checks()},
                      {'phase': 'recovering', 'notDispatched': True, 'checks': self.checks()}):
            before = self.disk_snapshot()
            with self.assertRaises(ValueError):
                self.service.event(self.rid, event)
            self.assertEqual(self.disk_snapshot(), before)

    def test_incoming_accepted_or_unknown_send_cannot_become_preparation(self):
        for state in ('accepted', 'unconfirmed'):
            with self.subTest(state=state):
                self.reject_atomically(self.proof(reason='ready'),
                    send_state=state, notDispatched=True)

    def test_saved_send_state_rejects_checks_and_keeps_diagnostics(self):
        self.prepare()
        for state in ('unconfirmed', 'accepted'):
            row = self.service.event(self.rid, {'phase': 'running', 'send_state': state})
            self.assertFalse(row['notDispatched'])
            self.assertFalse(row['preparation_state']['not_dispatched'])
            self.assertEqual(row['preparation_state']['checks'], self.checks())
            with self.subTest(state=state):
                self.reject_atomically(self.proof(reason='ready', attempt=2))
        row = self.service.get(self.rid)
        self.assertEqual(row['send_state'], 'accepted')
        self.assertFalse(self.service._not_dispatched(row))

    def test_cancelled_request_cannot_be_reopened_by_checks(self):
        self.prepare()
        self.service.event(self.rid, {'phase': 'cancelled'})
        before = self.disk_snapshot()
        row = self.prepare(self.proof(reason='ready', attempt=2))
        self.assertEqual(row['phase'], 'cancelled')
        self.assertEqual(self.disk_snapshot(), before)


if __name__ == '__main__':
    unittest.main()
