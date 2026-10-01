"""A failed single attach uses its canonical image, never an upload retry."""
import base64
import tempfile
import unittest
from itertools import count
from pathlib import Path
from queue import Queue
from unittest import mock

from PIL import Image
from core.cancellable_process import OperationCancelled
from core.story_manager import StoryManager
from ui.main_window import MainWindow
import test_product_flow_fallback as product_fixture


def evidence(run="RUN-ATTACH", shot=2):
    return {
        "schema_version": 1, "phase": "before_submit", "run_id": run,
        "project_id": "PROJECT-ATTACH", "attempt_key": f"JOB:{shot}:PROJECT-ATTACH",
        "attempt_started_at": 1000, "grace_started_at": 2000, "grace_elapsed_ms": 30000,
        "attachment_attempt_count": 1, "submission_absent": True,
        "generation_absent": True, "result_absent": True,
        "confirmation_absent": True, "terminal_latched": True,
    }


def terminal():
    error = RuntimeError("FLOW_ATTACHMENT_UNCONFIRMED • attachment terminal")
    error.flow_attachment_terminal = True
    error.flow_run_id = "RUN-ATTACH"
    error.failure_card_fingerprint = "ATTACH-CARD"
    error.attachment_failure_evidence = evidence()
    return error


class PassiveBridge:
    REQUIRED_EXTENSION_VERSION = "test-compatible"

    def __init__(self, snapshots):
        self.snapshots = snapshots
        self.commands = []

    def extension_status(self):
        current = self.snapshots.pop(0) if len(self.snapshots) > 1 else self.snapshots[0]
        return {"clients": [{"version": self.REQUIRED_EXTENSION_VERSION,
            "flow_job_id": "JOB-ATTACH", "flow_shot_index": 2, **current}]}

    def queue_extension_command(self, *args, **_kwargs):
        self.commands.append(args)


