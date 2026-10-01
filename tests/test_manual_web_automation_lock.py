import inspect
import threading
import unittest
from unittest.mock import Mock, patch

from core.local_bridge import LocalBridge
from ui.main_window import MainWindow


class ManualWebAutomationLockTests(unittest.TestCase):
    @staticmethod
    def _window():
        window = MainWindow.__new__(MainWindow)
        window._product_pipeline_job_id = ""
        window._story_pipeline_job_id = ""
        window._manual_multi_flow_job_id = ""
        window._manual_multi_flow_cancel_event = None
        window.status = Mock()
        window._write_console = Mock()
        return window

    def test_manual_multi_flow_is_tracked_and_cleared_by_worker_wrapper(self):
        window = self._window()
        window._selected_product_job = Mock(return_value="JOB-MANUAL-FLOW")
        window.products = Mock()
        window.products.flow_package.return_value = {
            "image_files": ["1.png", "2.png", "3.png"],
            "shot_count": 3,
        }
        window.products.get_job.return_value = {"id": "JOB-MANUAL-FLOW"}
        window.bridge = Mock()
        window.bridge.extension_status.return_value = {"connected": True}
        window._video_provider_label = Mock(return_value="Google Flow")
        window._multi_flow_worker = Mock(return_value=("done",))

        with patch("ui.main_window.threading.Thread") as thread_cls:
            self.assertTrue(window._start_multi_flow())

        self.assertEqual(window._manual_multi_flow_job_id, "JOB-MANUAL-FLOW")
        cancel_event = window._manual_multi_flow_cancel_event
        self.assertIsInstance(cancel_event, threading.Event)
        target = thread_cls.call_args.kwargs["target"]
        args = thread_cls.call_args.kwargs["args"]
        target(*args)
        window._multi_flow_worker.assert_called_once_with(
            "JOB-MANUAL-FLOW", cancel_event=cancel_event
        )
        self.assertEqual(window._manual_multi_flow_job_id, "")
        self.assertIsNone(window._manual_multi_flow_cancel_event)

    def test_manual_multi_flow_rejects_active_product_or_story_pipeline(self):
        for field, job_id in (
            ("_product_pipeline_job_id", "JOB-PRODUCT"),
            ("_story_pipeline_job_id", "STORY-ACTIVE"),
        ):
            with self.subTest(field=field):
                window = self._window()
                setattr(window, field, job_id)
                window._selected_product_job = Mock()
                with patch("ui.main_window.messagebox.showinfo"):
                    self.assertFalse(window._start_multi_flow())
                window._selected_product_job.assert_not_called()

    def test_create_actions_reject_overlap_with_manual_multi_flow(self):
        window = self._window()
        window._manual_multi_flow_job_id = "JOB-MANUAL-FLOW"
        window._manual_multi_flow_cancel_event = threading.Event()

        for action in ("create_product", "create_story", "create_drama_series"):
            with self.subTest(action=action):
                with self.assertRaisesRegex(ValueError, "กำลัง"):
                    window._desktop_execute_action(action, {})

    def test_real_bridge_accepts_the_run_scoped_manual_cancel_contract(self):
        parameters = inspect.signature(LocalBridge.queue_extension_command).parameters
        self.assertIn("run_id", parameters)

    def test_cancel_product_stops_manual_multi_flow_and_extension_run(self):
        window = self._window()
        cancel_event = threading.Event()
        window._manual_multi_flow_job_id = "JOB-MANUAL-FLOW"
        window._manual_multi_flow_cancel_event = cancel_event
        window.bridge = Mock()
        window.bridge.extension_status.return_value = {
            "clients": [{
                "flow_job_id": "JOB-MANUAL-FLOW",
                "flow_shot_index": 2,
                "flow_run_id": "RUN-2",
            }]
        }

        result = window._desktop_execute_action("cancel_product", {})

        self.assertTrue(result["ok"])
        self.assertTrue(cancel_event.is_set())
        window.bridge.queue_extension_command.assert_called_once_with(
            "stop_flow_generation", "JOB-MANUAL-FLOW", 2, run_id="RUN-2"
        )


if __name__ == "__main__":
    unittest.main()
