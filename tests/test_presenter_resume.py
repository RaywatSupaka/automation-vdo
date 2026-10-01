"""Presenter resumes use real persistence/bridge/wait, with no live browser."""
import logging
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.local_bridge import LocalBridge
from core.presenter import PresenterManager
from core.presenter_pipeline import PresenterPipeline
from core.product_manager import ProductManager
from ui.presenter import PresenterMixin


class ClockEvent:
    def __init__(self):
        self.now = 100.0
        self.cancelled = False

    def is_set(self):
        return self.cancelled

    def set(self):
        self.cancelled = True

    def wait(self, seconds):
        self.now += seconds
        return self.cancelled


class SimulatedExtensionBridge(LocalBridge):
    """Real queue, clear and status methods; simulated Extension observations."""
    def __init__(self, root, manager):
        super().__init__('127.0.0.1', 0, ProductManager(root),
                         logging.getLogger('presenter-resume-test'), presenters=manager)
        self.observe = lambda: None
        self.observations = 0
        self.clears = []

    def extension_status(self):
        self.observations += 1
        self.observe()
        return super().extension_status()

    def clear_flow_progress(self, ident, shot_index=0):
        self.clears.append((ident, shot_index))
        return super().clear_flow_progress(ident, shot_index)

    def progress(self, ident, run, step, inspection='', shot=1):
        self._extension_clients['fixture'] = {
            'client_id': 'fixture', 'version': self.REQUIRED_EXTENSION_VERSION,
            'last_seen_epoch': time.time(), 'flow_job_id': ident, 'flow_run_id': run,
            'flow_shot_index': shot, 'flow_step': step, 'flow_message': step,
            'flow_inspection_command_id': inspection,
        }

    def acknowledge(self, command, status='completed', error=''):
        stored = next(c for c in self._extension_commands if c['id'] == command['id'])
        stored.update(status=status, error=error, completed_at=time.time())


class PresenterResumeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='SmartFlow-presenter-resume-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manager = PresenterManager(self.root)
        self.ident = self.manager.create('Guide', 'Navy clothed presenter')['id']
        self.folder = self.manager.folder(self.ident)
        (self.folder / 'generated/character.png').write_bytes(b'preserved fixture portrait')
        self.manager.update(self.ident, image='generated/character.png', status='running',
                            run_id='RUN-new', intents={'image': 'RUN-image', 'flow_1': 'RUN-old'})
        self.bridge = SimulatedExtensionBridge(self.root, self.manager)
        self.event = ClockEvent()
        self.notify = Mock()
        self.pipeline = PresenterPipeline(self.manager, self.bridge, self.notify, Mock(), self.event)
        self.clock = patch('core.presenter_pipeline.time.monotonic', side_effect=lambda: self.event.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def inspect(self):
        return self.pipeline._queue_flow('inspect_flow', self.ident, 1, 'RUN-old')

    def wait(self, command, predicate=None):
        return self.pipeline.wait(self.ident, 'flow', 'RUN-old',
            predicate or (lambda c: c['flow_step'] == 'generation_complete'), shot=1, command=command)

    def test_old_terminal_before_ack_and_wrong_inspection_after_ack_do_not_kill_resume(self):
        self.bridge.progress(self.ident, 'RUN-old', 'checkpoint_missing', 'CMD-previous')
        command = self.inspect()
        self.assertNotIn('flow_step', self.bridge._extension_clients['fixture'])

        def observe():
            cycle = self.bridge.observations
            if cycle == 1:
                self.bridge.progress(self.ident, 'RUN-old', 'checkpoint_missing', 'CMD-previous')
            elif cycle == 2:
                self.bridge.acknowledge(command)
            else:
                self.bridge.progress(self.ident, 'RUN-old', 'generation_complete', command['id'])
        self.bridge.observe = observe
        self.assertEqual(self.wait(command)['flow_step'], 'generation_complete')
        self.assertEqual(self.bridge.observations, 3)
        self.assertEqual([c['action'] for c in self.bridge._extension_commands], ['inspect_flow'])
        self.assertNotIn('checkpoint_missing', [call.args[0] for call in self.notify.call_args_list])

    def test_fresh_checkpoint_missing_stops_without_open_or_resume(self):
        command = self.inspect()
        def observe():
            self.bridge.acknowledge(command)
            self.bridge.progress(self.ident, 'RUN-old', 'checkpoint_missing', command['id'])
        self.bridge.observe = observe
        with self.assertRaisesRegex(RuntimeError, 'checkpoint_missing'):
            self.wait(command)
        self.assertEqual([c['action'] for c in self.bridge._extension_commands], ['inspect_flow'])

    def test_matching_fresh_state_cannot_pass_before_command_ack(self):
        command = self.inspect()
        def observe():
            self.bridge.progress(self.ident, 'RUN-old', 'generation_complete', command['id'])
            if self.bridge.observations == 3:
                self.bridge.acknowledge(command)
        self.bridge.observe = observe
        self.wait(command)
        self.assertEqual(self.bridge.observations, 3)

    def test_wrong_run_and_shot_are_ignored(self):
        command = self.inspect()
        def observe():
            self.bridge.acknowledge(command)
            if self.bridge.observations == 1:
                self.bridge.progress(self.ident, 'RUN-foreign', 'error', command['id'])
            elif self.bridge.observations == 2:
                self.bridge.progress(self.ident, 'RUN-old', 'error', command['id'], shot=2)
            else:
                self.bridge.progress(self.ident, 'RUN-old', 'generation_complete', command['id'])
        self.bridge.observe = observe
        self.wait(command)
        self.assertEqual(self.bridge.observations, 3)

    def test_missing_inspection_id_is_bounded_without_resubmit(self):
        command = self.inspect()
        def observe():
            self.bridge.acknowledge(command)
            self.bridge.progress(self.ident, 'RUN-old', 'checkpoint_missing', 'CMD-previous')
        self.bridge.observe = observe
        with self.assertRaisesRegex(RuntimeError, 'ไม่มีผลตรวจของรอบนี้'):
            self.wait(command)
        self.assertLessEqual(self.bridge.observations, 62)
        self.assertEqual(len(self.bridge._extension_commands), 1)

    def test_unknown_current_state_is_bounded_without_new_paid_request(self):
        command = self.inspect()
        def observe():
            self.bridge.acknowledge(command)
            self.bridge.progress(self.ident, 'RUN-old', 'generation_status_unknown', command['id'])
        self.bridge.observe = observe
        with self.assertRaisesRegex(RuntimeError, 'หยุดตรวจโดยไม่ส่งซ้ำ'):
            self.wait(command)
        self.assertLessEqual(self.bridge.observations, 92)
        self.assertEqual(len(self.bridge._extension_commands), 1)

    def test_failed_command_surfaces_its_own_error(self):
        command = self.inspect()
        self.bridge.observe = lambda: self.bridge.acknowledge(command, 'failed', 'owned project not found')
        with self.assertRaisesRegex(RuntimeError, 'owned project not found'):
            self.wait(command)

    def test_unacknowledged_command_is_bounded_even_if_old_progress_looks_complete(self):
        command = self.inspect()
        self.bridge.observe = lambda: self.bridge.progress(self.ident, 'RUN-old', 'generation_complete', command['id'])
        with self.assertRaisesRegex(RuntimeError, 'ยังไม่ยืนยันว่าคำสั่ง Flow'):
            self.wait(command)
        self.assertLessEqual(self.bridge.observations, 122)
        self.assertEqual(len(self.bridge._extension_commands), 1)

    def test_existing_generation_continues_after_current_inspection_without_resubmission(self):
        command = self.inspect()
        def observe():
            self.bridge.acknowledge(command)
            if self.bridge.observations == 1:
                self.bridge.progress(self.ident, 'RUN-old', 'generation_in_progress', command['id'])
            else:
                self.bridge.progress(self.ident, 'RUN-old', 'generation_complete')
        self.bridge.observe = observe
        self.wait(command)
        self.assertEqual(self.bridge.observations, 2)
        self.assertEqual([c['action'] for c in self.bridge._extension_commands], ['inspect_flow'])

    def test_old_credit_request_never_approved_before_fresh_inspection(self):
        command = self.inspect()
        def observe():
            if self.bridge.observations == 1:
                self.bridge.progress(self.ident, 'RUN-old', 'awaiting_credit_approval', 'CMD-earlier')
            else:
                self.bridge.acknowledge(command)
                self.bridge.progress(self.ident, 'RUN-old', 'generation_complete', command['id'])
        self.bridge.observe = observe
        self.wait(command)
        self.assertEqual([c['action'] for c in self.bridge._extension_commands], ['inspect_flow'])

    def ready_other_clips(self):
        clips = {}
        for i in (2, 3):
            relative = f'clips/take_{i:02d}.mp4'
            (self.folder / relative).write_bytes(b'preserved clip fixture')
            clips[str(i)] = {'path': relative}
        self.manager.update(self.ident, clips=clips)

    def app(self):
        app = PresenterMixin()
        app.presenters = self.manager
        app.bridge = self.bridge
        app._presenter_worker = SimpleNamespace(is_alive=lambda: True)
        app._presenter_cancel = threading.Event()
        app._presenter_progress = {'id': self.ident}
        app._creation_idle_reason = lambda **kwargs: ''
        return app

    def test_cancel_preserves_intents_and_requests_preserving_stop_for_unfinished_only(self):
        self.ready_other_clips()
        app = self.app()
        app._presenter_action('presenter_cancel', {})
        job = self.manager.get(self.ident)
        stop = next(c for c in self.bridge._extension_commands if c['action'] == 'stop_flow_generation')
        self.assertIs(stop['preserve_checkpoint'], True)
        self.assertEqual(stop['run_id'], 'RUN-old')
        self.assertEqual(stop['shot_index'], 1)
        self.assertEqual(job['pending_stop_commands'], [stop['id']])
        self.assertEqual(job['intents']['flow_1'], 'RUN-old')
        self.assertEqual(len(job['clips']), 2)
        self.assertEqual((self.folder / job['image']).read_bytes(), b'preserved fixture portrait')
        with self.assertRaisesRegex(ValueError, 'รอให้หยุดเรียบร้อย'):
            app._presenter_action('presenter_run', {'id': self.ident})

    def test_missing_stop_receipt_after_restart_reissues_only_one_preserving_pause(self):
        self.manager.update(self.ident, pending_stop_commands=['CMD-before-restart'])
        app = self.app()
        with self.assertRaisesRegex(ValueError, 'กำลังยืนยันพัก Flow'):
            app._presenter_action('presenter_run', {'id': self.ident})
        self.assertEqual(len(self.bridge._extension_commands), 1)
        replacement = self.bridge._extension_commands[0]
        self.assertEqual(replacement['action'], 'stop_flow_generation')
        self.assertIs(replacement['preserve_checkpoint'], True)
        self.assertEqual(replacement['run_id'], 'RUN-old')
        self.assertEqual(self.manager.get(self.ident)['stop_receipt_recovery_count'], 1)
        with self.assertRaisesRegex(ValueError, 'รอให้หยุดเรียบร้อย'):
            app._presenter_action('presenter_run', {'id': self.ident})
        self.assertEqual(len(self.bridge._extension_commands), 1)
        self.bridge.acknowledge(replacement)
        app._compatible_extension = lambda: ({'connected': True}, False)
        with self.assertRaisesRegex(ValueError, 'โหลด SmartFlow Extension'):
            app._presenter_action('presenter_run', {'id': self.ident})
        self.assertEqual(self.manager.get(self.ident)['pending_stop_commands'], [])

    def test_second_lost_stop_receipt_stops_for_review_without_endless_requeue(self):
        self.manager.update(self.ident, pending_stop_commands=['CMD-lost-again'], stop_receipt_recovery_count=1)
        with self.assertRaisesRegex(ValueError, 'หลังตรวจซ้ำหนึ่งครั้ง'):
            self.app()._presenter_action('presenter_run', {'id': self.ident})
        self.assertEqual(self.bridge._extension_commands, [])

    def test_cancel_then_resume_inspects_before_continuing_same_pre_submit_project(self):
        self.ready_other_clips()
        app = self.app()
        app._presenter_action('presenter_cancel', {})
        stop = next(c for c in self.bridge._extension_commands if c['action'] == 'stop_flow_generation')
        self.bridge.acknowledge(stop)
        # Verify the real adapter passes the stop barrier without starting a
        # GUI thread: deliberately report an incompatible connected version.
        app._compatible_extension = lambda: ({'connected': True}, False)
        with self.assertRaisesRegex(ValueError, 'โหลด SmartFlow Extension'):
            app._presenter_action('presenter_run', {'id': self.ident})
        self.assertEqual(self.manager.get(self.ident)['pending_stop_commands'], [])
        self.manager.update(self.ident, status='running', run_id='RUN-new')
        inspection_cycles = 0
        def observe():
            nonlocal inspection_cycles
            command = self.bridge._extension_commands[-1]
            if command['action'] == 'inspect_flow':
                inspection_cycles += 1
                if inspection_cycles == 1:
                    self.bridge.progress(self.ident, 'RUN-old', 'checkpoint_missing', 'CMD-earlier')
                    return
                self.bridge.acknowledge(command)
                self.bridge.progress(self.ident, 'RUN-old', 'checkpoint_preparing', command['id'])
            elif command['action'] == 'resume_flow_workspace':
                self.bridge.acknowledge(command)
                self.bridge.progress(self.ident, 'RUN-old', 'generation_complete')
        self.bridge.observe = observe
        downloaded = self.folder / 'clips/fixture-download.mp4'
        downloaded.write_bytes(b'new downloaded fixture')
        self.pipeline.download.return_value = downloaded
        def save(ident, index, path, run):
            self.assertEqual(run, 'RUN-new')
            job = self.manager.get(ident)
            clips = {**job['clips'], str(index): {'path': 'clips/fixture-download.mp4'}}
            return self.manager.update(ident, clips=clips)
        with patch.object(self.manager, 'save_clip', side_effect=save), patch('core.presenter_pipeline.PresenterRenderer'):
            self.pipeline.run(self.ident, 'RUN-new')
        actions = [c['action'] for c in self.bridge._extension_commands]
        self.assertEqual(actions, ['cancel_story_chatgpt', 'stop_flow_generation',
                                  'inspect_flow', 'resume_flow_workspace', 'download_flow_result'])
        self.assertEqual([c['run_id'] for c in self.bridge._extension_commands if c['action'] in
                          {'inspect_flow', 'resume_flow_workspace', 'download_flow_result'}], ['RUN-old'] * 3)
        self.assertEqual(self.bridge.clears, [(self.ident, 1), (self.ident, 1)])
        self.assertEqual(self.manager.get(self.ident)['status'], 'ready')
        self.pipeline.download.assert_called_once()


if __name__ == '__main__':
    unittest.main()
