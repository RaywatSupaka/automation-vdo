"""Bounded Meta gesture telemetry must never change Send/recovery authority."""
import copy
import json
import unittest
from pathlib import Path

from core.meta_video import MetaVideoManager
from tests import test_meta_video as fixtures


class MetaSendDiagnostics453Tests(unittest.TestCase):
    setUp = fixtures.MetaVideoTests.setUp
    advance = fixtures.MetaVideoTests.advance

    def diagnostic(self, **changes):
        return dict(phase='pressed', outcome='release_cancelled',
                    reason='target_moved', press_dispatched=True,
                    release_dispatched=False, **changes)

    def report(self, body, diagnostic, stage='send_intent', **changes):
        return self.manager.event({**body, 'stage': stage,
                                   'send_diagnostic': diagnostic, **changes})

    def test_only_allowlisted_fields_are_persisted_and_survive_restart(self):
        body = self.advance('send_intent')
        safe = self.diagnostic()
        result = self.report(body, {**safe, 'text': 'not-for-diagnostics' * 10000,
            'html': '<input>', 'coordinates': [123, 456], 'token': 'not-for-diagnostics',
            'url': 'https://example.test/private', 'nested': {'prompt': 'discard'}})
        self.assertEqual(result['send_diagnostic'], safe)
        self.assertLess(len(json.dumps(result['send_diagnostic'])), 200)
        self.manager = MetaVideoManager(self.stories, self.manager.validator)
        self.assertEqual(self.manager.get(self.job_id, 1)['send_diagnostic'], safe)
        self.assertNotIn('not-for-diagnostics', json.dumps(self.manager._store(self.job_id).read()))

    def test_each_reason_is_exactly_allowlisted(self):
        body = self.advance('send_intent')
        reasons = ('owner_changed', 'tab_changed', 'document_changed', 'draft_changed',
                   'target_changed', 'target_moved', 'source_changed', 'busy',
                   'dispatch_error', 'validation_failed')
        for reason in reasons:
            with self.subTest(reason=reason):
                value = {**self.diagnostic(), 'reason': reason}
                self.assertEqual(self.report(body, value)['send_diagnostic'], value)

    def test_all_outcomes_are_diagnostic_only(self):
        body = self.advance('send_intent')
        original = copy.deepcopy(self.stories.get(self.job_id))
        for outcome in ('blocked_before_press', 'release_cancelled',
                        'dispatch_unknown', 'gesture_released'):
            with self.subTest(outcome=outcome):
                value = {'phase': 'pressed', 'outcome': outcome}
                result = self.report(body, value)
                self.assertEqual(result['stage'], 'send_intent')
                self.assertEqual(result['request_id'], body['request_id'])
                self.assertEqual(self.manager.begin(self.job_id, 1)['request_id'], body['request_id'])
                with self.assertRaises(ValueError):
                    self.manager.event({**body, 'stage': 'retry_prepared',
                                        'send_diagnostic': value})
                self.assertNotIn('attempt_history', self.manager._store(self.job_id).read())
        self.assertEqual(self.stories.get(self.job_id), original)

    def test_malformed_fields_do_not_block_submission_or_replace_known_diagnostic(self):
        body = self.advance('send_intent')
        safe = self.diagnostic()
        self.report(body, safe)
        malformed = (None, [], 'pressed', {}, {'phase': 'pressed'},
            {**safe, 'phase': []}, {**safe, 'phase': 'Pressed'},
            {**safe, 'outcome': {}}, {**safe, 'outcome': 'accepted'},
            {**safe, 'reason': []}, {**safe, 'reason': 'raw error text'},
            {**safe, 'reason': ''}, {**safe, 'press_dispatched': 1},
            {**safe, 'press_dispatched': 'true'}, {**safe, 'release_dispatched': None})
        for value in malformed:
            with self.subTest(value=value):
                result = self.report(body, value, 'submitted',
                    conversation_url='https://www.meta.ai/prompt/test-123')
                self.assertEqual(result['stage'], 'submitted')
                self.assertEqual(result['send_diagnostic'], safe)

    def test_optional_legacy_event_does_not_add_or_erase_diagnostics(self):
        body = self.advance('send_intent')
        self.assertNotIn('send_diagnostic', self.manager.get(self.job_id, 1))
        result = self.manager.event({**body, 'stage': 'send_intent',
                                    'future_unknown_field': {'ignored': True}})
        self.assertNotIn('send_diagnostic', result)
        safe = self.diagnostic()
        self.report(body, safe)
        result = self.manager.event({**body, 'stage': 'send_intent'})
        self.assertEqual(result['send_diagnostic'], safe)

    def test_late_lower_phase_cannot_erase_known_dispatch_progress(self):
        body = self.advance('send_intent')
        pressed = self.diagnostic()
        self.report(body, pressed)
        older = dict(phase='before_press', outcome='blocked_before_press',
                     reason='draft_changed', press_dispatched=False, release_dispatched=False)
        self.assertEqual(self.report(body, older)['send_diagnostic'], pressed)
        released = dict(phase='released', outcome='gesture_released',
                        press_dispatched=True, release_dispatched=True)
        self.report(body, released)
        self.assertEqual(self.report(body, pressed)['send_diagnostic'], released)

    def test_dispatch_attempt_flags_cannot_be_downgraded_or_lost(self):
        body = self.advance('send_intent')
        self.report(body, self.diagnostic())
        result = self.report(body, {'phase': 'released', 'outcome': 'dispatch_unknown',
                                   'reason': 'dispatch_error', 'press_dispatched': False,
                                   'release_dispatched': True})
        self.assertIs(result['send_diagnostic']['press_dispatched'], True)
        result = self.report(body, {'phase': 'released', 'outcome': 'gesture_released'})
        self.assertEqual(result['send_diagnostic'], {'phase': 'released',
            'outcome': 'gesture_released', 'press_dispatched': True, 'release_dispatched': True})
        self.assertNotIn('reason', result['send_diagnostic'])

    def test_wrong_owner_or_invalid_transition_cannot_persist_diagnostics(self):
        body = self.advance('send_intent')
        before = self.manager.get(self.job_id, 1)
        for changes in ({'request_id': 'other'}, {'context_id': 'other'}, {'stage': 'prepared'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.manager.event({**body, 'stage': 'send_intent',
                                    'send_diagnostic': self.diagnostic(), **changes})
            self.assertEqual(self.manager.get(self.job_id, 1), before)

    def test_unknown_send_resume_preserves_receipt_and_diagnostic(self):
        body = self.advance('send_intent')
        safe = self.diagnostic()
        self.report(body, safe, 'needs_attention')
        result = self.manager.begin(self.job_id, 1, resume=True)
        self.assertEqual(result['stage'], 'send_intent')
        self.assertEqual(result['request_id'], body['request_id'])
        self.assertEqual(result['send_diagnostic'], safe)
        with self.assertRaises(ValueError):
            self.report(body, safe, 'ready_to_send')

    def test_invalid_diagnostic_cannot_block_real_saved_clip_or_alter_stored_replay(self):
        body = self.advance('downloading')
        source = Path(self.temp.name) / 'result.mp4'
        source.write_bytes(b'video-data' * 200)
        result = self.report(body, {'phase': 'raw text'}, 'stored', filename=str(source))
        self.assertEqual(result['stage'], 'stored')
        self.assertNotIn('send_diagnostic', result)
        self.assertEqual(self.report(body, self.diagnostic(), 'stored'), result)
        self.assertEqual(self.manager.clips(self.job_id)[0].read_bytes(), source.read_bytes())


if __name__ == '__main__':
    unittest.main()
