"""Offline execution of remaining-scene collectors, composition and ownership."""
import copy
import hashlib
import inspect
import json
import tempfile
import threading
import unittest
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.atomic_json import AtomicJsonFile
from core.scene_pipeline import ScenePipeline
from core import scene_video_plan as plans
from core.scene_video_worker import collect_all, collect_scene, complete_missing_segments, provenance, flow_download_path, retire_saved_meta_terminal, retire_saved_flow_terminal
from core.video_library import VideoLibrary
from core.local_bridge import LocalBridge
from ui.main_window import MainWindow


class SavedStories:
    def __init__(self, root, provider='google_flow', count=4):
        self.root = Path(root)
        self._manifest_lock = threading.RLock()
        self.job_id = 'STORY-PLAN-TEST'
        self.folder = self.root / self.job_id
        (self.folder / 'generated').mkdir(parents=True)
        (self.folder / 'videos').mkdir()
        images = []
        for index in range(1, count + 1):
            path = self.folder / 'generated' / f'scene_{index:02d}.png'
            path.write_bytes(bytes([index]) * 2048)
            images.append(path.relative_to(self.folder).as_posix())
        self._save({'id': self.job_id, 'product_story': {'version': 1}, 'job_type': 'story_short',
            'status': 'ready_to_render', 'ai_status': 'ready', 'scene_count': count,
            'video_generation_mode': provider, 'scene_pipeline_version': 0,
            'generated_images': images, 'scene_prompts': ['fixture motion'] * count,
            'scene_narrations': [f'fixture narration {i}' for i in range(count)],
            'scene_durations': [1] * count, 'flow_clips': {}, 'meta_clips': {},
            'audio_choices': {'mode': 'none', 'subtitle': False, 'music': False, 'sfx': False},
            'render_snapshot': {'width': 360, 'height': 640, 'fps': 24, 'crf': 25, 'transition_sec': .22}})

    def _folder(self, job_id):
        if job_id != self.job_id:
            raise ValueError('wrong job')
        return self.folder

    def _manifest_store(self, path):
        return AtomicJsonFile(path)

    def get(self, job_id):
        return self._manifest_store(self._folder(job_id) / 'job.json').read()

    def _save(self, job):
        self._manifest_store(self.folder / 'job.json').write(job)

    def mark_running(self, job_id, stage):
        return self.get(job_id)

    def clip(self, index, provider):
        path = self.folder / 'videos' / f'{provider}-{index}.mp4'
        path.write_bytes((f'{provider}-{index} '.encode()) * 300)
        job = self.get(self.job_id)
        field = 'flow_clips' if provider == 'google_flow' else 'meta_clips'
        job.setdefault(field, {})[str(index)] = path.relative_to(self.folder).as_posix()
        if provider == 'meta_ai':
            job.setdefault('meta_clip_receipts', {})[str(index)] = {
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'request_id': f'req-{index}',
                'context_id': f'context-{index}', 'download_id': str(index)}
        self._save(job)
        return path

    def attach_flow_clip(self, job_id, index, path, **kwargs):
        job = self.get(job_id)
        job['flow_clips'][str(index)] = Path(path).relative_to(self.folder).as_posix()
        self._save(job)
        return job

    def save_video(self, job_id, path, plan):
        job = self.get(job_id)
        job.update(render_plan=plan, video_source_type=plan['source_type'], video_status='ready')
        self._save(job)
        return job


