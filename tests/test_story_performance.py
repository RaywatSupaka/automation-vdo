import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.story_manager import StoryManager
from core.story_performance import validate_option, validate_plan, audio_instruction, composition_choices
from core.media_audio import flow_audio_instruction
from core.creation_queue import CreationQueue
from core.flow_motion_plan import plan_context
from core.story_visual_plan import motion_request
from core.scene_context_revision import revised_story


class StoryPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manager = StoryManager(self.temp.name)
        self.job = self.manager.create('เพื่อนตามหากุญแจ', scene_count=6, video_generation_mode='google_flow', actor_dialogue=True)
        self.folder = self.manager._folder(self.job['id'])
        self.plan = dict(job_id=self.job['id'], video_title='กุญแจอยู่ไหน', video_description='เรื่องของเพื่อน',
            narration_script='บทที่ถูกแทนด้วยบทสนทนา', visual_bible={},
            story_entities=[{'id':'a','name':'มะลิ','visual_identity':'หญิงเสื้อสีฟ้า'}, {'id':'b','name':'ต้น','visual_identity':'ชายเสื้อสีเขียว'}], scene_entities=[['a','b']]*6,
            character_bible=[{'name':'มะลิ','appearance':'หญิงเสื้อสีฟ้า'}, {'name':'ต้น','appearance':'ชายเสื้อสีเขียว'}],
            scene_prompts=['มะลิ และ ต้น ยืนมองกันหน้าประตู มะลิใส่เสื้อสีฟ้า ต้นใส่เสื้อสีเขียว มือถือกุญแจ ภาพแนวตั้ง']*6,
            scene_narrations=['เพื่อนสองคนมองหากุญแจที่ประตู']*6, scene_durations=[6]*6,
            scene_dialogue_turns=[[{'speaker':'มะลิ','listener':'ต้น','text':'เห็นกุญแจไหม'},
                                   {'speaker':'ต้น','listener':'มะลิ','text':'อยู่ตรงนี้ไง'}], [], [], [], [], []])

    def test_request_is_acting_not_narrator_cta(self):
        prompt = (self.folder/'prompts/chatgpt_request.txt').read_text(encoding='utf-8')
        request = json.loads((self.folder/'ai_request.json').read_text(encoding='utf-8'))
        self.assertIn('ACTOR STORY MODE:', prompt)
        self.assertNotIn('2. เขียน narration_script ภาษาไทยสำหรับ AI Voice', prompt)
        self.assertNotIn('6. ฉากสุดท้ายต้องปิดเรื่อง', prompt)
        self.assertNotIn('or ผู้บรรยาย', prompt)
        self.assertIn('character_bible', request['required_fields'])
        self.assertIn('scene_dialogue_turns', request['required_fields'])
        self.assertIn('CONVERSATION ONLY:', prompt)
        self.assertIn('No subtitles, captions', prompt)

    def test_conversation_contract_and_legacy_subtitle_preservation(self):
        self.assertEqual(self.job['actor_dialogue_version'], 2)
        job = self.manager.save_analysis_checkpoint(self.job['id'], self.plan)
        job['audio_choices'].update(subtitle=True, keep_video_audio=True)
        choices = composition_choices(job)
        self.assertFalse(choices['subtitle'])
        self.assertFalse(choices['keep_video_audio'])
        self.assertTrue(job['audio_choices']['subtitle'])
        job.pop('actor_dialogue_version')
        self.assertTrue(composition_choices(job)['subtitle'])

    def test_conversation_rejects_monologue_missing_listener_and_reading_beat(self):
        for variant in ['monologue', 'listener', 'beat']:
            plan = copy.deepcopy(self.plan)
            if variant == 'monologue': plan['scene_dialogue_turns'][0].pop()
            if variant == 'listener': plan['scene_dialogue_turns'][0][0].pop('listener')
            if variant == 'beat': plan['scene_dialogue_turns'][0][0]['text'] = plan['scene_narrations'][0]
            with self.subTest(variant=variant), self.assertRaisesRegex(ValueError, 'ACTOR_PLAN_REVIEW'):
                validate_plan(self.job, plan)

    def test_final_conversation_bypasses_transcription_and_subtitle_render(self):
        from core.story_finisher import finish_story_media
        from unittest.mock import Mock
        job = self.manager.save_analysis_checkpoint(self.job['id'], self.plan)
        job['audio_choices'].update(subtitle=True, music=False, sfx=False)
        self.manager._save(job)
        source = self.folder / 'videos/source.mp4'
        source.write_bytes(b'fixture-video')
        mixer = Mock()
        mixer.duration.return_value = 2.0
        def render(src, dest, **kwargs):
            Path(dest).write_bytes(Path(src).read_bytes())
            self.assertFalse(kwargs['source_silent'])
            return {'output':dest}
        mixer.render.side_effect = render
        with patch('core.story_finisher.AudioMixer', return_value=mixer), \
             patch('core.media_audio.native_transcript', side_effect=AssertionError('Unexpected Subtitle API')), \
             patch('core.story_finisher.SubtitleVideoRenderer', side_effect=AssertionError('Unexpected subtitle renderer')):
            final, plan = finish_story_media(self.temp.name, self.manager, job['id'], source, {})
        self.assertFalse(plan['subtitle_included'])
        self.assertEqual(plan['subtitle_source'], 'disabled')
        self.assertEqual(final.read_bytes(), b'fixture-video')
        self.assertFalse((self.folder/'captions/story_subtitle.srt').exists())

    def test_new_queue_conversation_disables_subtitle_even_with_saved_default(self):
        q = CreationQueue(self.temp.name)
        q.enqueue('story',['สนทนา'],video_generation_mode='meta_ai',settings={
            'actor_dialogue':True,'audio_choices':{'mode':'flow_original','subtitle':True,'music':True}})
        settings = CreationQueue(self.temp.name).snapshot()['items'][0]['settings']
        self.assertTrue(settings['actor_dialogue'])
        self.assertFalse(settings['audio_choices']['subtitle'])
        self.assertTrue(settings['audio_choices']['music'])
        self.assertFalse(settings['subtitle_enabled'])

    def test_checkpoint_resume_and_scene_gate_keep_actors(self):
        job = self.manager.save_analysis_checkpoint(self.job['id'], self.plan)
        self.assertEqual(job['narration_script'], 'เห็นกุญแจไหม อยู่ตรงนี้ไง')
        self.assertEqual(job['scene_dialogue_turns'][1], [])
        self.assertEqual(self.manager.load_analysis_checkpoint(job['id'])['scene_dialogue_turns'], self.plan['scene_dialogue_turns'])
        (self.folder/'generated/scene_01.png').write_bytes(b'fixture')
        prepared = self.manager.prepare_scene_pipeline(job['id'], 1)
        self.assertEqual(prepared['scene_dialogue_turns'][0][0]['speaker'], 'มะลิ')
        self.assertNotIn('ผู้บรรยาย', json.dumps(prepared['dialogue_turns'], ensure_ascii=False))
        self.assertEqual(prepared['scene_narrations'], self.plan['scene_narrations'])
        context = plan_context(self.folder, prepared, 1)
        self.assertIn('ACTOR DIALOGUE:', context['audio_instruction'])
        self.assertIn('เห็นกุญแจไหม', context['audio_instruction'])
        request = motion_request(context)
        self.assertIn('no narrator', request)
        self.assertNotIn('moral commentary and audience calls to action are voiceover', request)

    def test_final_image_commit_keeps_actor_plan_without_cta(self):
        import base64
        result = {**self.plan, 'generated_images':[base64.b64encode(b'fixture-media'*100).decode()]*6}
        saved = self.manager.apply_ai_result(result)
        self.assertEqual(saved['scene_dialogue_turns'], self.plan['scene_dialogue_turns'])
        self.assertEqual(saved['dialogue_turns'][0]['listener'], 'ต้น')
        self.assertFalse(saved['engagement_cta_enabled'])
        self.assertEqual(saved['narration_script'], 'เห็นกุญแจไหม อยู่ตรงนี้ไง')

    def test_cast_registry_mismatch_rejected_before_checkpoint(self):
        bad = copy.deepcopy(self.plan)
        bad['story_entities'] = []
        with self.assertRaisesRegex(ValueError,'ACTOR_PLAN_REVIEW'):
            self.manager.save_analysis_checkpoint(self.job['id'],bad)
        self.assertFalse((self.folder/'prompts/ai_analysis_checkpoint.json').exists())

    def test_invalid_speaker_no_silent_narrator_coercion(self):
        for speaker in ['ผู้บรรยาย','คนที่ไม่มีในรายชื่อ']:
            plan = copy.deepcopy(self.plan)
            plan['scene_dialogue_turns'][0][0]['speaker'] = speaker
            with self.assertRaisesRegex(ValueError, 'ACTOR_PLAN_REVIEW'):
                self.manager.save_analysis_checkpoint(self.job['id'], plan)
        self.assertFalse((self.folder/'prompts/ai_analysis_checkpoint.json').exists())

    def test_wrong_count_long_speech_or_no_dialogue_rejected(self):
        for variant in ['count','long','empty']:
            plan = copy.deepcopy(self.plan)
            if variant=='count': plan['scene_dialogue_turns'].pop()
            if variant=='long': plan['scene_dialogue_turns'][0][0]['text']='คำพูดยาวมาก'*50
            if variant=='empty': plan['scene_dialogue_turns']=[[]]*6
            with self.assertRaises(ValueError): validate_plan(self.job, plan)

    def test_queue_roundtrip_and_invalid_voice_provider(self):
        q = CreationQueue(self.temp.name)
        for provider in ['google_flow','meta_ai']:
            q.enqueue('story',[provider],video_generation_mode=provider,settings={'actor_dialogue':True,'audio_choices':{'mode':'flow_original'}})
        rows = CreationQueue(self.temp.name).snapshot()['items']
        self.assertTrue(all(r['settings']['actor_dialogue'] for r in rows))
        for provider, mode in [('image_motion','flow_original'),('meta_ai','api'),('google_flow','none')]:
            with self.assertRaises(ValueError): validate_option(True, provider, {'mode':mode})

    def test_silent_scene_only_and_native_meta_prompt(self):
        from core.meta_video import MetaVideoManager
        job = self.manager.save_analysis_checkpoint(self.job['id'], self.plan)
        self.assertIn('intentionally silent', flow_audio_instruction(job, 2))
        self.assertNotIn('Spoken line:', flow_audio_instruction(job, 2))
        self.assertEqual(composition_choices(job)['silent_scene_indices'], [2,3,4,5,6])
        self.assertEqual(composition_choices(job, 1)['silent_scene_indices'], [])
        self.assertFalse(composition_choices({**job,'audio_choices':{'allow_silent':True}})['allow_silent'])
        (self.folder/'generated/scene_01.png').write_bytes(b'fixture')
        job.update(video_generation_mode='meta_ai', generated_images=['generated/scene_01.png'])
        self.manager._save(job)
        prompt = MetaVideoManager(self.manager).package(job['id'],1)['prompt']
        self.assertIn('ACTOR DIALOGUE:', prompt)
        self.assertIn('เห็นกุญแจไหม',prompt)
        self.assertNotIn('No music, speech or ambient audio',prompt)

    def test_repair_changes_action_not_speakers_or_script(self):
        job = self.manager.save_analysis_checkpoint(self.job['id'], self.plan)
        revision = dict(scene_narration='เพื่อนสองคนย้ายไปมองหากุญแจในสวน', revision_hash='new')
        updated = revised_story(job, {'1':{'phase':'ready','revision':revision}})
        self.assertEqual(updated['scene_dialogue_turns'],job['scene_dialogue_turns'])
        self.assertEqual(updated['narration_script'],job['narration_script'])
        self.assertEqual(updated['scene_narrations'][0],revision['scene_narration'])
        self.assertEqual(job['scene_narrations'],self.plan['scene_narrations'])

    def test_narrated_request_unchanged_and_edit_guard(self):
        old = self.manager.create('เรื่องเดิม',video_generation_mode='google_flow')
        prompt=(self.manager._folder(old['id'])/'prompts/chatgpt_request.txt').read_text(encoding='utf-8')
        self.assertIn('2. เขียน narration_script ภาษาไทยสำหรับ AI Voice',prompt)
        self.assertNotIn('ACTOR STORY MODE:',prompt)
        with self.assertRaises(ValueError):self.manager.update_narration(self.job['id'],'บทเล่าแทน')

    def test_missing_spoken_audio_not_excused_by_silent_neighbor(self):
        from core.flow_native_audio import compose_native
        rows=[{'path':'one.mp4','duration':1,'has_audio':False},{'path':'two.mp4','duration':1,'has_audio':False}]
        with patch('core.flow_native_audio.inspect_clips',return_value=rows):
            with self.assertRaisesRegex(ValueError,'ไม่มีแทร็กเสียง'):
                compose_native(['one.mp4','two.mp4'],self.folder/'videos/test.mp4',silent_scene_indices=[2])

    def test_real_silent_acting_segment_no_tts(self):
        from core.scene_voice import render_scene_asset
        from core.flow_native_audio import inspect_clips
        source=Path('C:/Users/keera/Downloads/morning_coffee_steam_silent.mp4')
        if not source.is_file():self.skipTest('existing silent clip unavailable')
        job=self.manager.save_analysis_checkpoint(self.job['id'],self.plan)
        render={'width':240,'height':426,'fps':24,'crf':28}
        with patch('core.scene_voice.render_chunked_voice',side_effect=AssertionError('Unexpected TTS')):
            with self.assertRaisesRegex(ValueError,'ไม่มีแทร็กเสียง'):
                render_scene_asset(self.folder,job,1,source,None,'',render,'',None,lambda *a:None)
            result=render_scene_asset(self.folder,job,2,source,None,'',render,'',None,lambda *a:None)
        self.assertEqual(result['voice'],'')
        self.assertAlmostEqual(inspect_clips([self.folder/result['segment']])[0]['duration'],10,delta=.25)


if __name__=='__main__':unittest.main()
