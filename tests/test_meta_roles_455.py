"""Offline contracts for new Meta role separation and legacy receipt identity."""
import base64
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core.atomic_json import AtomicJsonFile
from core.creation_queue import CreationQueue
from core.media_audio import flow_audio_instruction
from core.meta_prompt import compliant_video_instruction
from core.meta_video import MetaVideoManager, digest
from core.story_manager import StoryManager


LINE = 'คืนนั้นพี่กลับมาชุ่มฝน เขาพูดแค่ว่า ขอโทษ แล้วเดินไปจัดชุดกู้ภัย'
VISUAL = 'An adult rescuer stands beside a rain-wet doorway and a rescue jacket.'
MOTION = 'The rescuer hangs the wet jacket, then turns toward the rescue equipment. Slow camera push.'


class MetaRoles455Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stories = StoryManager(self.temp.name)
        self.job = self.stories.create(topic='A rescuer returns home', scene_count=6,
            video_generation_mode='meta_ai', storytelling_options={'version': 1, 'mode': 'narrator'})
        self.folder = self.stories._folder(self.job['id'])
        image = self.folder / 'generated' / 'scene_01.png'
        image.write_bytes(b'owned-synthetic-image')
        self.job.update(scene_count=1, generated_images=[image.relative_to(self.folder).as_posix()],
            scene_prompts=[VISUAL], scene_narrations=[LINE],
            audio_choices={'mode': 'flow_original', 'subtitle': False})
        self.stories._save(self.job)
        self.manager = MetaVideoManager(self.stories, lambda _: {})

    def package(self, **changes):
        self.job.update(changes)
        self.stories._save(self.job)
        return self.manager.package(self.job['id'], 1)

    def checkpoint(self, **changes):
        value = {'job_id': self.job['id'], 'scene_prompts': [VISUAL],
                 'scene_narrations': [LINE], 'flow_shot_prompts': [MOTION]}
        value.update(changes)
        AtomicJsonFile(self.folder / 'prompts' / 'ai_analysis_checkpoint.json').write(value)

    def test_new_narrator_uses_saved_motion_not_quoted_narration(self):
        self.checkpoint()
        package = self.package()
        self.assertIn('\nAction: ' + MOTION, package['prompt'])
        self.assertNotIn('\nAction: ' + LINE, package['prompt'])
        self.assertIn('off-screen narrator', package['audio_instruction'])
        self.assertIn('Characters remain silent', package['audio_instruction'])
        self.assertEqual(package['prompt'].count(LINE), 1)
        self.assertEqual(package['scene_value'], MOTION)

    def test_new_contract_saved_at_create_and_enqueue(self):
        self.assertEqual(self.job['meta_prompt_version'], 5)
        queue = CreationQueue(self.temp.name)
        queue.enqueue('story', ['new'], video_generation_mode='meta_ai')
        self.assertEqual(CreationQueue(self.temp.name).snapshot()['items'][0]['settings']['meta_prompt_version'], 5)
        queue.enqueue('story', ['legacy'], video_generation_mode='meta_ai', settings={'meta_prompt_version': 4})
        self.assertEqual(queue.snapshot()['items'][1]['settings']['meta_prompt_version'], 4)

    def test_missing_or_wrong_plan_uses_visual_motion_without_narration(self):
        for changes in (None, {'job_id': 'OTHER'}, {'scene_prompts': ['different scene']},
                        {'flow_shot_prompts': [MOTION, 'extra']}, {'flow_shot_prompts': [LINE]}):
            with self.subTest(changes=changes):
                if changes is not None:
                    self.checkpoint(**changes)
                package = self.package()
                self.assertNotIn(LINE, package['scene_value'])
                self.assertNotEqual(package['scene_value'], MOTION)
                self.assertIn('starting image', package['scene_value'])

    def test_manifest_motion_is_preserved_without_checkpoint(self):
        package = self.package(flow_shot_prompts=[MOTION])
        self.assertEqual(package['scene_value'], MOTION)

    def test_legacy_v4_prompt_and_hash_are_exact_and_receipt_is_reused(self):
        self.checkpoint()
        package = self.package(meta_prompt_version=4)
        audio = ('Generate this video with its original audible soundtrack. '
                 'All spoken dialogue must be in Thai only. No background music. '
                 '\nAUDIO: Include clear natural Thai speech for this scene. No subtitles or captions burned into the picture. Spoken line: ' + LINE)
        expected = ('Create exactly one playable vertical 9:16 video using the attached image as visual reference and, when suitable, the first frame. '
                    'Keep its characters, product and setting. Animate the described action with subtle background motion '
                    'and one smooth camera move; no text or watermark. ' + audio + '\nScene: ' + VISUAL + '\nAction: ' + LINE
                    + '\nReturn the actual video, not options or an explanation. If unavailable, report that truthfully.'
                    + '\nGeneration instruction: ' + compliant_video_instruction())
        self.assertEqual(package['prompt'], expected)
        self.assertEqual(package['context_id'], hashlib.sha256((self.job['id'] + ':1:' + digest(Path(package['image_path'])) + ':' + expected).encode()).hexdigest())
        receipt = self.manager.begin(self.job['id'], 1)
        before = (self.folder / 'prompts' / 'meta_video_receipts.json').read_bytes()
        self.assertEqual(self.manager.begin(self.job['id'], 1), receipt)
        self.assertEqual((self.folder / 'prompts' / 'meta_video_receipts.json').read_bytes(), before)

    def test_shared_flow_audio_legacy_bytes_do_not_change(self):
        job = {**self.job, 'video_generation_mode': 'google_flow'}
        job.pop('meta_prompt_version', None)
        expected = '\nAUDIO: Include clear natural Thai speech for this scene. No subtitles or captions burned into the picture. Spoken line: ' + LINE
        self.assertEqual(flow_audio_instruction(job, 1), expected)
        self.assertEqual(flow_audio_instruction({**job, 'meta_prompt_version': 4}, 1), expected)

    def test_api_and_none_never_generate_narrator_or_use_narration_as_motion(self):
        for mode, keep in [('api', False), ('api', True), ('none', False)]:
            with self.subTest(mode=mode, keep=keep):
                package = self.package(audio_choices={'mode': mode, 'keep_video_audio': keep})
                self.assertNotIn(LINE, package['prompt'])
                self.assertNotIn('Voiceover text:', package['audio_instruction'])
                self.assertIn('No speech', package['audio_instruction'] if keep else package['audio_instruction'].replace('No music, speech', 'No speech'))

    def test_product_reviewer_keeps_on_camera_delivery(self):
        package = self.package(product_short=True, product_presentation_version=1, storytelling_options=None)
        self.assertIn('visible reviewer speaks Thai directly to camera', package['audio_instruction'])
        self.assertNotIn('off-screen narrator reads', package['audio_instruction'])
        self.assertNotIn(LINE, package['scene_value'])

    def test_solo_dialogue_visual_keep_the_saved_performance(self):
        for mode in ['solo', 'dialogue', 'visual']:
            with self.subTest(mode=mode):
                turns = [] if mode == 'visual' else [{'speaker': 'พี่', 'listener': 'น้อง', 'text': 'กลับมาแล้ว', 'action': 'turns'}]
                package = self.package(actor_dialogue=True, storytelling_options={'version': 1, 'mode': mode},
                    scene_dialogue_turns=[turns], character_bible=[{'name': 'พี่'}, {'name': 'น้อง'}], scene_narrations=[MOTION])
                self.assertEqual(package['scene_value'], MOTION)
                self.assertIn('VISUAL ONLY:' if mode == 'visual' else 'ACTOR DIALOGUE:', package['audio_instruction'])
                self.assertNotIn('off-screen narrator reads', package['audio_instruction'])

    def test_new_redesign_request_separates_visual_motion_and_audio(self):
        self.checkpoint()
        package = self.package()
        request = self.manager._redesign_prompt_request(package, {'image_sha256': 'a' * 64})
        self.assertIn('visible motion only', request)
        self.assertIn('off-screen narrator', request)
        self.assertEqual(package['scene_value'], MOTION)

    def redesign_ready(self):
        self.checkpoint()
        package = self.package()
        receipt = self.manager.begin(self.job['id'], 1)
        body = dict(job_id=self.job['id'], index=1, request_id=receipt['request_id'], context_id=receipt['context_id'])
        for stage in self.manager.STAGES[1:]:
            if stage == 'submitted':
                body['conversation_url'] = 'https://www.meta.ai/prompt/roles-455'
            self.manager.event({**body, 'stage': stage})
            if stage == 'generating':
                break
        receipt = self.manager.event({**body, 'stage': 'redesign_prepare', 'retry_evidence': {
            'matched_request': True, 'answer_complete': True, 'answer_truncated': False,
            'stop': False, 'busy': False, 'video_count': 0, 'samples': 2, 'stable_ms': 6000,
            'answer_text': 'ขออภัย ดูเหมือนว่าทางฝั่งของฉันจะเกิดปัญหาบางอย่าง โปรดลองอีกครั้ง'}})
        body['redesign_id'] = receipt['redesign']['id']
        self.manager.redesign_event({**body, 'action': 'claim'})
        out = io.BytesIO()
        Image.new('RGB', (360, 640), 'blue').save(out, format='PNG')
        self.manager.redesign_event({**body, 'action': 'save_image',
            'image': 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()})
        return body, package

    def test_redesign_saves_clean_audio_once_and_resumes_same_successor(self):
        body, original = self.redesign_ready()
        proposal = {'needs_review': False, 'video_prompt': 'The rescuer turns to the window; a slow camera pan follows.'}
        next_scene = self.manager.redesign_event({**body, 'action': 'save_prompt', 'proposal': proposal})
        package = self.manager.package(self.job['id'], 1)
        self.assertEqual(package['audio_instruction'], original['audio_instruction'])
        self.assertEqual(package['prompt'].count(LINE), 1)
        self.assertNotIn('Saved story/dialogue context:', package['prompt'])
        self.assertIn('Saved visual action: ' + MOTION, package['prompt'])
        self.assertEqual(self.manager.redesign_event({**body, 'action': 'save_prompt', 'proposal': proposal}), next_scene)
        self.assertEqual(self.manager.begin(self.job['id'], 1)['context_id'], next_scene['context_id'])

    def test_redesign_rejects_narration_as_motion_keeps_saved_new_image(self):
        body, _ = self.redesign_ready()
        path = self.folder / 'prompts' / 'meta_video_receipts.json'
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'ผู้บรรยาย'):
            self.manager.redesign_event({**body, 'action': 'save_prompt',
                'proposal': {'needs_review': False, 'video_prompt': 'Action: ' + LINE}})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.manager.get(self.job['id'], 1)['redesign']['phase'], 'image_saved')

    def test_generated_music_keeps_one_narrator_and_saved_selection(self):
        from core.generated_music import freeze_plan, MARKER
        for mode in ['api', 'flow_original']:
            with self.subTest(mode=mode):
                self.job.update(audio_choices={'mode': mode, 'keep_video_audio': mode == 'api'},
                    generated_music_options={'version': 1, 'enabled': True, 'frequency': 'moderate', 'mood': 'auto'})
                freeze_plan(self.job)
                package = self.package()
                self.assertEqual(package['prompt'].count(MARKER), 1)
                self.assertNotIn('No background music.', package['prompt'])
                self.assertEqual(package['prompt'].count(LINE), 1 if mode == 'flow_original' else 0)
                before = (self.folder / 'job.json').read_bytes()
                self.assertEqual(self.manager.package(self.job['id'], 1)['context_id'], package['context_id'])
                self.assertEqual((self.folder / 'job.json').read_bytes(), before)

    def test_long_api_and_native_preserve_landscape_and_role(self):
        Image.new('RGB', (640, 360), 'blue').save(self.folder / 'generated' / 'scene_01.png')
        for mode in ['api', 'flow_original']:
            with self.subTest(mode=mode):
                package = self.package(long_video={'version': 2}, audio_choices={'mode': mode},
                    flow_shot_prompts=[MOTION])
                self.assertEqual(package['aspect_ratio'], '16:9')
                self.assertIn('landscape 16:9', package['prompt'])
                self.assertNotIn('vertical 9:16', package['prompt'])
                self.assertEqual(package['scene_value'], MOTION)
                self.assertEqual(package['prompt'].count(LINE), 1 if mode == 'flow_original' else 0)

    def test_drama_narrator_and_api_actor_keep_distinct_audio(self):
        package = self.package(job_type='drama_episode')
        self.assertIn('off-screen narrator', package['audio_instruction'])
        package = self.package(actor_dialogue=True, storytelling_options={'version': 1, 'mode': 'dialogue'},
            audio_choices={'mode': 'api'}, scene_narrations=[MOTION],
            scene_dialogue_turns=[[{'speaker': 'พี่', 'listener': 'น้อง', 'text': 'กลับมาแล้ว'}]],
            character_bible=[{'name': 'พี่'}, {'name': 'น้อง'}])
        self.assertNotIn('กลับมาแล้ว', package['prompt'])
        self.assertIn('narration is added separately', package['audio_instruction'])
        self.assertEqual(package['scene_value'], MOTION)

    def test_short_film_motion_is_action_and_native_audio_is_saved_dialogue(self):
        from tests.test_product_film_395 import OPTIONS
        scene = {'roles': ['hook', 'setup'], 'action': MOTION, 'speaker': 'พี่', 'listener': 'น้อง',
                 'spoken_text': 'กลับมาแล้ว', 'product_visible': False, 'facts_used': []}
        package = self.package(product_short=True, product_presentation_version=1, storytelling_options=None,
            product_script_options=OPTIONS, product_film_plan={'version': 1, 'scenes': [scene]},
            scene_narrations=['กลับมาแล้ว'])
        self.assertEqual(package['scene_value'], MOTION)
        self.assertIn('SHORT FILM AUDIO:', package['audio_instruction'])
        self.assertNotIn('off-screen narrator reads', package['audio_instruction'])
        self.assertIn('Spoken line: "กลับมาแล้ว"', package['audio_instruction'])

    def test_visual_saved_mode_without_actor_flag_has_no_narrator(self):
        package = self.package(actor_dialogue=False, storytelling_options={'version': 1, 'mode': 'visual'},
            scene_narrations=[MOTION], scene_dialogue_turns=[[]])
        self.assertIn('VISUAL ONLY:', package['audio_instruction'])
        self.assertNotIn('NARRATOR AUDIO:', package['audio_instruction'])

    def test_empty_native_narration_does_not_invent_speech(self):
        package = self.package(scene_narrations=[''])
        self.assertIn('No narration is saved', package['audio_instruction'])
        self.assertIn('Characters remain silent', package['audio_instruction'])

    def test_checkpoint_motion_lookup_is_read_only_even_when_backup_exists(self):
        self.checkpoint()
        path = self.folder / 'prompts' / 'ai_analysis_checkpoint.json'
        AtomicJsonFile(path).write(json.loads(path.read_text(encoding='utf-8')))
        before = {file.name: file.read_bytes() for file in path.parent.iterdir() if file.is_file()}
        package = self.manager.package(self.job['id'], 1)
        self.assertEqual(package['scene_value'], MOTION)
        self.assertEqual({file.name: file.read_bytes() for file in path.parent.iterdir() if file.is_file()}, before)

    def test_analysis_and_final_ingress_preserve_motion_only_for_new_contract(self):
        out = io.BytesIO()
        Image.new('RGB', (360, 640), 'green').save(out, format='PNG')
        result = dict(job_id=self.job['id'], video_title='เรื่องพี่', video_description='คำอธิบาย',
            narration_script=LINE, scene_narrations=[LINE], scene_prompts=[VISUAL], scene_durations=[5],
            visual_bible={}, flow_shot_prompts=[MOTION],
            generated_images=['data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()])
        self.job.pop('story_content_contract', None)
        for version in [4, 5]:
            for ingress in [self.stories.save_analysis_checkpoint, self.stories.apply_ai_result]:
                with self.subTest(version=version, ingress=ingress.__name__):
                    self.job.pop('flow_shot_prompts', None)
                    self.package(meta_prompt_version=version)
                    if ingress.__name__ == 'save_analysis_checkpoint':
                        saved = ingress(self.job['id'], result)
                    else:
                        saved = ingress(result)
                    self.assertEqual(saved.get('flow_shot_prompts'), [MOTION] if version == 5 else None)


if __name__ == '__main__':
    unittest.main()
