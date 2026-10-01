import threading
import unittest
from itertools import count
from queue import Queue
from types import SimpleNamespace
from unittest import mock

from ui.main_window import MainWindow


class StoryBrowserRecoveryMessageTests(unittest.TestCase):
    def window(self, current_percent):
        window = MainWindow.__new__(MainWindow)
        window._story_pipeline_job_id = 'STORY-TEST'
        window._story_cancel_event = threading.Event()
        window._story_phase_owner = (None, 0)
        window._story_progress_value = mock.Mock()
        window._story_progress_value.get.return_value = current_percent
        window._story_progress_percent = mock.Mock()
        window._story_progress_message = mock.Mock()
        window._story_progress_detail = mock.Mock()
        window.story_job_id = mock.Mock()
        window.story_status = mock.Mock()
        window.status = mock.Mock()
        window._write_console = mock.Mock()
        window._story_progress_stage_widgets = {}
        return window

    def test_same_job_recovery_updates_message_without_regressing_percent(self):
        window = self.window(23)
        window._update_story_progress({'stage':'chatgpt','step':'recovering_response',
            'percent':5,'message':'กำลังตรวจผลเดิมหลังรีเฟรช','detail':'ภาพเสร็จจริง 3/15'})
        window._story_progress_value.set.assert_called_once_with(23)
        window._story_progress_message.set.assert_called_once_with('กำลังตรวจผลเดิมหลังรีเฟรช')

    def test_old_browser_recovery_cannot_replace_video_progress(self):
        window = self.window(79)
        window._update_story_progress({'stage':'chatgpt','step':'recovering_response',
            'percent':5,'message':'old browser event'})
        window._story_progress_message.set.assert_not_called()


class StoryFlowProgressDetailTests(unittest.TestCase):
    def window(self, snapshots):
        window = MainWindow.__new__(MainWindow)
        window.events = Queue()
        window._story_pipeline_job_id = 'STORY-TEST'
        window._story_flow_progress_owner = ('STORY-TEST', 6)
        window._product_pipeline_job_id = ''

        def status():
            snapshot = snapshots.pop(0) if len(snapshots) > 1 else snapshots[0]
            return {'clients': [{'version': 'test', 'flow_job_id': 'STORY-TEST',
                'flow_shot_index': 6, 'flow_run_id': 'RUN-6', **snapshot}]}

        window.bridge = SimpleNamespace(REQUIRED_EXTENSION_VERSION='test', extension_status=status,
            _extension_lock=threading.RLock(),
            _extension_runs={('flow', 'STORY-TEST', 6): {'run_id': 'RUN-6'}})
        window._update_story_progress = mock.Mock()
        return window

    def test_repair_detail_reaches_story_without_advancing_completed_scene_count(self):
        message = 'ฉาก 6 กำลังแก้พรอมต์จากภาพเดิมกับ ChatGPT Web'
        window = self.window([
            {'flow_step': 'generation_in_progress', 'flow_message': message},
            {'flow_step': 'generation_in_progress', 'flow_message': message},
            {'flow_step': 'generation_complete', 'flow_message': 'Flow video is ready'},
        ])
        ticks = count(1)
        with mock.patch('ui.main_window.time.monotonic', side_effect=lambda: next(ticks)), \
                mock.patch('ui.main_window.time.sleep'):
            result = window._wait_flow_step('STORY-TEST', 6, timeout=100, total_shots=6)
        self.assertEqual(result['flow_step'], 'generation_complete')
        events = list(window.events.queue)
        progress = [payload for kind, payload in events if kind == 'story_flow_progress']
        self.assertEqual(len(progress), 2)
        self.assertEqual(progress[0]['detail'], message)
        self.assertEqual(progress[0]['percent'], 86)
        self.assertEqual(progress[1]['percent'], 86)
        self.assertEqual(progress[0]['message'], 'Google Flow • ฉาก 6/6')
        window._update_story_flow_progress(progress[0])
        window._update_story_progress.assert_called_once_with(progress[0])

    def test_old_job_run_scene_or_missing_owner_cannot_replace_story_detail(self):
        window = self.window([])
        current = {'job_id': 'STORY-TEST', 'shot_index': 6,
                   'flow_run_id': 'RUN-6', 'detail': 'Actual helper progress', 'percent': 86}
        for override in [{'job_id': 'STORY-OTHER'}, {'job_id': 'JOB-TEST'},
                         {'flow_run_id': 'RUN-OLD'}, {'flow_run_id': ''},
                         {'shot_index': 5}, {'shot_index': True}, {'shot_index': 51}]:
            with self.subTest(override=override):
                window._update_story_flow_progress({**current, **override})
        window._story_pipeline_job_id = ''
        window._update_story_flow_progress(current)
        window._update_story_progress.assert_not_called()

    def test_changed_run_after_event_enqueue_is_rejected(self):
        window = self.window([])
        queued = {'job_id': 'STORY-TEST', 'shot_index': 6,
                  'flow_run_id': 'RUN-6', 'detail': 'Late old helper message', 'percent': 86}
        window.bridge._extension_runs[('flow', 'STORY-TEST', 6)] = {'run_id': 'RUN-NEW'}
        window._update_story_flow_progress(queued)
        window._update_story_progress.assert_not_called()

    def test_completed_neighbor_run_is_not_current_scene_progress(self):
        window = self.window([])
        window.bridge._extension_runs[('flow', 'STORY-TEST', 5)] = {'run_id': 'RUN-5'}
        window._update_story_flow_progress({'job_id': 'STORY-TEST', 'shot_index': 5,
            'flow_run_id': 'RUN-5', 'detail': 'Late scene 5', 'percent': 86})
        window._update_story_progress.assert_not_called()
