"""Offline real desktop boundaries: capture once, persist, then use saved options."""
import copy
from pathlib import Path
import queue
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core.product_runtime_snapshot import prepared_product_runtime
from ui.main_window import MainWindow


CONTEXT = {'kind': 'product_story', 'product_short': True,
           'source_product_id': 'JOB-FIXTURE', 'snapshot_id': 'SNAP-FIXTURE'}
RUNTIME = {
    'provider': 'gemini', 'ai_web_model': 'flash', 'voice_reference_id': 'frozen-voice',
    'voice_reference_file': '', 'audio_choices': {'mode': 'api', 'subtitle': False, 'music': False, 'sfx': False},
    'voice': {'model': 'fixture-voice-model', 'temperature': 0.7},
    'audio': {'background_files': ['frozen-music.mp3']},
    'finish_config': {'subtitle_font': 'Frozen font', 'subtitle_auto_after_voice': False},
    'render': {'fps': 24}, 'flow_settings': {}, 'ai_cover_options': {'enabled': False},
    'intro_options': {'enabled': False}, 'green_options': {'enabled': False},
    'presenter': {'enabled': False}, 'subtitle_enabled': False,
    'product_script_options': {'version': 1, 'style': 'standard'},
}


def products(prepared=None):
    source = {'id': 'JOB-FIXTURE', 'story_source_only': True,
              'story_creative_context': copy.deepcopy(CONTEXT),
              'story_prepare_options': copy.deepcopy(prepared if prepared is not None else
                                                    {'product_runtime_snapshot': RUNTIME})}
    return SimpleNamespace(get_job=lambda ident: copy.deepcopy(source)), source


