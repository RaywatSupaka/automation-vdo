import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from core.story_prompt_recovery import record_recovery


class FlowPromptRepairTests(unittest.TestCase):
    def test_fresh_project_transactions(self):
        result=subprocess.run(['node','tests/flow_fresh_project_harness.js'],cwd=Path(__file__).resolve().parents[1],
                              capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_extension_repair_transactions(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run(['node','tests/flow_prompt_repair_harness.js'],cwd=root,
                              capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_separate_idempotent_flow_ledger(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            body={'index':1,'run_id':'RUN-X','event':{'phase':'submitted','round':2,
                  'request_id':'R2','original_prompt':'original','prompt':'revised','fingerprint':'fp'}}
            job={'id':'JOB-X','scene_count':3}
            record_recovery(root,job,body,flow=True)
            record_recovery(root,job,body,flow=True)
            data=json.loads((root/'prompts/flow_recovery.json').read_text())
            self.assertEqual(len(data['scenes']['1']),1)
            self.assertFalse((root/'prompts/scene_recovery.json').exists())
            self.assertFalse((root/'job.json').exists())
            with self.assertRaises(ValueError):
                record_recovery(root,job,body)
