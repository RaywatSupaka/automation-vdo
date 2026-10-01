"""Exercise the desktop review adapter without starting a UI or browser."""
import copy
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core.story_manager import StoryManager
from core.story_pipeline import story_recovery_action
from ui.main_window import MainWindow


class StoryPromptReviewTests(unittest.TestCase):
    revised_prompt = "Doctor Doom waits by the portal before the confrontation; no strikes, blood or visible injury"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.manager = StoryManager(temporary.name)
        self.job = self.new_job()
        self.window = SimpleNamespace(
            stories=self.manager, _story_pipeline_job_id="", _write_console=Mock(),
            _retry_story_job=Mock(), _run_story_pipeline=Mock(), _render_story=Mock(),
            _schedule_story_recovery=Mock(), _close_automation_browser=Mock(),
            _refresh=Mock(), bridge=Mock(), root=Mock(), events=Mock(),
        )

    def new_job(self):
        job = self.manager.create("ตัวละคร: Doctor Doom", scene_count=6, visual_style="comic")
        self.manager.save_analysis_checkpoint(job["id"], {
            "video_title": "ประตูมิติก่อนพายุ", "video_description": "เรื่องเดิม",
            "narration_script": "ด็อกเตอร์ดูมเปิดประตูมิติ", "pronunciation_notes": {"Doctor Doom": "ด็อกเตอร์ดูม"},
            "scene_prompts": [f"Doctor Doom beside the portal, scene {index}" for index in range(1, 7)],
            "scene_narrations": ["ด็อกเตอร์ดูมเปิดประตูมิติ"] * 6, "scene_durations": [4] * 6,
            "visual_bible": {"character": "Doctor Doom wears a green cloak and metal mask"},
            "story_entities": [{"id": "doom", "name": "Doctor Doom", "aliases": ["ด็อกเตอร์ดูม"],
                                "visual_identity": "green cloak and metal mask"}],
            "scene_entities": [["doom"] for _ in range(6)],
        })
        return self.manager.mark_failed(job["id"], "chatgpt", "STORY_IMAGE_REFUSED: scene 1")

    def action(self, action="story_save_scene_prompt", job=None, **changes):
        job = job or self.job
        payload = {"job_id": job["id"], "revision": job["revision"],
                   "scene_index": 1, "prompt": self.revised_prompt, **changes}
        return MainWindow._desktop_execute_action(self.window, action, payload)

    def snapshot(self, job=None):
        folder = self.manager._folder((job or self.job)["id"])
        return {str(path.relative_to(folder)): path.read_bytes()
                for path in folder.rglob("*") if path.is_file()}

    def assert_no_work_started(self):
        for name in ("_retry_story_job", "_run_story_pipeline", "_render_story",
                     "_schedule_story_recovery", "_close_automation_browser", "_refresh"):
            getattr(self.window, name).assert_not_called()
        self.assertEqual(self.window.bridge.mock_calls, [])
        self.assertEqual(self.window.root.mock_calls, [])
        self.assertEqual(self.window.events.mock_calls, [])

    def test_review_is_read_only_and_exposes_valid_stopped_plan(self):
        before = self.snapshot()
        result = self.action("story_review")
        self.assertTrue(result["ok"])
        review = result["review"]
        self.assertEqual(review["content_review"]["status"], "ready")
        self.assertEqual(review["revision"], self.job["revision"])
        self.assertFalse(review["active"])
        self.assertTrue(all(scene["prompt_editable"] for scene in review["scenes"]))
        self.assertFalse(any(scene["prompt_revised"] for scene in review["scenes"]))
        self.assertEqual(self.snapshot(), before)
        self.window._write_console.assert_not_called()
        self.assert_no_work_started()

    def test_save_only_preserves_narration_failure_and_original_analysis(self):
        before_files = self.snapshot()
        before_job = copy.deepcopy(self.job)
        result = self.action()
        saved = self.manager.get(self.job["id"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["review"]["revision"], before_job["revision"] + 1)
        self.assertEqual(result["review"]["last_error"], before_job["last_error"])
        self.assertTrue(result["review"]["scenes"][0]["prompt_revised"])
        self.assertEqual(result["review"]["scenes"][0]["prompt"], self.revised_prompt)
        self.assertEqual(saved["scene_prompts"][1:], before_job["scene_prompts"][1:])
        for field in ("narration_script", "scene_narrations", "pronunciation_notes", "scene_durations",
                      "story_entities", "scene_entities", "visual_bible", "visual_style",
                      "status", "last_error", "pipeline_stage", "analysis_status", "ai_status"):
            self.assertEqual(saved.get(field), before_job.get(field), field)
        self.assertEqual(saved["scene_prompt_overrides"], {"1": self.revised_prompt})
        self.assertEqual(saved["scene_prompt_edit_history"][-1]["old_prompt"], before_job["scene_prompts"][0])
        after_files = self.snapshot()
        self.assertEqual({key: value for key, value in after_files.items() if key != "job.json"},
                         {key: value for key, value in before_files.items() if key != "job.json"})
        self.window._write_console.assert_called_once()
        self.assert_no_work_started()

    def test_runtime_active_guard_wins_over_stopped_manifest(self):
        self.window._story_pipeline_job_id = self.job["id"]
        before = self.snapshot()
        review = self.action("story_review")["review"]
        self.assertTrue(review["active"])
        self.assertTrue(all(not scene["prompt_editable"] for scene in review["scenes"]))
        with self.assertRaisesRegex(ValueError, "กำลังทำ"):
            self.action()
        self.assertEqual(self.snapshot(), before)
        self.window._write_console.assert_not_called()
        self.assert_no_work_started()

    def test_other_active_job_does_not_change_the_selected_stopped_job(self):
        self.window._story_pipeline_job_id = "STORY-OTHER"
        self.assertTrue(self.action()["ok"])
        self.assertEqual(self.window._story_pipeline_job_id, "STORY-OTHER")
        self.assert_no_work_started()

    def test_fresh_manifest_guards_terminal_and_recovering_states(self):
        for fields in ({"status": "running"}, {"status": "recovering"}, {"status": "cancelled"},
                       {"status": "deleted"}, {"cancel_requested": True}, {"active": True}):
            with self.subTest(fields=fields):
                job = self.new_job()
                job.update(fields)
                self.manager._save(job)
                before = self.snapshot(job)
                with self.assertRaises(ValueError):
                    self.action(job=job)
                self.assertEqual(self.snapshot(job), before)
        self.window._write_console.assert_not_called()
        self.assert_no_work_started()

    def test_stale_modal_revision_cannot_overwrite_saved_scene(self):
        self.action()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "งานเปลี่ยน"):
            self.action(prompt="Doctor Doom returns to the original confrontation")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.manager.get(self.job["id"])["scene_prompts"][0], self.revised_prompt)
        self.window._write_console.assert_called_once()
        self.assert_no_work_started()

    def test_job_transition_after_adapter_read_is_rechecked_before_save(self):
        real_get = self.manager.get
        transition_snapshot = None

        def read_then_start(job_id):
            nonlocal transition_snapshot
            previously_stopped = real_get(job_id)
            self.manager._save(dict(previously_stopped, status="running"))
            transition_snapshot = self.snapshot()
            return previously_stopped

        with patch.object(self.manager, "get", side_effect=read_then_start):
            with self.assertRaises(ValueError):
                self.action()
        self.assertEqual(self.snapshot(), transition_snapshot)
        saved = real_get(self.job["id"])
        self.assertEqual(saved["status"], "running")
        self.assertEqual(saved["scene_prompts"], self.job["scene_prompts"])
        self.assertNotIn("scene_prompt_overrides", saved)
        self.window._write_console.assert_not_called()
        self.assert_no_work_started()

    def test_validation_errors_do_not_log_success_or_change_files(self):
        before = self.snapshot()
        for changes in ({"scene_index": "1"}, {"scene_index": True}, {"scene_index": 7},
                        {"revision": None}, {"prompt": ""}, {"prompt": "x" * 12001},
                        {"prompt": "A completely unrelated stranger waits by the portal"}):
            with self.subTest(changes=str(changes)[:80]), self.assertRaises(ValueError):
                self.action(**changes)
            self.assertEqual(self.snapshot(), before)
        self.window._write_console.assert_not_called()
        self.assert_no_work_started()

    def test_target_image_and_clip_checkpoints_are_protected_even_when_file_is_missing(self):
        cases = [
            ({"partial_generated_images": ["generated/scene_01.png"]}, None),
            ({"flow_clips": {"1": "videos/flow_scene_01.mp4"}}, None),
            ({"flow_fallback_clips": {"1": "videos/local_motion_scene_01.mp4"}}, None),
            ({}, "generated/scene_01.png"),
            ({}, "videos/flow_scene_01.mp4"),
            ({}, "videos/.working/local_motion_scene_01.mp4.partial"),
        ]
        for fields, relative in cases:
            with self.subTest(fields=fields, relative=relative):
                job = self.new_job()
                job.update(fields)
                self.manager._save(job)
                if relative:
                    path = self.manager._folder(job["id"]) / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"existing target media")
                before = self.snapshot(job)
                with self.assertRaises(ValueError):
                    self.action(job=job)
                self.assertEqual(self.snapshot(job), before)
        self.window._write_console.assert_not_called()
        self.assert_no_work_started()

    def test_paid_voice_and_final_are_protected_without_touching_narration(self):
        cases = [({"voice_job_id": "paid-queue-id"}, None),
                 ({"voice_path": "audio/voice.mp3"}, None),
                 ({"dialogue_voice_checkpoints": {"1": {"status": "queued"}}}, None),
                 ({"video_path": "videos/final.mp4"}, None),
                 ({}, "audio/orphaned_voice.wav"), ({}, "videos/story_short_complete.mp4")]
        for fields, relative in cases:
            with self.subTest(fields=fields, relative=relative):
                job = self.new_job()
                job.update(fields)
                self.manager._save(job)
                if relative:
                    path = self.manager._folder(job["id"]) / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"existing paid media")
                before = self.snapshot(job)
                with self.assertRaises(ValueError):
                    self.action(job=job)
                self.assertEqual(self.snapshot(job), before)
                self.assertEqual(self.manager.get(job["id"])["narration_script"], job["narration_script"])
        self.window._write_console.assert_not_called()
        self.assert_no_work_started()

    def test_other_scene_media_does_not_lock_a_missing_scene(self):
        folder = self.manager._folder(self.job["id"])
        image = folder / "generated/scene_02.png"
        image.write_bytes(b"scene two remains intact")
        self.job["partial_generated_images"] = ["generated/scene_02.png"]
        self.manager._save(self.job)
        review = self.action("story_review")["review"]
        self.assertTrue(review["scenes"][0]["prompt_editable"])
        self.assertFalse(review["scenes"][1]["prompt_editable"])
        self.assertTrue(self.action()["ok"])
        self.assertEqual(image.read_bytes(), b"scene two remains intact")
        self.assert_no_work_started()

    def test_stale_prompt_callback_is_manual_terminal_without_scheduling_recovery(self):
        self.action()
        saved = self.manager.get(self.job["id"])
        before = self.snapshot()
        self.assertEqual(story_recovery_action(saved, "temporary connection lost"), "resume_chatgpt")
        for message in ("STORY_SCENE_PROMPT_STALE: scene 1 was revised",
                        "story_scene_prompt_stale: late callback", "STORY_IMAGE_REFUSED: review image"):
            with self.subTest(message=message):
                self.assertEqual(story_recovery_action(saved, message), "")
                self.assertFalse(MainWindow._schedule_story_recovery(self.window, saved["id"], message))
        self.assertEqual(self.snapshot(), before)
        self.assert_no_work_started()


if __name__ == "__main__":
    unittest.main()
