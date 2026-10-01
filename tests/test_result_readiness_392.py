import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs
from test_ai_send_error_log import AISendErrorLogTests


class ResultReadiness392Tests(unittest.TestCase):
    def test_actual_dom_and_guards(self):
        result = subprocess.run(['node', 'tests/result_readiness_392.cjs'],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding='utf-8',
                                timeout=45, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class FlowOrigin392Tests(AISendErrorLogTests):
    def test_flow_origin_beats_relaying_ai_snapshot(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        flow = dict(ai_job_id='STORY-X', ai_run_id='RUN', flow_run_id='RUN',
                    flow_job_id='STORY-X', flow_step='error', flow_failure_code='FLOW_REPAIR_REVIEW',
                    flow_message='prompt_content_mismatch', flow_page_url='https://flow.google.com/project/current',
                    flow_page_excerpt='safe flow diagnostic', ai_page_url='https://chatgpt.com/c/relay',
                    ai_page_excerpt='irrelevant AI snapshot')
        for changed, expected in [({}, True), ({'flow_job_id': 'OTHER'}, False),
                                  ({'flow_run_id': 'OLD'}, False), ({'flow_step': 'generation_in_progress'}, False)]:
            client = {**flow, **changed}
            window = SimpleNamespace(bridge=SimpleNamespace(extension_status=lambda: {'clients':[client]}),
                                     log=Mock(), _desktop_set_notice=Mock())
            self.capture(window,'STORY-X','FLOW_REPAIR_REVIEW • paused','Story / ChatGPT Web / Google Flow')
            output=window._automation_error_log['text']
            self.assertEqual('https://flow.google.com/project/current' in output, expected)

    def test_unavailable_bridge_still_captures_error(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        for bridge in [Mock(side_effect=RuntimeError('offline')), Mock(return_value=None)]:
            window = SimpleNamespace(bridge=SimpleNamespace(extension_status=bridge),
                                     log=Mock(), _desktop_set_notice=Mock())
            self.capture(window,'STORY-X','FLOW_REPAIR_REVIEW • paused','Story / ChatGPT Web / Google Flow')
            self.assertIn('FLOW_REPAIR_REVIEW', window._automation_error_log['text'])
