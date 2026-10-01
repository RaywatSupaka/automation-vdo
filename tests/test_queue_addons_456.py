"""Queue-only addon edits exercise the real adapter and persisted temporary FIFO."""
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from core.creation_queue import CreationQueue
from ui.creation_queue import CreationQueueMixin


class QueueAddons456(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='smartflow-queue-addons-')
        self.addCleanup(self.temp.cleanup)
        self.queue = CreationQueue(self.temp.name)
        self.settings = {
            'ai_cover_options': {'enabled': True, 'headline': 'Saved custom headline', 'scene_index': 2},
            'green_options': {'enabled': True, 'clips': [{'file': 'assets/screenfx/' + 'a'*64 + '.mp4',
                'color': '#00ff00', 'similarity': .2, 'blend': .1}], 'opacity': .35, 'fit': 'cover'},
            'voice_reference_id': 'saved-voice', 'subtitle_enabled': False,
            'render': {'width': 1080}, 'intro_options': {'enabled': False, 'file': ''}}
        self.row = self.queue.enqueue('product', ['https://s.shopee.co.th/one'],
            settings=self.settings, provider='gemini', ai_web_model='pro')['items'][0]
        self.app = SimpleNamespace(story_queue=self.queue, _write_console=Mock(),
            _creation_queue_state=self.queue.snapshot, _creation_capture_settings=Mock(),
            _creation_idle_reason=Mock(return_value=''), _creation_recoverable_jobs=Mock(return_value=[]))

    def edit(self, **payload):
        return CreationQueueMixin._creation_queue_action.__wrapped__(self.app, 'creation_edit',
            dict(queue_id=self.row['queue_id'], value='https://s.shopee.co.th/renamed', **payload))

    def saved(self):
        return self.queue.get_item(self.row['queue_id'])['settings']

    def test_cover_omitted_headline_preserves_saved_text_and_scene(self):
        self.edit(ai_cover_options={'enabled': False, 'scene_index': 2})
        expected = copy.deepcopy(self.row['settings'])
        expected['ai_cover_options']['enabled'] = False
        self.assertEqual(self.saved(), expected)
        self.app._creation_capture_settings.assert_not_called()

    def test_explicit_blank_headline_clears_only_that_field(self):
        self.edit(ai_cover_options={'headline': ''})
        expected = copy.deepcopy(self.row['settings'])
        expected['ai_cover_options']['headline'] = ''
        self.assertEqual(self.saved(), expected)

    def test_green_toggle_changes_only_this_row_and_preserves_saved_clips(self):
        other = self.queue.enqueue('product', ['https://s.shopee.co.th/other'],
            settings={'green_options': {'enabled': False}})['items'][0]
        self.edit(green_options={'enabled': False})
        expected = copy.deepcopy(self.row['settings'])
        expected['green_options']['enabled'] = False
        self.assertEqual(self.saved(), expected)
        self.assertEqual(self.queue.get_item(other['queue_id']), other)
        self.app._creation_capture_settings.assert_not_called()

    def test_rename_without_addon_payload_keeps_exact_options(self):
        self.edit()
        self.assertEqual(self.saved(), self.row['settings'])

    def test_invalid_or_unsupported_green_edit_is_atomic(self):
        for options in ({'enabled': 'yes'}, {'opacity': 0}, {'clips': [], 'enabled': True}):
            with self.subTest(options=options):
                before = self.queue.snapshot()
                with self.assertRaises(ValueError):
                    self.edit(green_options=options)
                self.assertEqual(self.queue.snapshot(), before)
        self.queue._update(self.row['queue_id'], long_video={'version': 2})
        before = self.queue.snapshot()
        with self.assertRaisesRegex(ValueError, 'ไม่รองรับ'):
            self.edit(green_options={'enabled': False})
        self.assertEqual(self.queue.snapshot(), before)

    def test_legacy_absent_green_cannot_adopt_global_by_enable_only(self):
        settings = copy.deepcopy(self.row['settings'])
        settings.pop('green_options')
        self.queue._update(self.row['queue_id'], settings=settings)
        before = self.queue.snapshot()
        with self.assertRaises(ValueError):
            self.edit(green_options={'enabled': True})
        self.assertEqual(self.queue.snapshot(), before)

    def test_recapture_is_explicit_and_does_not_implicitly_clear_headline(self):
        captured = copy.deepcopy(self.row['settings'])
        captured['voice_reference_id'] = 'current-voice'
        def capture(payload):
            result = copy.deepcopy(captured)
            result['ai_cover_options'] = payload['ai_cover_options']
            return result
        self.app._creation_capture_settings.side_effect = capture
        self.edit(use_current_settings=True, ai_cover_options={'enabled': False, 'scene_index': 0})
        self.app._creation_capture_settings.assert_called_once()
        self.assertEqual(self.saved()['voice_reference_id'], 'current-voice')
        self.assertEqual(self.saved()['ai_cover_options'],
            {'enabled': False, 'headline': 'Saved custom headline', 'scene_index': 0})

    def test_locked_or_started_rows_cannot_change_addons(self):
        for changes in ({'status': 'running'}, {'job_id': 'JOB-EXISTING'}, {'status': 'completed'}, {'mode': 'drama'}):
            with self.subTest(changes=changes):
                self.queue._update(self.row['queue_id'], **(dict(status='queued', job_id='', mode='product') | changes))
                before = self.queue.snapshot()
                with self.assertRaises(ValueError):
                    self.edit(green_options={'enabled': False}, ai_cover_options={'headline': ''})
                self.assertEqual(self.queue.snapshot(), before)

    def test_native_ui_uses_saved_row_not_global_addons(self):
        first = copy.deepcopy(self.row['settings'])
        first['green_options']['enabled'] = False
        self.queue._update(self.row['queue_id'], settings=first)
        self.queue.enqueue('product', ['https://s.shopee.co.th/two'], settings=self.settings)
        state = CreationQueueMixin._creation_queue_state(self.app)
        result = subprocess.run(['node', 'tests/queue_addons_456.cjs', json.dumps(state)],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_public_editor_state_allowlist_keeps_options_but_not_execution_data(self):
        settings = copy.deepcopy(self.row['settings'])
        settings.update(voice_reference_file='PRIVATE_VOICE.wav', finish_config={'logo_file':'PRIVATE_LOGO.png'},
            render={'output': 'PRIVATE_RENDER.mp4'}, voice={'api_key': 'PRIVATE_KEY'})
        settings['green_options']['clips'][0]['private_path'] = 'PRIVATE_GREEN.mp4'
        settings['ai_cover_options']['credential'] = 'PRIVATE_CREDENTIAL'
        self.queue._update(self.row['queue_id'], settings=settings, long_video={'version': 2, 'private_path': 'PRIVATE_LONG'})
        before = self.queue.snapshot()
        state = CreationQueueMixin._creation_queue_state(self.app)
        self.assertNotIn('PRIVATE_', json.dumps(state))
        public = state['items'][0]
        self.assertTrue(public['long_video'])
        self.assertEqual(public['settings']['green_options'], self.row['settings']['green_options'])
        self.assertEqual(public['settings']['ai_cover_options'], self.row['settings']['ai_cover_options'])
        self.assertNotIn('voice_reference_id', public['settings'])
        self.assertEqual(self.queue.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
