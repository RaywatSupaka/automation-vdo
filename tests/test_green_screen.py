import io
import os
import json
import logging
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import patch, Mock
from types import SimpleNamespace

from core.green_screen import GreenLibrary, green_options, render_green, finish_product_green
from core.audio_mixer import AudioMixer
from core.video_intro import IntroLibrary, inspect_video
from core.cancellable_process import run_cancellable, hidden_process_kwargs, OperationCancelled
from core.creation_queue import CreationQueue, clean_settings
from core.drama_options import drama_render_options
from core.local_bridge import LocalBridge
from core.product_manager import ProductManager


class GreenTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='smartflow-green-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.library=GreenLibrary(self.root)
        self.ffmpeg=str(AudioMixer().ffmpeg)

    def video(self,name,duration=1,color='blue',effect=False,audio=True,size='192x108'):
        path=self.root/name
        cmd=[self.ffmpeg,'-v','error','-y','-f','lavfi','-i',f'color=c={"0x00ff00" if effect else color}:s={size}:r=24:d={duration}']
        if audio:cmd+=['-f','lavfi','-i',f'sine=frequency={880 if effect else 440}:sample_rate=48000:duration={duration}']
        if effect:cmd+=['-vf',f'drawbox=x=10:y=10:w=40:h=40:color={color}:t=fill']
        cmd+=['-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(path)]
        result=run_cancellable(cmd,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        return path

    def options(self, count=1):
        clips=[]
        for i,color in enumerate(['red','yellow','white'][:count]):
            asset=self.library.import_file(self.video(f'fx-{i}.mp4',effect=True,color=color))['asset']
            clips.append({'file':asset['file']})
        return green_options({'enabled':True,'clips':clips,'opacity':1})

    def binary(self,args):
        result=subprocess.run([self.ffmpeg,'-v','error',*args],capture_output=True,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stderr)
        return result.stdout

    def pixel(self,path,second,x=20,y=20):
        data=self.binary(['-ss',str(second),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
        pos=(y*inspect_video(path)['width']+x)*3
        return tuple(data[pos:pos+3])

    def test_ordered_one_two_three_loops_and_effect_audio_never_used(self):
        source=self.video('base.mp4',duration=4)
        original_audio=self.binary(['-i',str(source),'-vn','-f','s16le','pipe:1'])
        for count in (1,2,3):
            options=self.options(count)
            output,plan=render_green(self.root,source,self.root/f'out{count}.mp4',options)
            self.assertAlmostEqual(inspect_video(output)['duration'],4,places=1)
            self.assertEqual(self.binary(['-i',str(output),'-vn','-f','s16le','pipe:1']),original_audio)
            for second in (.5,1.5,2.5,3.5):
                color=self.pixel(output,second)
                index=int(second)%count
                self.assertGreater(color[0],180)
                self.assertLess(color[2],70) if index<2 else self.assertGreater(color[2],180)
                self.assertLess(color[1],70) if index==0 else self.assertGreater(color[1],180)
            blue=self.pixel(output,.5,150,80)
            self.assertGreater(blue[2],180);self.assertLess(blue[1],50)
            self.assertEqual(plan['audio'],'base_only_effect_audio_discarded')

    def test_no_audio_disabled_cancel_and_failed_render_preserve_output(self):
        options=self.options()
        source=self.video('silent.mp4',duration=.5,audio=False)
        output=self.root/'out.mp4'
        render_green(self.root,source,output,options)
        self.assertFalse(inspect_video(output)['has_audio'])
        old=output.read_bytes()
        event=threading.Event();event.set()
        with self.assertRaises(OperationCancelled):render_green(self.root,source,output,options,cancel_event=event)
        with patch('core.green_screen.run_cancellable',return_value=Mock(returncode=1)):
            with self.assertRaises(ValueError):render_green(self.root,source,output,options)
        self.assertEqual(output.read_bytes(),old)
        self.assertEqual(render_green(self.root,source,output,None)[0],source)

    def test_validation_defaults_and_queue_snapshot_isolation(self):
        options=self.options(2)
        targets={'story':True,'drama':False,'product':True}
        state=self.library.save(options,targets)
        self.assertEqual(GreenLibrary(self.root).state(),state)
        self.assertEqual(IntroLibrary(self.root).state()['assets'],[])
        queue=CreationQueue(self.root/'queue')
        queued=queue.enqueue('story',['เรื่องทดสอบ'],settings={'green_options':options})['items'][0]
        self.library.save({**options,'opacity':.2},{})
        self.assertEqual(queue.get_item(queued['queue_id'])['settings']['green_options'],options)
        self.assertEqual(drama_render_options({'green_options':options})['green_options'],options)
        self.assertNotIn('green_options',clean_settings({}))
        for value in [{'enabled':True}, {'clips':[{}]*4}, {'enabled':'yes'}, {'opacity':float('nan')},
                      {'clips':[{'file':'../bad.mp4'}]}, {'clips':[options['clips'][0]]*2},
                      {'clips':[{'file':options['clips'][0]['file'],'color':'x;evil'}]}]:
            with self.assertRaises(ValueError):green_options(value)

    def test_upload_and_preview_routes_with_real_media(self):
        source=self.video('fx.mp4',effect=True,color='red',audio=True)
        bridge=LocalBridge('127.0.0.1',0,ProductManager(self.root),logging.getLogger('green-test'),desktop_green_library=self.library).start()
        self.addCleanup(bridge.stop)
        base=f'http://127.0.0.1:{bridge.server.server_address[1]}'
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req=urllib.request.Request(base+'/api/desktop/green-upload',data=source.read_bytes(),headers={'Content-Type':'application/octet-stream','X-File-Name':'test.mp4','Origin':base})
        with opener.open(req,timeout=20) as response:result=json.load(response)
        self.assertTrue(result['asset']['file'].startswith('assets/screenfx/'))
        self.assertEqual(IntroLibrary(self.root).state()['assets'],[])
        preview=self.library.preview({'clips':[{'file':result['asset']['file']}]})
        with opener.open(base+preview['url'],timeout=10) as response:self.assertGreater(len(response.read()),100)
        token=preview['url'].split('=')[-1]
        self.assertFalse(inspect_video(self.root/'workspace'/'preview'/'screenfx'/(token+'.mp4'))['has_audio'])

    def test_real_story_finisher_green_above_intro_repeat_and_failure(self):
        from core.story_finisher import finish_story_media
        source=self.video('base.mp4',duration=2)
        intro=IntroLibrary(self.root).import_file(self.video('intro.mp4',duration=1,color='blue'))['asset']
        green={**self.options(),'opacity':.5}
        folder=self.root/'stories'/'STORY-GREEN';(folder/'captions').mkdir(parents=True);(folder/'videos').mkdir()
        job={'green_options':green,'intro_options':{'enabled':True,'file':intro['file']},
             'audio_choices':{'mode':'flow_original','subtitle':False,'music':False,'sfx':False}}
        manager=SimpleNamespace(root=folder.parent,get=lambda _:job)
        config={'logo_file':'absent.png','audio_background_enabled':False,'audio_sfx_enabled':False}
        first,plan=finish_story_media(self.root,manager,'STORY-GREEN',source,config)
        self.assertTrue(plan['green_screen']['enabled'])
        self.assertAlmostEqual(plan['duration'],3.,places=1)
        before=first.read_bytes();original_pixel=self.pixel(first,.2);pixel=self.pixel(first,plan['intro']['insert_at']+.2)
        self.assertGreater(pixel[0],70)  # Overlay covers the inserted intro too.
        with patch('core.green_screen.render_green',side_effect=ValueError('GREEN_SCREEN_REVIEW')):
            with self.assertRaises(ValueError):finish_story_media(self.root,manager,'STORY-GREEN',source,config)
        self.assertEqual(first.read_bytes(),before)
        second,_=finish_story_media(self.root,manager,'STORY-GREEN',source,config)
        self.assertEqual(self.pixel(second,.2),original_pixel)
        self.assertAlmostEqual(inspect_video(second)['duration'],3.,places=1)

    def test_product_repeat_uses_pre_effect_source(self):
        from core.atomic_json import AtomicJsonFile
        products=ProductManager(self.root)
        folder=products.root/'JOB-GREEN';(folder/'videos').mkdir(parents=True)
        source=self.video('base.mp4',duration=1)
        target=folder/'videos'/'base.mp4';target.write_bytes(source.read_bytes())
        options={**self.options(),'opacity':.5}
        AtomicJsonFile(folder/'job.json').write({'id':'JOB-GREEN','video_path':'videos/base.mp4','green_options':options})
        output=finish_product_green(products,'JOB-GREEN',self.root)
        before=self.pixel(output,.5)
        output=finish_product_green(products,'JOB-GREEN',self.root)
        self.assertEqual(self.pixel(output,.5),before)
        from core.video_library import VideoLibrary
        manifest=products.get_job('JOB-GREEN')
        manifest.update(video_status='ready',audio_mix_status='ready',audio_mix_path='videos/base.mp4')
        item=VideoLibrary(self.root)._item('product',folder/'job.json',manifest)
        self.assertEqual(Path(item['path']),output)

    def test_story_capture_binds_immediate_queue_and_drama_without_old_defaults(self):
        import textwrap
        options=self.options()
        code=(Path(__file__).parents[1]/'ui'/'main_window.py').read_text(encoding='utf-8')
        start=code.index('            flow_source = ((drama_context')
        block='from core.flow_settings import flow_settings\n'+textwrap.dedent(code[start:code.index('            self.stories._save(job)',start)])
        app=SimpleNamespace(cfg={},_story_green_options=options,_creation_settings=lambda:{'green_options':options},
                            _story_intro_options=None,_story_flow_settings={},_story_ai_cover_options={})
        for queued,drama in ((False,False),(True,False),(False,True)):
            context={'self':app,'queue_item_id':'Q' if queued else '',
                'drama_context':{'render_options':{'green_options':options}} if drama else None,
                'flow_smoke_test':False,'job':{}}
            with patch('ui.green_screen.ROOT',self.root):exec(block,context)
            self.assertEqual(context['job']['green_options'],options)
        app._creation_settings=lambda:{}
        context={'self':app,'queue_item_id':'OLD','drama_context':None,'flow_smoke_test':False,'job':{}}
        with patch('ui.green_screen.ROOT',self.root):exec(block,context)
        self.assertFalse(context['job']['green_options']['enabled'])

    def test_actual_ui_script(self):
        fixture=self.video('preview-browser.mp4',duration=1,effect=True,color='red',audio=True)
        result=subprocess.run(['node',str(Path(__file__).with_name('green_screen_ui_harness.js')),str(fixture)],
            capture_output=True,text=True,encoding='utf-8',timeout=60,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        print(result.stdout.strip())

    def test_vertical_fit_and_hide_keeps_queued_asset_bytes(self):
        options=self.options()
        source=self.video('vertical.mp4',duration=.5,size='108x192',audio=False)
        for fit in ('contain','cover'):
            output,_=render_green(self.root,source,self.root/(fit+'.mp4'),{**options,'fit':fit})
            info=inspect_video(output)
            self.assertEqual((info['width'],info['height']),(108,192))
            if fit=='contain':self.assertGreater(self.pixel(output,.2,1,1)[2],180)
        self.library.save(options,{'story':True})
        with self.assertRaises(ValueError):self.library.remove_from_library(options['clips'][0]['file'])
        self.library.save({'clips':[]},{})
        state=self.library.remove_from_library(options['clips'][0]['file'])
        self.assertEqual(state['assets'],[])
        self.assertTrue(self.library.resolve(options['clips'][0]['file']).is_file())
        self.assertTrue(self.library.validate(options)['enabled'])


if __name__=='__main__':unittest.main()
