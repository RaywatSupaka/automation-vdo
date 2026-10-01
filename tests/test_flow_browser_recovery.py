import queue
import tempfile
import unittest
from itertools import count
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ui.main_window import MainWindow


class _NeverCancelled:
    def is_set(self):
        return False

    def wait(self, _timeout):
        return False


class _Bridge:
    REQUIRED_EXTENSION_VERSION = "0.15.74"

    def __init__(self):
        self.statuses = [
            {"clients": []},
            {"clients": []},
            {"clients": [{"version": self.REQUIRED_EXTENSION_VERSION}]},
        ]
        self.cleared = []
        self.commands = []

    def extension_status(self):
        if len(self.statuses) > 1:
            return self.statuses.pop(0)
        return self.statuses[0]

    def clear_flow_progress(self, job_id, shot_index):
        self.cleared.append((job_id, shot_index))

    def queue_extension_command(self, action, job_id, shot_index=0):
        self.commands.append((action, job_id, shot_index))
        return {"id": "CMD-RECOVERY"}


class _FlowWaitBridge:
    REQUIRED_EXTENSION_VERSION = "0.15.74"

    def __init__(self):
        self.commands = []
        self.steps = ["generate_button_missing", "generation_complete"]

    def extension_status(self):
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        return {"clients": [{
            "version": self.REQUIRED_EXTENSION_VERSION,
            "flow_job_id": "JOB-WAIT",
            "flow_shot_index": 3,
            "flow_step": step,
            "flow_message": "ข้อมูลพร้อมแต่ปุ่มสร้างยังไม่พร้อม",
        }]}

    def queue_extension_command(self, action, job_id, shot_index=0):
        self.commands.append((action, job_id, shot_index))
        return {"id": "CMD-WAIT"}


class _FlowPromptBindingBridge:
    REQUIRED_EXTENSION_VERSION = "0.15.74"

    def __init__(self):
        self.commands = []
        self.steps = ["prepare_incomplete", "generation_started", "generation_complete"]

    def extension_status(self):
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        return {"clients": [{
            "version": self.REQUIRED_EXTENSION_VERSION,
            "flow_job_id": "JOB-PROMPT",
            "flow_shot_index": 2,
            "flow_step": step,
            "flow_message": "รูป ใส่แล้ว • Prompt ยังกรอกอัตโนมัติไม่ได้" if step == "prepare_incomplete" else step,
            "flow_image_ready": True,
            "flow_prompt_ready": step != "prepare_incomplete",
        }]}

    def queue_extension_command(self, action, job_id, shot_index=0):
        self.commands.append((action, job_id, shot_index))
        return {"id": "CMD-PROMPT"}


class _FlowSubmissionBridge:
    REQUIRED_EXTENSION_VERSION = "0.15.74"

    def __init__(self):
        self.commands = []
        self.steps = ["submission_blocked", "generation_started", "generation_complete"]

    def extension_status(self):
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        return {"clients": [{
            "version": self.REQUIRED_EXTENSION_VERSION,
            "flow_job_id": "JOB-SUBMIT",
            "flow_shot_index": 1,
            "flow_step": step,
            "flow_message": "Google Flow ยังไม่รับคำสั่ง" if step == "submission_blocked" else step,
            "flow_image_ready": True,
            "flow_prompt_ready": True,
        }]}

    def queue_extension_command(self, action, job_id, shot_index=0):
        self.commands.append((action, job_id, shot_index))
        return {"id": "CMD-SUBMIT"}


class _FlowExplicitErrorBridge:
    REQUIRED_EXTENSION_VERSION = "0.15.74"

    def __init__(self):
        self.commands = []

    def extension_status(self):
        return {"clients": [{
            "version": self.REQUIRED_EXTENSION_VERSION,
            "flow_job_id": "JOB-ERROR",
            "flow_shot_index": 3,
            # This is the real state observed on Flow: stale approval controls
            # remain above a newer error card.
            "flow_step": "awaiting_credit_approval",
            "flow_message": "Google Flow รออนุมัติใช้เครดิตอัตโนมัติ",
            "flow_confirmation_kind": "credit",
            "flow_page_excerpt": (
                "อนุมัติ ไม่ต้องถามอีก\n"
                "ล้มเหลว การสร้างนี้อาจละเมิดนโยบายของเรา ระบบไม่ได้เรียกเก็บเงินจากคุณ\n"
                "ลองอีกครั้ง"
            ),
        }]}

    def queue_extension_command(self, action, job_id, shot_index=0):
        self.commands.append((action, job_id, shot_index))
        return {"id": "CMD-ERROR"}


