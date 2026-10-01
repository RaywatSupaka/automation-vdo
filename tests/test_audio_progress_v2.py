import queue
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from ui.main_window import MainWindow


class Value:
    def __init__(self, value=''):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class AudioProgressTests(unittest.TestCase):
    def setUp(self):
        self.w = MainWindow.__new__(MainWindow)
        self.w.events = queue.Queue()
        self.w._story_pipeline_job_id = 'STORY-CURRENT'
        self.w._story_cancel_event = threading.Event()
        self.w._story_progress_value = Value(61)
        self.w._story_progress_percent = Value('61%')
        self.w._story_progress_message = Value('old voice message')
        self.w._story_progress_detail = Value()
        self.w._story_progress_stage_widgets = {}
        self.w.story_status = Value()
        self.w.status = Value()
        self.w._write_console = Mock()

    def emit(self, phase, percent, message='new phase', **overrides):
        self.w._queue_story_phase('STORY-CURRENT', self.w._story_cancel_event,
            phase, {'percent': percent, 'message': message, 'stage': 'voice' if phase == 'voice' else 'video'})
        _, payload = self.w.events.get_nowait()
        self.w._update_story_progress({**payload, **overrides})

    def test_meta_first_scene_updates_message_after_61(self):
        self.emit('source_video', 60, 'Meta scene 1/3')
        self.assertEqual(self.w._story_progress_value.get(), 61)
        self.assertEqual(self.w._story_progress_message.get(), 'Meta scene 1/3')

    def test_voice_lower_percent_is_new_phase_not_stale(self):
        self.emit('source_video', 72)
        self.emit('voice', 68, 'SmartSub processing')
        self.assertEqual(self.w._story_progress_value.get(), 72)
        self.assertEqual(self.w._story_progress_message.get(), 'SmartSub processing')
        self.emit('source_video', 99, 'old video update')
        self.assertEqual(self.w._story_progress_message.get(), 'SmartSub processing')

    def test_wrong_job_old_run_cancel_and_invalid_phase_are_rejected(self):
        for fields in ({'progress_job_id': 'STORY-OTHER'},
                       {'progress_cancel_event': threading.Event()},
                       {'pipeline_phase': 'invalid'}, {'progress_cancel_event': None}):
            self.emit('voice', 75, **fields)
            self.assertEqual(self.w._story_progress_value.get(), 61)
        self.w._story_cancel_event.set()
        self.emit('voice', 75)
        self.assertEqual(self.w._story_progress_value.get(), 61)

    def test_late_image_callback_cannot_replace_local_phase(self):
        self.emit('source_video', 60, 'Meta')
        self.w._update_story_progress({'percent': 65, 'stage': 'chatgpt', 'message': 'old image callback'})
        self.assertEqual(self.w._story_progress_message.get(), 'Meta')

    def test_new_run_does_not_inherit_old_phase_rank(self):
        self.emit('compose', 88)
        self.w._story_cancel_event = threading.Event()
        self.w._story_progress_value.set(15)
        self.emit('source_video', 60, 'new run')
        self.assertEqual(self.w._story_progress_message.get(), 'new run')

    def test_legacy_lower_progress_still_rejected(self):
        self.w._update_story_progress({'percent': 30, 'stage': 'chatgpt', 'message': 'old'})
        self.assertEqual(self.w._story_progress_value.get(), 61)

    def test_hybrid_phase_payload_matches_source_provider_and_active_run(self):
        self.w.stories = SimpleNamespace(root=Path('unused'))
        self.emit('voice', 68)
        for mode, required in [('meta_ai', True), ('google_flow', True), ('image_motion', False)]:
            job = {'id': 'STORY-CURRENT', 'video_generation_mode': mode, 'audio_choices': {'mode': 'api'}}
            view = self.w._desktop_scene_progress(job, True)
            self.assertEqual(view['pipeline_phase'], 'voice')
            self.assertEqual(view['source_video_required'], required)
            self.assertNotIn('pipeline_phase', self.w._desktop_scene_progress(job, False))
        self.w._story_cancel_event = threading.Event()
        self.assertNotIn('pipeline_phase', self.w._desktop_scene_progress(job, True))
