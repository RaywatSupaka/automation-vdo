import tempfile
import unittest
from pathlib import Path
from core.music_library import resolve_track, validate_selection, selected_paths
from core.audio_mixer import AudioMixer


class MusicLibraryTests(unittest.TestCase):
    def test_queued_options_do_not_resolve_current_library(self):
        import copy
        from unittest.mock import MagicMock
        from ui.main_window import MainWindow
        fake=MagicMock()
        fake.cfg={}
        fake._product_audio_choices=None
        fake._creation_dispatch_item={'queue_id':'Q'}
        fake._presenter_product_selection={'enabled':False}
        saved={'audio':{'background_files':['queued.wav'],'sfx_files':[],'music_track_count':1}}
        fake._creation_pipeline_options.side_effect=lambda options:{**options,**copy.deepcopy(saved)}
        fake._selected_audio_files.side_effect=AssertionError('current library must not be read for queued work')
        result=MainWindow._product_pipeline_options(fake)
        self.assertEqual(result['audio']['background_files'],['queued.wav'])
        self.assertEqual(result['audio']['music_track_count'],1)
        fake._selected_audio_files.assert_not_called()

    def test_real_five_song_render_and_resume_plan(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);mixer=AudioMixer();source=folder/'source.mp4'
            subprocess.run([str(mixer.ffmpeg),'-y','-f','lavfi','-i','color=c=black:s=240x240:r=10:d=50','-f','lavfi','-i','sine=frequency=500:duration=50','-shortest','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True,capture_output=True)
            tracks=[]
            for i in range(6):
                path=folder/f'{i}.wav'
                subprocess.run([str(mixer.ffmpeg),'-y','-f','lavfi','-i',f'sine=frequency={150+i*50}:duration=14','-c:a','pcm_s16le',str(path)],check=True,capture_output=True)
                tracks.append(path)
            plans=[]
            for name in ('first','resume'):
                plans.append(mixer.render(source,folder/f'{name}.mp4',background_files=tracks[:5],music_track_count=5,seed='saved-job'))
            self.assertEqual(plans[0]['music_unique_tracks'],5)
            self.assertEqual(plans[0]['music_plan'],plans[1]['music_plan'])
            self.assertNotIn(str(tracks[-1]),plans[0]['music_selected_files'])
            self.assertAlmostEqual(mixer.duration(folder/'first.mp4'),50,delta=.25)

    def test_preview_http_range_and_traversal(self):
        import logging, urllib.request, urllib.error
        from core.local_bridge import LocalBridge
        from core.product_manager import ProductManager
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'assets/audio/background';folder.mkdir(parents=True)
            (folder/'song.wav').write_bytes(b'0123456789')
            bridge=LocalBridge('127.0.0.1',0,ProductManager(root),logging.getLogger('music-preview'),desktop_web_root=root/'web_ui').start()
            try:
                url=f'http://127.0.0.1:{bridge.server.server_address[1]}/api/desktop/music-preview?file='
                with urllib.request.urlopen(urllib.request.Request(url+'song.wav',headers={'Range':'bytes=2-5'})) as response:
                    self.assertEqual(response.status,206);self.assertEqual(response.read(),b'2345')
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(url+'..%2Fsecret.wav')
            finally:bridge.stop()

    def test_queue_count_and_pool_survive_reload(self):
        from core.creation_queue import CreationQueue
        with tempfile.TemporaryDirectory() as tmp:
            settings={'audio':{'background_files':['a.wav','b.wav'],'music_track_count':2}}
            queue=CreationQueue(tmp);queue.enqueue('story',['test'],settings=settings)
            settings['audio']['background_files'].clear()
            row=CreationQueue(tmp).snapshot()['items'][0]
            self.assertEqual(row['settings']['audio']['background_files'],['a.wav','b.wav'])
            self.assertEqual(row['settings']['audio']['music_track_count'],2)
    def test_selection_is_explicit_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'เพลง.wav';p.touch()
            self.assertEqual(validate_selection(tmp,[p.name,p.name],1),([p.name],1))
            self.assertEqual(selected_paths([p],[]),[])
            self.assertEqual(selected_paths([p],None),[p])
            with self.assertRaises(ValueError):validate_selection(tmp,[p.name],2)
            with self.assertRaises(ValueError):validate_selection(tmp,[p.name],True)
            with self.assertRaises(ValueError):selected_paths([p],['missing.mp3'])

    def test_preview_cannot_read_outside_music_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('../secret.mp3','..\\secret.mp3','C:/secret.mp3','settings.json',''):
                with self.subTest(name=name), self.assertRaises(ValueError):resolve_track(tmp,name)

    def test_five_tracks_are_used_before_repetition_when_clip_fits(self):
        tracks=[{'file':f'{n}.wav','duration':90} for n in range(5)]
        plan=AudioMixer.build_music_plan(70,tracks,seed='saved-job')
        self.assertEqual(len({x['file'] for x in plan[:5]}),5)
        self.assertEqual(plan,AudioMixer.build_music_plan(70,tracks,seed='saved-job'))
        self.assertTrue(all(a['file']!=b['file'] for a,b in zip(plan,plan[1:])))

    def test_short_clip_preserves_smooth_segments(self):
        plan=AudioMixer.build_music_plan(15,[{'file':str(n),'duration':50} for n in range(5)],seed='short')
        self.assertEqual(len(plan),2)
        self.assertAlmostEqual(plan[-1]['timeline_end'],15)

    def test_ui_real_dom(self):
        import subprocess
        result=subprocess.run(['node','tests/music_library_dom.js'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,encoding='utf-8',timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
