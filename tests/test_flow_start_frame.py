import os
import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs


class FlowStartFrameTests(unittest.TestCase):
    def test_stalled_picker_refresh_guards(self):
        result = subprocess.run(['node', 'tests/flow_picker_refresh_harness.js'],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, encoding='utf-8', timeout=30, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_actual_selector_and_initial_attachment_branch(self):
        env=dict(os.environ)
        env.setdefault('NODE_PATH',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result=subprocess.run(['node','tests/flow_start_frame_harness.js'],cwd=Path(__file__).resolve().parents[1],
                              env=env,capture_output=True,text=True,encoding='utf-8',timeout=30,**hidden_process_kwargs())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
