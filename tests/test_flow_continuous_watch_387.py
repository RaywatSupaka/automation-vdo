"""Replay the current desktop waiter; no Chrome or provider requests."""
import queue
import unittest
from unittest.mock import patch

from core.cancellable_process import OperationCancelled
from ui.main_window import MainWindow


class Clock:
    def __init__(self):
        self.now = 1000
        self.cancel = False

    def is_set(self):
        return self.cancel

    def wait(self, seconds):
        self.now += seconds
        return self.cancel


class Bridge:
    REQUIRED_EXTENSION_VERSION = 'fixture'

    def __init__(self, clock, rows):
        self.clock, self.rows = clock, iter(rows)
        self.commands = []
        self.current = {}

    def extension_status(self):
        self.current = next(self.rows, self.current)
        row = dict(self.current)
        if row.pop('fresh', False):
            row['flow_observation'] = {'received_at': self.clock.now, 'acknowledged': True,
                'identity': ['STORY-FIXTURE', 'RUN', 7], 'scene_index': 5}
        return {'clients': [{'version': 'fixture', 'flow_job_id': 'STORY-FIXTURE',
            'flow_run_id': 'RUN', 'flow_tab_id': 7, 'flow_shot_index': 5,
            'flow_page_url': 'https://flow.google.com/project/current', **row}]}

    def queue_extension_command(self, action, job, shot):
        self.commands.append(action)
        return {'id': 'fixture'}


class ContinuousWatch387Tests(unittest.TestCase):
    def test_actual_extension_timer(self):
        import subprocess
        from pathlib import Path
        from core.cancellable_process import hidden_process_kwargs
        result = subprocess.run(['node', 'tests/flow_continuous_watch_387.js'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
            encoding='utf-8', timeout=30, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bridge_transports_and_clears_continuous_observation_flag(self):
        import tempfile, logging, json, urllib.request
        from core.local_bridge import LocalBridge
        from core.product_manager import ProductManager
        with tempfile.TemporaryDirectory() as root:
            bridge = LocalBridge('127.0.0.1', 0, ProductManager(root), logging.getLogger('flow387-test')).start()
            def post(path, data):
                req = urllib.request.Request(f'http://127.0.0.1:{bridge.server.server_address[1]}' + path,
                    data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req) as response:
                    return json.load(response)
            try:
                post('/api/extension/heartbeat', {'client_id': 'test', 'version': bridge.REQUIRED_EXTENSION_VERSION})
                progress = {'client_id': 'test', 'job_id': 'STORY-X', 'run_id': 'RUN-TEST', 'tab_id': 7,
                    'shot_index': 5, 'step': 'generation_in_progress', 'observed_at_ms': 200, 'continuous_wait': True}
                self.assertTrue(post('/api/extension/progress', progress)['ok'])
                client = bridge.extension_status()['client']
                self.assertTrue(client['flow_continuous_wait'])
                self.assertTrue(client['flow_observation']['acknowledged'])
                self.assertEqual(client['flow_observation']['scene_index'], 5)
                progress.pop('continuous_wait')
                post('/api/extension/progress', {**progress, 'observed_at_ms': 201})
                self.assertFalse(bridge.extension_status()['client']['flow_continuous_wait'])
            finally:
                bridge.stop()

    def run_wait(self, rows, *, timeout=1800, clock=None):
        clock = clock or Clock()
        window = MainWindow.__new__(MainWindow)
        window.bridge = Bridge(clock, rows)
        window.events = queue.Queue()
        window._product_pipeline_job_id = ''
        self.bridge = window.bridge
        with patch('ui.main_window.time.monotonic', side_effect=lambda: clock.now), \
                patch('ui.main_window.time.time', side_effect=lambda: clock.now):
            return window._wait_flow_step('STORY-FIXTURE', 5, timeout=timeout, cancel_event=clock)

    def test_eight_rounds_do_not_add_unknown_polls_across_attempts(self):
        rows = []
        for attempt in range(8):
            rows += [{'flow_step': 'generation_status_unknown', 'flow_message': 'unknown',
                'flow_repair_request_id': f'repair-{attempt}',
                'flow_page_url': f'https://flow.google.com/project/p-{attempt}'}] * 18
        rows.append({'flow_step': 'generation_complete'})
        self.assertEqual(self.run_wait(rows)['flow_step'], 'generation_complete')
        self.assertEqual(self.bridge.commands, ['inspect_flow'] * 8)

    def test_fresh_owned_wait_exceeds_two_hours_without_stop_or_new_send(self):
        rows = [{'flow_step': 'generation_in_progress', 'flow_message': 'waiting',
            'flow_continuous_wait': True, 'fresh': True}] * 2500
        rows.append({'flow_step': 'generation_complete'})
        self.assertEqual(self.run_wait(rows, timeout=20)['flow_step'], 'generation_complete')
        self.assertTrue(all(action == 'inspect_flow' for action in self.bridge.commands))

    def test_stale_or_wrong_owner_observation_does_not_extend_forever(self):
        for observation in [{}, {'received_at': 999, 'acknowledged': True,
                'identity': ['ANOTHER', 'RUN', 7], 'scene_index': 5}]:
            with self.subTest(observation=observation):
                with self.assertRaises(TimeoutError) as caught:
                    self.run_wait([{'flow_step': 'generation_in_progress', 'flow_message': 'stale',
                        'flow_continuous_wait': True, 'flow_observation': observation}], timeout=20)
                self.assertTrue(caught.exception.flow_retry_forbidden)
                self.assertNotIn('stop_flow_generation', self.bridge.commands)

    def test_review_still_takes_priority_over_continuous_marker(self):
        with self.assertRaisesRegex(RuntimeError, 'FLOW_SEND_REVIEW') as caught:
            self.run_wait([{'flow_step': 'error', 'flow_failure_code': 'FLOW_SEND_REVIEW',
                'flow_continuous_wait': True, 'fresh': True}])
        self.assertTrue(caught.exception.flow_retry_forbidden)
        self.assertEqual(self.bridge.commands, [])

    def test_user_cancel_still_exits_continuous_wait(self):
        clock = Clock()
        def rows():
            yield {'flow_step': 'generation_in_progress', 'flow_continuous_wait': True, 'fresh': True}
            clock.cancel = True
            yield {'flow_step': 'generation_in_progress', 'flow_continuous_wait': True, 'fresh': True}
        with self.assertRaises(OperationCancelled):
            self.run_wait(rows(), clock=clock)


if __name__ == '__main__':
    unittest.main()