class ProductRuntimeSnapshot451Tests(unittest.TestCase):
    def test_incomplete_saved_runtime_never_falls_back_to_live_settings(self):
        for runtime in ({}, {'audio_choices': {'mode': 'api'}}, {**RUNTIME, 'voice_reference_id': None}):
            manager, _ = products({'product_runtime_snapshot': runtime})
            with self.subTest(runtime_keys=list(runtime)), self.assertRaisesRegex(ValueError, 'ไม่ครบ'):
                prepared_product_runtime(manager, {'creative_context': CONTEXT})

    def test_saved_product_voice_runtime_survives_finished_or_missing_queue(self):
        for item in (None, {'status':'completed', 'settings':{'voice_reference_id':'wrong'}}):
            app = SimpleNamespace(story_queue=SimpleNamespace(item_for_job=lambda ident: item),
                stories=SimpleNamespace(get=lambda ident:{'product_runtime_snapshot':copy.deepcopy(RUNTIME)}))
            result = MainWindow._creation_settings(app, 'STORY-FIXTURE')
            self.assertEqual(result['voice_reference_id'], 'frozen-voice')
            self.assertEqual(result['render']['fps'], 24)

    def test_saved_source_is_authoritative_and_detached(self):
        manager, source = products()
        result = prepared_product_runtime(manager, {'creative_context': CONTEXT,
            'product_runtime_snapshot': {'voice_reference_id': 'injected'}, 'audio_choices': {'mode': 'none'}})
        self.assertEqual(result['voice_reference_id'], 'frozen-voice')
        self.assertEqual(result['audio_choices']['mode'], 'api')
        result['render']['fps'] = 60
        self.assertEqual(source['story_prepare_options']['product_runtime_snapshot']['render']['fps'], 24)

    def test_mismatched_or_non_source_reference_rejected(self):
        manager, source = products()
        for change in ({'snapshot_id': 'different'}, {'snapshot_id': ''}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                prepared_product_runtime(manager, {'creative_context': {**CONTEXT, **change}})
        source['story_source_only'] = False
        with self.assertRaises(ValueError):
            prepared_product_runtime(manager, {'creative_context': CONTEXT})

    def test_explicit_legacy_defaults_do_not_read_current_controls(self):
        manager, _ = products({'audio_choices': {'mode': 'none', 'subtitle': False}, 'provider': 'gemini'})
        result = prepared_product_runtime(manager, {'creative_context': CONTEXT, 'voice_reference_id': 'current'})
        self.assertEqual(result['voice_reference_id'], '')
        for key in ('intro_options', 'green_options', 'ai_cover_options', 'presenter'):
            self.assertFalse(result[key]['enabled'])
        for key in ('finish_config', 'audio'):
            self.assertEqual(result[key], {})
        self.assertEqual(result['render']['width'], 720)
        self.assertEqual(result['render']['fps'], 30)
        self.assertEqual(result['voice']['language'], 'th')
        self.assertEqual(result['voice']['silence_sec'], 0.3)
        manager, _ = products({'provider': 'gemini'})
        with self.assertRaisesRegex(ValueError, 'ไม่มีค่าการพากย์'):
            prepared_product_runtime(manager, {'creative_context': CONTEXT})

    def test_queue_capture_for_prepared_product_never_reads_live_widgets(self):
        manager, _ = products()
        app = SimpleNamespace(products=manager)
        result = MainWindow._creation_capture_settings(app, {'creative_context': CONTEXT,
            'audio_choices': {'mode': 'none'}, 'product_runtime_snapshot': {'render': {'fps': 60}}})
        self.assertEqual(result['render']['fps'], 24)
        self.assertEqual(result['render']['width'], 720)
        self.assertEqual(result['voice_reference_id'], 'frozen-voice')

    def test_first_prepare_captures_once_and_poll_does_not_recapture(self):
        app = SimpleNamespace(products=object(), product_cast=object(), bridge=object(), story_queue=Mock(),
                              _desktop_request=Mock(return_value=copy.deepcopy(RUNTIME)))
        with patch('core.membership.guard_action'), patch('core.product_story.prepare_link', return_value={'ok': True}) as prepare:
            for form in ('product', 'product-batch'):
                payload = {'link': 'https://s.shopee.co.th/FIXTURE',
                           'product_option_snapshot': {'version': 1, 'form': form},
                           'product_runtime_snapshot': {'voice_reference_id': 'injected'}}
                MainWindow._desktop_action_request(app, 'product_story_prepare', payload)
                self.assertEqual(prepare.call_args.args[3]['product_runtime_snapshot'], RUNTIME)
                self.assertEqual(payload['product_runtime_snapshot']['voice_reference_id'], 'injected')
                before = app._desktop_request.call_count
                MainWindow._desktop_action_request(app, 'product_story_prepare', {**payload, 'product_id': 'JOB-FIXTURE'})
                self.assertEqual(app._desktop_request.call_count, before)
        self.assertEqual(app._desktop_request.call_count, 2)

    def capture_app(self):
        app = SimpleNamespace(cfg={}, _ui_thread_id=threading.get_ident(), _desktop_requests=queue.Queue(),
            _product_pipeline_options=lambda **kw: copy.deepcopy(RUNTIME),
            _presenter_selection=lambda value: value)
        app._creation_capture_settings = lambda payload: MainWindow._creation_capture_settings(app, payload)
        app._capture_product_prepare_settings = lambda payload: MainWindow._capture_product_prepare_settings(app, payload)
        return app

    def test_product_settings_poll_captures_all_script_styles_before_context_exists(self):
        app = self.capture_app()
        for style in ({'version': 1, 'style': 'standard'}, {'version': 1, 'style': 'story_first_review'},
                      {'version': 2, 'style': 'short_film_ad', 'genre': 'warm', 'ending_cta': True}):
            with self.subTest(style=style):
                completed, result = threading.Event(), {}
                app._desktop_requests.put(('product_settings', {**copy.deepcopy(RUNTIME),
                    'product_script_options': style, 'video_generation_mode': 'google_flow'}, completed, result))
                MainWindow._poll_desktop_requests(app)
                self.assertTrue(completed.is_set())
                self.assertNotIn('error', result)
                self.assertEqual(result['value']['product_script_options'], style)
                self.assertEqual(result['value']['creative_context'], {'kind': 'product_story', 'product_short': True})

    def test_product_settings_ui_thread_fastpath_matches_worker_poll(self):
        app = self.capture_app()
        result = MainWindow._desktop_request(app, 'product_settings', {**copy.deepcopy(RUNTIME),
            'video_generation_mode': 'google_flow', 'product_runtime_snapshot': {'render': {'fps': 60}}})
        self.assertEqual(result['render'], {'fps': 24})
        self.assertEqual(result['creative_context'], {'kind': 'product_story', 'product_short': True})

    def test_direct_creation_receives_saved_runtime_without_recapturing(self):
        app = Mock()
        app.membership = None
        app._app_update_pending = False
        app._manual_multi_flow_job_id = app._story_pipeline_job_id = app._product_pipeline_job_id = ''
        app._creation_workers_alive.return_value = False
        app.story_queue.snapshot.return_value = {'active_count': 0, 'paused': True}
        app.cfg = {}
        app.products, _ = products()
        app.voice_api_key.get.return_value = 'synthetic-key-not-persisted'
        app.voice_reference_id.get.return_value = ''
        app.voice_reference_file.get.return_value = ''
        app._resolve_desktop_reference_image.return_value = ''
        app._presenter_selection.return_value = {'enabled': False}
        payload = dict(creative_context=CONTEXT, topic='Fixture product', scene_count=3,
            video_generation_mode='google_flow', audio_choices={'mode': 'flow_original', 'subtitle': True})
        with patch('core.membership.guard_action'), patch('ui.presenter.PresenterMixin._presenter_busy', return_value=False):
            MainWindow._desktop_execute_action.__wrapped__(app, 'create_story', payload)
        self.assertEqual(app._create_story_and_run.call_args.kwargs['product_runtime_snapshot']['voice_reference_id'], 'frozen-voice')
        self.assertEqual(app._story_audio_choices['mode'], 'api')
        app._creation_capture_settings.assert_not_called()
        app._subtitle_store.assert_not_called()

    def test_direct_and_queued_job_save_the_same_frozen_render_and_audio(self):
        # All managers/UI/dispatch are inert mocks. Stop at mark_running, before
        # any browser call; no job or output is written on the real workspace.
        with tempfile.TemporaryDirectory() as temp:
            for queued in (False, True):
                with self.subTest(queued=queued):
                    runtime = {**copy.deepcopy(RUNTIME), 'creative_context': copy.deepcopy(CONTEXT)}
                    app = Mock()
                    app.membership = None
                    app._story_pipeline_job_id = app._product_pipeline_job_id = ''
                    app._story_progress_dialog = None
                    app.cfg = {}
                    app._story_audio_choices = copy.deepcopy(RUNTIME['audio_choices'])
                    app._story_flow_settings = {}
                    app._story_ai_cover_options = app._story_intro_options = app._story_green_options = {'enabled': False}
                    app._presenter_story_selection = {'enabled': False}
                    app._creation_dispatch_item = {'settings': {'presenter': {'enabled': False}}}
                    app._creation_settings.return_value = copy.deepcopy(runtime)
                    app._image_provider_key.return_value = 'gemini'
                    app._ai_web_model_key.return_value = 'flash'
                    app._story_video_mode_key.return_value = 'google_flow'
                    app._compatible_extension.return_value = ({}, True)
                    app.voice_api_key.get.return_value = 'synthetic-key'
                    app.voice_reference_id.get.return_value = ''
                    app.voice_reference_file.get.return_value = ''
                    app.stories.root = Path(temp)
                    job = {'id': 'STORY-FIXTURE', 'scene_count': 3}
                    app.stories.create.return_value = job
                    app.stories.mark_running.side_effect = RuntimeError('STOP_BEFORE_DISPATCH')
                    with patch('ui.main_window.messagebox.showerror'), patch('core.product_story.attach_context'):
                        MainWindow._create_story_and_run.__wrapped__(app, queue_item_id='Q-FIXTURE' if queued else '',
                            creative_context=None if queued else copy.deepcopy(CONTEXT),
                            product_runtime_snapshot=None if queued else copy.deepcopy(runtime))
                    self.assertEqual(job['product_runtime_snapshot']['voice_reference_id'], 'frozen-voice')
                    self.assertEqual(job['product_runtime_snapshot']['voice'], RUNTIME['voice'])
                    self.assertEqual(job['product_runtime_snapshot']['creative_context'], CONTEXT)
                    self.assertEqual(job['render_snapshot'], {'fps': 24})
                    self.assertEqual(job['audio_mix_choices'], RUNTIME['audio'])
                    self.assertEqual(job['media_finish_config'], RUNTIME['finish_config'])
                    app._creation_capture_settings.assert_not_called()
                    app._video_render_settings.assert_not_called()
                    app._activate_or_launch_chrome.assert_not_called()
                    app.bridge.queue_extension_command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
