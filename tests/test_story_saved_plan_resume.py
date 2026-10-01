"""Actual desktop paths with isolated local jobs; no UI, browser or paid API."""
import copy
import json
import queue
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.story_manager import StoryManager
from ui.main_window import MainWindow


class SavedStoryPlanResumeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.manager = StoryManager(temporary.name)

    def job_and_analysis(self, provider="gemini"):
        job = self.manager.create("แม่น้ำยามเช้า", scene_count=6, image_ai_provider=provider)
        return job, {
            "job_id": job["id"], "video_title": "แม่น้ำยามเช้า", "video_description": "เรื่องเดิม",
            "narration_script": "แม่น้ำไหลผ่านหมู่บ้าน", "visual_bible": {"lighting": "dawn"},
            "scene_prompts": [f"A river at dawn, camera angle {index}" for index in range(6)],
            "scene_narrations": ["แม่น้ำไหลผ่านหมู่บ้าน"] * 6, "scene_durations": [4] * 6,
            "story_entities": [], "scene_entities": [[] for _ in range(6)],
        }

    def window(self):
        return SimpleNamespace(
            stories=self.manager, bridge=Mock(), root=Mock(), events=queue.Queue(),
            _story_pipeline_job_id="", _story_cancel_event=None, story_job_id=Mock(),
            _compatible_extension=Mock(return_value=({}, True)), _close_story_progress=Mock(),
            _show_story_progress=Mock(), _update_story_progress=Mock(), _render_story=Mock(),
            _chrome_window_available=Mock(return_value=True), _launch_story_browser=Mock(),
            _activate_or_launch_chrome=Mock(), _ai_web_url=Mock(return_value="provider-web"),
            _monitor_story_browser_progress=Mock(),
        )

    def test_save_package_and_resume_agree_on_optional_metadata_for_both_providers(self):
        for provider in ("chatgpt", "gemini"):
            for optional in ("video_description", "scene_durations", "visual_bible"):
                with self.subTest(provider=provider, optional=optional):
                    job, result = self.job_and_analysis(provider)
                    result.pop(optional)
                    self.manager.save_analysis_checkpoint(job["id"], result)
                    folder = self.manager.root / job["id"]
                    target = folder / "prompts/ai_analysis_checkpoint.json"
                    before = {p: p.read_bytes() for p in (target, folder / "job.json")}
                    resolved = self.manager.load_analysis_checkpoint(job["id"])
                    package = self.manager.plugin_request(job["id"])
                    self.assertEqual(resolved, package["analysis_checkpoint"])
                    self.assertEqual({p: p.read_bytes() for p in before}, before)
                    self.assertEqual(resolved["scene_prompts"], result["scene_prompts"])
                    self.assertEqual(resolved["narration_script"], result["narration_script"])
                    self.assertEqual(resolved["story_entities"], result["story_entities"])
                    self.assertTrue(resolved["video_description"])
                    self.assertEqual(len(resolved["scene_durations"]), 6)
                    app = self.window()
                    MainWindow._retry_story_job(app, job["id"])
                    app.bridge.queue_extension_command.assert_called_once_with("resume_chatgpt", job["id"])
                    self.assertEqual(target.read_bytes(), before[target])

    def test_complete_legacy_manifest_plan_is_reused_without_recreating_checkpoint(self):
        job, result = self.job_and_analysis()
        self.manager.save_analysis_checkpoint(job["id"], result)
        folder = self.manager.root / job["id"]
        checkpoint = folder / "prompts/ai_analysis_checkpoint.json"
        checkpoint.unlink()  # Only this temporary test artifact is removed.
        before = (folder / "job.json").read_bytes()
        package = self.manager.plugin_request(job["id"])
        self.assertEqual(package["analysis_checkpoint"]["scene_prompts"], result["scene_prompts"])
        self.assertEqual((folder / "job.json").read_bytes(), before)
        self.assertFalse(checkpoint.exists())
        app = self.window()
        MainWindow._retry_story_job(app, job["id"])
        app.bridge.queue_extension_command.assert_called_once_with("resume_chatgpt", job["id"])
        self.assertFalse(checkpoint.exists())

    def test_bad_explicit_checkpoint_cannot_be_hidden_by_a_complete_manifest(self):
        for broken in ("{broken", {"job_id": "STORY-OTHER"}):
            with self.subTest(broken=broken):
                job, result = self.job_and_analysis()
                self.manager.save_analysis_checkpoint(job["id"], result)
                folder = self.manager.root / job["id"]
                target = folder / "prompts/ai_analysis_checkpoint.json"
                target.write_text(broken if isinstance(broken, str) else json.dumps(broken), encoding="utf-8")
                before = {p: p.read_bytes() for p in (target, folder / "job.json")}
                app = self.window()
                for action in (lambda: self.manager.load_analysis_checkpoint(job["id"]),
                               lambda: self.manager.plugin_request(job["id"]),
                               lambda: MainWindow._retry_story_job(app, job["id"])):
                    with self.assertRaisesRegex(ValueError, "STORY_ANALYSIS_CHECKPOINT_REVIEW"):
                        action()
                self.assertEqual({p: p.read_bytes() for p in before}, before)
                self.assertEqual(app.bridge.mock_calls, [])

    def test_missing_scene_plan_and_identity_mismatch_are_not_defaulted(self):
        job, result = self.job_and_analysis()
        for field, value in (("scene_prompts", ["one"]), ("scene_narrations", ["one"]),
                             ("story_entities", None), ("scene_entities", [[]])):
            with self.subTest(field=field):
                invalid = {**copy.deepcopy(result), field: value}
                with self.assertRaises(ValueError):
                    self.manager.save_analysis_checkpoint(job["id"], invalid)
                self.assertFalse((self.manager.root / job["id"] / "prompts/ai_analysis_checkpoint.json").exists())

    def test_auto_recovery_uses_the_same_saved_plan_even_with_a_stale_status(self):
        job, result = self.job_and_analysis()
        job = self.manager.save_analysis_checkpoint(job["id"], result)
        job["analysis_status"] = "pending"
        self.manager._save(job)
        app = self.window()
        for name in ("_story_progress_message", "_story_progress_detail", "story_status", "status",
                     "_write_console", "_resume_story_automatically"):
            setattr(app, name, Mock())
        app._story_cancel_event = threading.Event()
        self.assertTrue(MainWindow._schedule_story_recovery(app, job["id"], "connection lost"))
        app.root.after.call_args.args[1]()
        app._resume_story_automatically.assert_called_once_with(
            job["id"], "resume_chatgpt", "gemini", cancel_event=app._story_cancel_event)

    def test_auto_recovery_does_not_spend_budget_on_corrupt_saved_analysis(self):
        job, result = self.job_and_analysis()
        self.manager.save_analysis_checkpoint(job["id"], result)
        folder = self.manager.root / job["id"]
        (folder / "prompts/ai_analysis_checkpoint.json").write_text("{broken", encoding="utf-8")
        before = (folder / "job.json").read_bytes()
        app = self.window()
        self.assertFalse(MainWindow._schedule_story_recovery(app, job["id"], "connection lost"))
        self.assertEqual((folder / "job.json").read_bytes(), before)
        app.root.after.assert_not_called()
        self.assertEqual(app.bridge.mock_calls, [])


class SavedStoryVoiceResumeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.manager = StoryManager(temporary.name)
        self.job = self.manager.create("เรื่องราว", scene_count=6)
        self.job.update(ai_status="ready", generated_images=[f"generated/scene_{i:02d}.png" for i in range(1, 7)],
                        narration_script="เรื่องราวของ Zylphorian [unsupported]", scene_narrations=["เรื่องราว"] * 6)
        self.manager._save(self.job)
        self.voice = self.manager.root / self.job["id"] / "audio/narration.wav"
        with wave.open(str(self.voice), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b"\0\0" * 800)
        self.manager.save_voice(self.job["id"], self.voice, "EXISTING-PAID-QUEUE")
        self.app = SimpleNamespace(stories=self.manager, _creation_settings=lambda _: {},
                                   events=queue.Queue(), _compose_story_media=Mock(return_value="composed"))
        self.app._queue_story_phase = lambda *args: MainWindow._queue_story_phase(self.app, *args)

    def run_worker(self):
        return MainWindow._render_story_worker(self.app, self.job["id"], "", "", "", threading.Event())

    def test_ready_voice_skips_new_tts_pronunciation_review_and_paid_api(self):
        before = self.voice.read_bytes()
        with patch("ui.main_window.ExternalTtsClient", side_effect=AssertionError("No paid request")):
            self.assertEqual(self.run_worker(), "composed")
        self.app._compose_story_media.assert_called_once()
        self.assertEqual(self.app._compose_story_media.call_args.args[2], self.voice)
        self.assertEqual(self.voice.read_bytes(), before)

    def test_narration_revision_invalidates_old_voice_and_still_checks_new_speech(self):
        # English is now valid narration; malformed voice tags still require review.
        self.manager.update_narration(self.job["id"], "บทใหม่ของ Zylphorian [unsupported]")
        self.assertEqual(self.manager.get(self.job["id"])["voice_status"], "needs_regeneration")
        with patch("ui.main_window.ExternalTtsClient", side_effect=AssertionError("No paid request")):
            with self.assertRaisesRegex(ValueError, "บทพากย์ยังไม่พร้อม"):
                self.run_worker()
        self.app._compose_story_media.assert_not_called()

    def test_empty_or_missing_voice_is_not_reused(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                if missing:
                    self.voice.unlink()
                else:
                    self.voice.write_bytes(b"")
                with self.assertRaisesRegex(ValueError, "บทพากย์ยังไม่พร้อม"):
                    self.run_worker()
                self.app._compose_story_media.assert_not_called()


if __name__ == "__main__":
    unittest.main()