class _FlowUnknownBridge:
    REQUIRED_EXTENSION_VERSION = "0.15.74"

    def __init__(self, complete_after=11, page_excerpt=""):
        self.commands = []
        self.calls = 0
        self.complete_after = complete_after
        self.page_excerpt = page_excerpt

    def extension_status(self):
        self.calls += 1
        step = "generation_complete" if self.calls >= self.complete_after else "generation_status_unknown"
        return {"clients": [{
            "version": self.REQUIRED_EXTENSION_VERSION,
            "flow_job_id": "JOB-UNKNOWN",
            "flow_shot_index": 1,
            "flow_step": step,
            "flow_message": "ยังระบุสถานะผลลัพธ์จาก Google Flow ไม่ได้",
            "flow_page_excerpt": self.page_excerpt,
        }]}

    def queue_extension_command(self, action, job_id, shot_index=0):
        self.commands.append((action, job_id, shot_index))
        return {"id": "CMD-UNKNOWN"}


class _FlowPreparingBridge:
    REQUIRED_EXTENSION_VERSION = "0.15.74"

    def __init__(self):
        self.commands = []
        self.cleared = []

    def extension_status(self):
        step = "generation_complete" if self.commands else "preparing"
        return {"clients": [{
            "version": self.REQUIRED_EXTENSION_VERSION,
            "flow_job_id": "JOB-PREPARING",
            "flow_shot_index": 1,
            "flow_step": step,
            "flow_message": "กำลังใส่รูปอ้างอิงและ Prompt",
            "flow_page_url": "https://labs.google/fx/th/tools/flow",
        }]}

    def clear_flow_progress(self, job_id, shot_index):
        self.cleared.append((job_id, shot_index))

    def queue_extension_command(self, action, job_id, shot_index=0):
        self.commands.append((action, job_id, shot_index))
        return {"id": "CMD-PREPARING"}


class _FlowPersistentAttachmentStopBridge:
    REQUIRED_EXTENSION_VERSION = "0.15.74"

    def __init__(self):
        self.commands = []
        self.calls = 0

    def extension_status(self):
        self.calls += 1
        return {"clients": [{
            "version": self.REQUIRED_EXTENSION_VERSION,
            "flow_job_id": "JOB-ATTACH-STOP",
            "flow_shot_index": 2,
            "flow_step": "attachment_waiting_manual",
            "flow_message": "รอตรวจรูปใน Prompt เดิมแบบอ่านอย่างเดียว • ไม่อัปโหลด ไม่เลือกรูป และไม่กดสร้างซ้ำ",
            "flow_image_ready": False,
            "flow_prompt_ready": True,
        }]}

    def queue_extension_command(self, action, job_id, shot_index=0):
        self.commands.append((action, job_id, shot_index))
        return {"id": "CMD-ATTACH-STOP"}


