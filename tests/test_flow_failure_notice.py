"""Actual desktop terminal notices with isolated bridge state and no browser."""
import logging
import queue
import subprocess
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from core.local_bridge import LocalBridge
from core.presenter_pipeline import PresenterPipeline
from ui.main_window import MainWindow


REASON = "ไม่สามารถสร้างวิดีโอที่อาจทำให้เกิดความเสี่ยงต่อชื่อเสียงหรือแสดงเหตุการณ์ปัจจุบันอย่างไม่ถูกต้อง โปรดลองใช้พรอมต์อื่นหรือส่งความคิดเห็น"


class FlowFailureNoticeTests(unittest.TestCase):
    def window(self, mode="story"):
        window = MainWindow.__new__(MainWindow)
        window.events = queue.Queue()
        window.bridge = LocalBridge("127.0.0.1", 0, Mock(), logging.getLogger("flow-notice-test"))
        window._automation_error_log = {}
        window._flow_failure_notice_ids = []
        window._write_console = Mock()
        window._poll_desktop_requests = Mock()
        # This fixture has no Tk widgets. Keep the owned Flow event consumer
        # real while mocking only its final progress-widget update.
        window._update_story_progress = Mock()
        window.status = Mock()
        event = threading.Event()
        job = {"story": "STORY-NOTICE", "product": "JOB-NOTICE", "manual_flow": "JOB-MANUAL",
               "presenter": "PRESENTER-ABCDEF123456"}[mode]
        if mode == "manual_flow":
            window._manual_multi_flow_job_id, window._manual_multi_flow_cancel_event = job, event
        elif mode == "presenter":
            window._presenter_cancel = event
            window._presenter_progress = {"id": job, "run_id": "PRESENTER-RUN", "stage": "error"}
        else:
            setattr(window, f"_{mode}_pipeline_job_id", job)
            setattr(window, f"_{mode}_cancel_event", event)
        client = {"client_id": "owned-client", "version": window.bridge.REQUIRED_EXTENSION_VERSION,
                  "last_seen_epoch": time.time(), "flow_job_id": job, "flow_shot_index": 2,
                  "flow_run_id": "RUN-NOTICE", "flow_step": "generation_failed",
                  "flow_message": "structured policy terminal", "flow_failure_code": "FLOW_POLICY_BLOCKED",
                  "flow_policy_failure_category": "general_policy", "flow_failure_card_fingerprint": "CARD-NOTICE",
                  "flow_failure_reason": REASON}
        window.bridge._extension_clients[client["client_id"]] = dict(client)
        window.bridge._extension_runs[("flow", job, 2)] = {"run_id": "RUN-NOTICE"}
        return window, job, event, client

    def test_real_waiter_notice_does_not_change_existing_fallback_terminal(self):
        window, job, event, client = self.window()
        with self.assertRaises(RuntimeError) as caught:
            window._wait_flow_step(job, 2, cancel_event=event, timeout=5)
        self.assertTrue(caught.exception.flow_policy_terminal)
        self.assertEqual(caught.exception.flow_run_id, "RUN-NOTICE")
        window._poll_once()
        window._update_story_progress.assert_called_once()
        progress = window._update_story_progress.call_args.args[0]
        self.assertEqual(progress['job_id'], job)
        self.assertEqual(progress['flow_run_id'], 'RUN-NOTICE')
        self.assertEqual(progress['shot_index'], 2)
        self.assertEqual(progress['detail'], client['flow_message'])
        report = window._automation_error_log
        self.assertEqual(report["title"], "สร้างวิดีโอฉาก 2 ไม่สำเร็จ")
        self.assertEqual(report["message"], "สาเหตุ: " + REASON)
        self.assertIn("Flow ระบุว่าไม่ได้เรียกเก็บเงิน", report["text"])
        self.assertIn("ไม่ใช้ภาพนิ่งแทนวิดีโอ", report["text"])
        self.assertFalse(event.is_set())
        self.assertEqual(window._story_pipeline_job_id, job)
        self.assertEqual(window.bridge._extension_commands, [])

    def test_product_and_manual_flow_share_notice_without_worker_mutation(self):
        for mode in ("product", "manual_flow"):
            with self.subTest(mode=mode):
                window, job, event, client = self.window(mode)
                self.assertTrue(window._queue_flow_failure_notice(job, 2, client, event))
                window._poll_once()
                self.assertIn("พักฉากนี้เพื่อตรวจสอบ", window._automation_error_log["text"])
                self.assertFalse(event.is_set())

    def test_old_client_run_card_reason_or_unstructured_page_never_notifies(self):
        changes = [{"client_id": "other-client"}, {"flow_run_id": "OLD-RUN"},
                   {"flow_job_id": "STORY-OTHER"}, {"flow_shot_index": 3},
                   {"flow_failure_card_fingerprint": "OTHER-CARD"}, {"flow_failure_reason": "old reason"},
                   {"flow_failure_reason": "", "flow_page_excerpt": REASON},
                   {"flow_failure_code": "", "flow_page_excerpt": REASON},
                   {"version": "old-version"}, {"flow_generation_active": True},
                   {"flow_has_playable_result": True}, {"flow_policy_failure_category": "unknown"}]
        for change in changes:
            with self.subTest(change=change):
                window, job, event, client = self.window()
                self.assertFalse(window._queue_flow_failure_notice(job, 2, {**client, **change}, event))
                self.assertTrue(window.events.empty())

    def test_new_run_registry_suppresses_retained_old_client_terminal(self):
        window, job, event, client = self.window()
        window.bridge._extension_runs[("flow", job, 2)] = {"run_id": "NEW-RUN"}
        self.assertFalse(window._queue_flow_failure_notice(job, 2, client, event))

    def test_queued_notice_survives_its_fallback_clear_and_deduplicates_replay(self):
        window, job, event, client = self.window()
        for _ in range(3):
            self.assertTrue(window._queue_flow_failure_notice(job, 2, client, event))
        window.bridge.clear_flow_progress(job, 2)
        window._poll_once()
        self.assertEqual(len(window._flow_failure_notice_ids), 1)
        window._write_console.assert_called_once()
        self.assertEqual(window._automation_error_log["message"], "สาเหตุ: " + REASON)

    def test_queued_notice_drops_after_cancel_new_job_or_same_job_resume(self):
        for change in ("cancel", "other_job", "same_job_resume"):
            with self.subTest(change=change):
                window, job, event, client = self.window()
                self.assertTrue(window._queue_flow_failure_notice(job, 2, client, event))
                if change == "cancel": event.set()
                elif change == "other_job": window._story_pipeline_job_id = "STORY-NEW"
                else: window._story_cancel_event = threading.Event()
                window._poll_once()
                self.assertEqual(window._automation_error_log, {})

    def test_presenter_real_waiter_carries_exact_reason_and_never_claims_fallback(self):
        window, job, event, client = self.window("presenter")
        pipeline = PresenterPipeline(Mock(), window.bridge, Mock(), Mock(), event)
        with self.assertRaises(RuntimeError) as caught:
            pipeline.wait(job, "flow", "RUN-NOTICE", lambda _: False, timeout=5, shot=2)
        error = caught.exception
        self.assertIn(REASON, str(error))
        self.assertTrue(window._queue_flow_failure_notice(job, 2, error.flow_failure_client, event,
                                                        presenter_run_id="PRESENTER-RUN"))
        window._poll_once()
        self.assertIn("งานตัวละครหยุดแล้ว", window._automation_error_log["text"])
        self.assertNotIn("ใช้รูปฉากเดิม", window._automation_error_log["text"])
        self.assertNotIn("ทำฉากถัดไป", window._automation_error_log["text"])
        self.assertEqual(window.bridge._extension_commands, [])

    def test_presenter_previous_desktop_run_is_not_current(self):
        window, job, event, client = self.window("presenter")
        self.assertFalse(window._queue_flow_failure_notice(job, 2, client, event, presenter_run_id="OLD"))

    def test_actual_ui_deduplicates_heartbeat_reload_and_respects_minimize(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(["node", str(root / "tests" / "flow_failure_notice_ui_harness.js")],
                                cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
