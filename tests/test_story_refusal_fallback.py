"""Temporary Story jobs only; confirmed refusal does not cause another provider request."""
import base64
import copy
import logging
import tempfile
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, Mock

from PIL import Image
from core.story_manager import StoryManager
from core.local_bridge import LocalBridge
from core.story_pipeline import story_recovery_action
from tests import test_story_content as fixtures


class StoryRefusalFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = StoryManager(self.temp.name)
        self.job = self.manager.create('จักรวาล: Marvel', 'ตัวละคร: Doctor Doom\nDoctor Doom เปิดประตูมิติแล้วกลับบ้าน', scene_count=6, visual_style='anime')
        self.ident = self.job['id']
        self.folder = self.manager._folder(self.ident)
        self.analysis = fixtures.StoryContentTests.analysis(self.job)
        self.manager.save_analysis_checkpoint(self.ident, self.analysis)
        self.images = []
        for index in range(1, 6):
            stream = BytesIO()
            Image.new('RGB', (96, 160), (index * 35, 50, 90)).save(stream, 'PNG')
            encoded = base64.b64encode(stream.getvalue()).decode('ascii')
            self.manager.save_partial_image(self.ident, index, encoded)
            self.images.append(encoded)

    def fallback(self):
        return self.manager.save_refused_image_fallback(self.ident, 6, 5, 'Provider refused the image')

    def result(self, fallback):
        return {**copy.deepcopy(self.analysis), 'generated_images': self.images + [fallback['image']],
                'story_image_fallbacks': {'6': fallback['metadata']}}

    def test_preserves_successful_files_and_finishes_image_set(self):
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in (self.folder / 'generated').glob('*.png')}
        fallback = self.fallback()
        result = self.manager.apply_ai_result(self.result(fallback))
        self.assertEqual(len(result['generated_images']), 6)
        self.assertEqual(result['story_image_fallback_count'], 1)
        self.assertEqual(result['scene_prompts'], self.analysis['scene_prompts'])
        for name, original in before.items():
            path = self.folder / 'generated' / name
            self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), original)

    def test_idempotent_retry_same_copy_without_generation(self):
        first = self.fallback()
        path = self.folder / 'generated/scene_06.png'
        stamp = path.stat().st_mtime_ns
        self.assertEqual(self.fallback(), first)
        self.assertEqual(path.stat().st_mtime_ns, stamp)

    def test_legacy_262_receipt_without_excerpt_reuses_without_fabricated_quote(self):
        proof = {'original_run_id': 'RUN-LEGACY-262', 'review_revision': 0, 'created_at': time.time() * 1000}
        bridge = LocalBridge('127.0.0.1', 0, Mock(), logging.getLogger('legacy-fallback-test'), stories=self.manager)
        bridge._extension_runs[('ai', self.ident, 0)] = {'run_id': 'RUN-RESUME-263'}
        result = bridge._accept_story_image_fallback({'job_id': self.ident, 'run_id': 'RUN-RESUME-263',
            'provider': 'chatgpt', 'reason': 'STORY_IMAGE_REFUSED', 'policy': 'reuse_saved_local_v1',
            'index': 6, 'source_index': 5, 'response_excerpt': '', 'receipt_proof': proof})
        self.assertFalse(result['metadata']['response_excerpt_available'])
        self.assertEqual(result['metadata']['response_excerpt'], '')
        self.assertEqual(result['metadata']['receipt_proof'], proof)
        self.manager.apply_ai_result(self.result(result))

    def test_pending_intent_recovers_after_copy_failure(self):
        original = Path.write_bytes
        def fail(target, payload):
            if str(target).endswith('.fallback.partial'):
                raise OSError('simulated disk full')
            return original(target, payload)
        with patch.object(Path, 'write_bytes', fail), self.assertRaises(OSError):
            self.fallback()
        self.assertEqual(self.manager.get(self.ident)['story_image_fallbacks']['6']['status'], 'pending')
        self.assertEqual(self.fallback()['metadata']['status'], 'ready')

    def test_never_overwrites_successful_target(self):
        self.manager.save_partial_image(self.ident, 6, self.images[0])
        with self.assertRaises(ValueError):
            self.fallback()

    def test_rejects_first_scene_bad_source_or_empty_evidence(self):
        for index, source, excerpt in [(1, 1, 'refused'), (6, 0, 'refused'), (6, 5, '')]:
            with self.assertRaises(ValueError):
                self.manager.save_refused_image_fallback(self.ident, index, source, excerpt)

    def test_flow_drama_and_cancel_are_not_automatic_fallback(self):
        original = self.manager.get(self.ident)
        for change in [{'video_generation_mode':'google_flow'}, {'job_type':'drama_episode'}, {'cancel_requested':True}]:
            self.manager._save({**original, **change})
            with self.assertRaises(ValueError):
                self.fallback()

    def test_fallback_and_donor_cannot_be_replaced_or_discarded(self):
        self.fallback()
        for index in (5, 6):
            with self.assertRaises(ValueError):
                self.manager.save_partial_image(self.ident, index, self.images[0])
            with self.assertRaises(ValueError):
                self.manager.discard_partial_image(self.ident, index)

    def test_final_forgery_rejected_before_any_file_writes(self):
        fallback = self.fallback()
        result = self.result(fallback)
        result['generated_images'][0] = self.images[1]
        before = (self.folder / 'generated/scene_01.png').read_bytes()
        with self.assertRaises(ValueError):
            self.manager.apply_ai_result(result)
        self.assertEqual((self.folder / 'generated/scene_01.png').read_bytes(), before)
        result = self.result(fallback)
        result.pop('story_image_fallbacks')
        with self.assertRaises(ValueError):
            self.manager.apply_ai_result(result)

    def test_switching_to_flow_cannot_expose_reused_image(self):
        fallback = self.fallback()
        job = self.manager.apply_ai_result(self.result(fallback))
        self.manager._save({**job, 'video_generation_mode': 'google_flow'})
        with self.assertRaisesRegex(ValueError, 'สำรอง'):
            self.manager.flow_package(self.ident, 6)

    def test_cancellation_keeps_provenance_and_rejects_late_fallback(self):
        fallback = self.fallback()
        cancelled = self.manager.mark_cancelled(self.ident)
        self.assertEqual(cancelled['story_image_fallbacks']['6'], fallback['metadata'])
        with self.assertRaises(ValueError):
            self.fallback()

    def test_unconfirmed_fallback_never_reopens_automation(self):
        self.assertEqual(story_recovery_action(self.job, 'STORY_IMAGE_FALLBACK_REVIEW • missing receipt'), '')

    def test_pending_fallback_prompt_is_not_editable(self):
        fallback = self.fallback()
        target = self.folder / 'generated/scene_06.png'
        target.unlink()
        job = self.manager.get(self.ident)
        job['story_image_fallbacks']['6']['status'] = 'pending'
        job['partial_generated_images'] = job['partial_generated_images'][:-1]
        job['status'] = 'error'
        self.manager._save(job)
        job = self.manager.get(self.ident)
        with self.assertRaises(ValueError):
            self.manager.save_scene_prompt(self.ident, 6, self.analysis['scene_prompts'][5] + ' updated', job['revision'])
        self.assertEqual(self.fallback()['metadata']['image_sha256'], fallback['metadata']['image_sha256'])


if __name__ == '__main__':
    unittest.main()
