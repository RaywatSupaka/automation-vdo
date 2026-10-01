import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from core.media_audio import audio_choices, audio_mode, product_audio_options, flow_audio_instruction
from core.creation_queue import CreationQueue, clean_settings
from core.drama_options import drama_render_options
from ui.main_window import MainWindow

class MediaAudioChoicesTests(unittest.TestCase):
    def test_video_volume_validation_and_queue_restart(self):
        for invalid in [-1,101,True,'20',float('nan'),float('inf')]:
            with self.assertRaises(ValueError): audio_choices({'video_audio_volume':invalid})
        self.assertEqual(audio_choices({'mode':'api'})['video_audio_volume'],35)
        self.assertEqual(audio_choices({'mode':'flow_original'})['video_audio_volume'],100)
        with tempfile.TemporaryDirectory() as folder:
            q=CreationQueue(folder)
            for level in [0,15,100]:
                q.enqueue('story',[f'volume {level}'],video_generation_mode='google_flow',settings={'audio_choices':{'mode':'api','keep_video_audio':True,'video_audio_volume':level}})
            self.assertEqual([x['settings']['audio_choices']['video_audio_volume'] for x in CreationQueue(folder).snapshot()['items']],[0,15,100])

    def test_keep_video_audio_snapshot_and_validation(self):
        choice=audio_choices({'mode':'api','keep_video_audio':True},'google_flow')
        self.assertTrue(clean_settings({'audio_choices':choice})['audio_choices']['keep_video_audio'])
        with self.assertRaises(ValueError): audio_choices(choice,'image_motion')
        with self.assertRaises(ValueError): audio_choices({'mode':'none','keep_video_audio':True},'google_flow')

    def test_queue_only_pauses_without_cancel_and_long_settings_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            q=CreationQueue(folder)
            q.enqueue('story',['first']);q.resume();active=q.claim_next()
            q.enqueue('story',['later'],queue_only=True,settings={'audio_choices':{'mode':'api','keep_video_audio':True}})
            self.assertTrue(q.snapshot()['paused'])
            self.assertEqual(q.running_item()['queue_id'],active['queue_id'])
            self.assertIsNone(q.claim_next())
            q.enqueue_batch(['long'],long_video={'duration_seconds':180},queue_only=True)
            self.assertIn('long_video',q.snapshot()['items'][-1])

    def test_legacy_default(self):
        self.assertIsNone(audio_choices(None))
        self.assertEqual(audio_mode({}), 'api')

    def test_flow_requires_flow(self):
        with self.assertRaises(ValueError): audio_choices({'mode':'flow_original'}, 'image_motion')
        with self.assertRaises(ValueError): audio_choices({'music':'false'})

    def test_options_do_not_mutate(self):
        old={'audio':{'background_files':['a'], 'sfx_files':['b']}}
        choices=audio_choices({'mode':'none','music':False,'subtitle':False})
        new=product_audio_options(old,choices)
        self.assertEqual(new['audio']['background_files'], [])
        self.assertEqual(old['audio']['background_files'], ['a'])
        self.assertFalse(new['subtitle_enabled'])

    def test_queue_choices_survive_clean_and_copy(self):
        choices=audio_choices({'mode':'flow_original','subtitle':False})
        frozen=clean_settings({'audio_choices':choices,'api_key':'never-save'})
        choices['mode']='api'
        self.assertEqual(frozen['audio_choices']['mode'],'flow_original')
        self.assertNotIn('api_key', frozen)

    def test_drama_saved_choices(self):
        options=drama_render_options({'video_generation_mode':'google_flow','audio_choices':{'mode':'flow_original','subtitle':False}})
        self.assertFalse(options['subtitle_enabled'])
        self.assertEqual(options['audio_choices']['mode'],'flow_original')

    def test_mixed_queue_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            service=CreationQueue(folder)
            for index, mode in enumerate(['api','flow_original','none']):
                service.enqueue('story',[f'เรื่อง {index}'],video_generation_mode='google_flow',settings={'audio_choices':audio_choices({'mode':mode,'subtitle':False})})
            reloaded=CreationQueue(folder).snapshot()['items']
            self.assertEqual([x['settings']['audio_choices']['mode'] for x in reloaded],['api','flow_original','none'])

    def test_prompt_only_opt_in(self):
        self.assertEqual(flow_audio_instruction({},1),'')
        self.assertIn('สวัสดี',flow_audio_instruction({'audio_choices':{'mode':'flow_original'},'scene_narrations':['สวัสดี']},1))

    def test_story_worker_skips_tts_and_pronunciation(self):
        for mode in ['none','flow_original']:
            window=MainWindow.__new__(MainWindow)
            window._story_cancel_event=None
            window._creation_settings=Mock(return_value={})
            window.events=queue.Queue()
            window.stories=Mock()
            window.stories.root=Path('unused')
            job={'ai_status':'ready','generated_images':['a'],'scene_count':1,'audio_choices':{'mode':mode},'narration_script':'HUNTER','video_generation_mode':'meta_ai'}
            window._collect_story_meta_clips=Mock(return_value=['saved.mp4'])
            window.stories.repair_program_cta.return_value=job
            window._compose_story_media=Mock(return_value='composed')
            with patch('ui.main_window.ExternalTtsClient',side_effect=AssertionError('TTS invoked')):
                self.assertEqual(window._render_story_worker('STORY-TEST','','',''),'composed')
            self.assertEqual(window._compose_story_media.call_args.args[2],'')
            window._collect_story_meta_clips.assert_called_once()

    def test_preflight_skips_voice_for_native(self):
        window=MainWindow.__new__(MainWindow)
        window.voice_api_key=Mock();window.voice_api_key.get.return_value=''
        window.voice_reference_id=Mock();window.voice_reference_id.get.return_value=''
        window.voice_reference_file=Mock();window.voice_reference_file.get.return_value=''
        window._compatible_extension=Mock(return_value=({'connected':False},True))
        window._creation_preflight({'mode':'story','settings':{'audio_choices':audio_choices({'mode':'flow_original'})}})
        with self.assertRaises(ValueError):window._creation_preflight({'mode':'story','settings':{}})

if __name__=='__main__':unittest.main()
