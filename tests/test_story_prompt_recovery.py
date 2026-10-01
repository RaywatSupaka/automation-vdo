import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from core.story_prompt_recovery import record_recovery


class StoryPromptRecoveryTests(unittest.TestCase):
    def test_audit_is_idempotent_durable_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); (folder/'prompts').mkdir()
            body={'index':1,'run_id':'RUN-1','event':{'phase':'requested','round':1,
                'original_prompt':'original','request_id':'abc','reason':'service'}}
            job={'id':'STORY-TEST','scene_count':3}
            record_recovery(folder,job,body); record_recovery(folder,job,body)
            body['event']={**body['event'],'phase':'ready','prompt':'revised'}
            record_recovery(folder,job,body)
            rows=json.loads((folder/'prompts/scene_recovery.json').read_text())['scenes']['1']
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]['original_prompt'],'original')
            self.assertEqual(rows[1]['prompt'],'revised')
            self.assertFalse((folder/'job.json').exists())

    def test_invalid_scope_phase_and_budget_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for body in [{'index':4,'event':{}},{'index':True,'event':{}},
                         {'index':1,'event':{'phase':'ready','round':3}},
                         {'index':1,'event':{'phase':'unknown','round':1}},
                         {'index':1,'event':{'phase':'ready','round':1,'request_id':'a','helper_url':'https://evil.test'}}]:
                with self.subTest(body=body), self.assertRaises(ValueError):
                    record_recovery(Path(tmp),{'id':'STORY-TEST','scene_count':3},body)

    def test_actual_background_helper_ownership_and_budget(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run(['node','tests/story_repair_background_harness.js'],cwd=root,capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(json.loads(result.stdout)['ok'])


if __name__=='__main__': unittest.main()
