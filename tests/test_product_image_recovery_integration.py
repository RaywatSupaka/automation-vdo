import base64
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.product_image_recovery import ProductImageRecovery
from core.product_image_review import product_image_review, product_image_asset
from core.product_pipeline import ai_package_complete, product_ai_recovery_action, product_runtime_recovery_action
from test_product_image_recovery import encoded
import test_product_flow_fallback as flow_fixture


class ImageRecoveryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = ProductManager(Path(self.temp.name))
        job, _ = self.manager.import_product({'product_name': 'กล่องสินค้า', 'images': [], 'product_url': 'https://shopee.co.th/test'})
        self.id = job['id']
        self.folder = self.manager.root / self.id
        source = self.folder / 'original' / 'source.png'
        source.parent.mkdir(exist_ok=True)
        Image.new('RGB', (320, 500), 'white').save(source)
        job['source_images'] = ['original/source.png']
        self.manager._save_manifest_file(self.folder / 'job.json', job)
        self.manager.plugin_request(self.id)
        self.analysis = {'job_id': self.id, 'image_prompts': ['one', 'two', 'three'],
                         'flow_shot_prompts': ['shot one', 'shot two', 'shot three'],
                         'caption_short': 'กล่องสินค้า', 'spoken_script': 'มาดูสินค้ากัน', 'video_prompt': 'product'}
        self.recovery = ProductImageRecovery(self.manager, self.id)
        self.rev = self.recovery.start(self.analysis)['revision']

    def finish(self, index, status='succeeded', color='blue', donor=0):
        r = self.recovery.reserve(self.rev, index, 'RUN-1', f'request-{index}-{donor}', donor)
        return self.recovery.finish(self.rev, index, 'RUN-1', r['token'], status, encoded(color))

    def approve(self):
        return self.recovery.approve_existing_source('generated/selling_image_02.png', self.rev)

    def test_sparse_slots_keep_original_number_and_flow_is_forbidden_for_reuse(self):
        self.finish(1, 'failed'); self.finish(2); self.finish(3, 'failed')
        job = self.approve()
        self.assertEqual(len(job['generated_images']), 1)
        self.assertEqual(job['reused_image_count'], 2)
        self.assertEqual(job['flow_target_clip_count'], 3)
        self.assertEqual(job['composition_images'], ['generated/selling_image_02.png'] * 3)
        self.assertTrue(ai_package_complete(job, self.folder))
        self.assertEqual(self.manager.flow_package(self.id, 2)['source_image_index'], 2)
        for slot in (1, 3):
            with self.assertRaisesRegex(ValueError, 'USER_APPROVED_IMAGE_REUSE_CHECKPOINT'):
                self.manager.flow_package(self.id, slot)
        with self.assertRaises(ValueError): self.approve()

    def test_all_failed_can_use_original_without_inventing_ai_count(self):
        for i in (1, 2, 3): self.finish(i, 'failed')
        job = self.recovery.approve_existing_source('original/source.png', self.rev)
        self.assertEqual(job['generated_images'], [])
        self.assertEqual(job['ai_generated_image_count'], 0)
        self.assertEqual(job['reused_image_count'], 3)
        self.assertTrue(ai_package_complete(job, self.folder))
        self.assertEqual(job['flow_target_clip_count'], 3)

    def test_partial_or_late_result_cannot_replace_approved_fallback(self):
        self.finish(1, 'failed'); self.finish(2); self.finish(3, 'failed')
        self.approve()
        before = (self.folder / 'job.json').read_bytes()
        with self.assertRaises(ValueError):
            self.recovery.validate_result(dict(self.analysis, generated_images=[encoded('blue')] * 3))
        self.assertEqual(before, (self.folder / 'job.json').read_bytes())

    def test_real_bridge_commits_provenance_and_durable_duplicate_does_not_reset_clips(self):
        images = [encoded(c) for c in ('red', 'green', 'blue')]
        for i, color in enumerate(('red', 'green', 'blue'), 1): self.finish(i, color=color)
        payload = dict(self.analysis, generated_images=images)
        bridge = LocalBridge('127.0.0.1', 0, self.manager, logging.getLogger('recovery-integration'))
        result = bridge._accept_product_ai_result(payload)
        self.assertEqual(result['job']['ai_generated_image_count'], 3)
        self.assertEqual(result['job']['image_slot_origins']['2']['origin'], 'generated')
        video = self.folder / 'videos' / 'one.mp4'
        video.write_bytes(b'real-existing-clip-checkpoint')
        self.manager.attach_flow_clip(self.id, 1, video)
        before = (self.folder / 'job.json').read_bytes()
        restarted = LocalBridge('127.0.0.1', 0, self.manager, logging.getLogger('recovery-integration'))
        response = restarted._accept_product_ai_result(payload)
        self.assertTrue(response['duplicate'])
        self.assertIsNone(response['flow_command'])
        self.assertEqual(before, (self.folder / 'job.json').read_bytes())

    def test_preview_path_does_not_decode_every_image_or_expose_tokens(self):
        self.finish(1)
        review = product_image_review(self.manager, self.id)
        self.assertNotIn('token', json.dumps(review))
        with patch('core.product_image_review.select_source_images', side_effect=AssertionError('must not decode')):
            self.assertEqual(Path(product_image_asset(self.manager, self.id, 1)), self.folder / 'generated/selling_image_01.png')
        with self.assertRaises(ValueError): product_image_asset(self.manager, self.id, -1)
        with self.assertRaises(ValueError): product_image_asset(self.manager, '../outside', 0)

    def test_pending_and_modified_source_cannot_be_approved(self):
        self.recovery.reserve(self.rev, 1, 'RUN-1', 'request')
        with self.assertRaises(ValueError): self.recovery.approve_existing_source('original/source.png', self.rev)
        self.assertFalse(product_image_review(self.manager, self.id)['can_reuse'])

    def test_auto_recovery_never_restarts_image_stop_even_with_chrome_text(self):
        job = {'ai_status': 'ready', 'generated_images': ['one'], 'automation_status': 'error'}
        for code in ('AI_IMAGE_RECOVERY_STOP', 'AI_IMAGE_POLICY_BLOCKED', 'SOURCE_IMAGES_NEED_REVIEW', 'AI_IMAGE_REVISION_CHANGED'):
            self.assertEqual(product_ai_recovery_action(job, code + ' Chrome Extension timeout'), '')
            self.assertEqual(product_runtime_recovery_action(job, code + ' Chrome Extension timeout'), '')

    def test_user_fallback_local_render_uses_consented_source_and_provenance(self):
        self.finish(1, 'failed'); self.finish(2); self.finish(3, 'failed')
        self.approve()
        fixture = flow_fixture.ProductFlowFallbackRetirementTests()
        window = fixture._window(self.manager, None)
        def render(source, target, **kwargs):
            self.assertEqual(Path(source), self.folder / 'generated/selling_image_02.png')
            fixture._write_probable_mp4(target, 'local')
            return {'output': str(target)}
        with patch('ui.main_window.ProductImageVideoComposer') as composer:
            composer.return_value.render_motion_segment.side_effect = render
            output, plan = window._render_product_policy_fallback_segment(self.id, 1)
        job = self.manager.get_job(self.id)
        self.assertTrue(output.is_file())
        self.assertEqual(plan['source_type'], 'product_local_motion_user_image_reuse')
        self.assertEqual(job['flow_remote_clip_count'], 0)
        self.assertEqual(job['flow_local_motion_clip_count'], 1)
        self.assertEqual(job['flow_segment_provenance']['1']['failure_category'], 'user_approved_image_reuse')
