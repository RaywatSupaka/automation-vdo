import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs
from core.flow_motion_plan import motion_plan_action


class GeminiMotionOwnershipTests(unittest.TestCase):
    def test_current_user_required_for_send_and_answer(self):
        result = subprocess.run(['node',str(Path(__file__).with_name('gemini_motion_ownership_harness.js'))],
            capture_output=True,text=True,encoding='utf-8',timeout=25,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout),{'ok':True,'cases':11})

    def test_passive_review_keeps_invalid_answer_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'generated').mkdir();(root/'generated/selling_image_02.png').write_bytes(b'fixture')
            job={'id':'JOB-X','image_ai_provider':'gemini'}
            def call(action,**extra):
                return motion_plan_action(root,job,{'action':action,'index':2,'provider':'gemini',**extra})
            ctx=call('status')['context'];key=ctx['context_id']
            call('claim',context_id=key,request='owned request')
            wrong={'job_id':'JOB-X','index':1,'context_id':'scene-one','prompt':'camera moves gently towards the same floor chair in the reference',
                   'needs_review':False,'reference_compatible':True,'material_change':False}
            rejected=call('review',context_id=key,result=wrong)
            self.assertFalse(rejected['validation']['repairable'])
            correct={**wrong,'index':2,'context_id':key}
            recovered=call('review',context_id=key,result=correct)['record']
            self.assertEqual(recovered['prior_invalid_answer'],wrong)
            self.assertEqual(recovered['validation']['errors'],[])
            self.assertEqual(call('save',context_id=key,result=correct)['record']['phase'],'ready')
