"""Approved B1/B2/C1: actual UI scripts and a temporary real queue, no providers."""
import ast
import copy
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.creation_queue import CreationQueue

ROOT = Path(__file__).resolve().parents[1]


class FunctionOverlapFormsTests(unittest.TestCase):
    def run_native(self, group):
        result = subprocess.run(['node', 'tests/function_overlap_forms.cjs', group], cwd=ROOT,
                                env=os.environ.copy(), capture_output=True, text=True,
                                encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dialogue_single_owner_all_current_scripts(self):
        self.run_native('dialogue')

    def test_subtitle_defaults_drafts_and_saved_choices_all_current_scripts(self):
        self.run_native('defaults')

    def test_long_buttons_policy_status_and_double_click_all_current_scripts(self):
        self.run_native('long')

    def test_actual_long_action_preserves_running_item_and_obeys_queue_policy(self):
        # Compile the actual dispatch branch, leaving its imports/queue calls
        # unchanged. All queue writes are beneath TemporaryDirectory only.
        source = ast.parse((ROOT / 'ui/main_window.py').read_text(encoding='utf-8'))
        branch = next(n for n in ast.walk(source) if isinstance(n, ast.If)
                      and ast.unparse(n.test) == "action == 'enqueue_long_video'")
        function = ast.FunctionDef(name='dispatch', args=ast.arguments(posonlyargs=[],
            args=[ast.arg(arg=x) for x in ('self', 'action', 'payload')],
            kwonlyargs=[], kw_defaults=[], defaults=[]), body=branch.body, decorator_list=[])
        namespace = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                     'actual enqueue_long_video source branch', 'exec'), namespace)
        for state in ('empty', 'paused', 'running'):
            for queue_only in (False, True):
                with self.subTest(state=state, queue_only=queue_only), tempfile.TemporaryDirectory() as temp:
                    queue = CreationQueue(temp)
                    active = None
                    if state != 'empty':
                        queue.enqueue('story', ['Existing synthetic'], settings={}, scene_count=6)
                        if state == 'running':
                            queue.resume()
                            active = copy.deepcopy(queue.claim_next())
                    app = SimpleNamespace(story_queue=queue, _creation_capture_settings=lambda payload: {})
                    payload = {'topic': 'New synthetic long', 'video_generation_mode': 'image_motion',
                               'long_video': {'version': 2, 'duration_seconds': 180, 'scene_count': 24},
                               'queue_only': queue_only}
                    result = namespace['dispatch'](app, 'enqueue_long_video', payload)
                    self.assertTrue(result['ok'])
                    self.assertEqual(result['story_queue']['paused'], state != 'running' or queue_only)
                    if active:
                        self.assertEqual(queue.running_item(), active)
                        self.assertFalse(queue.running_item().get('cancel_requested'))
                    new = queue.snapshot()['items'][-1]
                    self.assertEqual(new['status'], 'queued')
                    self.assertEqual(new['long_video']['scene_count'], 24)


if __name__ == '__main__':
    unittest.main()
