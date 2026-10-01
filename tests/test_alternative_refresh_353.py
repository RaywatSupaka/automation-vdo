import os
import subprocess
from pathlib import Path
from test_flow_replacement import FlowReplacementTests

ROOT=Path(__file__).resolve().parents[1]


class AlternativeRefresh353(FlowReplacementTests):
    def test_wait_event_does_not_downgrade_saved_image(self):
        self.act('begin')
        self.assertEqual(self.act('image_wait',wait_state='checking_empty')['replacement']['phase'],'requested')
        self.act('image',image=self.image())
        self.assertEqual(self.act('image_wait',wait_state='empty_after_refresh')['replacement']['phase'],'image_saved')
        with self.assertRaises(ValueError): self.act('image_wait',wait_state='invented')

    def test_actual_dom_and_background_refresh(self):
        result=subprocess.run(['node','tests/alternative_refresh_353.js'],cwd=ROOT,env=os.environ.copy(),
                              capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
