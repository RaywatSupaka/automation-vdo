import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ui import main_window as main_window_module
from ui.main_window import MainWindow


class HybridEventLoopRecoveryTests(unittest.TestCase):
    @staticmethod
    def _cancellable_product_window():
        window = MainWindow.__new__(MainWindow)
        window._product_pipeline_job_id = "JOB-CANCEL"
        window._product_cancel_event = threading.Event()
        window._product_verification_job = "JOB-CANCEL"
        window._product_web_action = {"kind": "flow"}
        window.bridge = Mock()
        window.products = Mock()
        window.root = Mock()
        window.status = Mock()
        window._product_progress_message = Mock()
        window._product_progress_detail = Mock()
        window._product_cancel_button = Mock()
        window.product_run_button = Mock()
        window._write_console = Mock()
        window._finish_product_popup = Mock()
        window._desktop_set_notice = Mock()
        window._refresh = Mock()
        window._close_automation_browser = Mock()
        window._creation_product_terminal = Mock(return_value=False)
        return window

    def test_product_cancel_has_bounded_ui_fallback_when_worker_is_stuck(self):
        window = self._cancellable_product_window()

        window._cancel_product_pipeline()

        self.assertTrue(window._product_cancel_event.is_set())
        window.root.after.assert_called_once()
        delay, callback = window.root.after.call_args.args
        self.assertEqual(delay, 700)

        callback()

        self.assertEqual(window._product_pipeline_job_id, "")
        self.assertIsNone(window._product_cancel_event)
        window.product_run_button.configure.assert_called_once_with(state="normal")
        window._finish_product_popup.assert_called_once()
        window._close_automation_browser.assert_called_once_with(
            "JOB-CANCEL", "ยกเลิกงานแล้ว"
        )

    def test_old_cancel_fallback_cannot_clear_a_new_product_job(self):
        window = self._cancellable_product_window()
        old_event = window._product_cancel_event
        old_event.set()
        window._product_pipeline_job_id = "JOB-NEW"
        window._product_cancel_event = threading.Event()

        self.assertFalse(window._finish_product_cancel("JOB-CANCEL", old_event))

        self.assertEqual(window._product_pipeline_job_id, "JOB-NEW")
        self.assertIsNotNone(window._product_cancel_event)
        window._finish_product_popup.assert_not_called()

    def test_hybrid_notifications_never_open_a_blocking_tk_messagebox(self):
        window = MainWindow.__new__(MainWindow)
        window._desktop_set_notice = Mock()
        window.status = Mock()
        window.log_activity = Mock()
        window._write_console = Mock()

        with (
            patch.object(main_window_module.messagebox, "showinfo") as original_info,
            patch.object(main_window_module.messagebox, "showwarning"),
            patch.object(main_window_module.messagebox, "showerror"),
        ):
            window._install_hybrid_messagebox_bridge()
            result = main_window_module.messagebox.showinfo(
                "สร้างคำบรรยายสำเร็จ", "บันทึกไฟล์ไว้แล้ว"
            )

            self.assertEqual(result, "ok")
            original_info.assert_not_called()
            window._desktop_set_notice.assert_called_once_with(
                "success", "สร้างคำบรรยายสำเร็จ • บันทึกไฟล์ไว้แล้ว"
            )
            window._write_console.assert_called_once()

    def test_local_product_fallback_ready_clears_busy_without_clip_count(self):
        window = MainWindow.__new__(MainWindow)
        window._creation_product_terminal = Mock(return_value=False)
        window._schedule_next_story_queue_item = Mock()
        window._product_pipeline_job_id = "JOB-FALLBACK"
        window._product_cancel_event = object()
        window._refresh = Mock()
        window._refresh_video_library = Mock()
        window._show_page = Mock()
        window.status = Mock()
        window._write_console = Mock()
        window._finish_product_popup = Mock()
        window._close_automation_browser = Mock()

        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "final.mp4"
            target.write_bytes(b"video")
            window._handle_product_pipeline_ready((
                "JOB-FALLBACK",
                target,
                {
                    "source_type": "product_image_sequence_fallback",
                    "image_count": 3,
                    "duration": 30.76,
                },
            ))

        self.assertEqual(window._product_pipeline_job_id, "")
        self.assertIsNone(window._product_cancel_event)
        window._refresh_video_library.assert_called_once_with("product:JOB-FALLBACK")
        self.assertIn("รูปสินค้าเดิม 3 ชุด", window._write_console.call_args.args[0])

    def test_poll_reschedules_after_one_ui_event_raises(self):
        window = MainWindow.__new__(MainWindow)
        window._poll_once = Mock(side_effect=KeyError("bad event payload"))
        window.log = Mock()
        window._desktop_set_notice = Mock()
        window.status = Mock()
        window.root = Mock()

        window._poll()

        window.log.exception.assert_called_once()
        window._desktop_set_notice.assert_called_once()
        window.root.after.assert_called_once_with(100, window._poll)


if __name__ == "__main__":
    unittest.main()
