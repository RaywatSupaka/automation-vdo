import base64
import unittest
from queue import Queue
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from PIL import Image
from core.story_manager import StoryManager
from ui.main_window import MainWindow


ROOT = Path(__file__).resolve().parents[1]


class StoryFlowContractTests(unittest.TestCase):
    def test_policy_scene_two_pauses_before_scene_three_without_fallback(self):
        # Run the real collector + waiter + manager. Only provider/download and
        # FFmpeg are simulated; scene3 is NOT pre-checkpointed like older tests.
        for terminal_on_inspect in (False, True):
            with self.subTest(terminal_on_inspect=terminal_on_inspect), TemporaryDirectory() as temp:
                root = Path(temp)
                stories = StoryManager(root)
                job = stories.create("Policy sequence", scene_count=6, video_generation_mode="google_flow")
                image = root / "image.png"
                Image.new("RGB", (64, 96), "orange").save(image)
                encoded = base64.b64encode(image.read_bytes()).decode()
                stories.apply_ai_result({
                    "job_id": job["id"], "video_title": "Policy sequence",
                    "video_description": "Test", "narration_script": "ทดสอบเรื่องต่อเนื่อง",
                    "scene_prompts": [f"scene {i}" for i in range(1, 7)],
                    "scene_narrations": [f"ฉากที่ {i}" for i in range(1, 7)],
                    "scene_durations": [4] * 6, "story_entities": [], "scene_entities": [[] for _ in range(6)],
                    "generated_images": [encoded] * 6,
                })
                for index in (1, 4, 5, 6):
                    clip = root / f"flow{index}.mp4"
                    clip.write_bytes(f"saved-flow-{index}".encode() * 200)
                    stories.attach_flow_clip(job["id"], index, clip)
                commands = []

                class Bridge:
                    REQUIRED_EXTENSION_VERSION = "test-compatible"
                    scene = 0
                    reads = 0
                    opened = False

                    def queue_extension_command(self, action, _job, scene, **_kwargs):
                        commands.append((action, scene))
                        self.scene = scene
                        if action == "inspect_flow":
                            self.reads = 0
                        if action == "open_flow":
                            if scene != 3:
                                raise AssertionError("Rejected scene was reopened")
                            self.opened = True

                    def clear_flow_progress(self, *_args):
                        pass

                    def extension_status(self):
                        self.reads += 1
                        terminal = self.scene == 2 and (terminal_on_inspect or self.reads > 1)
                        step = "generation_failed" if terminal else "generation_in_progress"
                        if self.scene == 3:
                            step = "generation_complete" if self.opened else "checkpoint_missing"
                        return {"clients": [{
                            "version": self.REQUIRED_EXTENSION_VERSION, "flow_job_id": job["id"],
                            "flow_shot_index": self.scene, "flow_run_id": f"RUN-{self.scene}",
                            "flow_step": step, "flow_message": "policy" if terminal else step,
                            "flow_failure_code": "FLOW_POLICY_BLOCKED" if terminal else "",
                            "flow_policy_failure_category": "face_or_public_figure" if terminal else "",
                            "flow_failure_card_fingerprint": "CARD2" if terminal else "",
                        }]}

                window = MainWindow.__new__(MainWindow)
                window.stories, window.bridge, window.events = stories, Bridge(), Queue()
                window.cfg = {"ffmpeg_path": ""}
                window._ensure_flow_extension = lambda *_args, **_kwargs: None
                window._write_console = lambda *_args, **_kwargs: None
                window._video_render_settings = lambda: {"width": 360, "height": 640, "fps": 24, "crf": 23, "motion_strength": 0.5}
                downloaded = root / "flow3.mp4"
                downloaded.write_bytes(b"new-scene-three" * 200)
                window._wait_download = mock.Mock(return_value=downloaded)
                canonical = stories.root / job["id"] / "generated" / "scene_02.png"
                canonical_bytes = canonical.read_bytes()

                def render_local(source, target, **kwargs):
                    self.assertEqual(Path(source), canonical)
                    self.assertEqual(Path(source).read_bytes(), canonical_bytes)
                    self.assertEqual(kwargs["duration"], 4)
                    Path(target).parent.mkdir(parents=True, exist_ok=True)
                    Path(target).write_bytes(b"local-scene-two" * 200)

                with mock.patch("ui.main_window.StoryVideoComposer") as composer:
                    composer.return_value.render_scene_motion_clip.side_effect = render_local
                    with self.assertRaises(RuntimeError) as caught:
                        window._collect_story_flow_clips(job["id"], None)
                    self.assertTrue(caught.exception.flow_retry_forbidden)
                    composer.assert_not_called()
                    self.assertNotIn(("open_flow", 2), commands)
                    self.assertNotIn(("download_flow_result", 2), commands)
                    self.assertFalse(any(scene == 3 for _, scene in commands))
                saved = stories.get(job["id"])
                self.assertEqual(len(saved["flow_clips"]), 4)
                self.assertFalse(saved.get("flow_fallback_clips"))
                self.assertFalse(saved.get("flow_policy_failure_history"))

    def test_drama_uses_the_video_mode_selected_by_the_user(self):
        self.assertEqual(
            MainWindow._story_video_mode_key("Google Flow ทุกฉาก"),
            "google_flow",
        )
        self.assertEqual(
            MainWindow._story_video_mode_key(
                "ภาพเคลื่อนไหวอัตโนมัติ",
                {"video_generation_mode": "google_flow"},
            ),
            "google_flow",
        )
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        creator = source.split("    def _create_story_and_run", 1)[1].split("\n    def ", 1)[0]
        queue_starter = source.split("    def _start_next_story_queue_item", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("self._story_video_mode_key", creator)
        self.assertNotIn('"image_motion" if drama_context', creator)
        self.assertIn('if queued_video_mode in {"image_motion", "google_flow", "meta_ai"}', queue_starter)
        self.assertNotIn('item.get("video_generation_mode") or "image_motion"', queue_starter)

    def test_desktop_story_row_reports_hybrid_sources_truthfully(self):
        row = MainWindow._desktop_story_row({
            "id": "STORY-HYBRID",
            "video_generation_mode": "google_flow",
            "video_status": "clips_ready",
            "scene_count": 3,
            "flow_clip_count": 2,
            "flow_fallback_count": 1,
            "flow_scene_count": 3,
            "video_source_type": "google_flow_story_hybrid_clips",
            "flow_fallback_metadata": {"2": {"source_type": "story_local_motion_fallback"}},
        })

        self.assertEqual(row["video_status"], "Flow 2 + Local 1/3")
        self.assertEqual(row["flow_remote_count"], 2)
        self.assertEqual(row["flow_fallback_count"], 1)
        self.assertEqual(row["flow_scene_count"], 3)
        self.assertEqual(row["video_source_type"], "google_flow_story_hybrid_clips")

    def test_story_composer_labels_bounded_policy_fallback_as_hybrid(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        method = source.split("    def _compose_story_media", 1)[1].split("\n    def ", 1)[0]
        collector = source.split("    def _collect_story_flow_clips", 1)[1].split("\n    def ", 1)[0]

        self.assertNotIn("flow_fallback_requested", method)
        self.assertNotIn("mark_flow_fallback", method)
        self.assertNotIn("story_image_sequence_fallback", method)
        self.assertIn('if video_generation_mode == "google_flow":', method)
        self.assertIn("_collect_story_flow_clips", method)
        self.assertIn("MultiFlowComposer", method)
        self.assertIn("google_flow_story_hybrid_fallback", method)
        self.assertIn("flow_fallback_scenes", method)
        self.assertNotIn("register_flow_policy_failure", collector)
        self.assertNotIn("render_scene_motion_clip", collector)
        self.assertNotIn("attach_flow_fallback_clip", collector)
        self.assertIn("flow_fallback_clips", collector)
        self.assertIn('getattr(exc, "flow_policy_terminal", False)', collector)
        self.assertIn("FlowVideoReviewError", collector)
        self.assertIn('getattr(exc, "flow_retry_forbidden", False)', collector)
        self.assertNotIn("may violate", collector.lower())
        self.assertNotIn("public figure", collector.lower())
        self.assertNotIn("retry_face_neutral_flow_prompt", collector)
        manager = (ROOT / "core" / "story_manager.py").read_text(encoding="utf-8")
        self.assertNotIn("retry_face_neutral_flow_prompt", manager)
        self.assertNotIn("ENVIRONMENT-MOTION RETRY", manager)
        self.assertIn('actual_source_type = "story_image_sequence"', method)

    def test_flow_waiter_prefers_structured_face_policy_signal(self):
        source = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        waiter = source.split("    def _wait_flow_step", 1)[1].split("\n    def ", 1)[0]

        self.assertIn('client.get("flow_failure_code")', waiter)
        self.assertIn('failure_code == "FLOW_POLICY_BLOCKED"', waiter)
        self.assertIn('client.get("flow_policy_failure_category")', waiter)
        self.assertIn("FLOW_FACE_POLICY_BLOCKED", waiter)
        self.assertIn("page_excerpt", waiter)

    def test_flow_waiter_raises_face_marker_from_structured_failure_code(self):
        class PolicyBridge:
            REQUIRED_EXTENSION_VERSION = "test-compatible"

            @staticmethod
            def extension_status():
                return {"clients": [{
                    "version": "test-compatible",
                    "flow_job_id": "STORY-POLICY",
                    "flow_shot_index": 4,
                    "flow_step": "user_action_required",
                    "flow_message": "request denied",
                    "flow_page_excerpt": "ambiguous visible text",
                    "flow_failure_code": "FLOW_POLICY_BLOCKED",
                    "flow_policy_failure_category": "face_or_public_figure",
                    "flow_run_id": "RUN-FACE-POLICY",
                    "flow_failure_card_fingerprint": "CARD-FACE-POLICY",
                }]}

        window = MainWindow.__new__(MainWindow)
        window.bridge = PolicyBridge()
        window.events = Queue()

        with self.assertRaisesRegex(RuntimeError, "FLOW_FACE_POLICY_BLOCKED") as raised:
            window._wait_flow_step("STORY-POLICY", 4, timeout=1, total_shots=6)
        self.assertEqual(raised.exception.flow_run_id, "RUN-FACE-POLICY")
        self.assertEqual(raised.exception.failure_card_fingerprint, "CARD-FACE-POLICY")
        self.assertTrue(raised.exception.flow_policy_terminal)

    def test_flow_waiter_does_not_classify_stale_policy_excerpt_as_terminal_code(self):
        class StaleExcerptBridge:
            REQUIRED_EXTENSION_VERSION = "test-compatible"

            @staticmethod
            def extension_status():
                return {"clients": [{
                    "version": "test-compatible",
                    "flow_job_id": "STORY-STALE",
                    "flow_shot_index": 4,
                    "flow_step": "generation_failed",
                    "flow_message": "generic generation failure",
                    "flow_page_excerpt": "An old card says this may violate our policy",
                    "flow_failure_code": "",
                    "flow_policy_failure_category": "",
                    "flow_run_id": "RUN-STALE",
                    "flow_failure_card_fingerprint": "CARD-STALE",
                }]}

        window = MainWindow.__new__(MainWindow)
        window.bridge = StaleExcerptBridge()
        window.events = Queue()

        with self.assertRaises(RuntimeError) as raised:
            window._wait_flow_step("STORY-STALE", 4, timeout=1, total_shots=6)
        self.assertNotIn("FLOW_POLICY_BLOCKED", str(raised.exception))
        self.assertNotIn("FLOW_FACE_POLICY_BLOCKED", str(raised.exception))
        self.assertFalse(getattr(raised.exception, "flow_policy_terminal", False))

    def test_duplicate_policy_heartbeat_safe_stops_without_open_or_resubmit(self):
        class DuplicateStories:
            def __init__(self, root):
                self.root = root

            @staticmethod
            def get(_job_id):
                return {
                    "scene_count": 2,
                    "flow_clips": {},
                    "flow_fallback_clips": {},
                }

            @staticmethod
            def mark_running(_job_id, _stage):
                return None

            @staticmethod
            def register_flow_policy_failure(*_args, **_kwargs):
                return {
                    "action": "duplicate_policy_event",
                    "attempt": 1,
                    "duplicate_reason": "same_run_and_failure_card",
                }

        class DuplicateBridge:
            REQUIRED_EXTENSION_VERSION = "test-compatible"

            def __init__(self):
                self.commands = []
                self.clear_count = 0

            @staticmethod
            def extension_status():
                return {"clients": [{
                    "version": "test-compatible",
                    "flow_job_id": "STORY-DUPLICATE",
                    "flow_shot_index": 1,
                    "flow_step": "generation_in_progress",
                }]}

            def queue_extension_command(self, action, *_args, **_kwargs):
                self.commands.append(action)

            def clear_flow_progress(self, *_args, **_kwargs):
                self.clear_count += 1

        with TemporaryDirectory() as temp:
            bridge = DuplicateBridge()
            window = MainWindow.__new__(MainWindow)
            window.stories = DuplicateStories(Path(temp))
            window.bridge = bridge
            window.events = Queue()
            window._ensure_flow_extension = lambda *_args, **_kwargs: None
            window._write_console = lambda *_args, **_kwargs: None
            window._flow_duplicate_passive_wait_seconds = 0.01

            terminal = RuntimeError("FLOW_FACE_POLICY_BLOCKED • duplicate heartbeat")
            terminal.flow_policy_terminal = True
            terminal.flow_run_id = "RUN-ONE"
            terminal.failure_card_fingerprint = "CARD-ONE"

            def raise_terminal(*_args, **_kwargs):
                raise terminal

            window._wait_flow_step = raise_terminal

            with self.assertRaisesRegex(RuntimeError, "FLOW_REPAIR_REVIEW"):
                window._collect_story_flow_clips("STORY-DUPLICATE", None)

            self.assertIn("inspect_flow", bridge.commands)
            self.assertNotIn("stop_flow_generation", bridge.commands)
            self.assertNotIn("open_flow", bridge.commands)
            self.assertNotIn("download_flow_result", bridge.commands)
            self.assertEqual(bridge.clear_count, 0)

        recovery = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        method = recovery.split("    def _schedule_story_recovery", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("STORY_FLOW_DUPLICATE_POLICY_EVENT", method)
        self.assertIn("return False", method)

    def test_first_policy_terminal_pauses_and_preserves_real_clips(self):
        class OneRunBridge:
            REQUIRED_EXTENSION_VERSION = "test-compatible"

            def __init__(self, job_id):
                self.job_id = job_id
                self.commands = []
                self.clear_count = 0

            def extension_status(self):
                return {"clients": [{
                    "version": "test-compatible",
                    "flow_job_id": self.job_id,
                    "flow_shot_index": 1,
                    "flow_step": "generation_in_progress",
                    "flow_run_id": "RUN-ORIGINAL",
                }]}

            def queue_extension_command(self, action, *_args, **_kwargs):
                self.commands.append(action)

            def clear_flow_progress(self, *_args, **_kwargs):
                self.clear_count += 1

        with TemporaryDirectory() as temp:
            root = Path(temp)
            stories = StoryManager(root)
            job = stories.create(
                "Story policy immediate fallback test", scene_count=6,
                video_generation_mode="google_flow",
            )
            image = root / "scene.png"
            Image.new("RGB", (64, 96), "orange").save(image)
            encoded = base64.b64encode(image.read_bytes()).decode()
            stories.apply_ai_result({
                "job_id": job["id"],
                "video_title": "Immediate policy fallback test",
                "video_description": "source accounting test",
                "narration_script": "ทดสอบการทำงานต่อเนื่อง",
                "scene_prompts": [f"scene prompt {index}" for index in range(1, 7)],
                "scene_narrations": [f"ฉากที่ {index}" for index in range(1, 7)],
                "scene_durations": [4] * 6,
                "story_entities": [], "scene_entities": [[] for _ in range(6)],
                "generated_images": [encoded] * 6,
            })
            for scene_index in range(2, 7):
                clip = root / f"flow-{scene_index}.mp4"
                clip.write_bytes((f"real-flow-{scene_index}-".encode()) * 100)
                stories.attach_flow_clip(job["id"], scene_index, clip)

            bridge = OneRunBridge(job["id"])
            window = MainWindow.__new__(MainWindow)
            window.stories = stories
            window.bridge = bridge
            window.events = Queue()
            window.cfg = {"ffmpeg_path": ""}
            window._ensure_flow_extension = lambda *_args, **_kwargs: None
            window._write_console = lambda *_args, **_kwargs: None
            window._video_render_settings = lambda: {
                "width": 360, "height": 640, "fps": 24, "crf": 23,
                "motion_strength": 0.5,
            }
            def raise_terminal(*_args, **_kwargs):
                error = RuntimeError("FLOW_FACE_POLICY_BLOCKED • terminal card")
                error.flow_policy_terminal = True
                error.flow_run_id = "RUN-ORIGINAL"
                error.failure_card_fingerprint = "POLICY-CARD"
                raise error

            window._wait_flow_step = raise_terminal

            def render_local(_image, target, **_kwargs):
                Path(target).parent.mkdir(parents=True, exist_ok=True)
                Path(target).write_bytes(b"local-motion-fallback-" * 100)
                return {"source_type": "story_local_motion_fallback"}

            with mock.patch("ui.main_window.StoryVideoComposer") as composer_type:
                composer_type.return_value.render_scene_motion_clip.side_effect = render_local
                with self.assertRaisesRegex(RuntimeError, "FLOW_REPAIR_REVIEW"):
                    window._collect_story_flow_clips(job["id"], None)
                composer_type.assert_not_called()
            saved = stories.get(job["id"])
            self.assertFalse(saved.get("flow_fallback_clips"))
            self.assertFalse(saved.get("flow_policy_failure_history"))
            self.assertEqual(len(saved["flow_clips"]), 5)
            self.assertNotIn("open_flow", bridge.commands)
            self.assertNotIn("download_flow_result", bridge.commands)
            self.assertNotIn("stop_flow_generation", bridge.commands)

    def test_persisted_legacy_policy_history_pauses_without_flow_command(self):
        class NoFlowBridge:
            REQUIRED_EXTENSION_VERSION = "test-compatible"

            def __init__(self):
                self.commands = []

            def queue_extension_command(self, action, *_args, **_kwargs):
                self.commands.append(action)

            @staticmethod
            def clear_flow_progress(*_args, **_kwargs):
                raise AssertionError("historical policy checkpoint must not clear/reopen Flow")

            @staticmethod
            def extension_status():
                raise AssertionError("historical policy checkpoint must not inspect Flow")

        with TemporaryDirectory() as temp:
            root = Path(temp)
            stories = StoryManager(root)
            job = stories.create(
                "Legacy policy checkpoint", scene_count=6,
                video_generation_mode="google_flow",
            )
            # This fixture represents a persisted job from before the Story
            # content contract, just like its historical Flow retry record.
            job.pop("story_content_contract")
            stories._save(job)
            image = root / "legacy-scene.png"
            Image.new("RGB", (64, 96), "purple").save(image)
            encoded = base64.b64encode(image.read_bytes()).decode()
            stories.apply_ai_result({
                "job_id": job["id"], "video_title": "Legacy checkpoint",
                "video_description": "compatibility", "narration_script": "ทดสอบ",
                "scene_prompts": [f"legacy scene {index}" for index in range(1, 7)],
                "scene_narrations": [f"ฉาก {index}" for index in range(1, 7)],
                "scene_durations": [4] * 6, "generated_images": [encoded] * 6,
            })
            stories.register_flow_policy_failure(
                job["id"], 1, "historical authenticated policy terminal",
                flow_run_id="RUN-HISTORICAL", failure_card_fingerprint="CARD-HISTORICAL",
            )
            legacy = stories.get(job["id"])
            legacy["flow_policy_failure_history"]["1"][0]["action"] = "retry_face_neutral_flow_prompt"
            legacy["flow_prompt_profiles"] = {"1": "face_neutral_environment_motion_v1"}
            legacy["flow_prompt_retries"] = {"1": {"status": "ready_to_retry_flow"}}
            stories._save(legacy)
            for scene_index in range(2, 7):
                clip = root / f"legacy-flow-{scene_index}.mp4"
                clip.write_bytes((f"legacy-real-{scene_index}-".encode()) * 100)
                stories.attach_flow_clip(job["id"], scene_index, clip)

            bridge = NoFlowBridge()
            window = MainWindow.__new__(MainWindow)
            window.stories = stories
            window.bridge = bridge
            window.events = Queue()
            window.cfg = {"ffmpeg_path": ""}
            window._write_console = lambda *_args, **_kwargs: None
            window._video_render_settings = lambda: {
                "width": 360, "height": 640, "fps": 24, "crf": 23,
                "motion_strength": 0.5,
            }

            def render_local(_image, target, **_kwargs):
                Path(target).parent.mkdir(parents=True, exist_ok=True)
                Path(target).write_bytes(b"legacy-local-fallback-" * 100)

            with mock.patch("ui.main_window.StoryVideoComposer") as composer_type:
                composer_type.return_value.render_scene_motion_clip.side_effect = render_local
                with self.assertRaisesRegex(RuntimeError, "FLOW_REPAIR_REVIEW"):
                    window._collect_story_flow_clips(job["id"], None)
                composer_type.assert_not_called()
            saved = stories.get(job["id"])
            self.assertFalse(saved.get("flow_fallback_clips"))
            self.assertEqual(saved["flow_policy_failure_history"]["1"][0]["flow_run_id"], "RUN-HISTORICAL")
            self.assertEqual(len(saved["flow_clips"]), 5)
            self.assertEqual(bridge.commands, [])


if __name__ == "__main__":
    unittest.main()
