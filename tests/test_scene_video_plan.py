"""Offline ownership/identity regressions for explicitly opted Shopee stories."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import scene_video_plan as plans
from core.flow_scene_edit import save as save_prompt
from core.flow_settings import flow_capabilities
from core.meta_video import MetaVideoManager
from core.story_manager import StoryManager
from core.studio_review import story_review, scene_asset


class SceneVideoPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = StoryManager(self.temp.name)
        self.job = self.manager.create('offline fixture', scene_count=6, video_generation_mode='google_flow')
        self.id = self.job['id']
        self.folder = self.manager._folder(self.id)
        images = [f'generated/scene_{i:02d}.png' for i in range(1, 7)]
        for image in images:
            (self.folder / image).write_bytes(image.encode())
        self.job.update(product_story={'product_id': 'TEST'}, generated_images=images,
            scene_prompts=['Scene fixture'] * 6, scene_narrations=['Narration fixture'] * 6,
            flow_settings={'model': 'Veo 3.1 - Fast', 'duration': '4s'}, status='error',
            audio_choices={'mode': 'none'}, voice_path='audio/kept.wav')
        self.manager._save(self.job)
        self.probe = patch.object(plans, '_probe', return_value={'duration': 8, 'width': 720, 'height': 1280})
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def clip(self, index, provider='google_flow'):
        path = self.folder / 'videos' / f'{provider}-{index}.mp4'
        path.parent.mkdir(exist_ok=True)
        path.write_bytes((f'{provider}-{index}'.encode() * 2048))
        job = self.manager.get(self.id)
        job.setdefault(plans.FIELDS[provider], {})[str(index)] = str(path.relative_to(self.folder))
        self.manager._save(job)
        return path

    def save(self, provider='meta_ai', indices=None, revision=0, settings=None, **kwargs):
        return plans.save(self.manager, self.id, revision, provider, indices or [1, 2, 3, 4, 5, 6], settings, **kwargs)

    def ledger(self, filename, scenes):
        (self.folder / 'prompts' / filename).write_text(json.dumps({'scenes': scenes}), encoding='utf-8')

    def test_read_does_not_migrate_and_scope_excludes_other_workflows(self):
        before = (self.folder / 'job.json').read_bytes()
        review = story_review(self.folder, self.manager.get(self.id))
        self.assertTrue(review['video_plan']['supported'])
        self.assertFalse(review['video_plan']['enabled'])
        self.assertEqual(before, (self.folder / 'job.json').read_bytes())
        for changes in ({'id': 'JOB-test'}, {'product_story': None}, {'long_video': {'version': 2}},
                        {'job_type': 'drama_episode'}, {'video_generation_mode': 'image_motion'}, {'cast_creation': True}):
            self.assertFalse(plans.eligible({**self.job, **changes}))

    def test_freezes_completed_mixed_assets_and_only_changes_remaining(self):
        paths = [self.clip(1), self.clip(2, 'meta_ai'), self.clip(3, 'local')]
        hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
        original = self.manager.get(self.id)
        saved = self.save(settings={'model': 'Veo 3.1 - Lite [Lower Priority]', 'duration': '8s'})
        self.assertEqual(saved['completed'], [1, 2, 3])
        self.assertEqual(saved['applied'], [4, 5, 6])
        job = saved['job']
        for key in ('video_generation_mode', 'scene_pipeline_version', 'revision', 'voice_path', 'scene_narrations'):
            self.assertEqual(original[key], job[key])
        self.assertEqual(saved['summary']['counts']['completed'], 3)
        self.assertEqual(saved['summary']['kept_indices'], [1, 2, 3])
        self.assertEqual(hashes, [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths])
        self.assertEqual([r['provider'] for r in plans.ordered_assets(self.folder, job, False)[:3]], ['google_flow', 'meta_ai', 'local'])
        review = story_review(self.folder, job)
        self.assertEqual([s['source'] for s in review['scenes'][:3]], ['flow', 'meta', 'local'])

    def test_plan_revision_separate_idempotent_and_stale_save_rejected(self):
        first = self.save()
        self.assertEqual(self.save()['revision'], first['revision'])
        job = self.manager.get(self.id)
        job['last_error'] = 'progress fixture'
        self.manager._save(job)
        second = self.save('google_flow', [5, 6], revision=1)
        self.assertEqual(second['revision'], 2)
        with self.assertRaisesRegex(ValueError, 'แผนวิดีโอเปลี่ยน'):
            self.save('google_flow', [4], revision=1)

    def test_stale_progress_preserves_new_plan_claim_and_completed_asset(self):
        stale_without_plan = self.manager.get(self.id)
        self.save('google_flow')
        old_plan = self.manager.get(self.id)
        plans.apply_at_safe_boundary(self.manager, self.id, 1)
        self.clip(1)
        plans.finish_scene(self.manager, self.id, 1)
        newest = self.manager.get(self.id)['scene_video_plan']
        for stale in (stale_without_plan, old_plan):
            stale['last_error'] = 'old worker progress'
            self.manager._save(stale)
            self.assertEqual(self.manager.get(self.id)['scene_video_plan'], newest)
            self.assertTrue(scene_asset(self.folder, self.manager.get(self.id), 1, 'flow').is_file())

    def test_old_global_action_cannot_change_opted_plan(self):
        job = self.save()['job']
        with self.assertRaisesRegex(ValueError, 'รายฉาก'):
            self.manager.set_video_generation_mode(self.id, 'meta_ai', job['revision'])
        self.assertEqual(self.manager.get(self.id), job)

    def test_claim_settings_snapshot_survives_future_revision(self):
        settings = {'model': 'Veo 3.1 - Lite [Lower Priority]', 'duration': '8s', 'resolution': '1080p', 'video_type': 'Frames'}
        self.save('google_flow', settings=settings)
        choice = plans.apply_at_safe_boundary(self.manager, self.id, 1)
        binding = plans.package_binding(choice['job'], 1)
        self.save('meta_ai', [1, 2], revision=1)
        job = self.manager.get(self.id)
        self.assertEqual(plans.package_binding(job, 1), binding)
        self.assertEqual(plans.provider_for(job, 1), 'google_flow')
        self.assertEqual(plans.provider_for(job, 2), 'meta_ai')
        self.assertTrue(plans.assert_binding(job, 1, binding))
        self.assertEqual(self.manager.flow_package(self.id, 1)['flow_settings'], {**settings, 'display': 'compact'})
        self.assertTrue(plans.summary(self.folder, job)['scenes'][0]['editable'])

    def test_active_original_result_accepts_once_and_future_legacy_rejected(self):
        saved = self.save(active_scene_indices=[1])
        self.assertEqual(saved['staged'], [1])
        self.assertTrue(self.manager.flow_package(self.id, 1)['scene_video_plan_legacy_active'])
        choice = plans.apply_at_safe_boundary(self.manager, self.id, 1)
        self.assertIsNone(choice['claim'])
        result = self.folder / 'videos' / 'download.mp4'
        result.parent.mkdir(exist_ok=True)
        result.write_bytes(b'new-flow-result' * 1024)
        self.manager.attach_flow_clip(self.id, 1, result)
        asset = plans.finish_scene(self.manager, self.id, 1)
        self.assertEqual(asset['provider'], 'google_flow')
        self.assertNotIn('pending', self.manager.get(self.id)['scene_video_plan']['scenes']['1'])
        with self.assertRaises(ValueError):
            self.manager.attach_flow_clip(self.id, 1, result)
        with self.assertRaises(ValueError):
            plans.assert_binding(self.manager.get(self.id), 2, None, allow_legacy_active=True)

    def test_unselected_current_scene_is_grandfathered(self):
        saved = self.save(indices=[3, 4], active_scene_indices=[1])
        self.assertTrue(plans.legacy_active(saved['job'], 1))
        self.assertEqual(plans.provider_for(saved['job'], 1), 'google_flow')

    def test_unknown_active_rechecks_receipt_before_promoting(self):
        self.save(unknown_active=True)
        self.ledger('meta_video_receipts.json', {'1': {'stage': 'generating', 'request_id': 'owned'}})
        current = plans.apply_at_safe_boundary(self.manager, self.id, 1)
        self.assertEqual(current['provider'], 'google_flow')
        self.assertIsNone(current['claim'])
        future = plans.apply_at_safe_boundary(self.manager, self.id, 2)
        self.assertEqual(future['provider'], 'meta_ai')
        self.assertTrue(future['claim'])

    def test_pending_download_receipt_is_not_failure(self):
        self.ledger('meta_video_receipts.json', {'1': {'stage': 'downloading', 'request_id': 'owned'}})
        saved = self.save()
        self.assertEqual(saved['staged'], [1])
        with self.assertRaises(ValueError):
            plans.retire_terminal(self.manager, self.id, 1, {'kind': 'timeout'})
        self.assertEqual(self.manager.get(self.id), saved['job'])

    def test_disconnected_flow_owner_is_durable_and_never_guessed_idle(self):
        (self.folder / 'logs').mkdir(exist_ok=True)
        log = self.folder / 'logs/flow_extension.jsonl'
        log.write_text(json.dumps({'shot_index': 1, 'run_id': 'owned-flow', 'step': 'generating',
                                   'page_excerpt': 'must never enter plan'}) + '\n', encoding='utf-8')
        saved = self.save()
        self.assertEqual(saved['staged'], [1])
        self.assertNotIn('page_excerpt', json.dumps(saved))
        self.assertEqual(plans.apply_at_safe_boundary(self.manager, self.id, 1)['provider'], 'google_flow')

    def test_native_retry_requires_exact_saved_proof_and_keeps_prior_asset(self):
        self.clip(1)
        segment = self.folder / 'videos/segment.mp4'
        segment.write_bytes(b'segment fixture' * 1024)
        sha = hashlib.sha256(segment.read_bytes()).hexdigest()
        self.ledger('scene_pipeline.json', {'1': {'phase': 'complete', 'segment': 'videos/segment.mp4',
                                                'segment_sha256': sha, 'voice': 'audio/kept.wav'}})
        job = self.save()['job']
        asset = job['scene_video_plan']['scenes']['1']['asset']
        job['flow_speech_retries'] = {'1': {'status': 'pending', 'retry_id': 'retry-fixture', 'segment_sha256': sha}}
        self.manager._save(job)
        with self.assertRaises(ValueError): plans.begin_native_retry(self.manager, self.id, 1, 'stale', sha)
        saved = plans.begin_native_retry(self.manager, self.id, 1, 'retry-fixture', sha)
        row = saved['scene_video_plan']['scenes']['1']
        self.assertEqual(row['asset_history'], [asset])
        self.assertEqual(segment.read_bytes(), b'segment fixture' * 1024)
        self.assertEqual(plans.begin_native_retry(self.manager, self.id, 1, 'retry-fixture', sha), saved)

    def test_confirmed_meta_terminal_can_reenter_without_erasing_old_receipt(self):
        self.save('meta_ai')
        first = plans.apply_at_safe_boundary(self.manager, self.id, 1)
        binding = plans.package_binding(first['job'], 1)
        meta = MetaVideoManager(self.manager)
        old = meta.begin(self.id, 1)
        receipt = meta.get(self.id, 1)
        receipt.update(stage='needs_attention', retry_exhausted=True, resume_stage='generating')
        self.ledger('meta_video_receipts.json', {'1': receipt})
        self.save('meta_ai', [1], revision=1, settings={'duration': '8s'})
        proof = {'terminal': True, 'busy': False, 'download_pending': False, 'kind': 'provider_failed',
                 'code': 'META_COMPLETED_NO_VIDEO', 'request_id': old['request_id']}
        with self.assertRaises(ValueError):
            plans.retire_terminal(self.manager, self.id, 1, {**proof, 'request_id': 'wrong'}, binding)
        plans.retire_terminal(self.manager, self.id, 1, proof, binding)
        self.assertEqual(meta.get(self.id, 1), receipt)
        plans.apply_at_safe_boundary(self.manager, self.id, 1)
        new = meta.begin(self.id, 1)
        self.assertNotEqual(new['request_id'], old['request_id'])
        archived = json.loads((self.folder / 'prompts/meta_video_receipts.json').read_text(encoding='utf-8'))
        self.assertEqual(archived['attempt_history']['1'][0], receipt)

    def test_confirmed_terminal_retires_exact_claim_preserving_history(self):
        self.save('google_flow')
        claimed = plans.apply_at_safe_boundary(self.manager, self.id, 1)
        binding = plans.package_binding(claimed['job'], 1)
        self.save('meta_ai', [1], revision=1)
        proof = {'terminal': True, 'busy': False, 'download_pending': False, 'kind': 'provider_failed', 'code': 'OWNED_TERMINAL_FIXTURE'}
        with self.assertRaises(ValueError):
            plans.retire_terminal(self.manager, self.id, 1, proof, {**binding, 'attempt_id': 'stale'})
        plans.retire_terminal(self.manager, self.id, 1, proof, binding)
        next_choice = plans.apply_at_safe_boundary(self.manager, self.id, 1)
        self.assertEqual(next_choice['provider'], 'meta_ai')
        row = next_choice['job']['scene_video_plan']['scenes']['1']
        self.assertEqual(row['attempt_history'][0]['claim']['attempt_id'], binding['attempt_id'])
        with self.assertRaises(ValueError):
            plans.assert_binding(next_choice['job'], 1, binding)

    def test_attach_exact_sha_and_binding_then_preserve_completed(self):
        self.save('google_flow')
        claimed = plans.apply_at_safe_boundary(self.manager, self.id, 1)
        binding = plans.package_binding(claimed['job'], 1)
        path = self.folder / 'videos' / 'result.mp4'
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b'owned result' * 1024)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        for kwargs in ({}, {'scene_video_plan': binding}, {'scene_video_plan': binding, 'expected_sha256': 'bad'}):
            with self.assertRaises(ValueError):
                self.manager.attach_flow_clip(self.id, 1, path, **kwargs)
        job = self.manager.attach_flow_clip(self.id, 1, path, scene_video_plan=binding, expected_sha256=sha)
        self.assertIn(binding['attempt_id'], job['flow_clips']['1'])
        plans.finish_scene(self.manager, self.id, 1)
        completed = self.manager.get(self.id)
        self.assertIsNone(plans.package_binding(completed, 1))
        self.assertTrue(plans.assert_binding(completed, 1, binding))
        with self.assertRaises(ValueError): plans.assert_binding(completed, 1, None)
        self.assertEqual(self.manager.attach_flow_clip(self.id, 1, path, scene_video_plan=binding, expected_sha256=sha), completed)
        path.write_bytes(b'other result' * 1024)
        with self.assertRaises(ValueError):
            self.manager.attach_flow_clip(self.id, 1, path, scene_video_plan=binding, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    def test_changed_content_invalidates_package_before_send(self):
        self.save('google_flow')
        plans.apply_at_safe_boundary(self.manager, self.id, 1)
        (self.folder / 'generated/scene_01.png').write_bytes(b'changed reference')
        with self.assertRaisesRegex(ValueError, 'ภาพหรือบทเปลี่ยน'):
            self.manager.flow_package(self.id, 1)

    def test_digest_cache_invalidates_and_corruption_never_becomes_pending(self):
        path = self.clip(1)
        job = self.save()['job']
        with patch.object(plans, '_uncached_digest', wraps=plans._uncached_digest) as digest:
            plans.summary(self.folder, job)
            first = digest.call_count
            plans.summary(self.folder, job)
            self.assertEqual(digest.call_count, first)
            path.write_bytes(b'changed-video' * 1024)
            summary = plans.summary(self.folder, job)
            self.assertGreater(digest.call_count, first)
        self.assertEqual(summary['scenes'][0]['state'], 'needs_review')
        self.assertNotIn(1, summary['remaining_indices'])

    def test_missing_or_ambiguous_completed_proof_blocks_save(self):
        path = self.clip(1)
        path.unlink()
        with self.assertRaises(ValueError): self.save()
        self.clip(1)
        self.clip(1, 'meta_ai')
        with self.assertRaises(ValueError): self.save()

    def test_completed_pipeline_missing_raw_is_review_not_resend(self):
        self.ledger('scene_pipeline.json', {'1': {'phase': 'complete', 'segment': 'videos/missing.mp4'}})
        summary = plans.summary(self.folder, self.manager.get(self.id))
        self.assertEqual(summary['scenes'][0]['state'], 'needs_review')
        with self.assertRaises(ValueError): self.save()

    def test_prompt_edits_do_not_revert_detailed_settings(self):
        settings = {'model': 'Veo 3.1 - Quality', 'duration': '8s', 'resolution': '1080p', 'video_type': 'Frames'}
        job = self.save('google_flow', settings=settings)['job']
        changed = save_prompt(self.manager, self.id, 2, 'Slow camera move for fixture.', 'old model', job['revision'])
        package = self.manager.flow_package(self.id, 2)
        self.assertIn('Slow camera move for fixture.', package['video_prompt'])
        self.assertEqual(package['flow_settings'], {**settings, 'display': 'compact'})
        self.assertEqual(story_review(self.folder, changed)['scenes'][1]['flow_model'], settings['model'])

    def test_meta_global_flow_selection_and_meta_plan_package(self):
        original = self.manager.get(self.id)
        original.update(video_generation_mode='meta_ai', meta_prompt_version=4, scene_pipeline_version=0)
        self.manager._save(original)
        self.save('google_flow', [2])
        plans.apply_at_safe_boundary(self.manager, self.id, 2)
        self.assertEqual(self.manager.flow_package(self.id, 2)['scene_video_plan']['provider'], 'google_flow')
        self.assertEqual(self.manager.get(self.id)['video_generation_mode'], 'meta_ai')
        self.save('meta_ai', [3], revision=1)
        plans.apply_at_safe_boundary(self.manager, self.id, 3)
        meta = MetaVideoManager(self.manager)
        package = meta.begin(self.id, 3)
        self.assertEqual(package['scene_video_plan']['provider'], 'meta_ai')
        self.assertEqual(package['meta_prompt_version'], 5)
        self.assertEqual(meta.get(self.id, 3)['scene_video_plan'], package['scene_video_plan'])
        with self.assertRaises(ValueError):
            meta.event({key: value for key, value in {**package, 'stage': 'uploading'}.items() if key != 'scene_video_plan'})
        self.assertEqual(meta.event({**package, 'stage': 'uploading'})['stage'], 'uploading')

    def test_meta_active_context_and_receipt_bytes_preserved(self):
        job = self.manager.get(self.id)
        job.update(video_generation_mode='meta_ai', meta_prompt_version=4)
        self.manager._save(job)
        meta = MetaVideoManager(self.manager)
        old = meta.begin(self.id, 1)
        for stage in ('uploading', 'ready_to_send', 'send_intent', 'submitted', 'generating'):
            meta.event({**old, 'stage': stage, **({'conversation_url': 'https://www.meta.ai/prompt/fixture'} if stage in {'submitted', 'generating'} else {})})
        before = (self.folder / 'prompts/meta_video_receipts.json').read_bytes()
        self.save('google_flow', active_scene_indices=[1])
        self.assertEqual(before, (self.folder / 'prompts/meta_video_receipts.json').read_bytes())
        now = meta.package(self.id, 1)
        self.assertEqual(now['context_id'], old['context_id'])
        self.assertTrue(now['scene_video_plan_legacy_active'])
        self.assertEqual(meta.event({**old, 'stage': 'generating'})['stage'], 'generating')
        with self.assertRaises(ValueError): meta.event({**old, 'stage': 'send_intent'})

    def test_mixed_final_checkpoint_requires_exact_ordered_provenance(self):
        self.clip(1)
        for index in range(2, 7): self.clip(index, 'meta_ai')
        job = self.save()['job']
        assets = plans.ordered_assets(self.folder, job)
        source = self.folder / 'videos/final.mp4'
        source.write_bytes(b'composite' * 1024)
        render = {'source_type': 'mixed_ai_story_composite', 'scene_video_sources': [
            {key: row[key] for key in ('index', 'provider', 'sha256')} for row in assets]}
        for bad in ({**render, 'source_type': 'google_flow_story_composite'}, {**render, 'scene_video_sources': list(reversed(render['scene_video_sources']))}):
            with self.assertRaises(ValueError): self.manager._save_video_checkpoint_locked(self.id, source, bad)
        saved = self.manager._save_video_checkpoint_locked(self.id, source, render)
        self.assertEqual(saved['video_source_type'], 'mixed_ai_story_composite')
        self.assertEqual(saved['render_plan']['flow_clip_count'], 1)
        self.assertEqual(saved['render_plan']['meta_clip_count'], 5)

    def test_capability_keeps_only_boolean_model_menu_observation(self):
        for value in (True, False):
            self.assertIs(flow_capabilities({'model_menu_open': value})['model_menu_open'], value)
        self.assertNotIn('model_menu_open', flow_capabilities({'model_menu_open': 'yes'}))

    def test_cancelled_plan_never_claims_new_scene(self):
        job = self.save()['job']
        job['cancel_requested'] = True
        self.manager._save(job)
        with self.assertRaises(ValueError): plans.apply_at_safe_boundary(self.manager, self.id, 1)

