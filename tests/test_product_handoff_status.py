import ast
import inspect
import logging
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from core.cancellable_process import OperationCancelled
from ui.main_window import MainWindow


class ProductHandoffStatusTests(unittest.TestCase):
    def window(self, folder, ready=False):
        window = MainWindow.__new__(MainWindow)
        window.events = queue.Queue()
        window.log = Mock()
        window.products = Mock()
        window.products.spoken_script.return_value = ({'voice_status': 'ready' if ready else 'pending',
            'voice_path': 'voice.mp3'}, 'บทพูดเดิม')
        window._create_voice_worker = Mock()
        window.bridge = Mock()
        return window

    @staticmethod
    def options():
        return {'voice_api_key': 'test-only', 'voice_reference_id': 'test-ref',
                'voice_reference_file': '', 'voice': {'output_format': 'mp3'}}

    def test_live_voice_updates_reach_product_popup_and_no_flow_command(self):
        with tempfile.TemporaryDirectory() as temp:
            window = self.window(Path(temp))
            def voice(*args, **kwargs):
                kwargs['on_progress']('กำลังประมวลผล')
                kwargs['on_progress']('กำลังประมวลผล')
                kwargs['on_progress']('กำลังบันทึกไฟล์เสียง')
            window._create_voice_worker.side_effect = voice
            window._prepare_product_narration('JOB-TEST', Path(temp), self.options(), threading.Event())
            rows = [payload for name, payload in window.events.queue if name == 'product_pipeline_progress']
            self.assertEqual([row['stage'] for row in rows], ['voice', 'voice', 'voice', 'flow'])
            self.assertIn('ภาพครบ 3/3', rows[0]['message'])
            self.assertIn('ผ่านไป', rows[1]['detail'])
            self.assertIn('กำลังประมวลผล', rows[1]['detail'])
            self.assertIn('กำลังบันทึกไฟล์เสียง', rows[2]['detail'])
            self.assertIn('Google Flow', rows[-1]['message'])
            window.bridge.queue_extension_command.assert_not_called()
            window._create_voice_worker.assert_called_once()
            self.assertFalse(window._create_voice_worker.call_args.kwargs['emit_event'])

    def test_reuse_voice_does_not_claim_synthesis(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'voice.mp3').touch()
            window = self.window(folder, ready=True)
            window._prepare_product_narration('JOB-TEST', folder, self.options(), threading.Event())
            window._create_voice_worker.assert_not_called()
            self.assertIn('ใช้ไฟล์เสียงเดิม', list(window.events.queue)[-1][1]['detail'])

    def test_missing_saved_file_still_uses_existing_voice_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            window = self.window(Path(temp), ready=True)
            window._prepare_product_narration('JOB-TEST', Path(temp), self.options(), threading.Event())
            window._create_voice_worker.assert_called_once()

    def test_failure_never_reports_voice_ready_or_opens_flow(self):
        with tempfile.TemporaryDirectory() as temp:
            window = self.window(Path(temp))
            window._create_voice_worker.side_effect = RuntimeError('voice failed')
            with self.assertRaisesRegex(RuntimeError, 'voice failed'):
                window._prepare_product_narration('JOB-TEST', Path(temp), self.options(), threading.Event())
            self.assertTrue(all(row['stage'] == 'voice' for _, row in window.events.queue))
            window.bridge.queue_extension_command.assert_not_called()

    def test_cancellation_preserved_before_and_during_voice(self):
        with tempfile.TemporaryDirectory() as temp:
            for before in [True, False]:
                window = self.window(Path(temp))
                cancel = threading.Event()
                if before: cancel.set()
                else: window._create_voice_worker.side_effect = lambda *a, **k: cancel.set()
                with self.assertRaises(OperationCancelled):
                    window._prepare_product_narration('JOB-TEST', Path(temp), self.options(), cancel)
                self.assertTrue(all(row['stage'] == 'voice' for _, row in window.events.queue))

    def test_original_pipeline_order_and_no_preload(self):
        # Resolve the actual named method, not the import-time line offset;
        # unrelated desktop methods and decorators may move this source block.
        module_source = Path(inspect.getfile(MainWindow)).read_text(encoding='utf-8')
        window_class = next(node for node in ast.parse(module_source).body
                            if isinstance(node, ast.ClassDef) and node.name == 'MainWindow')
        worker = next(node for node in window_class.body
                      if isinstance(node, ast.FunctionDef) and node.name == '_product_pipeline_worker')
        source = ast.get_source_segment(module_source, worker)
        self.assertIsNotNone(source)
        stages = ['self.products.approve_ai_result(job_id)', 'self._prepare_product_narration(',
                  'worker = self._multi_meta_product_worker', 'result = worker(']
        positions = [source.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('prepare_flow_landing', source)


if __name__ == '__main__':
    unittest.main()
