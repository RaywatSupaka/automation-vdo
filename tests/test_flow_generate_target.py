"""Click-target regressions and real desktop wait; no live browser or jobs."""
import json
import subprocess
import unittest
from itertools import count
from pathlib import Path
from queue import Queue
from unittest.mock import patch

from core.cancellable_process import hidden_process_kwargs
from core.product_pipeline import product_runtime_recovery_action
from ui.main_window import MainWindow
from test_flow_attachment_fallback_worker import PassiveBridge


class FlowGenerateTargetTests(unittest.TestCase):
    def test_actual_extension_target_and_high_demand_wait(self):
        result = subprocess.run(['node', str(Path(__file__).with_name('flow_generate_target_harness.js'))],
                                capture_output=True, text=True, encoding='utf-8', timeout=25,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'ok': True, 'cases': 37})

    def test_desktop_send_review_never_enters_generation_retry_or_local_fallback(self):
        window = MainWindow.__new__(MainWindow)
        window.events = Queue()
        window._product_pipeline_job_id = ''
        window.bridge = PassiveBridge([{'flow_step': 'error', 'flow_failure_code': 'FLOW_SEND_REVIEW',
                                       'flow_message': 'FLOW_SEND_REVIEW • หยุดอย่างปลอดภัย'}])
        ticks = count(1, 2)
        with patch('ui.main_window.time.monotonic', side_effect=lambda: next(ticks)), patch('ui.main_window.time.sleep'):
            with self.assertRaises(RuntimeError) as caught:
                window._wait_flow_step('JOB-ATTACH', 2, timeout=200)
        self.assertTrue(caught.exception.flow_retry_forbidden)
        self.assertFalse(getattr(caught.exception, 'flow_policy_terminal', False))
        self.assertEqual(window.bridge.commands, [])

    def test_runtime_recovery_does_not_auto_resume_unknown_send(self):
        self.assertEqual(product_runtime_recovery_action(
            {'ai_status': 'ready', 'automation_status': 'error'}, 'Google Flow FLOW_SEND_REVIEW'), '')


if __name__ == '__main__':
    unittest.main()
