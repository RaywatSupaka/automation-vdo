import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from core.video_composer import MultiFlowComposer
from core.cancellable_process import hidden_process_kwargs


class VideoVoiceFitTests(unittest.TestCase):
    def test_retained_source_audio_and_voice_both_present(self):
        import array, math
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);c=MultiFlowComposer()
            def ff(*args):
                return subprocess.run([str(c.ffmpeg),'-v','error','-y',*map(str,args)],check=True,capture_output=True,timeout=90,**hidden_process_kwargs()).stdout
            clip=root/'source.mp4'
            ff('-f','lavfi','-i','color=blue:s=360x640:r=24:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',clip)
            voice=root/'voice.wav';ff('-f','lavfi','-i','sine=frequency=880:duration=4',voice)
            out=root/'mix.mp4'
            c.compose([clip,clip],out,voice,width=360,height=640,fps=24,audio_choices={'mode':'api','keep_video_audio':True})
            raw=ff('-ss',.5,'-i',out,'-t',1,'-vn','-ac',1,'-ar',16000,'-f','f32le','pipe:1')
            samples=array.array('f',raw)
            def magnitude(freq):
                return abs(sum(x*complex(math.cos(2*math.pi*freq*i/16000),math.sin(2*math.pi*freq*i/16000)) for i,x in enumerate(samples)))
            self.assertGreater(max(magnitude(f) for f in range(438,443)),10)
            self.assertGreater(max(magnitude(f) for f in range(878,883)),10)
            original_source=magnitude(440);original_voice=magnitude(880)
            quiet=root/'quiet.mp4'
            c.compose([clip,clip],quiet,voice,width=360,height=640,fps=24,audio_choices={'mode':'api','keep_video_audio':True,'video_audio_volume':0})
            samples=array.array('f',ff('-ss',.5,'-i',quiet,'-t',1,'-vn','-ac',1,'-ar',16000,'-f','f32le','pipe:1'))
            self.assertLess(magnitude(440),original_source*.1)
            self.assertAlmostEqual(magnitude(880)/original_voice,1,delta=.15)
            from core.flow_native_audio import compose_native
            native_full=root/'native-full.mp4';native_low=root/'native-low.mp4'
            compose_native([clip],native_full,str(c.ffmpeg),width=360,height=640)
            compose_native([clip],native_low,str(c.ffmpeg),width=360,height=640,video_audio_volume=20)
            samples=array.array('f',ff('-i',native_full,'-t',.8,'-vn','-ac',1,'-ar',16000,'-f','f32le','pipe:1'));full=magnitude(440)
            samples=array.array('f',ff('-i',native_low,'-t',.8,'-vn','-ac',1,'-ar',16000,'-f','f32le','pipe:1'))
            self.assertAlmostEqual(magnitude(440)/full,.2,delta=.03)
            single=c.compose([clip],root/'single.mp4',voice,width=360,height=640,fps=24,audio_choices={'mode':'api','keep_video_audio':True})
            self.assertEqual(single['clip_count'],1)
            self.assertAlmostEqual(single['duration'],4.75,delta=.2)

    def test_smooth_fit_keeps_moving_after_old_hold_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); composer=MultiFlowComposer()
            def ff(*args):
                return subprocess.run([str(composer.ffmpeg),'-v','error','-y',*map(str,args)],check=True,capture_output=True,timeout=90,**hidden_process_kwargs()).stdout
            clips=[]
            for i in range(2):
                clip=root/f'{i}.mp4'
                ff('-f','lavfi','-i','testsrc2=s=360x640:r=24:d=1','-c:v','libx264','-pix_fmt','yuv420p',clip)
                clips.append(clip)
            voice=root/'voice.wav';ff('-f','lavfi','-i','sine=duration=6',voice)
            out=root/'smooth.mp4'
            plan=composer.compose(clips,out,voice,width=360,height=640,fps=24,scene_durations=[1,1])
            self.assertEqual(plan['extend_mode'],'smooth')
            self.assertAlmostEqual(plan['duration'],6.75,delta=.2)
            # Previously the first1s clip froze after1.25s until3s.
            frames=[ff('-ss',t,'-i',out,'-frames:v',1,'-f','rawvideo','-pix_fmt','rgb24','pipe:1') for t in (1.7,2.5)]
            self.assertNotEqual(frames[0],frames[1])
    def test_landscape_loop_preserves_full_voice_without_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); composer=MultiFlowComposer()
            def ff(*args):
                subprocess.run([str(composer.ffmpeg),'-v','error','-y',*map(str,args)],check=True,capture_output=True,timeout=90,**hidden_process_kwargs())
            clips=[]
            for index,color in enumerate(('red','blue')):
                clip=root/f'{index}.mp4'
                ff('-f','lavfi','-i',f'color={color}:s=1280x720:r=24:d=1','-c:v','libx264','-pix_fmt','yuv420p',clip)
                clips.append(clip)
            voice=root/'voice.wav'; ff('-f','lavfi','-i','sine=duration=5',voice)
            result=composer.compose(clips,root/'out.mp4',voice,width=1280,height=720,fps=24,extend_mode='loop',transition_sec=0)
            self.assertAlmostEqual(result['duration'],5.75,delta=.2)
            self.assertEqual(result['extend_mode'],'loop')
            from core.video_logo import VideoLogoRenderer
            info=VideoLogoRenderer().video_info(root/'out.mp4')
            self.assertEqual((info['width'],info['height']),(1280,720))
    def test_short_and_long_voice_keep_all_scenes_and_full_voice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            composer = MultiFlowComposer()
            def ff(*args):
                return subprocess.run([str(composer.ffmpeg),"-v","error","-y",*map(str,args)],
                    check=True,capture_output=True,timeout=90,**hidden_process_kwargs()).stdout
            clips=[]
            for color in ("red","green","blue"):
                clip=root/f"{color}.mp4"
                ff("-f","lavfi","-i",f"color=c={color}:s=360x640:r=24:d=2","-c:v","libx264","-pix_fmt","yuv420p",clip)
                clips.append(clip)
            for duration in (3,8):
                with self.subTest(duration=duration):
                    voice=root/f"voice{duration}.wav"
                    ff("-f","lavfi","-i",f"sine=frequency=440:duration={duration}",voice)
                    out=root/f"final{duration}.mp4"
                    plan=composer.compose(clips,out,voice,width=360,height=640,fps=24,scene_durations=[1,1,1])
                    self.assertAlmostEqual(plan["duration"],duration+0.75,delta=0.2)
                    self.assertEqual(len(plan["scene_output_durations"]),3)
                    self.assertAlmostEqual(sum(plan["scene_output_durations"]),duration+0.75)
                    self.assertEqual(plan["timing_method"],"planned_scene_weights")
                    elapsed=0
                    for index, seconds in enumerate(plan["scene_output_durations"]):
                        raw=ff("-ss",elapsed+seconds/2,"-i",out,"-frames:v",1,"-f","image2pipe","-vcodec","png","pipe:1")
                        pixel=Image.open(io.BytesIO(raw)).convert("RGB").getpixel((180,320))
                        self.assertEqual(pixel.index(max(pixel)),index, "scene missing or wrong order")
                        elapsed+=seconds
                    # There is still non-silent narration immediately before its
                    # original end; bounded video fitting must not trim speech.
                    audio=ff("-ss",duration-0.2,"-i",out,"-t",0.1,"-vn","-f","s16le","pipe:1")
                    self.assertTrue(any(audio))
