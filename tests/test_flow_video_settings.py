"""Offline settings DOM and paired desktop recovery; no live sessions or credits."""
import json
import os
import subprocess
import unittest
from pathlib import Path
from itertools import count
from queue import Queue
from unittest.mock import patch
from core.cancellable_process import hidden_process_kwargs
from core.product_pipeline import product_runtime_recovery_action
from core.story_pipeline import story_recovery_action
from ui.main_window import MainWindow
from test_flow_attachment_fallback_worker import PassiveBridge


class FlowVideoSettingsTests(unittest.TestCase):
    def test_actual_settings_handler_with_browser_dom(self):
        env = dict(os.environ)
        env.setdefault('NODE_PATH', str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result = subprocess.run(['node', str(Path(__file__).with_name('flow_video_settings_harness.js'))],
                                capture_output=True, text=True, encoding='utf-8', timeout=60, env=env,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'ok': True, 'cases': 64})

    def test_settings_review_preserves_media_and_never_auto_retries(self):
        message = 'FLOW_VIDEO_SETTINGS_REVIEW Google Flow'
        self.assertEqual(product_runtime_recovery_action({'ai_status':'ready','automation_status':'error'},message),'')
        self.assertEqual(story_recovery_action({'status':'error','scene_count':6},message),'')
        window = MainWindow.__new__(MainWindow)
        window.events = Queue()
        window._product_pipeline_job_id = ''
        window.bridge = PassiveBridge([{'flow_step':'error','flow_failure_code':'FLOW_VIDEO_SETTINGS_REVIEW', 'flow_message':message}])
        ticks = count(1,2)
        with patch('ui.main_window.time.monotonic',side_effect=lambda:next(ticks)), patch('ui.main_window.time.sleep'):
            with self.assertRaises(RuntimeError) as caught:
                window._wait_flow_step('JOB-ATTACH',2,timeout=200)
        self.assertTrue(caught.exception.flow_retry_forbidden)
        self.assertEqual(window.bridge.commands,[])
