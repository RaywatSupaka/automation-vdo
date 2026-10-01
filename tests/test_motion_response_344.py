import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from core.atomic_json import AtomicJsonFile
from core.flow_motion_plan import motion_plan_action, plan_context, saved_motion_prompt

ROOT = Path(__file__).resolve().parents[1]


class MotionResponse344Tests(unittest.TestCase):
    def test_actual_stream_completion_and_passive_resume(self):
        node = shutil.which('node')
        self.assertIsNotNone(node)
        result = subprocess.run([node, str(ROOT / 'tests/motion_response_344_harness.js')],
                                cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])

    def test_real_request_extension_parser_and_backend_recover_scene_ten_without_resend(self):
        # The Node fixture invokes the real Extension parser/Resume path with
        # this production-generated request. Replay every recorded RPC against
        # the real backend in a temporary job, never the user's running bridge.
        for provider in ('chatgpt', 'gemini'):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                (folder / 'generated').mkdir()
                images = []
                for index in range(1, 11):
                    relative = f'generated/scene_{index:02d}.png'
                    Image.new('RGB', (288, 512), (index, 30, 70)).save(folder / relative)
                    images.append(relative)
                job = dict(id='STORY-344-FIXTURE', image_ai_provider=provider, scene_count=10,
                           scene_prompts=['Starting frame of the traveler by the city path'] * 10,
                           scene_narrations=['The traveler leaves the city without accepting a reward'] * 10,
                           generated_images=images, video_generation_mode='google_flow')
                original_job = json.dumps(job, sort_keys=True)
                media = {relative: (folder / relative).read_bytes() for relative in images}
                store = AtomicJsonFile(folder / 'prompts/flow_motion_plans.json')
                ready = {}
                for index in range(1, 10):
                    current = plan_context(folder, job, index)
                    ready[current['context_id']] = dict(phase='ready', context=current,
                                                       prompt=f'Preserved ready scene {index}')
                store.write({'schema': 1, 'plans': ready})
                context = plan_context(folder, job, 10)

                def call(action, **extra):
                    return motion_plan_action(folder, job, dict(action=action, provider=provider, index=10,
                                                               context_id=context['context_id'], **extra))

                request = call('status')['visual_request']
                self.assertIn('STARTING FRAME', request)
                self.assertIn('review_reason', request)
                call('prepare', request=request)
                call('mark_sending')
                partial = '{\n"job_id":_'
                call('review_text', answer_text=partial)
                record = call('status')['record']
                answer = dict(job_id=job['id'], index=10, context_id=context['context_id'],
                    prompt='Vertical 9:16, one video. The traveler pauses, turns naturally on the path, and walks away from the city without a reward. The camera stays beside the path. All spoken dialogue must be in Thai only.',
                    needs_review=False, reference_compatible=True, material_change=False,
                    review_reason='A natural turn preserves the departure event and uses the image as the starting frame.')
                packet = dict(context={**context, 'image_url':'http://fixture.invalid/scene.png'},
                              provider=provider, request=request, record=record, result=answer)
                result = subprocess.run([shutil.which('node'), str(ROOT / 'tests/motion_response_344_harness.js'), '--packet'],
                    input=json.dumps(packet, ensure_ascii=False), cwd=ROOT, capture_output=True,
                    text=True, encoding='utf-8', timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                observed = json.loads(result.stdout)
                self.assertEqual(observed['sends'], 0)
                self.assertGreater(observed['reads'], 0)
                self.assertEqual([message['action'] for message in observed['messages']],
                                 ['status', 'prepare', 'review', 'save'])
                for message in observed['messages']:
                    response = motion_plan_action(folder, job, message)
                    self.assertTrue(response['ok'])
                    if message['action'] == 'review':
                        self.assertEqual(response['validation']['errors'], [])
                final = call('status')['record']
                self.assertEqual(final['phase'], 'ready')
                self.assertEqual(final['prior_invalid_answer_text'], partial)
                self.assertEqual(final['result'], answer)
                self.assertFalse(final.get('format_attempt'))
                self.assertFalse(final.get('story_visual_repair'))
                self.assertIn('walks away from the city', saved_motion_prompt(folder, job, 10, images[-1]))
                data = store.read({})['plans']
                self.assertEqual({key: data[key] for key in ready}, ready)
                self.assertEqual({relative: (folder / relative).read_bytes() for relative in images}, media)
                self.assertEqual(json.dumps(job, sort_keys=True), original_job)
                self.assertEqual(len(list((folder / 'generated').iterdir())), 10)
