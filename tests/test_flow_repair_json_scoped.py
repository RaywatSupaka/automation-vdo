import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from core.story_prompt_recovery import record_recovery
from core.cancellable_process import hidden_process_kwargs

class FlowRepairScopedTests(unittest.TestCase):
    def test_actual_parser(self):
        result=subprocess.run(['node',str(Path(__file__).with_name('flow_repair_json_scoped.js'))],capture_output=True,text=True,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_completion_keeps_history_not_stale_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'prompts').mkdir()
            event=dict(phase='needs_review',round=1,request_id='r',error='old error',pause_reason='old reason')
            body=dict(index=1,event=event)
            job=dict(id='STORY-TEST',scene_count=1)
            record_recovery(folder,job,body,flow=True)
            event['phase']='completed';record_recovery(folder,job,body,flow=True)
            rows=json.loads((folder/'prompts'/'flow_recovery.json').read_text())['scenes']['1']
            self.assertEqual(rows[0]['error'],'old error')
            self.assertEqual(rows[-1]['error'],'')
            self.assertEqual(rows[-1]['pause_reason'],'')
