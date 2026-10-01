import base64
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from core.atomic_json import AtomicJsonFile
from core.flow_replacement import replacement_action, apply_replacement


class FlowReplacementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        (self.folder/'generated').mkdir()
        Image.new('RGB',(288,512),'red').save(self.folder/'generated/scene_01.png')
        self.job = dict(id='STORY-TEST',image_ai_provider='gemini',generated_images=['generated/scene_01.png'],
                        scene_prompts=['A hand collects a bottle.'],scene_narrations=['Original narration'])
        self.body = dict(index=1,request_id='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',run_id='RUN-1',replacement_action='begin')
        AtomicJsonFile(self.folder/'prompts/flow_recovery.json').write({'scenes':{'1':[dict(run_id='RUN-1',fingerprint='fp',reason='failed')]}})

    def image(self, color='blue', size=(288,512)):
        out=io.BytesIO();Image.new('RGB',size,color).save(out,format='PNG')
        return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()

    def act(self, action, **extra):
        return replacement_action(self.folder,self.job,{**self.body,'replacement_action':action,**extra})

    def test_full_checkpoint_and_package_preserve_original(self):
        original=(self.folder/'generated/scene_01.png').read_bytes()
        self.act('begin');self.act('begin')
        self.act('image',image=self.image())
        candidate=dict(prompt='Vertical 9:16. A hand gently picks up a bottle in a clean recycling area. All spoken dialogue must be in Thai only.',needs_review=False,reference_compatible=True,material_change=False)
        self.act('ready',candidate=candidate);self.act('ready',candidate=candidate)
        self.act('image',image=self.image())  # Delayed ACK must not downgrade ready.
        package={};apply_replacement(self.folder,self.job,1,package)
        self.assertTrue(package['motion_prompt_ready']);self.assertEqual(package['video_prompt'],candidate['prompt'])
        self.assertNotEqual(package['image_files'],self.job['generated_images'])
        self.assertEqual(original,(self.folder/'generated/scene_01.png').read_bytes())
        self.assertEqual(self.job['scene_narrations'],['Original narration'])

    def test_budget_survives_new_run_and_request(self):
        self.act('begin');self.body.update(run_id='RUN-2',request_id='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb')
        with self.assertRaises(ValueError):self.act('begin')

    def test_no_proven_failure_no_generation(self):
        self.body['run_id']='OTHER'
        with self.assertRaises(ValueError):self.act('begin')

    def test_reject_material_change_and_bad_image(self):
        self.act('begin')
        with self.assertRaises(ValueError):self.act('image',image=self.image(size=(512,288)))
        self.act('image',image=self.image())
        for flag in ['needs_review','reference_compatible','material_change']:
            c=dict(prompt='A safe 9:16 image with a slow camera movement over a recycling bin.',needs_review=False,reference_compatible=True,material_change=False)
            c[flag]=not c[flag]
            with self.subTest(flag=flag),self.assertRaises(ValueError):self.act('ready',candidate=c)
        package={};apply_replacement(self.folder,self.job,1,package);self.assertEqual(package,{})

    def test_no_overwrite_and_context_change(self):
        self.act('begin');self.act('image',image=self.image())
        with self.assertRaises(ValueError):self.act('image',image=self.image('green'))
        self.job['scene_prompts']=['Different story']
        with self.assertRaises(ValueError):self.act('image',image=self.image())

    def test_actual_helper_stages(self):
        result=subprocess.run(['node','tests/flow_alternative_harness.js'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_finished_scene_is_not_replaced(self):
        self.job['flow_clips']={'1':'flow/scene-1.mp4'}
        with self.assertRaises(ValueError):self.act('begin')

    def test_product_and_wide_alternative(self):
        self.job.update(id='JOB-TEST',long_video=True,image_ai_provider='chatgpt')
        self.act('begin');self.act('image',image=self.image(size=(512,288)))
        c=dict(prompt='Horizontal 16:9. The bag rests on a table as the camera moves closer. All spoken dialogue must be in Thai only.',
               needs_review=False,reference_compatible=True,material_change=False)
        self.act('ready',candidate=c)
        package={};apply_replacement(self.folder,self.job,1,package)
        self.assertEqual(package['video_prompt'],c['prompt'])
