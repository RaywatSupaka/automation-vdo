"""Exercise the actual manual resume method without GUI, browser or user jobs."""
import ast
import copy
import json
import queue
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

from core.story_pipeline import story_provider_failover_action
from core.story_manager import StoryManager
from core.media_audio import audio_mode
from core.job_file_guard import uses_job_files


SOURCE = Path(__file__).resolve().parents[1] / "ui" / "main_window.py"


class StoryAnalysisResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"))
        method = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef) and node.name == "_retry_story_job")
        scope = {"Path": Path, "threading": threading,
                 "uses_job_files": uses_job_files,
                 "audio_mode": audio_mode,
                 "story_provider_failover_action": story_provider_failover_action}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), "exec"), scope)
        cls.resume_method = staticmethod(scope["_retry_story_job"])

    def window(self, *, checkpoint=True, provider="chatgpt", **changes):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        job = {
            "id": "STORY-RESUME", "scene_count": 6, "job_type": "story_short",
            "ai_status": "request_ready", "analysis_status": "ready", "status": "error",
            "image_ai_provider": provider, "visual_style": "anime",
            "story_content_contract": {"version": 1},
            "last_error": "STORY_IMAGE_REFUSED • first scene",
            **changes,
        }
        result = {
            "job_id": job["id"], "video_title": "River story", "video_description": "A river at dawn",
            "narration_script": "แม่น้ำยามเช้า", "visual_bible": {"light": "dawn"},
            "scene_prompts": [f"A river landscape, frame {index}" for index in range(6)],
            "scene_narrations": ["แม่น้ำยามเช้า"] * 6, "scene_durations": [4] * 6,
            "story_entities": [], "scene_entities": [[] for _ in range(6)],
        }
        path = root / job["id"] / "prompts" / "ai_analysis_checkpoint.json"
        path.parent.mkdir(parents=True)
        if checkpoint:
            path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        stories = Mock(root=root)
        stories.get.return_value = copy.deepcopy(job)
        resolver = StoryManager(root)
        resolver.root = root
        resolver.get = stories.get
        stories.load_analysis_checkpoint.side_effect = resolver.load_analysis_checkpoint
        window = types.SimpleNamespace(
            stories=stories, bridge=Mock(), root=Mock(), events=queue.Queue(),
            video_library=types.SimpleNamespace(root=root),
            _story_pipeline_job_id="", _story_cancel_event=None, story_job_id=Mock(),
            _compatible_extension=Mock(return_value=({}, True)), _close_story_progress=Mock(),
            _show_story_progress=Mock(), _update_story_progress=Mock(), _render_story=Mock(),
            _chrome_window_available=Mock(return_value=True), _launch_story_browser=Mock(),
            _activate_or_launch_chrome=Mock(), _ai_web_url=Mock(return_value=f"{provider}-web"),
            _monitor_story_browser_progress=Mock(),
        )
        window._retry_story_job = types.MethodType(self.resume_method, window)
        return window, job, result, path

    def assert_browser_action(self, window, action):
        self.assertEqual(window.bridge.mock_calls, [
            call.clear_ai_progress("STORY-RESUME"),
            call.queue_extension_command(action, "STORY-RESUME"),
        ])
        window.stories.set_image_ai_provider.assert_not_called()
        window._render_story.assert_not_called()

    def test_zero_images_and_saved_analysis_resume_the_existing_plan_on_either_provider(self):
        for provider in ("chatgpt", "gemini"):
            with self.subTest(provider=provider):
                window, job, _, path = self.window(provider=provider)
                before = path.read_bytes()
                window._retry_story_job(job["id"])
                self.assert_browser_action(window, "resume_chatgpt")
                self.assertEqual(path.read_bytes(), before)
                window.stories.mark_running.assert_called_once_with(job["id"], "chatgpt")
                window._ai_web_url.assert_called_once_with(provider)
                self.assertFalse(window._story_cancel_event.is_set())
                self.assertEqual(window.root.after.call_args.args[0], 700)

    def test_reviewed_prompt_override_does_not_trigger_fresh_analysis_or_rewrite_checkpoint(self):
        window, job, _, path = self.window(
            scene_prompt_overrides={"1": "The same river in a wide view"},
            scene_prompt_override_revision=1,
        )
        before = path.read_bytes()
        window._retry_story_job(job["id"])
        self.assert_browser_action(window, "resume_chatgpt")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(window.stories.get.return_value["scene_prompt_overrides"], job["scene_prompt_overrides"])

    def test_invalid_saved_analysis_stops_without_sending_a_new_master(self):
        for case in ("json", "wrong_job", "short_prompts", "blank_prompt", "missing_title", "missing_registry"):
            with self.subTest(case=case):
                window, job, result, path = self.window(checkpoint=case != "missing")
                if case == "json":
                    path.write_text("{broken", encoding="utf-8")
                elif case != "missing":
                    if case == "wrong_job": result["job_id"] = "STORY-OTHER"
                    elif case == "short_prompts": result["scene_prompts"].pop()
                    elif case == "blank_prompt": result["scene_prompts"][0] = " "
                    elif case == "missing_title": result.pop("video_title")
                    elif case == "missing_registry": result.pop("story_entities")
                    path.write_text(json.dumps(result), encoding="utf-8")
                before = path.read_bytes() if path.exists() else None
                with self.assertRaisesRegex(ValueError, "STORY_ANALYSIS_CHECKPOINT_REVIEW"):
                    window._retry_story_job(job["id"])
                self.assertEqual(window.bridge.mock_calls, [])
                window.stories.mark_running.assert_not_called()
                self.assertEqual(path.read_bytes() if path.exists() else None, before)

    def test_saved_valid_plan_does_not_depend_on_a_stale_status_flag(self):
        window, job, _, _ = self.window(analysis_status="pending")
        window._retry_story_job(job["id"])
        self.assert_browser_action(window, "resume_chatgpt")

    def test_no_saved_plan_or_images_still_starts_initial_analysis(self):
        window, job, _, _ = self.window(checkpoint=False)
        window._retry_story_job(job["id"])
        self.assert_browser_action(window, "open_story_chatgpt")

    def test_existing_partial_image_resume_does_not_require_the_new_checkpoint_check(self):
        window, job, _, _ = self.window(checkpoint=False, partial_generated_images=["generated/scene_01.png"])
        window._retry_story_job(job["id"])
        self.assert_browser_action(window, "resume_chatgpt")

    def test_complete_images_and_voice_continue_locally_without_browser_commands(self):
        images = [f"generated/scene_{index:02d}.png" for index in range(1, 7)]
        window, job, _, path = self.window(checkpoint=False, ai_status="ready", generated_images=images,
                                         voice_status="ready", voice_path="audio/narration.wav")
        folder = path.parent.parent
        for relative in [*images, "audio/narration.wav"]:
            target = folder / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"saved-test-checkpoint")
        window._retry_story_job(job["id"])
        self.assertEqual(window.bridge.mock_calls, [])
        window.stories.mark_running.assert_called_once_with(job["id"], "voice")
        window.root.after.assert_called_once_with(300, window._render_story)
        window._launch_story_browser.assert_not_called()

    def test_legacy_valid_analysis_without_entity_metadata_still_resumes(self):
        window, job, result, path = self.window()
        window.stories.get.return_value.pop("story_content_contract")
        result.pop("story_entities")
        result.pop("scene_entities")
        path.write_text(json.dumps(result), encoding="utf-8")
        window._retry_story_job(job["id"])
        self.assert_browser_action(window, "resume_chatgpt")

    def test_active_job_guard_does_not_read_or_queue_another_job(self):
        window, job, _, _ = self.window()
        window._story_pipeline_job_id = "STORY-ACTIVE"
        window._retry_story_job(job["id"])
        window.stories.get.assert_not_called()
        window.bridge.assert_not_called()
        self.assertEqual(window.bridge.mock_calls, [])
        window.root.after.assert_not_called()

    def test_incompatible_extension_preserves_provider_launch_and_same_resume_action(self):
        window, job, _, _ = self.window(provider="gemini")
        window._compatible_extension.return_value = ({}, False)
        window._retry_story_job(job["id"])
        self.assert_browser_action(window, "resume_chatgpt")
        self.assertEqual(window._launch_story_browser.call_args.args[:2], (job["id"], "gemini"))
        window._activate_or_launch_chrome.assert_not_called()

    def test_manual_meta_continue_does_not_replace_receipt_before_extension_is_paired(self):
        window, job, _, _ = self.window(scene_count=1, ai_status="ready",
                                        video_generation_mode="meta_ai",
                                        generated_images=["generated/scene_01.png"],
                                        voice_status="ready", voice_path="voice.wav")
        folder = window.stories.root / job["id"]
        (folder / "generated").mkdir()
        (folder / "generated" / "scene_01.png").write_bytes(b"saved image")
        (folder / "voice.wav").write_bytes(b"saved voice")
        window._compatible_extension.return_value = ({}, False)
        window.bridge.REQUIRED_EXTENSION_VERSION = "0.15.443"
        with self.assertRaisesRegex(ValueError, "0.15.443"):
            window._retry_story_job(job["id"], fresh_meta_scene=True)
        window.stories.mark_running.assert_not_called()
        self.assertEqual(window._story_pipeline_job_id, "")
        window.bridge.queue_extension_command.assert_not_called()

    def test_explicit_meta_continue_uses_fresh_scene_api_and_ordinary_resume_does_not(self):
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                window, job, _, _ = self.window(checkpoint=False, scene_count=1, ai_status="ready",
                                                video_generation_mode="meta_ai",
                                                generated_images=["generated/scene_01.png"],
                                                audio_choices={"mode": "none"})
                folder = window.stories.root / job["id"]
                (folder / "generated").mkdir()
                (folder / "generated" / "scene_01.png").write_bytes(b"saved image")
                with patch('core.meta_video.MetaVideoManager') as manager:
                    manager.return_value.restart_unfinished_on_continue.return_value = {
                        'index': 1, 'stage': 'prepared', 'fresh_start_reason': 'manual_continue'}
                    window._retry_story_job(job["id"], fresh_meta_scene=explicit)
                    if explicit:
                        manager.return_value.restart_unfinished_on_continue.assert_called_once_with(job['id'])
                        self.assertIn('Meta ฉาก 1 ใหม่', window._update_story_progress.call_args.args[0]['message'])
                    else:
                        manager.assert_not_called()
                window.root.after.assert_called_once_with(300, window._render_story)
                window.bridge.queue_extension_command.assert_not_called()

    def test_dispatch_failure_preserves_new_cancel_event_ownership(self):
        window, job, _, _ = self.window()
        window.bridge.queue_extension_command.side_effect = RuntimeError("transport unavailable")
        window._retry_story_job(job["id"])
        kind, payload = window.events.get_nowait()
        self.assertEqual(kind, "story_error")
        self.assertEqual(payload["job_id"], job["id"])
        self.assertIs(payload["cancel_event"], window._story_cancel_event)
        self.assertEqual(payload["value"], "transport unavailable")
        window.root.after.assert_not_called()


if __name__ == "__main__":
    unittest.main()
