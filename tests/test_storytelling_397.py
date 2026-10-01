import copy
import json
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path
from PIL import Image
from core.storytelling import storytelling_options, validate_settings, ending_instruction
from core.story_manager import StoryManager
from core.story_performance import validate_plan, composition_choices
from core.drama_options import drama_render_options
from core.drama_series import DramaSeriesManager
from core.drama_series import generated_drama_cast
from core.creation_queue import CreationQueue
from core.flow_motion_plan import plan_context
from core.media_audio import flow_audio_instruction
from core.scene_voice import scene_turns
from core.scene_voice import render_scene_asset
from core.scene_context_revision import revised_story


def options(mode='dialogue', **kwargs):
    return storytelling_options(dict(version=1, mode=mode, **kwargs))


def plan(job):
    groups = [[dict(speaker='มะลิ', listener='ต้น', text='เห็นกุญแจไหม'),
               dict(speaker='ต้น', listener='มะลิ', text='อยู่ตรงนี้ไง')]] + [[] for _ in range(5)]
    mode = job['storytelling_options']['mode']
    if mode == 'solo':
        groups[0] = [dict(speaker='มะลิ', listener='', text='กุญแจอยู่ไหนเนี่ย')]
    if mode == 'visual':
        groups = [[] for _ in range(6)]
    return dict(job_id=job['id'], video_title='กุญแจ', video_description='เรื่องของเพื่อน',
        narration_script=' '.join(t['text'] for g in groups for t in g),
        dialogue_turns=[t for g in groups for t in g], visual_bible={'place':'หน้าประตู'},
        episode_title='กุญแจ', episode_summary='พบกุญแจ', next_episode_hook='เดินกลับบ้าน', continuity_state={'place':'บ้าน'},
        story_entities=[dict(id='a', name='มะลิ', visual_identity='หญิงเสื้อฟ้า'),dict(id='b', name='ต้น', visual_identity='ชายเสื้อเขียว')],
        scene_entities=[['a','b'] for _ in range(6)],
        character_bible=[dict(name='มะลิ', appearance='หญิงเสื้อฟ้า'),dict(name='ต้น', appearance='ชายเสื้อเขียว')],
        scene_prompts=['มะลิ และ ต้น ยืนหน้าประตู มะลิสวมเสื้อฟ้า ต้นสวมเสื้อเขียว ถือกุญแจ ภาพแนวตั้ง']*6,
        scene_narrations=['เพื่อนสองคนมองหากุญแจหน้าประตู']*6,
        scene_durations=[6]*6, scene_dialogue_turns=groups)


