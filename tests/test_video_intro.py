import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import array
import math
from core.video_intro import IntroLibrary, intro_options, insert_intro, inspect_video, choose_intro_point, _digest
from core.audio_mixer import AudioMixer
from core.cancellable_process import OperationCancelled, hidden_process_kwargs, run_cancellable
from core.creation_queue import CreationQueue, clean_settings
from core.drama_options import drama_render_options


class IntroTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='smartflow-intro-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.library=IntroLibrary(self.root)
        self.mixer=AudioMixer()

    def video(self, name, duration=2, audio=True, color='green', size='192x108'):
        path=self.root/name
        args=[str(self.mixer.ffmpeg),'-v','error','-y','-f','lavfi','-i',f'color={color}:s={size}:r=30:d={duration}']
        if audio:args+=['-f','lavfi','-i',f'sine=frequency=1200:sample_rate=48000:duration={duration}']
        args+=['-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(path)]
        result=run_cancellable(args);self.assertEqual(result.returncode,0,result.stderr)
        return path

    def main(self, duration=6):
        path=self.root/'main.mp4'
        # Continuous speech-like tones, intentionally NO silence near3 seconds.
        result=run_cancellable([str(self.mixer.ffmpeg),'-v','error','-y','-f','lavfi','-i',
            f'color=red:s=90x160:r=30:d={duration/2}', '-f','lavfi','-i',f'color=blue:s=90x160:r=30:d={duration/2}',
            '-f','lavfi','-i',f'sine=frequency=400:sample_rate=48000:duration={duration/2}',
            '-f','lavfi','-i',f'sine=frequency=800:sample_rate=48000:duration={duration/2}',
            '-filter_complex','[0:v][2:a][1:v][3:a]concat=n=2:v=1:a=1[v][a]',
            '-map','[v]','-map','[a]','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(path)])
        self.assertEqual(result.returncode,0,result.stderr)
        return path

    def selected(self, path):
        row=self.library.import_file(path)
        return {'enabled':True,'file':row['asset']['file']}

    def test_import_snapshot_defaults_validation_and_queue(self):
        path=self.video('my-intro.mp4')
        settings=self.selected(path)
        self.library.save(settings)
        self.assertEqual(self.library.state()['settings'],settings)
        queue=CreationQueue(self.root/'queue')
        queued=queue.enqueue('story',['เรื่องทดสอบ'],settings={'intro_options':settings})['items'][0]
        series=drama_render_options({'intro_options':settings})
        self.library.save({'enabled':False,'file':settings['file']})
        path.unlink()  # Only test-owned source; the imported snapshot survives.
        self.assertEqual(queue.get_item(queued['queue_id'])['settings']['intro_options'],settings)
        self.assertEqual(series['intro_options'],settings)
        self.assertEqual(self.library.validate(settings),settings)
        self.assertFalse(intro_options()['enabled'])
        self.assertNotIn('intro_options',clean_settings({}))
        self.assertNotIn('intro_options',drama_render_options({}))
        for value in ({'enabled':True},{'enabled':'yes'},{'enabled':True,'file':'../outside.mp4'}, {'file':'/arbitrary.mp4'}):
            with self.subTest(value=value),self.assertRaises(ValueError):intro_options(value)
        (self.root/settings['file']).write_bytes(b'tampered test clip')
        with self.assertRaises(ValueError):self.library.validate(settings)

    def test_rejects_image_audio_corrupt_and_preserves_original(self):
        for name in ('picture.jpg','sound.mp3','broken.mp4'):
            path=self.root/name;path.write_bytes(b'test only')
            with self.subTest(name=name),self.assertRaises(ValueError):self.library.import_file(path)
            self.assertEqual(path.read_bytes(),b'test only')
        self.assertEqual(self.library.state()['assets'],[])

    def test_splice_random_opening_preserves_picture_audio_and_length(self):
        main=self.main();settings=self.selected(self.video('intro.mp4'));before=_digest(main)
        result,plan=insert_intro(self.root,main,self.root/'out.mp4',settings)
        self.assertGreaterEqual(plan['insert_at'],1.5)
        self.assertLessEqual(plan['insert_at'],3.9)
        self.assertEqual(plan['selection'],'random_opening_no_pause')
        self.assertAlmostEqual(plan['duration'],8,delta=.1)
        self.assertEqual(_digest(main),before)
        info=inspect_video(result);self.assertEqual((info['width'],info['height']),(90,160))
        for at,dominant,frequency in ((.25,0,400),(plan['insert_at']+.5,1,1200),(6.5,2,800)):
            with self.subTest(at=at):
                rgb=subprocess.run([str(self.mixer.ffmpeg),'-v','error','-ss',str(at),'-i',str(result),
                    '-frames:v','1','-vf','crop=2:2:44:80','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,**hidden_process_kwargs())
                self.assertEqual(rgb.returncode,0,rgb.stderr)
                color=[sum(rgb.stdout[i::3]) for i in range(3)]
                self.assertEqual(color.index(max(color)),dominant)
                audio=subprocess.run([str(self.mixer.ffmpeg),'-v','error','-ss',str(at),'-i',str(result),
                    '-t','0.25','-vn','-ac','1','-ar','48000','-f','f32le','pipe:1'],capture_output=True,**hidden_process_kwargs())
                self.assertEqual(audio.returncode,0,audio.stderr)
                samples=array.array('f',audio.stdout)
                self.assertGreater(len(samples),10000)
                energies={hz:sum(v*math.sin(2*math.pi*hz*i/48000) for i,v in enumerate(samples))**2
                    +sum(v*math.cos(2*math.pi*hz*i/48000) for i,v in enumerate(samples))**2 for hz in (400,800,1200)}
                self.assertEqual(max(energies,key=energies.get),frequency)
        probe=run_cancellable([str(self.mixer.ffprobe),'-v','error','-show_streams','-of','json',str(result)])
        streams=json.loads(probe.stdout)['streams'];v=next(s for s in streams if s['codec_type']=='video')
        self.assertEqual((v['codec_name'],v['pix_fmt'],v['profile']),('h264','yuv420p','High'))
        self.assertEqual(next(s['codec_name'] for s in streams if s['codec_type']=='audio'),'aac')
        again,p=insert_intro(self.root,main,self.root/'again.mp4',settings)
        self.assertAlmostEqual(p['duration'],plan['duration'],delta=.04)
        self.assertEqual(p['insert_at'],plan['insert_at'])

    def test_silent_intro_short_source_disabled_cancel_and_failed_publish(self):
        main=self.main(2);settings=self.selected(self.video('silent.mp4',audio=False))
        out,plan=insert_intro(self.root,main,self.root/'short.mp4',settings)
        self.assertGreaterEqual(plan['insert_at'],.5);self.assertLessEqual(plan['insert_at'],1.3)
        self.assertAlmostEqual(plan['duration'],4,delta=.1)
        original,off=insert_intro(self.root,main,self.root/'unused.mp4',{})
        self.assertEqual(original,main);self.assertFalse(off['enabled']);self.assertFalse((self.root/'unused.mp4').exists())
        event=threading.Event();event.set();before=_digest(out)
        with self.assertRaises(OperationCancelled):insert_intro(self.root,main,out,settings,cancel_event=event)
        self.assertEqual(_digest(out),before)
        with patch('core.video_intro.run_cancellable',return_value=Mock(returncode=1,stderr='fixture error')):
            with self.assertRaises(ValueError):insert_intro(self.root,main,out,settings)
        self.assertEqual(_digest(out),before)

    def test_real_quiet_beats_randomized_and_retry_stable(self):
        voice=self.root/'voice.wav'
        result=run_cancellable([str(self.mixer.ffmpeg),'-v','error','-y','-f','lavfi','-i',
            'sine=frequency=500:sample_rate=48000:duration=13',
            '-af',"volume=0:enable='between(t,5,6)+between(t,9,10)'",str(voice)])
        self.assertEqual(result.returncode,0,result.stderr)
        positions=[]
        for seed in range(8):
            point=choose_intro_point(voice,20,30,seed)
            self.assertEqual(point['selection'],'random_quiet_beat')
            cut=point['insert_at'];positions.append(cut)
            self.assertTrue(5.05<cut<5.95 or 9.05<cut<9.95,point)
            self.assertEqual(point,choose_intro_point(voice,20,30,seed))
        self.assertGreater(len(set(positions)),3)

    def test_no_audio_fallback_and_precise_cancellation(self):
        source=self.video('no-audio.mp4',audio=False)
        point=choose_intro_point(source,2,30,'same-job')
        self.assertEqual(point['selection'],'random_opening_no_pause')
        self.assertTrue(.5 <= point['insert_at'] <= 1.3)
        self.assertEqual(choose_intro_point(source,.03,30,'tiny')['selection'],'short_source_end')
        with patch('core.video_intro.run_cancellable',side_effect=OperationCancelled('test cancel')):
            with self.assertRaises(OperationCancelled):choose_intro_point(source,2,30,'cancel')

    def test_ui_actual_script_and_creation_payloads(self):
        env=dict(os.environ)
        env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result=subprocess.run(['node',str(Path(__file__).with_name('video_intro_ui_harness.js'))],
            capture_output=True,text=True,encoding='utf-8',env=env,timeout=30,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_story_job_selection_direct_queue_drama_and_legacy(self):
        options=self.selected(self.video('intro.mp4'))
        source=(Path(__file__).resolve().parents[1]/'ui/main_window.py').read_text(encoding='utf-8')
        start=source.index('            flow_source = ((drama_context')
        block='from core.flow_settings import flow_settings\n'+textwrap.dedent(source[start:source.index('            self.stories._save(job)',start)])
        app=SimpleNamespace(cfg={},_story_intro_options=options,_story_flow_settings={},_story_ai_cover_options={},
                            _creation_settings=lambda:{'intro_options':options})
        for queued,drama in ((False,False),(True,False),(False,True)):
            context={'self':app,'queue_item_id':'Q' if queued else '', 'drama_context':{'render_options':{'intro_options':options}} if drama else None,
                     'flow_smoke_test':False,'job':{}}
            with patch('ui.video_intro.ROOT',self.root):exec(block,context)
            self.assertEqual(context['job']['intro_options'],options)
        app._creation_settings=lambda:{}
        context={'self':app,'queue_item_id':'OLD-QUEUE','drama_context':None,'flow_smoke_test':False,'job':{}}
        with patch('ui.video_intro.ROOT',self.root):exec(block,context)
        self.assertEqual(context['job']['intro_options'],{'enabled':False,'file':''})

    def test_real_story_finisher_inserts_once_and_preserves_final_on_failure(self):
        from core.story_finisher import finish_story_media
        main=self.main();options=self.selected(self.video('intro.mp4'))
        folder=self.root/'stories'/'STORY-INTRO';(folder/'captions').mkdir(parents=True);(folder/'videos').mkdir()
        job={'intro_options':options,'audio_choices':{'mode':'flow_original','subtitle':False,'music':False,'sfx':False}}
        manager=SimpleNamespace(root=folder.parent,get=lambda _:job)
        config={'logo_file':'absent-test-logo.png','audio_background_enabled':False,'audio_sfx_enabled':False}
        final,plan=finish_story_media(self.root,manager,'STORY-INTRO',main,config)
        self.assertTrue(plan['intro']['enabled']);self.assertAlmostEqual(plan['duration'],8,delta=.12)
        cut=plan['intro']['insert_at']
        before=_digest(final)
        with patch('core.video_intro.insert_intro',side_effect=ValueError('test intro failed')):
            with self.assertRaises(ValueError):finish_story_media(self.root,manager,'STORY-INTRO',main,config)
        self.assertEqual(_digest(final),before)
        final,plan=finish_story_media(self.root,manager,'STORY-INTRO',main,config)
        self.assertAlmostEqual(plan['duration'],8,delta=.12)
        self.assertEqual(plan['intro']['insert_at'],cut)
        self.assertTrue(list((folder/'backups'/'finals').glob('*.mp4')))
