import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from PIL import Image, ImageChops
from core.logo_layout import frozen_logo_config, logo_geometry, normalize_logo_layout
from core.video_logo import VideoLogoRenderer
from core.cancellable_process import run_cancellable, hidden_process_kwargs
from core.subtitle_renderer import SubtitleVideoRenderer
from ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[1]


def layout(x=.5, y=.5, size=20):
    return {'version': 1, 'portrait': {'x': x, 'y': y, 'size_percent': size},
            'landscape': {'x': x, 'y': y, 'size_percent': size}}


class LogoLayoutTests(unittest.TestCase):
    def test_shared_browser_geometry_cases(self):
        cases = json.loads((ROOT/'tests/logo_geometry_cases.json').read_text())
        for case in cases:
            with self.subTest(case=case['name']):
                row = case['profile']
                value = layout(row['x'], row['y'], row['size_percent'])
                self.assertEqual(logo_geometry(value, *case['video'], *case['image']), case['expected'])

    def test_missing_layout_and_old_anchors_are_unchanged(self):
        self.assertIsNone(normalize_logo_layout(None))
        renderer = object.__new__(VideoLogoRenderer)
        with tempfile.TemporaryDirectory() as temp:
            logo = Path(temp)/'logo.png'; Image.new('RGBA', (100, 50), 'red').save(logo)
            with patch.object(renderer, '_logo_image', wraps=renderer._logo_image) as legacy:
                image, x, y = renderer.prepare_overlay(logo, 720, 1280, .8, 20, 'bottom_right', 28)
            legacy.assert_called_once()
            self.assertEqual((image.size, x, y), ((144,72),548,1180))

    def test_bad_schema_and_non_finite_coordinates_fail(self):
        for value in ({}, {'version':2}, {'version':1, 'portrait':{}}, layout(float('nan')), layout(-.1), layout(True), layout(size=61)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_logo_layout(value)

    def test_layout_is_detached_and_profiles_independent(self):
        original=layout(); saved=normalize_logo_layout(original)
        saved['portrait']['x']=.1
        self.assertEqual(original['portrait']['x'], .5)
        self.assertEqual(saved['landscape']['x'], .5)

    def test_live_defaults_cannot_activate_an_old_job(self):
        config={'logo_layout':layout(), 'logo_margin':28}
        self.assertNotIn('logo_layout', frozen_logo_config(config, {}, {'logo_opacity':.8}))
        frozen={'logo_layout':layout(.2,.3)}
        result=frozen_logo_config(config, frozen)
        config['logo_layout']['portrait']['x']=.9
        self.assertEqual(result['logo_layout']['portrait']['x'], .2)
        self.assertIsNone(frozen_logo_config(config, frozen, {'logo_layout':None})['logo_layout'])

    def test_transparent_tall_logo_fits_without_distortion(self):
        renderer=object.__new__(VideoLogoRenderer)
        with tempfile.TemporaryDirectory() as temp:
            logo=Path(temp)/'tall.png'; Image.new('RGBA',(100,1000),(255,0,0,128)).save(logo)
            prepared,x,y=renderer.prepare_overlay(logo,1920,1080,.5,60,'top_left',0,layout(0,0,60))
            self.assertEqual((prepared.size,x,y),((108,1080),0,0))
            self.assertEqual(prepared.getpixel((20,20))[3],64)

    def test_stale_preview_cannot_publish_or_remove_current_files(self):
        window=object.__new__(MainWindow); window._logo_editor_request='new'
        with tempfile.TemporaryDirectory() as temp:
            stale=Path(temp)/'stale.png'; stale.write_bytes(b'old')
            current=Path(temp)/'current.png'; current.write_bytes(b'new')
            window._logo_editor_files=(current,)
            window._logo_editor_preview={'request':'new'}
            window._accept_logo_editor_preview({'request':'old','files':(stale,)})
            self.assertFalse(stale.exists());self.assertTrue(current.exists())
            self.assertEqual(window._logo_editor_preview,{'request':'new'})

    def test_new_job_uses_saved_logo_file_opacity_and_layout(self):
        window=object.__new__(MainWindow)
        window.cfg={'logo_file':'C:/live-new.png','logo_opacity':.9,'logo_layout':layout(.9,.9)}
        window._creation_settings=lambda _:{}
        window.products=Mock(root=Path('C:/fixture/products'))
        job={'id':'JOB-X','logo_layout':layout(.2,.2),'media_finish_config':{
            'logo_file':'C:/saved.png','logo_opacity':.4,'logo_layout':layout(.2,.2)}}
        self.assertEqual(str(window._job_logo_file(job)).replace('\\','/'),'C:/saved.png')
        options=window._job_logo_options(job)
        self.assertEqual(options['opacity'],.4);self.assertEqual(options['layout']['portrait']['x'],.2)
        legacy=window._job_logo_options({'id':'JOB-OLD','media_finish_config':{'logo_opacity':.1}})
        self.assertNotIn('layout',legacy);self.assertEqual(legacy['opacity'],.9)

    def test_zero_margin_and_layout_round_trip_preferences(self):
        from tests.test_video_logo import DummyVar
        window=object.__new__(MainWindow);window.cfg={}
        for key,value in (('logo_file',''),('logo_opacity',80),('logo_size',18),('logo_position','ล่างขวา'),('logo_margin',28),('logo_status','')):
            setattr(window,key,DummyVar(value))
        with tempfile.TemporaryDirectory() as temp:
            logo=Path(temp)/'brand.png';Image.new('RGBA',(20,10),'red').save(logo)
            window.logo_file.set(str(logo))
            window._apply_logo_payload({'layout':layout(.3,.7),'margin':0,'position':'top_left'})
            with patch('ui.main_window.save_logo_settings'):
                saved=window._save_logo_preferences()
            self.assertEqual(saved['logo_margin'],0);self.assertEqual(saved['logo_position'],'top_left')
            self.assertEqual(saved['logo_layout']['portrait']['y'],.7)

    def test_real_frame_uses_original_dimensions_but_other_profile_is_template(self):
        import queue
        window=object.__new__(MainWindow);window.cfg={};window.events=queue.Queue()
        window._logo_source_video=lambda _:Path('owned.mp4')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);logo=root/'brand.png';Image.new('RGBA',(100,50),'red').save(logo)
            renderer=object.__new__(VideoLogoRenderer)
            renderer.video_info=Mock(return_value={'width':1280,'height':720})
            renderer.extract_preview_frame=Mock(return_value=Image.new('RGB',(1280,720),'white'))
            with patch('ui.main_window.ROOT',root),patch('ui.main_window.VideoLogoRenderer',return_value=renderer):
                window._preview_logo_editor_worker({'id':'JOB-X'},logo,{'layout':layout()},'landscape','real')
                _,real=window.events.get_nowait()
                window._preview_logo_editor_worker({'id':'JOB-X'},logo,{'layout':layout()},'portrait','sample')
                _,sample=window.events.get_nowait()
            self.assertTrue(real['real_frame']);self.assertEqual((real['width'],real['height']),(1280,720))
            self.assertFalse(sample['real_frame']);self.assertEqual((sample['width'],sample['height']),(720,1280))
            renderer.extract_preview_frame.assert_called_once_with(Path('owned.mp4'))

    def test_no_job_preview_uses_profile_and_never_extracts_video(self):
        import queue
        window=object.__new__(MainWindow);window.cfg={};window.events=queue.Queue()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); logo=root/'logo.png';Image.new('RGBA',(100,50),'red').save(logo)
            with patch('ui.main_window.ROOT',root),patch.object(VideoLogoRenderer,'extract_preview_frame') as extract:
                window._preview_logo_editor_worker(None,logo,{'layout':layout()},'landscape','owned')
            extract.assert_not_called()
            kind,value=window.events.get_nowait()
            self.assertEqual(kind,'logo_editor_preview');self.assertEqual(value['request'],'owned')
            self.assertFalse(value['real_frame']);self.assertEqual((value['width'],value['height']),(1920,1080))
            self.assertEqual(len(value['files']),2)

    def test_actual_renderer_and_fused_subtitle_positions(self):
        renderer=VideoLogoRenderer()
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);logo=folder/'logo.png';Image.new('RGBA',(100,50),'red').save(logo)
            subtitle=folder/'sub.srt';subtitle.write_text('1\n00:00:00,000 --> 00:00:00,200\n.\n',encoding='utf8')
            for w,h in ((720,1280),(1280,720)):
                with self.subTest(size=(w,h)):
                    source=folder/f'source-{w}.mp4'
                    result=run_cancellable([str(renderer.ffmpeg),'-v','error','-f','lavfi','-i',f'color=black:s={w}x{h}:r=10',
                        '-t','0.3','-c:v','libx264','-pix_fmt','yuv420p',str(source)],timeout=30)
                    self.assertEqual(result.returncode,0,result.stderr)
                    value=layout(.25,.25,20);opts={'opacity':1,'size_percent':20,'position':'bottom_right','margin':28,'layout':value}
                    output=folder/f'logo-{w}.mp4';renderer.render(source,logo,output,**opts)
                    fused=folder/f'fused-{w}.mp4';SubtitleVideoRenderer(str(renderer.ffmpeg)).render(source,subtitle,fused,logo_overlay={'file':str(logo),**opts})
                    expected=logo_geometry(value,w,h,100,50)
                    for target in (output,fused):
                        frame=renderer.extract_preview_frame(target,0)
                        # Sample the colored area bounding box; subtitles contain no red.
                        r,g,b=frame.split();red=r.point(lambda n:255 if n>180 else 0)
                        dark_g=g.point(lambda n:255 if n<80 else 0);dark_b=b.point(lambda n:255 if n<80 else 0)
                        bounds=ImageChops.multiply(ImageChops.multiply(red,dark_g),dark_b).getbbox()
                        self.assertIsNotNone(bounds)
                        for got,want in zip(bounds,(expected['x'],expected['y'],expected['x']+expected['width'],expected['y']+expected['height'])):
                            self.assertLessEqual(abs(got-want),2)

    def test_native_logo_editor(self):
        env=dict(os.environ);env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result=subprocess.run(['node','tests/logo_editor_ui.cjs'],cwd=ROOT,capture_output=True,text=True,encoding='utf8',env=env,timeout=50,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS native logo editor',result.stdout)