class Storytelling397Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.manager=StoryManager(self.root)

    def job(self, mode='dialogue', **kw):
        return self.manager.create('เพื่อนตามหากุญแจ',scene_count=6,video_generation_mode='google_flow',
            storytelling_options=options(mode), **kw)

    def test_strict_options_legacy_and_provider_contract(self):
        self.assertIsNone(storytelling_options(None))
        for bad in [{},dict(version=True),dict(version=1,mode='unknown'),dict(version=1,cta_enabled='false'),
                    dict(version=1,mode='visual',cta_enabled=True)]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):storytelling_options(bad)
        for mode in ('solo','dialogue','visual'):
            for video in ('google_flow','meta_ai'):
                self.assertEqual(validate_settings(options(mode),video)['mode'],mode)
            if mode=='visual':
                self.assertEqual(validate_settings(options(mode),'image_motion',{'mode':'none'})['mode'],'visual')
            else:
                with self.assertRaises(ValueError):validate_settings(options(mode),'image_motion')
            self.assertEqual(validate_settings(options(mode),'meta_ai',drama=True)['mode'],mode)
            with self.assertRaises(ValueError):validate_settings(options(mode),'google_flow',{'mode':'api'})

    def test_all_modes_checkpoint_resume_and_motion_preserve_speech(self):
        for mode in ('solo','dialogue','visual'):
            for provider in ('chatgpt','gemini'):
                with self.subTest(mode=mode,provider=provider):
                    job=self.job(mode,image_ai_provider=provider);result=plan(job)
                    saved=self.manager.save_analysis_checkpoint(job['id'],result)
                    self.assertEqual(saved['storytelling_options'],options(mode))
                    self.assertEqual(self.manager.load_analysis_checkpoint(job['id'])['scene_dialogue_turns'],result['scene_dialogue_turns'])
                    folder=self.manager._folder(job['id']);(folder/'generated/scene_01.png').write_bytes(b'fixture')
                    ready=self.manager.prepare_scene_pipeline(job['id'],1)
                    context=plan_context(folder,ready,1)
                    self.assertIn('No narrator',context['audio_instruction'])
                    self.assertEqual(context['provider'],provider)
                    self.assertNotIn('กดหัวใจ',ready['narration_script'])
                    if mode=='visual':
                        self.assertEqual(ready['narration_script'],'')
                        self.assertEqual(composition_choices(ready)['silent_scene_indices'],[1,2,3,4,5,6])
                    if mode=='solo':self.assertIn('SOLO:',flow_audio_instruction(ready,1))

    def test_reject_bad_dialogue_and_disabled_cta(self):
        for mode in ('solo','dialogue','visual'):
            job=self.job(mode);good=plan(job)
            bad=copy.deepcopy(good);bad['scene_dialogue_turns'][0]=[dict(speaker='ผู้บรรยาย',text='เรื่องเริ่มที่บ้าน')]
            with self.assertRaises(ValueError):validate_plan(job,bad)
            if mode!='visual':
                bad=copy.deepcopy(good);bad['scene_dialogue_turns'][0][0]['text']='กดติดตามด้วยนะ'
                with self.assertRaisesRegex(ValueError,'CTA'):validate_plan(job,bad)
        solo=self.job('solo');bad=plan(self.job('dialogue'));bad['job_id']=solo['id']
        with self.assertRaisesRegex(ValueError,'คนเดียว'):validate_plan(solo,bad)

    def test_drama_cast_options_endings_and_references(self):
        series_manager=DramaSeriesManager(self.root)
        image=self.root/'ref.png';Image.new('RGB',(160,240),'blue').save(image)
        series=series_manager.create('กุญแจ',episode_count=2,characters=[{},dict(name='มะลิ',image=str(image),voice_reference_id='voice-a'),dict(name='ต้น')],
            render_options=dict(video_generation_mode='google_flow',storytelling_options=options()))
        self.assertTrue((series_manager.folder_path(series['id'])/series['characters'][0]['source_image']).is_file())
        context=series_manager.episode_context(series['id'],1)
        job=self.job(job_type='drama_episode',series_context=context)
        saved=self.manager.save_analysis_checkpoint(job['id'],plan(job))
        self.assertEqual(saved['character_bible'][0]['voice_reference_id'],'voice-a')
        changed=plan(job);changed['character_bible'][0]['name']='คนใหม่'
        with self.assertRaises(ValueError):validate_plan(job,changed)
        self.assertIn('turning point',ending_instruction(job))
        job['episode_no']=2;self.assertIn('Resolve',ending_instruction(job))
        text=series_manager.episode_context(series['id'],2)['story_text']
        self.assertNotIn('ปิดตอนด้วยจุดชวนติดตาม EP ถัดไป',text)
        self.assertIn('Resolve',text)

    def test_series_requires_two_cast_only_for_dialogue(self):
        manager=DramaSeriesManager(self.root)
        with self.assertRaisesRegex(ValueError,'สองคน'):
            manager.create('test',characters=[dict(name='หนึ่ง')],render_options=dict(video_generation_mode='google_flow',storytelling_options=options()))
        manager.create('test',characters=[dict(name='หนึ่ง')],render_options=dict(video_generation_mode='google_flow',storytelling_options=options('solo')))

    def test_narrated_drama_can_create_cast_at_first_episode_and_freezes_main_voice(self):
        manager=DramaSeriesManager(self.root)
        voice=self.root/'voice.wav';voice.write_bytes(b'voice-fixture')
        series=manager.create('ร้านลับ',characters=[],render_options=dict(video_generation_mode='image_motion',
            storytelling_options=options('narrator'),audio_choices=dict(mode='api',subtitle=False),
            primary_voice_reference_id='voice-a',primary_voice_reference_file=str(voice)))
        context=manager.episode_context(series['id'],1)
        self.assertTrue(context['auto_cast_pending'])
        self.assertEqual(context['characters'],[])
        self.assertEqual(Path(context['primary_voice_reference_file']).read_bytes(),b'voice-fixture')
        self.assertEqual(context['primary_voice_reference_id'],'voice-a')
        self.assertEqual(len(generated_drama_cast([{'name':'มะลิ','appearance':'ผมสั้น เสื้อสีฟ้า'}])),1)
        job=self.manager.create('ร้านลับ',scene_count=6,video_generation_mode='image_motion',
            job_type='drama_episode',series_context=context,storytelling_options=options('narrator'))
        self.assertTrue(job['auto_cast_pending'])
        self.assertEqual(job['primary_voice_reference_id'],'voice-a')
        request=(self.manager._folder(job['id'])/'prompts/chatgpt_request.txt').read_text(encoding='utf-8')
        self.assertIn('FIRST EP CAST SETUP',request)
        self.assertNotIn('LOCKED CAST',request)
        result=plan(job)
        saved=self.manager.save_analysis_checkpoint(job['id'],result)
        self.assertEqual([row['name'] for row in saved['character_bible']],['มะลิ','ต้น'])
        manager.attach_story_job(series['id'],1,job['id'])
        frozen=manager.update_from_story(saved)
        self.assertFalse(frozen['auto_cast_pending'])
        self.assertEqual([row['name'] for row in frozen['characters']],['มะลิ','ต้น'])

    def test_queued_drama_binds_voice_once_at_first_start(self):
        manager=DramaSeriesManager(self.root)
        voice=self.root/'queued-voice.wav';voice.write_bytes(b'queued-voice')
        series=manager.create('เข้าคิวไว้',characters=[],render_options=dict(video_generation_mode='image_motion',
            storytelling_options=options('narrator'),audio_choices=dict(mode='api',subtitle=False)))
        self.assertFalse(manager.episode_context(series['id'],1)['primary_voice_reference_id'])
        manager.bind_first_episode_voice(series['id'],'voice-first',str(voice))
        manager.bind_first_episode_voice(series['id'],'voice-later','')
        context=manager.episode_context(series['id'],1)
        self.assertEqual(context['primary_voice_reference_id'],'voice-first')
        self.assertEqual(Path(context['primary_voice_reference_file']).read_bytes(),b'queued-voice')
        legacy=manager.create('เรื่องเดิม',characters=[],render_options=dict(video_generation_mode='image_motion',
            storytelling_options=options('narrator'),audio_choices=dict(mode='api',subtitle=False)))
        manager.attach_story_job(legacy['id'],1,'STORY-existing')
        manager.bind_first_episode_voice(legacy['id'],'voice-later',str(voice))
        self.assertFalse(manager.episode_context(legacy['id'],1)['primary_voice_reference_id'])

    def test_narrated_drama_preserves_saved_character_voices(self):
        manager=DramaSeriesManager(self.root)
        series=manager.create('กุญแจ',characters=[{'name':'มะลิ','voice_reference_id':'voice-a'},
                                                    {'name':'ต้น','voice_reference_id':'voice-b'}],
            render_options=dict(video_generation_mode='google_flow',storytelling_options=options('narrator'),
                                audio_choices=dict(mode='api',subtitle=False)))
        job=self.manager.create('กุญแจ',scene_count=6,video_generation_mode='google_flow',
            job_type='drama_episode',series_context=manager.episode_context(series['id'],1),
            storytelling_options=options('narrator'))
        result=plan(job)
        saved=self.manager.save_analysis_checkpoint(job['id'],result)
        checkpoint=self.manager.load_analysis_checkpoint(job['id'])
        self.assertEqual(saved['character_bible'][0]['voice_reference_id'],'voice-a')
        self.assertEqual(checkpoint['character_bible'][1]['voice_reference_id'],'voice-b')
        changed=plan(job);changed['character_bible'][0]['name']='คนใหม่'
        with self.assertRaisesRegex(ValueError,'DRAMA_CAST_REVIEW'):
            self.manager.save_analysis_checkpoint(job['id'],changed)

    def test_drama_dubbed_dialogue_uses_actual_turns_not_visual_beats(self):
        self.assertEqual(validate_settings(options('dialogue'),'google_flow',{'mode':'api','keep_video_audio':False},drama=True)['mode'],'dialogue')
        with self.assertRaises(ValueError):validate_settings(options('dialogue'),'google_flow',{'mode':'api'})
        job=self.job('dialogue')
        job.update(validate_plan(job,plan(job)))
        job['audio_choices']={'mode':'api','subtitle':True}
        self.assertEqual([row['text'] for row in scene_turns(job,1)],['เห็นกุญแจไหม','อยู่ตรงนี้ไง'])
        self.assertEqual(scene_turns(job,2),[])
        self.assertIn('WITHOUT generated speech',flow_audio_instruction(job,1))

    def test_intentionally_silent_dubbed_scene_never_requests_empty_voice(self):
        video=self.root/'silent.mp4';video.write_bytes(b'fixture-video')
        job={'id':'STORY-fixture','job_type':'drama_episode','scene_count':2,'actor_dialogue':True,
             'video_generation_mode':'google_flow','storytelling_options':options('solo'),
             'audio_choices':{'mode':'api','subtitle':False},
             'scene_dialogue_turns':[[],[{'speaker':'มะลิ','text':'กุญแจอยู่ไหน'}]],
             'character_bible':[{'name':'มะลิ'}]}
        render={'width':720,'height':1280,'fps':30,'crf':20}
        composer=Mock();composer.compose.return_value={'duration':6}
        with patch('core.video_composer.MultiFlowComposer',return_value=composer), \
             patch('core.video_logo.locate_ffmpeg',return_value=Path('ffmpeg')):
            result=render_scene_asset.__wrapped__(self.root,job,1,video,None,'',render,'ffmpeg',None,lambda *a:None)
        self.assertEqual(result['voice'],'')
        self.assertEqual(composer.compose.call_args.kwargs['audio_choices']['mode'],'none')

    def test_native_repeat_audit_uses_dialogue_not_scene_direction(self):
        from core.story_finisher import finish_story_media
        job=self.job('dialogue');job=self.manager.save_analysis_checkpoint(job['id'],plan(job))
        job['audio_choices'].update(subtitle=True,music=False,sfx=False)
        self.manager._save(job);folder=self.manager._folder(job['id'])
        source=folder/'videos/source.mp4';source.write_bytes(b'fixture-video')
        mixer=Mock();mixer.duration.return_value=2.0
        transcript={'segments':[{'text':'เห็นกุญแจไหมอยู่ตรงนี้ไงเห็นกุญแจไหมอยู่ตรงนี้ไง',
                                 'start':0,'end':0.2}]}
        with patch('core.story_finisher.AudioMixer',return_value=mixer), \
             patch('core.scene_pipeline.ScenePipeline',return_value=SimpleNamespace(get=lambda index:{'duration':2/6})), \
             patch('core.media_audio.native_transcript',return_value=transcript):
            with self.assertRaisesRegex(ValueError,'FLOW_SPEECH_REPEAT'):
                finish_story_media(self.root,self.manager,job['id'],source,{})

    def test_queue_snapshot_is_independent_and_legacy_is_unchanged(self):
        queue=CreationQueue(self.root)
        for mode in ('narrator','solo','dialogue','visual'):
            selected=options(mode);settings=dict(storytelling_options=selected,audio_choices=dict(mode='flow_original',subtitle=False,music=False,sfx=False))
            queue.enqueue('story',[mode],video_generation_mode='google_flow',settings=settings)
            selected['tone']='comedy'
        rows=CreationQueue(self.root).snapshot()['items']
        self.assertTrue(all(row['settings']['storytelling_options']['tone']=='auto' for row in rows))
        self.assertEqual([row['settings']['actor_dialogue'] for row in rows],[False,True,True,True])
        old=self.manager.create('เก่า',scene_count=6)
        self.assertNotIn('storytelling_options',old)
        self.assertNotIn('storytelling_options',drama_render_options({}))

    def test_visual_queue_without_audio_defaults_to_silence(self):
        row=CreationQueue(self.root).enqueue('story',['ภาพล้วน'],video_generation_mode='image_motion',
            settings={'storytelling_options':options('visual')})['items'][0]
        self.assertEqual(row['settings']['audio_choices']['mode'],'none')
        self.assertFalse(row['settings']['audio_choices']['subtitle'])

    def test_request_has_single_contract_for_all_modes_and_models(self):
        models=['Omni 1.1 Flash','Veo 3.1 - Lite','Veo 3.1 - Fast','Veo 3.1 - Quality','Veo 3.1 - Lite [Lower Priority]']
        for mode in ('narrator','solo','dialogue','visual'):
            job=self.job(mode);folder=self.manager._folder(job['id'])
            for model in models:
                job['flow_settings']=dict(model=model,duration='8s')
                self.manager._write_request(folder,job)
                prompt=(folder/'prompts/chatgpt_request.txt').read_text(encoding='utf-8')
                request=json.loads((folder/'ai_request.json').read_text(encoding='utf-8'))
                self.assertEqual(request['storytelling_options']['mode'],mode)
                self.assertIn('CTA OFF',prompt);self.assertIn('8s',prompt)
                self.assertNotIn('แล้วชวนผู้ชมกดหัวใจ',prompt)
                self.assertNotIn('ต้องรวมประโยคปิดเรื่องและคำชวน',prompt)
                if mode=='visual':self.assertNotIn('narration_script',request['required_fields'])

    def test_native_subtitle_choice_and_repaired_scene_keep_contract(self):
        job=self.job();job.update(validate_plan(job,plan(job)))
        job['audio_choices'].update(subtitle=True)
        self.assertTrue(composition_choices(job)['subtitle'])
        replacement={'1':{'phase':'ready','revision':dict(scene_narration='ทั้งคู่เดินมาที่หน้าต่าง',revision_hash='changed')}}
        revised=revised_story(job,replacement)
        self.assertEqual(revised['scene_dialogue_turns'],job['scene_dialogue_turns'])
        self.assertEqual(revised['storytelling_options'],job['storytelling_options'])

    def test_extension_actual_source_contract(self):
        run=subprocess.run(['node','tests/storytelling_397.cjs'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)

    def test_finisher_uses_actual_audio_only_for_explicit_native_subtitles(self):
        from core.story_finisher import finish_story_media
        for mode, subtitle in [('dialogue', True), ('dialogue', False), ('visual', False)]:
            job=self.job(mode);job=self.manager.save_analysis_checkpoint(job['id'],plan(job))
            job['audio_choices'].update(subtitle=subtitle,music=False,sfx=False)
            self.manager._save(job);folder=self.manager._folder(job['id'])
            source=folder/'videos/source.mp4';source.write_bytes(b'fixture-video')
            mixer=Mock();mixer.duration.return_value=2.0
            def copy_media(src,dest,**kwargs):
                Path(dest).write_bytes(Path(src).read_bytes());return {'output':dest}
            mixer.render.side_effect=copy_media
            renderer=Mock();renderer.render.side_effect=lambda src,srt,dest,**kwargs:copy_media(src,dest)
            with patch('core.story_finisher.AudioMixer',return_value=mixer), \
                 patch('core.story_finisher.SubtitleVideoRenderer',return_value=renderer), \
                 patch('core.scene_pipeline.ScenePipeline',return_value=SimpleNamespace(get=lambda index:{'duration':2/6,'segment_sha256':'fixture'})), \
                 patch('core.media_audio.native_transcript',return_value={'segments':[{'text':'เสียงจริง','words':[{'text':'เสียงจริง','start':0,'end':1}]}]}) as transcript:
                final,result=finish_story_media(self.root,self.manager,job['id'],source,{})
            self.assertEqual(result['subtitle_included'],subtitle)
            self.assertEqual(result['subtitle_source'],'flow_actual_audio' if subtitle else 'disabled')
            self.assertEqual(transcript.call_count,int(subtitle))
            self.assertEqual(renderer.render.call_count,int(subtitle))
            self.assertEqual(final.read_bytes(),b'fixture-video')
            if subtitle:
                caption=(folder/'captions/story_subtitle.srt').read_text(encoding='utf-8')
                self.assertIn('เสียงจริง',caption);self.assertNotIn('เพื่อนสองคน',caption)

    def test_desktop_capture_and_story_drama_dispatch_boundaries(self):
        from ui.main_window import MainWindow
        owner=SimpleNamespace(cfg={},_product_pipeline_options=lambda **kw:dict(provider='gemini',subtitle_enabled=False,audio={}))
        captured=MainWindow._creation_capture_settings(owner,dict(storytelling_options=options('solo'),video_generation_mode='google_flow',
            audio_choices=dict(mode='flow_original',subtitle=True)))
        self.assertEqual(captured['storytelling_options'],options('solo'))
        self.assertTrue(captured['audio_choices']['subtitle'])
        for route in ('direct','queue','drama'):
            window=Mock();window.membership=None;window._story_pipeline_job_id=window._product_pipeline_job_id=''
            window._story_audio_choices={'mode':'api'} if route=='drama' else {'mode':'flow_original'}
            window._creation_settings.return_value=captured
            window._story_video_mode_key.return_value='google_flow';window._compatible_extension.return_value=({},True)
            window.stories.create.side_effect=RuntimeError('TEST_STOP_AT_CAPTURE')
            context=dict(series_id='SERIES-test',episode_no=1,render_options=dict(storytelling_options=options('solo'),audio_choices={'mode':'flow_original'})) if route=='drama' else None
            MainWindow._create_story_and_run(window,queue_item_id='Q' if route!='direct' else '',drama_context=context,
                storytelling_options=options('solo') if route=='direct' else None)
            self.assertEqual(window.stories.create.call_args.kwargs['storytelling_options'],options('solo'))
            window.bridge.queue_extension_command.assert_not_called()

    def test_visual_final_commit_does_not_restore_narration_from_beats(self):
        import base64
        job=self.job('visual');result=plan(job)
        result['generated_images']=[base64.b64encode(b'fixture-media'*100).decode()]*6
        saved=self.manager.apply_ai_result(result)
        self.assertEqual(saved['narration_script'],'')
        self.assertEqual(saved['dialogue_turns'],[])
        self.assertFalse(saved['engagement_cta_enabled'])

    def test_scene_duration_is_bounded_by_saved_flow_setting(self):
        job=self.job('solo');job['flow_settings']={'duration':'4s'}
        with self.assertRaisesRegex(ValueError,'ยาวกว่าคลิป'):validate_plan(job,plan(job))

    def test_queue_edit_retains_mode_and_rejects_conflicting_audio(self):
        queue=CreationQueue(self.root)
        row=queue.enqueue('story',['เรื่อง'],video_generation_mode='google_flow',settings=dict(storytelling_options=options('solo'),
            audio_choices=dict(mode='flow_original',subtitle=True)))['items'][0]
        edited=queue.edit(row['queue_id'],'ปรับชื่อ',settings={'audio_choices':dict(mode='flow_original',subtitle=True)})
        self.assertEqual(edited['settings']['storytelling_options']['mode'],'solo')
        self.assertTrue(edited['settings']['audio_choices']['subtitle'])
        with self.assertRaises(ValueError):queue.edit(row['queue_id'],'ผิด',settings={'audio_choices':dict(mode='api')})


if __name__=='__main__':unittest.main()