class FlowAttachmentFallbackWorkerTests(unittest.TestCase):
    def wait(self, snapshots):
        window = MainWindow.__new__(MainWindow)
        window.bridge = PassiveBridge(snapshots)
        window.events = Queue()
        window._product_pipeline_job_id = ""
        ticks = count(1, 2)
        with mock.patch("ui.main_window.time.monotonic", side_effect=lambda: next(ticks)), mock.patch("ui.main_window.time.sleep"):
            result = window._wait_flow_step("JOB-ATTACH", 2, timeout=200)
        self.assertEqual(window.bridge.commands, [])
        return result

    @staticmethod
    def snapshot():
        return {"flow_step": "attachment_failed", "flow_run_id": "RUN-ATTACH",
            "flow_failure_code": "FLOW_ATTACHMENT_UNCONFIRMED",
            "flow_failure_card_fingerprint": "ATTACH-CARD",
            "flow_attachment_failure_evidence": evidence()}

    def test_typed_latched_terminal_selects_image_fallback(self):
        with self.assertRaises(RuntimeError) as caught:
            self.wait([self.snapshot()])
        self.assertTrue(caught.exception.flow_attachment_terminal)
        self.assertFalse(getattr(caught.exception, "flow_policy_terminal", False))

    def test_late_image_after_manual_wait_keeps_real_flow_result(self):
        result = self.wait([
            {"flow_step": "attachment_needs_review", "flow_message": "ไม่อัปโหลดรูปซ้ำ"},
            {"flow_step": "attachment_waiting_manual"},
            {"flow_step": "generation_complete"},
        ])
        self.assertEqual(result["flow_step"], "generation_complete")

    def test_uploaded_asset_recovery_queues_once_then_accepts_real_result(self):
        terminal = self.snapshot()
        terminal["flow_attachment_failure_evidence"]["selection_recovery_available"] = True
        window = MainWindow.__new__(MainWindow)
        window.bridge = PassiveBridge([terminal, terminal, {"flow_step": "generation_complete"}])
        window.events = Queue()
        window._product_pipeline_job_id = ""
        ticks = count(1, 2)
        with mock.patch("ui.main_window.time.monotonic", side_effect=lambda: next(ticks)), mock.patch("ui.main_window.time.sleep"):
            result = window._wait_flow_step("JOB-ATTACH", 2, timeout=200)
        self.assertEqual(result["flow_step"], "generation_complete")
        self.assertEqual(window.bridge.commands, [("resume_flow_workspace", "JOB-ATTACH", 2)])

    def test_unaccepted_recovery_does_not_loop_commands(self):
        terminal = self.snapshot()
        terminal["flow_attachment_failure_evidence"]["selection_recovery_available"] = True
        window = MainWindow.__new__(MainWindow)
        window.bridge = PassiveBridge([terminal])
        window.events = Queue()
        window._product_pipeline_job_id = ""
        ticks = count(1, 2)
        with mock.patch("ui.main_window.time.monotonic", side_effect=lambda: next(ticks)), mock.patch("ui.main_window.time.sleep"):
            with self.assertRaises(RuntimeError) as caught:
                window._wait_flow_step("JOB-ATTACH", 2, timeout=300)
        self.assertTrue(caught.exception.flow_attachment_terminal)
        self.assertEqual(window.bridge.commands, [("resume_flow_workspace", "JOB-ATTACH", 2)])

    def test_live_picker_waits_without_recovery_commands(self):
        with mock.patch("ui.main_window.time.time", return_value=1000):
            result = self.wait([
                {"flow_step": "attachment_selecting", "flow_observation": {"received_at": 990}},
                {"flow_step": "generation_complete"},
            ])
        self.assertEqual(result["flow_step"], "generation_complete")

    def test_stale_picker_is_not_reported_as_live_loading(self):
        with mock.patch("ui.main_window.time.time", return_value=1000):
            with self.assertRaisesRegex(RuntimeError, "Extension"):
                self.wait([{"flow_step": "attachment_selecting", "flow_observation": {"received_at": 100}}])

    def test_generation_activity_wins_over_stale_attachment_terminal(self):
        result = self.wait([
            {**self.snapshot(), "flow_generation_active": True},
            {"flow_step": "generation_complete"},
        ])
        self.assertEqual(result["flow_step"], "generation_complete")

    def test_unlatched_or_mismatched_evidence_never_selects_fallback(self):
        for change in ({"terminal_latched": False}, {"run_id": "OLD"},
                       {"grace_elapsed_ms": 1000}, {"result_absent": False}):
            with self.subTest(change=change), self.assertRaises(RuntimeError) as caught:
                self.wait([{**self.snapshot(), "flow_attachment_failure_evidence": {**evidence(), **change}}])
            self.assertFalse(getattr(caught.exception, "flow_attachment_terminal", False))
            self.assertTrue(caught.exception.flow_retry_forbidden)

    def test_product_shot2_attachment_terminal_pauses_without_local_render(self):
        fixture = product_fixture.ProductFlowFallbackRetirementTests()
        with tempfile.TemporaryDirectory() as temp:
            manager, folder = fixture._make_job(Path(temp), "JOB-ATTACH")
            manager.attach_flow_clip("JOB-ATTACH", 1, fixture._write_probable_mp4(folder / "one.mp4", "one"))
            bridge = PassiveBridge([{"flow_step": "checkpoint_missing"}])
            bridge.clear_flow_progress = lambda *_args: None
            # The initial inspect is for shot2; shot3 takes a separate run.
            bridge.extension_status = lambda: {"clients": [{
                "version": bridge.REQUIRED_EXTENSION_VERSION, "flow_job_id": "JOB-ATTACH",
                "flow_shot_index": bridge.commands[-1][2], "flow_step": "checkpoint_missing",
            }]}
            window = fixture._window(manager, bridge)
            rendered, waited, downloaded = [], [], []

            def wait_flow(_job, shot, **_kwargs):
                waited.append(shot)
                if shot == 2:
                    raise terminal()

            def download(_job, shot, **_kwargs):
                downloaded.append(shot)
                return fixture._write_probable_mp4(folder / "three.mp4", "three")

            def render_local(source, target, **_kwargs):
                self.assertEqual(manager.get_job("JOB-ATTACH")["flow_attachment_fallbacks"]["2"]["status"], "render_pending")
                rendered.append(Path(source).resolve())
                fixture._write_probable_mp4(target, "local-two")
                return {"source_type": "product_local_motion_attachment_fallback"}

            def compose(_clips, target, **_kwargs):
                fixture._write_probable_mp4(target, "joined")
                return {"output": str(target)}

            window._wait_flow_step = wait_flow
            window._wait_download = download
            with mock.patch("ui.main_window.ProductImageVideoComposer") as local, mock.patch("ui.main_window.MultiFlowComposer") as composer:
                local.return_value.render_motion_segment.side_effect = render_local
                composer.return_value.compose.side_effect = compose
                with self.assertRaisesRegex(RuntimeError, "FLOW_REPAIR_REVIEW"):
                    window._multi_flow_worker("JOB-ATTACH", emit_event=False, raise_errors=True)
                composer.assert_not_called()
            saved = manager.get_job("JOB-ATTACH")
            self.assertEqual(waited, [2])
            self.assertEqual(downloaded, [])
            self.assertEqual(rendered, [])
            self.assertIn("1", saved["flow_clips"])
            self.assertFalse(saved.get("flow_attachment_fallbacks"))
            self.assertFalse(saved.get("flow_local_motion_clips"))

    def test_invalid_terminal_or_cancel_never_retries_or_renders(self):
        fixture = product_fixture.ProductFlowFallbackRetirementTests()
        invalid = RuntimeError("incomplete attachment evidence")
        invalid.flow_retry_forbidden = True
        for error in (invalid, OperationCancelled("cancelled")):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as temp:
                manager, folder = fixture._make_job(Path(temp), "JOB-ATTACH")
                manager.attach_flow_clip("JOB-ATTACH", 1, fixture._write_probable_mp4(folder / "one.mp4", "one"))
                bridge = PassiveBridge([{"flow_step": "checkpoint_missing"}])
                bridge.clear_flow_progress = lambda *_args: None
                window = fixture._window(manager, bridge)
                window._wait_flow_step = mock.Mock(side_effect=error)
                with mock.patch("ui.main_window.ProductImageVideoComposer") as local, self.assertRaises(type(error)):
                    window._multi_flow_worker("JOB-ATTACH", emit_event=False, raise_errors=True)
                local.assert_not_called()
                self.assertEqual([c[0] for c in bridge.commands].count("open_flow"), 1)
                self.assertNotIn("stop_flow_generation", [c[0] for c in bridge.commands])
                self.assertEqual(manager.get_job("JOB-ATTACH").get("flow_attachment_fallbacks", {}), {})

    def test_story_pending_attachment_checkpoint_pauses_without_browser(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stories = StoryManager(root)
            job = stories.create("Attachment fallback Story", scene_count=6, video_generation_mode="google_flow")
            image = root / "image.png"
            Image.new("RGB", (64, 96), "green").save(image)
            encoded = base64.b64encode(image.read_bytes()).decode()
            stories.apply_ai_result({"job_id": job["id"], "video_title": "Test",
                "video_description": "Test", "narration_script": "ทดสอบการประกอบคลิป",
                "scene_prompts": [f"scene {i}" for i in range(6)],
                "scene_narrations": ["ทดสอบ"] * 6, "scene_durations": [4] * 6,
                "story_entities": [], "scene_entities": [[] for _ in range(6)],
                "generated_images": [encoded] * 6})
            stories.register_flow_attachment_failure(job["id"], 2, "attachment terminal",
                flow_run_id="RUN-ATTACH", failure_card_fingerprint="ATTACH-CARD", evidence=evidence())
            for index in (1, 3, 4, 5, 6):
                path = root / f"flow-{index}.mp4"
                path.write_bytes(str(index).encode() * 2048)
                stories.attach_flow_clip(job["id"], index, path)
            window = MainWindow.__new__(MainWindow)
            window.stories, window.events, window.cfg = stories, Queue(), {"ffmpeg_path": ""}
            window.bridge = mock.Mock()
            window._video_render_settings = lambda: {"width": 360, "height": 640, "fps": 24, "crf": 23, "motion_strength": .5}
            window._write_console = lambda *_args: None
            rendered = []

            def render(source, target, **_kwargs):
                rendered.append(Path(source).name)
                Path(target).parent.mkdir(parents=True, exist_ok=True)
                Path(target).write_bytes(b"local-two" * 2048)
                return {}

            with mock.patch("ui.main_window.StoryVideoComposer") as composer:
                composer.return_value.render_scene_motion_clip.side_effect = render
                with self.assertRaisesRegex(RuntimeError, "FLOW_REPAIR_REVIEW"):
                    window._collect_story_flow_clips(job["id"], None)
                composer.assert_not_called()
            self.assertEqual(rendered, [])
            self.assertEqual(window.bridge.mock_calls, [])
            self.assertEqual(len(stories.get(job["id"])["flow_clips"]), 5)
            self.assertTrue(stories.get(job["id"])["flow_attachment_failure_history"])