class SceneVideoWorker457Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.probe = patch('core.scene_video_plan._probe', return_value={'duration': 1.0, 'width': 360, 'height': 640})
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def app(self, provider='google_flow', count=4):
        stories = SavedStories(Path(self.temp.name) / provider, provider, count)
        dispatched = []
        def controller(selected):
            def run(job_id, cancel, only_scene=None, _planned_route=False, **kwargs):
                self.assertTrue(_planned_route)
                dispatched.append((selected, only_scene))
                return [stories.clip(only_scene, selected)]
            return run
        app = SimpleNamespace(stories=stories, cfg={}, events=Queue(),
            _collect_story_flow_clips=controller('google_flow'),
            _collect_story_meta_clips=controller('meta_ai'))
        return app, dispatched

    def test_flow_to_meta_keeps_completed_hashes_and_dispatches_only_remaining(self):
        app, sent = self.app()
        saved = [app.stories.clip(index, 'google_flow') for index in (1, 2)]
        before = [path.read_bytes() for path in saved]
        plans.save(app.stories, app.stories.job_id, 0, 'meta_ai', [1, 2, 3, 4])
        paths = collect_all(app, app.stories.job_id, None)
        self.assertEqual(sent, [('meta_ai', 3), ('meta_ai', 4)])
        self.assertEqual(paths[:2], saved)
        self.assertEqual([path.read_bytes() for path in saved], before)
        collect_all(app, app.stories.job_id, None)
        self.assertEqual(len(sent), 2)

    def test_meta_to_flow_and_back_do_not_regenerate_completed_scene(self):
        app, sent = self.app('meta_ai')
        app.stories.clip(1, 'meta_ai')
        plans.save(app.stories, app.stories.job_id, 0, 'google_flow', [2, 3, 4], {'model': 'Veo fixture', 'duration': '8s'})
        collect_scene(app, app.stories.job_id, 2, None)
        plans.save(app.stories, app.stories.job_id, 1, 'meta_ai', [2, 3, 4])
        collect_all(app, app.stories.job_id, None)
        self.assertEqual(sent, [('google_flow', 2), ('meta_ai', 3), ('meta_ai', 4)])
        assets = plans.ordered_assets(app.stories.folder, app.stories.get(app.stories.job_id))
        self.assertEqual([row['provider'] for row in assets], ['meta_ai', 'google_flow', 'meta_ai', 'meta_ai'])

    def test_changed_completed_file_never_dispatches_a_replacement(self):
        app, sent = self.app()
        clip = app.stories.clip(1, 'google_flow')
        plans.save(app.stories, app.stories.job_id, 0, 'meta_ai', [2, 3, 4])
        clip.write_bytes(b'changed' * 600)
        with self.assertRaises(ValueError):
            collect_scene(app, app.stories.job_id, 1, None)
        self.assertEqual(sent, [])

    def test_completed_sequential_segments_never_call_voice_or_scene_worker(self):
        app, sent = self.app(count=2)
        job = app.stories.get(app.stories.job_id)
        job['scene_pipeline_version'] = 1
        app.stories._save(job)
        pipeline = ScenePipeline(app.stories.folder)
        for index in (1, 2):
            clip = app.stories.clip(index, 'google_flow')
            row = pipeline.request(index, 2, {'fixture': index})
            pipeline.update(index, row['revision'], phase='complete', segment=clip.relative_to(app.stories.folder).as_posix(),
                            voice=f'audio/paid-{index}.wav', duration=1)
        plans.save(app.stories, app.stories.job_id, 0, 'meta_ai', [1, 2])
        app._run_story_scene_worker = Mock(side_effect=AssertionError('must reuse paid segment'))
        paths = complete_missing_segments(app, app.stories.job_id, '', '', '', None)
        self.assertEqual(paths, pipeline.segments(2))
        self.assertFalse(app._run_story_scene_worker.called)
        self.assertEqual(sent, [])

    def test_future_staged_selection_claimed_before_new_local_busy_marker(self):
        app, sent = self.app(count=2)
        jid = app.stories.job_id
        job = app.stories.get(jid)
        job['scene_pipeline_version'] = 1
        app.stories._save(job)
        plans.save(app.stories, jid, 0, 'meta_ai', [1, 2], unknown_active=True)
        pipeline = ScenePipeline(app.stories.folder)
        def worker(payload, *_):
            index = payload['index']
            self.assertEqual(plans.package_binding(app.stories.get(jid), index)['provider'], 'meta_ai')
            path = app.stories.clip(index, 'meta_ai')
            pipeline.update(index, payload['revision'], phase='complete',
                segment=path.relative_to(app.stories.folder).as_posix(), duration=1)
        app._run_story_scene_worker = Mock(side_effect=worker)
        result = complete_missing_segments(app, jid, '', '', '', None)
        self.assertEqual(len(result), 2)
        self.assertEqual(app._run_story_scene_worker.call_count, 2)
        self.assertEqual(sent, [])

    def test_explicit_save_action_returns_authoritative_review_and_never_dispatches(self):
        app, sent = self.app(count=2)
        jid = app.stories.job_id
        app._story_pipeline_job_id = jid
        app._write_console = Mock()
        app.bridge = SimpleNamespace(_extension_lock=threading.RLock(), _extension_commands=[], _extension_clients={})
        payload = {'job_id': jid, 'expected_plan_revision': 0, 'provider': 'meta_ai', 'scene_indices': [1, 2]}
        def review(folder, job, active):
            return {'video_plan': plans.summary(folder, job, active)}
        with patch('core.membership.guard_action'), patch('ui.main_window.story_review', side_effect=review):
            response = inspect.unwrap(MainWindow._desktop_execute_action)(app, 'story_save_video_plan', payload)
            self.assertTrue(response['ok'])
            self.assertEqual(response['review']['video_plan']['revision'], 1)
            self.assertEqual(response['video_plan']['staged'], [1, 2])
            with self.assertRaises(ValueError):
                inspect.unwrap(MainWindow._desktop_execute_action)(app, 'story_save_video_plan',
                    {**payload, 'provider': 'google_flow'})
            with self.assertRaisesRegex(ValueError, 'JOB'):
                inspect.unwrap(MainWindow._desktop_execute_action)(app, 'story_save_video_plan',
                    {**payload, 'job_id': 'JOB-LEGACY'})
        self.assertEqual(sent, [])

    def test_flow_collector_adopts_plan_saved_while_first_scene_is_generating(self):
        app, sent = self.app(count=3)
        jid = app.stories.job_id
        app._collect_story_flow_clips = lambda *args, **kw: MainWindow._collect_story_flow_clips(app, *args, **kw)
        app._ensure_flow_extension = Mock()
        app._close_saved_flow_tab = Mock()
        app._write_console = Mock()
        app.bridge = SimpleNamespace(REQUIRED_EXTENSION_VERSION='fixture', clear_flow_progress=Mock(),
            queue_extension_command=Mock(return_value={'id': 'owned', 'run_id': 'run'}),
            extension_status=lambda: {'clients': [{'version': 'fixture', 'flow_job_id': jid,
                'flow_shot_index': 1, 'flow_step': 'generation_complete'}]})
        def during_first(*args, **kwargs):
            self.assertFalse(plans.enabled(app.stories.get(jid)))
            plans.save(app.stories, jid, 0, 'meta_ai', [1, 2, 3], active_scene_indices=[1])
        app._wait_flow_step = Mock(side_effect=during_first)
        app._wait_download = Mock(side_effect=lambda *_a, **_kw: app.stories.clip(1, 'google_flow'))
        result = app._collect_story_flow_clips(jid, None)
        self.assertEqual([path.name for path in result], ['google_flow-1.mp4', 'meta_ai-2.mp4', 'meta_ai-3.mp4'])
        self.assertEqual(sent, [('meta_ai', 2), ('meta_ai', 3)])
        self.assertNotIn('stop_flow_generation', [call.args[0] for call in app.bridge.queue_extension_command.call_args_list])

    def test_meta_collector_adopts_plan_saved_during_original_download(self):
        app, sent = self.app('meta_ai', count=3)
        jid = app.stories.job_id
        app._collect_story_meta_clips = lambda *args, **kw: MainWindow._collect_story_meta_clips(app, *args, **kw)
        app._compatible_extension = lambda: ({}, True)
        app.bridge = SimpleNamespace(queue_extension_command=Mock(return_value={'id': 'old-meta'}),
            extension_command_status=lambda _: {'status': 'completed'})
        manager = SimpleNamespace(begin=lambda *_: {'stage': 'submitted'}, package=lambda *_: {}, clips=Mock())
        def complete(*_):
            plans.save(app.stories, jid, 0, 'google_flow', [1, 2, 3], active_scene_indices=[1])
            saved = app.stories.clip(1, 'meta_ai')
            return {'stage': 'stored', 'path': saved.relative_to(app.stories.folder).as_posix(),
                    'sha256': hashlib.sha256(saved.read_bytes()).hexdigest()}
        manager.get = complete
        with patch('core.meta_video.MetaVideoManager', return_value=manager):
            result = app._collect_story_meta_clips(jid, None)
        self.assertEqual([path.name for path in result], ['meta_ai-1.mp4', 'google_flow-2.mp4', 'google_flow-3.mp4'])
        self.assertEqual(sent, [('google_flow', 2), ('google_flow', 3)])
        self.assertFalse(manager.clips.called)

    def test_mixed_composition_keeps_order_global_voice_and_saved_options(self):
        app, _ = self.app('meta_ai', count=3)
        jid = app.stories.job_id
        app.stories.clip(1, 'meta_ai')
        plans.save(app.stories, jid, 0, 'google_flow', [2, 3])
        collect_all(app, jid, None)
        job = app.stories.get(jid)
        job['audio_choices'].update(mode='api', keep_video_audio=True, video_audio_volume=23)
        # Audio stays frozen during real switch. Use the same fixture audio in
        # all frozen identities rather than editing an adopted production job.
        for row in job['scene_video_plan']['scenes'].values():
            row.pop('asset', None)
        app.stories._save(job)
        voice = app.stories.folder / 'paid-narration.wav'
        voice.write_bytes(b'paid voice' * 200)
        app._queue_story_phase = Mock()
        app._creation_settings = lambda _: {}
        composer = Mock()
        composer.compose.side_effect = lambda paths, target, **kw: {'output': target, 'duration': 3}
        rendered = {**job, 'scene_narrations': ['effective creative revision'] * 3}
        with patch('ui.main_window.MultiFlowComposer', return_value=composer), \
             patch('core.scene_context_revision.render_story', return_value=rendered), \
             patch('ui.main_window.finish_story_media', side_effect=lambda _root, _m, _jid, final, *_a, **_kw: (final, {})), \
             patch('ui.ai_cover.finish_ai_cover'):
            inspect.unwrap(MainWindow._compose_story_media)(app, jid, job, voice, None)
        args = composer.compose.call_args
        self.assertEqual([path.name for path in args.args[0]], ['meta_ai-1.mp4', 'google_flow-2.mp4', 'google_flow-3.mp4'])
        self.assertEqual(args.kwargs['voice_path'], voice)
        self.assertEqual(args.kwargs['audio_choices']['video_audio_volume'], 23)
        final_plan = app.stories.get(jid)['render_plan']
        self.assertEqual(final_plan['source_type'], 'mixed_ai_story_composite')
        self.assertEqual([row['provider'] for row in final_plan['scene_video_sources']], ['meta_ai', 'google_flow', 'google_flow'])

    def test_terminal_old_flow_promotes_staged_meta_without_stop_or_second_flow(self):
        app, sent = self.app(count=2)
        jid = app.stories.job_id
        plans.save(app.stories, jid, 0, 'google_flow', [1, 2])
        plans.apply_at_safe_boundary(app.stories, jid, 1)
        app._collect_story_flow_clips = lambda *a, **kw: MainWindow._collect_story_flow_clips(app, *a, **kw)
        app._ensure_flow_extension = Mock()
        app._write_console = Mock()
        app.bridge = SimpleNamespace(REQUIRED_EXTENSION_VERSION='fixture', clear_flow_progress=Mock(),
            queue_extension_command=Mock(return_value={'id': 'owned', 'run_id': 'owned-run'}),
            extension_status=lambda: {'clients': [{'version': 'fixture', 'flow_job_id': jid,
                'flow_shot_index': 1, 'flow_step': 'generation_in_progress'}]})
        def failed(*_a, **_kw):
            plans.save(app.stories, jid, 1, 'meta_ai', [1, 2], active_scene_indices=[1])
            error = RuntimeError('confirmed terminal upload failure')
            error.flow_retry_forbidden = True
            error.scene_video_terminal_proof = {'terminal': True, 'busy': False,
                'download_pending': False, 'kind': 'never_dispatched', 'code': 'FLOW_ATTACHMENT_UNCONFIRMED'}
            raise error
        app._wait_flow_step = Mock(side_effect=failed)
        paths = collect_all(app, jid, None)
        self.assertEqual(sent, [('meta_ai', 1), ('meta_ai', 2)])
        self.assertEqual(len(paths), 2)
        self.assertEqual(app._wait_flow_step.call_count, 1)
        self.assertNotIn('stop_flow_generation', [call.args[0] for call in app.bridge.queue_extension_command.call_args_list])

    def test_interrupted_terminal_meta_claim_can_switch_but_unknown_send_cannot(self):
        app, sent = self.app('meta_ai', count=2)
        jid = app.stories.job_id
        plans.save(app.stories, jid, 0, 'meta_ai', [1, 2])
        plans.apply_at_safe_boundary(app.stories, jid, 1)
        binding = plans.package_binding(app.stories.get(jid), 1)
        plans.save(app.stories, jid, 1, 'google_flow', [1, 2])
        store = AtomicJsonFile(app.stories.folder / 'prompts' / 'meta_video_receipts.json')
        receipt = {'stage': 'needs_attention', 'request_id': 'same-request', 'scene_video_plan': binding}
        store.write({'scenes': {'1': receipt}})
        self.assertFalse(retire_saved_meta_terminal(app, jid, 1))
        self.assertEqual(plans.provider_for(app.stories.get(jid), 1), 'meta_ai')
        receipt.update(retry_exhausted=True, failure_reason='completed_no_video', failure_answer_sha256='a' * 64)
        store.write({'scenes': {'1': receipt}})
        collect_all(app, jid, None)
        self.assertEqual(sent, [('google_flow', 1), ('google_flow', 2)])

    def test_disconnected_legacy_flow_terminal_requires_latest_exact_run_and_card(self):
        app, sent = self.app(count=2)
        jid = app.stories.job_id
        job = app.stories.get(jid)
        job['flow_policy_failure_history'] = {'1': [{'flow_run_id': 'failed-run',
            'failure_card_fingerprint': 'owned-card', 'image_sha256': 'saved', 'prompt_sha256': 'saved',
            'failure_code': 'FLOW_POLICY_BLOCKED'}]}
        app.stories._save(job)
        plans.save(app.stories, jid, 0, 'meta_ai', [1, 2], active_scene_indices=[1])
        log = app.stories.folder / 'logs' / 'flow_extension.jsonl'
        log.parent.mkdir()
        log.write_text(json.dumps({'shot_index': 1, 'run_id': 'newer-unknown-run', 'step': 'generation_in_progress'}), encoding='utf-8')
        self.assertFalse(retire_saved_flow_terminal(app, jid, 1))
        log.write_text(json.dumps({'shot_index': 1, 'run_id': 'failed-run', 'step': 'generation_failed',
            'failure_code': 'FLOW_POLICY_BLOCKED', 'failure_card_fingerprint': 'owned-card'}), encoding='utf-8')
        collect_all(app, jid, None)
        self.assertEqual(sent, [('meta_ai', 1), ('meta_ai', 2)])

    def test_planned_native_retry_uses_flow_claim_and_preserves_other_paid_segment(self):
        app, sent = self.app(count=2)
        jid = app.stories.job_id
        job = app.stories.get(jid)
        job['scene_pipeline_version'] = 1
        app.stories._save(job)
        pipeline = ScenePipeline(app.stories.folder)
        for index in (1, 2):
            path = app.stories.clip(index, 'google_flow')
            row = pipeline.request(index, 2, {'scene': index})
            pipeline.update(index, row['revision'], phase='complete', segment=path.relative_to(app.stories.folder).as_posix(), duration=1)
        plans.save(app.stories, jid, 0, 'meta_ai', [1, 2])
        before = pipeline.get(1)
        state = {'status': 'pending', 'retry_id': 'speech-owned', 'segment_sha256': pipeline.get(2)['segment_sha256'], 'attempt': 1}
        job = app.stories.get(jid)
        job['flow_speech_retries'] = {'2': state}
        job['flow_clips'].pop('2')
        app.stories._save(job)
        new = app.stories.folder / 'videos' / 'retry-owned.mp4'
        new.write_bytes(b'new authorized raw clip' * 200)
        def collect(_jid, _cancel, only_scene, fresh_scene_attempt):
            self.assertEqual((only_scene, fresh_scene_attempt), (2, 'speech-owned'))
            self.assertEqual(plans.package_binding(app.stories.get(jid), 2)['provider'], 'google_flow')
            job = app.stories.get(jid)
            job['flow_clips']['2'] = new.relative_to(app.stories.folder).as_posix()
            app.stories._save(job)
            return [new]
        app._collect_story_flow_clips = Mock(side_effect=collect)
        app._queue_story_phase = Mock()
        app._creation_settings = lambda _: {}
        app.stories.complete_native_speech_retry = Mock()
        with patch('core.scene_voice.render_scene_asset', return_value={'segment': new.relative_to(app.stories.folder).as_posix(), 'duration': 1, 'voice': ''}):
            MainWindow._retry_story_native_speech_scene(app, jid, 2, state, None)
        self.assertEqual(pipeline.get(1), before)
        self.assertEqual(plans.ordered_assets(app.stories.folder, app.stories.get(jid))[1]['path'], str(new.relative_to(app.stories.folder)))
        self.assertEqual(sent, [])

    def test_finisher_checks_raw_assets_and_never_sends_meta_findings_to_flow_retry(self):
        from core.story_finisher import finish_story_media
        from core.flow_speech_quality import RepeatedNativeSpeechError
        app, _ = self.app('meta_ai', count=2)
        jid = app.stories.job_id
        job = app.stories.get(jid)
        job.update(scene_pipeline_version=1, audio_choices={'mode': 'flow_original', 'subtitle': True, 'music': False, 'sfx': False})
        app.stories._save(job)
        pipeline = ScenePipeline(app.stories.folder)
        for index, provider in ((1, 'meta_ai'), (2, 'google_flow')):
            clip = app.stories.clip(index, provider)
            row = pipeline.request(index, 2, {'scene': index})
            pipeline.update(index, row['revision'], phase='complete', segment=clip.relative_to(app.stories.folder).as_posix(), duration=1)
        plans.save(app.stories, jid, 0, 'google_flow', [1, 2])
        rendered = {**app.stories.get(jid), 'scene_narrations': ['effective revision'] * 2}
        for scene, error_type in ((1, ValueError), (2, RepeatedNativeSpeechError)):
            audit = {'status': 'repeat_confirmed', 'findings': [{'scene': scene, 'phrase': 'duplicate'}], 'source_sha256': 'fixture'}
            with patch('core.scene_context_revision.render_story', return_value=rendered), \
                 patch('core.story_finisher.AudioMixer') as mixer, \
                 patch('core.media_audio.native_transcript', return_value={'segments': []}), \
                 patch('core.flow_speech_quality.audit_native_scene_speech', return_value=audit):
                mixer.return_value.duration.return_value = 2
                with self.assertRaises(error_type) as caught:
                    finish_story_media(Path(self.temp.name), app.stories, jid, app.stories.folder / 'source.mp4', {})
                if scene == 1:
                    self.assertIn('Meta AI', str(caught.exception))
                    self.assertNotIsInstance(caught.exception, RepeatedNativeSpeechError)

    def test_library_uses_accepted_sources_not_archived_provider_counts(self):
        job = {'scene_video_plan': {'version': 1}, 'video_generation_mode': 'meta_ai', 'scene_count': 3,
               'video_source_type': 'mixed_ai_story_composite', 'meta_clip_count': 12, 'flow_clip_count': 9,
               'render_plan': provenance([{'index': 1, 'provider': 'meta_ai', 'sha256': 'a'},
                   {'index': 2, 'provider': 'google_flow', 'sha256': 'b'},
                   {'index': 3, 'provider': 'local', 'sha256': 'c'}])}
        result = VideoLibrary._video_source_summary('story', job)
        self.assertEqual(result['video_plan_summary'], {'completed': 3, 'flow': 1, 'meta': 1, 'local': 1, 'pending': 0})
        self.assertIn('Meta AI 1', result['video_source_label'])

    def test_bridge_requires_original_binding_and_unique_download_path(self):
        app, _ = self.app(count=2)
        jid = app.stories.job_id
        plans.save(app.stories, jid, 0, 'google_flow', [1, 2])
        plans.apply_at_safe_boundary(app.stories, jid, 1)
        binding = plans.package_binding(app.stories.get(jid), 1)
        bridge = SimpleNamespace(stories=app.stories)
        with patch('pathlib.Path.home', return_value=Path(self.temp.name)):
            target = flow_download_path(jid, 1, binding)
            target.parent.mkdir(parents=True)
            target.write_bytes(b'owned complete download' * 150)
            body = {'job_id': jid, 'shot_index': 1, 'scene_video_plan': binding, 'video_provider': 'google_flow',
                    'step': 'generation_complete', 'download_path': str(target)}
            result = LocalBridge._validated_scene_video_flow_progress(bridge, body)
            self.assertEqual(result['flow_download_sha256'], hashlib.sha256(target.read_bytes()).hexdigest())
            wrong = copy.deepcopy(body)
            wrong['scene_video_plan']['attempt_id'] = 'old-attempt'
            with self.assertRaises(ValueError):
                LocalBridge._validated_scene_video_flow_progress(bridge, wrong)
            old = flow_download_path(jid, 1)
            old.write_bytes(b'old file' * 300)
            with self.assertRaises(ValueError):
                LocalBridge._validated_scene_video_flow_progress(bridge, {**body, 'download_path': str(old)})


if __name__ == '__main__':
    unittest.main()
