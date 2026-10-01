import copy
import os
import subprocess
import unittest
from pathlib import Path
from core.product_continue import product_continue_action

ROOT=Path(__file__).resolve().parents[1]

class ProductContinueTests(unittest.TestCase):
    def test_cancelled_product_keeps_identity_and_settings(self):
        for ident,extra,action in [('JOB-OLD',{},'create_product'),('STORY-NEW',{'product_story':{'version':1}},'retry_story')]:
            job={'id':ident,'status':'cancelled','image_ai_provider':'gemini','flow_settings':{'model':'saved'},**extra}
            before=copy.deepcopy(job)
            self.assertEqual(product_continue_action(job),(action,{'job_id':ident}))
            self.assertEqual(job,before)

    def test_finished_deleted_and_nonproduct_rejected(self):
        for job in [{'id':'STORY-OTHER'},{'id':'JOB-X','story_source_only':True},
                    {'id':'JOB-X','status':'deleted'},{'id':'JOB-X','readiness':{'ready':True}},
                    {'id':'STORY-X','product_story':{'version':1},'status':'ready','video_status':'ready'}]:
            with self.subTest(job=job),self.assertRaises(ValueError):product_continue_action(job)

    def test_ui(self):
        result=subprocess.run(['node','tests/product_continue_ui.js'],cwd=ROOT,env=os.environ.copy(),
                              capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