class FlowBrowserRecoveryTests(unittest.TestCase):
    def test_persistent_attachment_without_terminal_evidence_stops_after_passive_grace(self):
        window = MainWindow.__new__(MainWindow)
        window.bridge = _FlowPersistentAttachmentStopBridge()
        window.events = queue.Queue()

        ticks = count(1, 3)
        with patch("ui.main_window.time.monotonic", side_effect=lambda: next(ticks)), self.assertRaisesRegex(RuntimeError, "รอตรวจรูปใน Prompt เดิม") as raised:
            window._wait_flow_step("JOB-ATTACH-STOP", 2, timeout=1800, cancel_event=_NeverCancelled())

        self.assertIn("หยุดอย่างปลอดภัยหลังลองแนบรูปหนึ่งครั้ง", str(raised.exception))
        self.assertEqual(window.bridge.commands, [])
        self.assertGreater(window.bridge.calls, 1)
        self.assertLess(window.bridge.calls, 30)
        self.assertFalse(getattr(raised.exception, "flow_attachment_terminal", False))

    def test_submitted_flow_receipt_survives_route_reload(self):
        flow = (Path(__file__).resolve().parents[1] / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        gate = flow.index("if (!requestMatches && !submissionReceiptActive)")
        idle = flow.index('report("package_ready"', gate)
        guarded = flow.index("if (submissionReceiptActive)", idle)
        self.assertLess(gate, idle)
        self.assertLess(idle, guarded)
        self.assertIn("ติดตามโปรเจกต์เดิมโดยไม่กดสร้างซ้ำ", Path(__file__).resolve().parents[1].joinpath("ui", "main_window.py").read_text(encoding="utf-8"))

    def test_reopens_chrome_and_resumes_same_flow_checkpoint(self):
        window = MainWindow.__new__(MainWindow)
        window.bridge = _Bridge()
        window.events = queue.Queue()
        opened = []
        progress = []
        window._activate_or_launch_chrome = lambda url: opened.append(url) or "launched"
        window._chrome_window_available = lambda: True
        window._product_progress_event = lambda *args, **kwargs: progress.append((args, kwargs))
        ticks = iter(range(0, 500, 5))

        with patch("ui.main_window.time.monotonic", side_effect=lambda: next(ticks)):
            compatible = window._ensure_flow_extension(
                "JOB-RECOVERY", 2, cancel_event=_NeverCancelled(), timeout=75, queue_resume=True
            )

        self.assertEqual(compatible["version"], "0.15.74")
        self.assertEqual(opened, ["https://labs.google/fx/th/tools/flow"])
        self.assertEqual(window.bridge.cleared, [("JOB-RECOVERY", 2)])
        self.assertEqual(window.bridge.commands, [("open_flow", "JOB-RECOVERY", 2)])
        self.assertTrue(progress)
        self.assertTrue(any("Extension กลับมาออนไลน์แล้ว" in call[0][3] for call in progress))

    def test_product_resume_opens_chrome_and_focuses_next_flow_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            job_id = "JOB-RESUME"
            folder = root / job_id
            (folder / "generated").mkdir(parents=True)
            (folder / "videos").mkdir(parents=True)
            images = []
            for index in (1, 2, 3):
                relative = f"generated/selling_image_{index:02d}.png"
                (folder / relative).write_bytes(b"image")
                images.append(relative)
            (folder / "videos" / "flow_shot_01.mp4").write_bytes(b"video")
            job = {
                "id": job_id,
                "ai_status": "ready",
                "voice_status": "ready",
                "generated_images": images,
                "flow_shot_prompts": ["one", "two", "three"],
                "caption": "พร้อมโพสต์",
                "spoken_script": "พร้อมพากย์",
                "flow_clips": {"1": "videos/flow_shot_01.mp4"},
            }
            window = MainWindow.__new__(MainWindow)
            window.products = SimpleNamespace(root=root)
            window.bridge = _Bridge()
            opened = []
            console = []
            window._activate_or_launch_chrome = lambda url: opened.append(url) or "focused"
            window._write_console = lambda *args: console.append(args)

            shot = window._focus_product_flow_checkpoint(job_id, job)

            self.assertEqual(shot, 2)
            self.assertEqual(opened, ["https://labs.google/fx/th/tools/flow"])
            self.assertEqual(window.bridge.commands, [("focus_flow_web", job_id, 2)])
            self.assertTrue(console)

    def test_offline_product_resume_opens_flow_without_queuing_a_second_helper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            job_id = "JOB-OFFLINE-RESUME"
            folder = root / job_id
            (folder / "generated").mkdir(parents=True)
            images = []
            for index in (1, 2, 3):
                relative = f"generated/selling_image_{index:02d}.png"
                (folder / relative).write_bytes(b"image")
                images.append(relative)
            job = {
                "id": job_id, "ai_status": "ready", "voice_status": "ready",
                "generated_images": images, "flow_shot_prompts": ["one", "two", "three"],
                "caption": "พร้อมโพสต์", "spoken_script": "พร้อมพากย์", "flow_clips": {},
            }
            window = MainWindow.__new__(MainWindow)
            window.products = SimpleNamespace(root=root)
            window.bridge = _Bridge()
            opened = []
            window._activate_or_launch_chrome = lambda url: opened.append(url) or "launched"
            window._write_console = lambda *_args: None

            shot = window._focus_product_flow_checkpoint(job_id, job, queue_focus=False)

            self.assertEqual(shot, 1)
            self.assertEqual(opened, ["https://labs.google/fx/th/tools/flow"])
            self.assertEqual(window.bridge.commands, [])

    def test_stale_extension_heartbeat_launches_chrome_when_no_window_exists(self):
        window = MainWindow.__new__(MainWindow)
        window.cfg = {}
        opened = []
        window._open_url = lambda url: opened.append(url) or True

        with patch.object(window, "_chrome_window_available", side_effect=[False, False]):
            result = window._activate_or_launch_chrome("https://labs.google/fx/th/tools/flow")

        self.assertEqual(result, "launched")
        self.assertEqual(opened, ["https://labs.google/fx/th/tools/flow"])

    def test_live_chrome_window_is_focused_without_opening_another_tab(self):
        window = MainWindow.__new__(MainWindow)
        window.cfg = {}
        opened = []
        window._open_url = lambda url: opened.append(url) or True

        with patch.object(window, "_chrome_window_available", return_value=True), patch("ui.main_window.threading.Thread") as worker:
            result = window._activate_or_launch_chrome("https://labs.google/fx/th/tools/flow")

        self.assertEqual(result, "focused")
        self.assertEqual(opened, [])
        worker.assert_called_once()

    def test_generate_button_delay_reuses_same_flow_workspace(self):
        window = MainWindow.__new__(MainWindow)
        window.bridge = _FlowWaitBridge()
        window.events = queue.Queue()
        window._product_pipeline_job_id = "JOB-WAIT"

        result = window._wait_flow_step("JOB-WAIT", 3, cancel_event=_NeverCancelled())

        self.assertEqual(result["flow_step"], "generation_complete")
        self.assertEqual(window.bridge.commands, [("resume_flow_workspace", "JOB-WAIT", 3)])

    def test_slate_prompt_binding_delay_reuses_same_flow_workspace(self):
        window = MainWindow.__new__(MainWindow)
        window.bridge = _FlowPromptBindingBridge()
        window.events = queue.Queue()
        window._product_pipeline_job_id = "JOB-PROMPT"

        result = window._wait_flow_step("JOB-PROMPT", 2, cancel_event=_NeverCancelled())

        self.assertEqual(result["flow_step"], "generation_complete")
        self.assertEqual(window.bridge.commands, [("resume_flow_workspace", "JOB-PROMPT", 2)])
        emitted = list(window.events.queue)
        self.assertTrue(any("ช่อง Prompt ยังโหลดไม่ครบ" in detail for event, detail in emitted if event == "multi_flow_progress"))

    def test_ignored_generate_click_reuses_same_flow_workspace_before_outer_retry(self):
        window = MainWindow.__new__(MainWindow)
        window.bridge = _FlowSubmissionBridge()
        window.events = queue.Queue()
        window._product_pipeline_job_id = "JOB-SUBMIT"

        result = window._wait_flow_step("JOB-SUBMIT", 1, cancel_event=_NeverCancelled())

        self.assertEqual(result["flow_step"], "generation_complete")
        self.assertEqual(window.bridge.commands, [("resume_flow_workspace", "JOB-SUBMIT", 1)])
        emitted = list(window.events.queue)
        self.assertTrue(any("ลองส่งใหม่" in detail for event, detail in emitted if event == "multi_flow_progress"))

    def test_explicit_flow_error_beats_stale_credit_approval(self):
        window = MainWindow.__new__(MainWindow)
        window.bridge = _FlowExplicitErrorBridge()
        window.events = queue.Queue()
        window._product_pipeline_job_id = "JOB-ERROR"

        with self.assertRaisesRegex(RuntimeError, "แสดงปุ่มลองอีกครั้ง") as raised:
            window._wait_flow_step("JOB-ERROR", 3, cancel_event=_NeverCancelled())
        self.assertNotIn("FLOW_POLICY_BLOCKED", str(raised.exception))
        self.assertFalse(getattr(raised.exception, "flow_policy_terminal", False))

        emitted = []
        while not window.events.empty():
            emitted.append(window.events.get_nowait())
        self.assertTrue(any(
            event == "multi_flow_progress" and "ซ่อมอัตโนมัติ" in detail
            for event, detail in emitted
        ))
        self.assertEqual(window.bridge.commands, [])

    def test_active_queue_beats_policy_card_from_previous_attempt(self):
        window = MainWindow.__new__(MainWindow)
        bridge = _FlowExplicitErrorBridge()
        bridge.extension_status = lambda: {"clients": [{
            "version": bridge.REQUIRED_EXTENSION_VERSION,
            "flow_job_id": "JOB-ERROR",
            "flow_shot_index": 3,
            "flow_step": "generation_in_progress",
            "flow_message": "Google Flow รับงานแล้วและกำลังรอคิว",
            "flow_generation_active": False,
            "flow_page_excerpt": (
                "ล้มเหลว การสร้างนี้อาจละเมิดนโยบายของเรา ระบบไม่ได้เรียกเก็บเงินจากคุณ\n"
                "ลองอีกครั้ง\nวิดีโอของคุณถูกส่งเข้าคิวเรียบร้อยแล้ว"
            ),
        }]}
        calls = {"count": 0}
        original = bridge.extension_status
        def status_then_complete():
            calls["count"] += 1
            state = original()
            if calls["count"] >= 2:
                state["clients"][0]["flow_step"] = "generation_complete"
            return state
        bridge.extension_status = status_then_complete
        window.bridge = bridge
        window.events = queue.Queue()
        window._product_pipeline_job_id = "JOB-ERROR"

        result = window._wait_flow_step("JOB-ERROR", 3, cancel_event=_NeverCancelled())

        self.assertEqual(result["flow_step"], "generation_complete")
        self.assertEqual(window.bridge.commands, [])

    def test_unknown_flow_state_rebinds_workspace_before_global_timeout(self):
        window = MainWindow.__new__(MainWindow)
        window.bridge = _FlowUnknownBridge(complete_after=11)
        window.events = queue.Queue()
        window._product_pipeline_job_id = "JOB-UNKNOWN"

        result = window._wait_flow_step("JOB-UNKNOWN", 1, cancel_event=_NeverCancelled())

        self.assertEqual(result["flow_step"], "generation_complete")
        self.assertEqual(window.bridge.commands, [("inspect_flow", "JOB-UNKNOWN", 1)])

    def test_unknown_flow_state_fails_current_shot_after_bounded_recovery(self):
        window = MainWindow.__new__(MainWindow)
        window.bridge = _FlowUnknownBridge(complete_after=1000)
        window.events = queue.Queue()
        window._product_pipeline_job_id = "JOB-UNKNOWN"

        with self.assertRaisesRegex(RuntimeError, "ไม่เริ่มสร้างภายใน 90 วินาที") as caught:
            window._wait_flow_step("JOB-UNKNOWN", 1, cancel_event=_NeverCancelled())
        self.assertTrue(caught.exception.flow_retry_forbidden)

        self.assertEqual(window.bridge.commands, [
            ("inspect_flow", "JOB-UNKNOWN", 1),
            ("inspect_flow", "JOB-UNKNOWN", 1),
        ])

    def test_unknown_flow_state_with_agent_activity_does_not_requeue_healthy_render(self):
        window = MainWindow.__new__(MainWindow)
        window.bridge = _FlowUnknownBridge(
            complete_after=11,
            page_excerpt="Considering Video Generation\nstop\nหยุด",
        )
        window.events = queue.Queue()
        window._product_pipeline_job_id = "JOB-UNKNOWN"

        result = window._wait_flow_step("JOB-UNKNOWN", 1, cancel_event=_NeverCancelled())

        self.assertEqual(result["flow_step"], "generation_complete")
        self.assertEqual(window.bridge.commands, [])

    def test_stale_preparing_on_landing_page_reopens_same_shot_checkpoint(self):
        window = MainWindow.__new__(MainWindow)
        window.bridge = _FlowPreparingBridge()
        window.events = queue.Queue()
        window._product_pipeline_job_id = "JOB-PREPARING"
        ticks = count(0, 10)

        with patch("ui.main_window.time.monotonic", side_effect=lambda: next(ticks)):
            result = window._wait_flow_step("JOB-PREPARING", 1, cancel_event=_NeverCancelled())

        self.assertEqual(result["flow_step"], "generation_complete")
        self.assertEqual(window.bridge.cleared, [("JOB-PREPARING", 1)])
        self.assertEqual(window.bridge.commands, [("open_flow", "JOB-PREPARING", 1)])


if __name__ == "__main__":
    unittest.main()
