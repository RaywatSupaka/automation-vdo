import threading
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from core.story_progress_stall import image_prompt_ready_stalled
from core.story_pipeline import story_recovery_action
from ui.main_window import MainWindow


JOB = "STORY-20261006-E3C5C5"
RUN = "RUN-BC7146167BAD"


class ImagePromptReadyStallTests(unittest.TestCase):
    def test_ambiguous_stall_review_never_schedules_generic_resume(self):
        job={"scene_count":6,"partial_generated_images":["scene_01.png"]}
        self.assertEqual(story_recovery_action(job,"STORY_IMAGE_STALL_REVIEW • draft_changed"),"")
        self.assertEqual(story_recovery_action(job,"STORY_IMAGE_AUDIT_TIMEOUT_PRE_SEND • no click"),
                         "resume_chatgpt")

    def test_exact_acked_run_stalls_only_after_limit(self):
        now = datetime(2026, 10, 6, 16, 7)
        client = {"ai_job_id": JOB, "ai_run_id": RUN, "ai_step": "image_prompt_ready",
                  "ai_updated_at": (now - timedelta(seconds=179)).isoformat(),
                  "ai_observation": {"acknowledged": True}}
        self.assertFalse(image_prompt_ready_stalled(client, JOB, RUN, now=now))
        client["ai_updated_at"] = (now - timedelta(seconds=180)).isoformat()
        self.assertTrue(image_prompt_ready_stalled(client, JOB, RUN, now=now))
        for changed in ({"ai_run_id": "RUN-OTHER"}, {"ai_job_id": "STORY-OTHER"},
                        {"ai_step": "ai_send_accepted"}, {"ai_step": "ai_send_dispatched"},
                        {"ai_observation": {"acknowledged": False}}, {"ai_updated_at": ""}):
            with self.subTest(changed=changed):
                self.assertFalse(image_prompt_ready_stalled({**client, **changed}, JOB, RUN, now=now))

    def test_monitor_requests_one_guarded_recovery_then_reports_timeout_once(self):
        stale = {"version": "0.15.517", "ai_job_id": JOB, "ai_run_id": RUN,
                 "ai_provider": "chatgpt", "ai_step": "image_prompt_ready",
                 "ai_updated_at": (datetime.now() - timedelta(minutes=5)).isoformat(),
                 "ai_observation": {"acknowledged": True}}
        emitted = []
        commands = []
        bridge = SimpleNamespace(REQUIRED_EXTENSION_VERSION="0.15.517",
                                 _extension_runs={("ai", JOB, 0): {"run_id": RUN}},
                                 extension_status=lambda: {"clients": [stale]},
                                 queue_extension_command=lambda *args, **kwargs: commands.append((args, kwargs)))
        app = SimpleNamespace(_story_pipeline_job_id=JOB, _story_cancel_event=threading.Event(),
                              stories=SimpleNamespace(get=lambda job_id: {
                                  "image_ai_provider": "chatgpt", "scene_count": 6}),
                              bridge=bridge, events=SimpleNamespace(put=emitted.append),
                              root=SimpleNamespace(after=lambda delay, callback: None),
                              _story_progress_value=SimpleNamespace(get=lambda: 48),
                              _update_story_progress=lambda payload: None)
        MainWindow._monitor_story_browser_progress(app, JOB)
        MainWindow._monitor_story_browser_progress(app, JOB)
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][0], ("recover_stalled_story_image", JOB))
        self.assertEqual(commands[0][1]["run_id"], RUN)
        self.assertFalse(emitted)
        app._story_image_stall_since -= 91
        MainWindow._monitor_story_browser_progress(app, JOB)
        MainWindow._monitor_story_browser_progress(app, JOB)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0][0], "story_error")
        self.assertIn("STORY_IMAGE_PROGRESS_STALLED", emitted[0][1]["value"])
        self.assertFalse(MainWindow._schedule_story_recovery(app, JOB, emitted[0][1]["value"]))


if __name__ == "__main__":
    unittest.main()
