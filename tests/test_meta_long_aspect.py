"""Long Meta contracts stay separate from saved 9:16 scene receipts."""
import base64
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core.meta_video import MetaVideoManager, meta_choice_offer, meta_safe_offer
from core.story_manager import StoryManager


def image_bytes(size, color):
    out = io.BytesIO()
    Image.new('RGB', size, color).save(out, format='PNG')
    return out.getvalue()


class MetaLongAspectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stories = StoryManager(self.temp.name)
        job = self.stories.create(topic='a train trip', scene_count=6,
                                  video_generation_mode='meta_ai')
        self.job_id = job['id']
        self.folder = self.stories._folder(self.job_id)
        self.image = self.folder / 'generated' / 'scene_01.png'
        self.image.write_bytes(image_bytes((1600, 900), 'blue'))
        job.update(scene_count=18, audio_choices={'mode': 'none'},
                   generated_images=[str(self.image.relative_to(self.folder))],
                   scene_prompts=['A train crosses a valley'], scene_narrations=['The journey begins'])
        self.stories._save(job)
        self.manager = MetaVideoManager(self.stories,
            lambda _: {'width': 1920, 'height': 1080, 'duration': 8})

    def long_job(self):
        job = self.stories.get(self.job_id)
        job['long_video'] = {'version': 2, 'aspect_ratio': '16:9', 'scene_count': 18,
                             'duration_seconds': 180, 'batch_size': 10,
                             'video_generation_mode': 'meta_ai'}
        job['aspect_ratio'] = '16:9'
        self.stories._save(job)

    def advance(self, end='downloading'):
        receipt = self.manager.begin(self.job_id, 1)
        body = dict(job_id=self.job_id, index=1, request_id=receipt['request_id'],
                    context_id=receipt['context_id'])
        for stage in ('uploading', 'ready_to_send', 'send_intent', 'submitted', 'generating',
                      'download_intent', 'downloading'):
            if stage == 'submitted': body['conversation_url'] = 'https://www.meta.ai/prompt/long-123'
            if stage == 'downloading': body['download_id'] = 42
            self.manager.event({**body, 'stage': stage})
            if stage == end:
                break
        return body

    def test_long_package_changes_context_but_short_prompt_and_receipt_stay_legacy(self):
        original = self.manager.package(self.job_id, 1)
        self.assertNotIn('aspect_ratio', original)
        self.assertIn('vertical 9:16', original['prompt'])
        self.long_job()
        long = self.manager.package(self.job_id, 1)
        self.assertEqual(long['aspect_ratio'], '16:9')
        self.assertIn('landscape 16:9', long['prompt'])
        self.assertNotIn('vertical 9:16', long['prompt'])
        self.assertNotEqual(original['context_id'], long['context_id'])
        self.assertEqual(self.manager.begin(self.job_id, 1)['context_id'], long['context_id'])
        job = self.stories.get(self.job_id)
        job.pop('long_video')
        self.stories._save(job)
        with self.assertRaisesRegex(ValueError, 'เปลี่ยนหลังเริ่มงาน'):
            self.manager.begin(self.job_id, 1)

    def test_long_source_and_download_must_be_16_by_9(self):
        self.long_job()
        self.image.write_bytes(image_bytes((1200, 800), 'red'))
        with self.assertRaisesRegex(ValueError, '16:9'):
            self.manager.package(self.job_id, 1)
        # 1600/950 is landscape, but outside the same ±.08 window used by MP4.
        self.image.write_bytes(image_bytes((1600, 950), 'red'))
        with self.assertRaisesRegex(ValueError, '16:9'):
            self.manager.package(self.job_id, 1)
        # 1600/940 is inside that window and remains a valid starting image.
        self.image.write_bytes(image_bytes((1600, 940), 'blue'))
        self.assertEqual(self.manager.package(self.job_id, 1)['aspect_ratio'], '16:9')
        self.image.write_bytes(image_bytes((1600, 900), 'blue'))
        body = self.advance()
        source = Path(self.temp.name) / 'result.mp4'
        source.write_bytes(b'video-fixture' * 200)
        self.manager.validator = lambda _: {'width': 720, 'height': 1280, 'duration': 8}
        with self.assertRaisesRegex(ValueError, '16:9'):
            self.manager.event({**body, 'stage': 'stored', 'filename': str(source)})
        self.assertEqual(self.manager.get(self.job_id, 1)['stage'], 'downloading')
        self.manager.validator = lambda _: {'width': 1920, 'height': 1080, 'duration': 8}
        result = self.manager.event({**body, 'stage': 'stored', 'filename': str(source)})
        self.assertEqual(result['stage'], 'stored')
        receipt = self.stories.get(self.job_id)['meta_clip_receipts']['1']
        self.assertEqual((receipt['aspect_ratio'], receipt['width'], receipt['height']),
                         ('16:9', 1920, 1080))

    def test_long_followup_and_redesign_keep_horizontal_aspect(self):
        self.long_job()
        options = ('Option 1: A static image. Option 2: A train moving gently through the valley. '
                   'Want me to generate that video?')
        self.assertIn('vertical 9:16', meta_choice_offer(options)['prompt'])
        self.assertIn('landscape 16:9', meta_choice_offer(options, '16:9')['prompt'])
        answer = ('I could not generate the video from this starting frame. '
                  'I can make a safer version with a wider framing. Want me to try?')
        self.assertIn('vertical 9:16', meta_safe_offer(answer)['prompt'])
        self.assertIn('landscape 16:9', meta_safe_offer(answer, '16:9')['prompt'])

        body = self.advance(end='generating')
        proof = dict(matched_request=True, answer_complete=True, answer_truncated=False,
                     stop=False, busy=False, video_count=0, samples=2, stable_ms=5000,
                     answer_text='The starting frame cannot be animated into a video.')
        prepared = self.manager.event({**body, 'stage': 'redesign_prepare',
                                       'retry_evidence': proof})
        self.assertIn('landscape 16:9', prepared['redesign']['request'])
        claim = self.manager.redesign_event(dict(job_id=self.job_id, index=1,
            request_id=prepared['request_id'], context_id=prepared['context_id'],
            redesign_id=prepared['redesign']['id'], action='claim'))
        self.assertTrue(claim['send_authorized'])
        proposal = dict(needs_review=False,
                        image_prompt='A fully clothed traveler in a wide scenic landscape.',
                        video_prompt='The train moves slowly across a valley with a smooth camera.')
        event = dict(job_id=self.job_id, index=1, request_id=prepared['request_id'],
                     context_id=prepared['context_id'], redesign_id=prepared['redesign']['id'],
                     action='save_image')
        portrait = 'data:image/png;base64,' + base64.b64encode(
            image_bytes((900, 1600), 'green')).decode()
        with self.assertRaisesRegex(ValueError, '16:9'):
            self.manager.redesign_event({**event, 'image': portrait})
        near_miss = 'data:image/png;base64,' + base64.b64encode(
            image_bytes((1600, 950), 'green')).decode()
        with self.assertRaisesRegex(ValueError, '16:9'):
            self.manager.redesign_event({**event, 'image': near_miss})
        landscape = 'data:image/png;base64,' + base64.b64encode(
            image_bytes((1600, 940), 'green')).decode()
        saved = self.manager.redesign_event({**event, 'image': landscape})
        self.assertEqual(saved['redesign']['phase'], 'image_saved')
        successor = self.manager.redesign_event({**event, 'action': 'save_prompt', 'proposal': proposal})
        self.assertEqual(successor['stage'], 'prepared')
        repaired = self.manager.package(self.job_id, 1)
        self.assertEqual(repaired['aspect_ratio'], '16:9')
        self.assertIn('landscape 16:9', repaired['prompt'])
        self.assertNotIn('vertical 9:16', repaired['prompt'])

    def test_extension_offer_prompts_match_desktop_in_both_aspects(self):
        script = Path(__file__).with_name('meta_long_aspect.cjs')
        result = subprocess.run(['node', str(script)], capture_output=True, text=True,
                                encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        values = json.loads(result.stdout)
        self.assertEqual(values['choiceShort']['prompt'],
                         meta_choice_offer(values['options'])['prompt'])
        self.assertEqual(values['choiceLong']['prompt'],
                         meta_choice_offer(values['options'], '16:9')['prompt'])
        self.assertEqual(values['safeShort']['prompt'],
                         meta_safe_offer(values['safer'])['prompt'])
        self.assertEqual(values['safeLong']['prompt'],
                         meta_safe_offer(values['safer'], '16:9')['prompt'])


if __name__ == '__main__':
    unittest.main()
