import json
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from core.creation_queue import CreationQueue
from ui.creation_queue import CreationQueueMixin


class RecoveryHarness(CreationQueueMixin):
    pass


class CreationQueueRecoveryControlsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.queue = CreationQueue(self.root)
        self.app = RecoveryHarness()
        self.app.story_queue = self.queue
        self.app._creation_dispatch_item = None
        self.app._product_pipeline_job_id = ""
        self.app._story_pipeline_job_id = ""
        self.app._product_cancel_event = None
        self.app._story_cancel_event = None
        self.app._creation_product_worker = None
        self.app._creation_story_worker = None
        self.app.root = Mock()
        self.app._schedule_next_story_queue_item = Mock()
        self.app._write_console = Mock()
        self.app._desktop_set_notice = Mock()
        self.app._cancel_product_pipeline = Mock()
        self.app._cancel_story_pipeline = Mock()
        self.app.bridge = Mock()
        self.app.bridge.REQUIRED_EXTENSION_VERSION = "0.15.245"
        self.app.bridge.extension_status.return_value = {"connected": False, "clients": []}
        self.app.products = SimpleNamespace(root=self.root / "products", get_job=self.read_product, set_automation_state=Mock())
        self.app.stories = SimpleNamespace(root=self.root / "stories", get=self.read_story, mark_cancelled=Mock())
        self.app._creation_capture_settings = Mock(return_value={
            "provider": "chatgpt", "ai_web_model": "auto", "voice_reference_id": "current-voice",
            "subtitle_enabled": True, "render": {"width": 1080},
        })

    def read_product(self, job_id):
        return json.loads((self.app.products.root / job_id / "job.json").read_text(encoding="utf-8"))

    def read_story(self, job_id):
        return json.loads((self.app.stories.root / job_id / "job.json").read_text(encoding="utf-8"))

    def job(self, job_id="JOB-OLD", **values):
        manager = self.app.products if job_id.startswith("JOB-") else self.app.stories
        folder = manager.root / job_id
        folder.mkdir(parents=True)
        job = {"id": job_id, "status": "failed", "automation_status": "error",
               "image_ai_provider": "gemini", "ai_web_model": "pro", "voice_reference_id": "old-voice",
               "voice_job_id": "PAID-VOICE-KEEP", "flow_clips": {"1": "videos/flow01.mp4"},
               "flow_attachment_fallbacks": {"2": {"run_id": "RUN-KEEP"}},
               "video_status": "pending", "updated_at": "2026-09-05", **values}
        (folder / "job.json").write_text(json.dumps(job), encoding="utf-8")
        (folder / "keep.mp4").write_bytes(b"existing-user-video")
        return folder

    def row(self, mode="product", job_id="JOB-OLD", status="failed"):
        values = ["https://s.shopee.co.th/old"] if mode == "product" else ["เรื่องเดิม"]
        item = self.queue.enqueue(mode, values, settings={"voice_reference_id": "frozen"})["items"][0]
        self.queue._update(item["queue_id"], status=status, job_id=job_id, attempt=3, error="old error")
        return self.queue.get_item(item["queue_id"])

    def action(self, name, **payload):
        return self.app._creation_queue_action(name, payload)

    def test_resume_failed_and_orphan_running_retains_job_order_options(self):
        first = self.row()
        second = self.row("story", "STORY-KEEP", "running")
        result = self.action("creation_resume_unfinished")
        self.assertFalse(result["creation_queue"]["paused"])
        self.assertEqual([r["job_id"] for r in self.queue.snapshot()["items"]], ["JOB-OLD", "STORY-KEEP"])
        self.assertEqual(self.queue.claim_next()["queue_id"], first["queue_id"])
        self.assertEqual(self.queue.get_item(second["queue_id"])["settings"]["voice_reference_id"], "frozen")
        self.assertEqual(self.queue.get_item(first["queue_id"])["attempt"], 4)
        self.app._schedule_next_story_queue_item.assert_called_once_with(200)

    def test_recoverable_long_video_keeps_mode_label_and_does_not_mutate_job(self):
        folder = self.job('STORY-LONG', long_video=True, scene_count=23, meta_clip_count=12)
        self.app.bridge.pending_job_commands.return_value = []
        before = (folder / 'job.json').read_bytes()
        rows = self.app._creation_recoverable_jobs([])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['long_video'])
        self.assertEqual(rows[0]['job_id'], 'STORY-LONG')
        self.assertEqual((folder / 'job.json').read_bytes(), before)

    def test_stopped_row_publishes_stop_time_without_frozen_options(self):
        row = self.row('story', 'STORY-STOPPED', 'cancelled')
        self.queue._update(row['queue_id'], finished_at='2026-09-20T01:51:02')
        state = self.app._creation_queue_state()
        exported = next(item for item in state['items'] if item['queue_id'] == row['queue_id'])
        self.assertEqual(exported['finished_at'], '2026-09-20T01:51:02')
        # The editor now receives an explicit public allowlist, not execution
        # settings. This row contains only a private frozen voice reference.
        self.assertEqual(exported['settings'], {})
        self.assertNotIn('voice_reference_id', json.dumps(exported))
        self.assertNotIn('frozen', json.dumps(exported))
        self.assertEqual(exported['status'], 'cancelled')

    def test_retry_is_one_click_resume_even_when_queue_was_paused(self):
        row = self.row(status="cancelled")
        self.action("creation_retry", queue_id=row["queue_id"])
        claimed = self.queue.claim_next()
        self.assertEqual(claimed["job_id"], "JOB-OLD")
        self.assertEqual(claimed["attempt"], 4)

    def test_bulk_resume_does_not_revive_intentionally_cancelled(self):
        row = self.row(status="cancelled")
        self.action("creation_resume_unfinished")
        self.assertEqual(self.queue.get_item(row["queue_id"])["status"], "cancelled")
        self.assertIsNone(self.queue.claim_next())

    def test_core_resume_cannot_assume_running_is_orphan(self):
        self.row(status="running")
        with self.assertRaises(ValueError):
            self.queue.resume_unfinished()

    def test_resume_does_not_skip_failed_drama_dependency(self):
        self.row()
        self.queue.pause("drama_failure:SERIES-OLD:1")
        with self.assertRaises(ValueError):
            self.action("creation_resume_unfinished")
        self.assertTrue(self.queue.snapshot()["paused"])

    def test_cancel_all_preserves_jobs_media_and_completed_history(self):
        folder = self.job()
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        cancelled = self.row()
        complete = self.row("story", "STORY-COMPLETE", "completed")
        self.action("creation_cancel_all")
        self.assertEqual(self.queue.get_item(cancelled["queue_id"])["status"], "cancelled")
        self.assertEqual(self.queue.get_item(complete["queue_id"])["status"], "completed")
        self.assertTrue(self.queue.snapshot()["paused"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
        self.app._cancel_product_pipeline.assert_not_called()

    def test_cancel_all_retains_live_row_until_terminal_and_rejects_late_success(self):
        row = self.row(status="running")
        self.app._product_pipeline_job_id = row["job_id"]
        self.app._creation_product_worker = Mock(is_alive=Mock(return_value=True))
        self.action("creation_cancel_all")
        pending = self.queue.get_item(row["queue_id"])
        self.assertEqual(pending["status"], "running")
        self.assertTrue(pending["cancel_requested"])
        self.app._cancel_product_pipeline.assert_called_once()
        self.assertIsNone(self.queue.claim_next())
        self.app._creation_product_terminal(row["job_id"], "completed", output="late-final.mp4")
        self.assertEqual(self.queue.get_item(row["queue_id"])["status"], "cancelled")

    def test_cancel_during_import_preserves_late_job_binding(self):
        row = self.row(job_id="", status="running")
        self.app._creation_dispatch_item = row
        self.app._product_pipeline_job_id = "กำลังสร้าง Job"
        self.action("creation_cancel_all")
        attached = self.queue.bind_job(row["queue_id"], 3, "JOB-JUST-IMPORTED")
        self.assertEqual(attached["job_id"], "JOB-JUST-IMPORTED")
        self.assertTrue(attached["cancel_requested"])

    def test_cancel_intent_survives_restart_and_cannot_be_claimed_until_explicit_retry(self):
        row = self.row(status="running")
        self.queue.cancel_all(active_queue_id=row["queue_id"])
        restored = CreationQueue(self.root)
        restored.recover_on_startup()
        restored.resume()
        self.assertIsNone(restored.claim_next())
        self.assertEqual(restored.get_item(row["queue_id"])["status"], "cancelled")
        restored.retry(row["queue_id"])
        self.assertEqual(restored.claim_next()["job_id"], "JOB-OLD")

    def test_claim_also_rejects_queued_cancellation_intent_without_startup_repair(self):
        row = self.row(status="queued")
        self.queue._update(row["queue_id"], cancel_requested=True)
        self.queue.resume()
        self.assertIsNone(self.queue.claim_next())

    def test_cancel_all_stops_only_remote_jobs_bound_to_cancelled_rows(self):
        self.row(status="running")
        self.app.bridge.extension_status.return_value = {"connected": True, "clients": [
            {"flow_job_id": "JOB-OLD", "flow_step": "generation_in_progress", "flow_shot_index": 2,
             "flow_run_id": "RUN-OLD", "flow_tab_id": 8, "flow_updated_at": datetime.now().isoformat(),
             "version": "0.15.245", "ai_job_id": "STORY-MANUAL", "ai_step": "generating_images"}]}
        self.action("creation_cancel_all")
        calls = self.app.bridge.queue_extension_command.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args, ("stop_flow_generation", "JOB-OLD", 2))
        self.assertEqual(calls[0].kwargs, {"run_id": "RUN-OLD"})
        self.assertEqual(calls[1].args, ("close_automation_browser", "JOB-OLD"))
        self.app.products.set_automation_state.assert_called_once_with("JOB-OLD", "cancelled", "cancelled")
        self.app.stories.mark_cancelled.assert_not_called()

    def test_cancel_remote_rejects_old_version_missing_owner_and_stale_progress(self):
        for fields in ({"version": "0.15.244"}, {"flow_tab_id": 0}, {"flow_run_id": ""},
                       {"flow_updated_at": "2020-01-01T00:00:00"}):
            client = {"flow_job_id": "JOB-OLD", "flow_step": "generation_in_progress", "flow_shot_index": 2,
                      "flow_run_id": "RUN-OLD", "flow_tab_id": 8, "flow_updated_at": datetime.now().isoformat(),
                      "version": "0.15.245", **fields}
            self.app.bridge.extension_status.return_value = {"connected": True, "clients": [client]}
            self.app._creation_cancel_remote_queue_jobs([{"job_id": "JOB-OLD", "status": "running"}])
        self.app.bridge.queue_extension_command.assert_not_called()

    def test_cancel_remote_story_supports_long_video_scenes_without_touching_media(self):
        folder = self.job('STORY-LONG', scene_count=50)
        before = {p.name: p.read_bytes() for p in folder.iterdir()}
        for shot in (1, 15, 16, 50):
            with self.subTest(shot=shot):
                self.app.bridge.queue_extension_command.reset_mock()
                self.app.stories.mark_cancelled.reset_mock()
                self.app.bridge.extension_status.return_value = {'connected': True, 'clients': [{
                    'version': '0.15.245', 'flow_job_id': 'STORY-LONG',
                    'flow_run_id': 'RUN-LONG', 'flow_tab_id': 8,
                    'flow_shot_index': shot, 'flow_step': 'generation_in_progress',
                    'flow_updated_at': datetime.now().isoformat(timespec='seconds'),
                }]}
                self.app._creation_cancel_remote_queue_jobs([{'job_id': 'STORY-LONG', 'status': 'running'}])
                calls = self.app.bridge.queue_extension_command.call_args_list
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0].args, ('stop_flow_generation', 'STORY-LONG', shot))
                self.assertEqual(calls[0].kwargs, {'run_id': 'RUN-LONG'})
                self.assertEqual(calls[1].args, ('close_automation_browser', 'STORY-LONG'))
                self.app.stories.mark_cancelled.assert_called_once_with('STORY-LONG', 'user_cancel')
        self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
        self.app.products.set_automation_state.assert_not_called()

    def test_cancel_remote_long_scene_keeps_owner_and_supported_range_guards(self):
        base = {'version': '0.15.245', 'flow_job_id': 'STORY-LONG',
                'flow_run_id': 'RUN-LONG', 'flow_tab_id': 8, 'flow_shot_index': 16,
                'flow_step': 'generation_in_progress', 'flow_updated_at': datetime.now().isoformat(timespec='seconds')}
        for fields in ({'flow_shot_index': 0}, {'flow_shot_index': 51},
                       {'flow_shot_index': 'invalid'}, {'flow_shot_index': None},
                       {'version': '0.15.244'}, {'flow_tab_id': 0}, {'flow_run_id': ''},
                       {'flow_updated_at': '2020-01-01T00:00:00'},
                       {'flow_step': 'generation_complete'}, {'flow_job_id': 'STORY-UNRELATED'},
                       {'flow_job_id': 'JOB-OLD'}):
            with self.subTest(fields=fields):
                self.app.bridge.extension_status.return_value = {'connected': True, 'clients': [{**base, **fields}]}
                self.app._creation_cancel_remote_queue_jobs([
                    {'job_id': 'STORY-LONG', 'status': 'running'}, {'job_id': 'JOB-OLD', 'status': 'running'}])
        self.app.bridge.queue_extension_command.assert_not_called()
        self.app.stories.mark_cancelled.assert_not_called()
        self.app.products.set_automation_state.assert_not_called()

    def test_cancel_all_does_not_cancel_unrelated_manual_pipeline(self):
        self.row(status="queued")
        self.app._product_pipeline_job_id = "JOB-MANUAL"
        self.action("creation_cancel_all")
        self.app._cancel_product_pipeline.assert_not_called()
        self.assertEqual(self.app._product_pipeline_job_id, "JOB-MANUAL")

    def test_clear_refuses_active_and_cancelling_worker_without_mutation(self):
        self.row(status="running")
        before = self.queue.path.read_bytes()
        self.app._creation_product_worker = Mock(is_alive=Mock(return_value=True))
        for action in ("creation_clear_stuck_state", "creation_resume_unfinished"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.action(action)
        self.assertEqual(before, self.queue.path.read_bytes())

    def test_scene_worker_still_running_blocks_retry_resume_and_clear_after_ui_cancel(self):
        row = self.row('story', 'STORY-OLD', 'cancelled')
        self.app._story_scene_threads = {('STORY-OLD', 8): Mock(is_alive=Mock(return_value=True))}
        before = self.queue.path.read_bytes()
        self.assertTrue(self.app._creation_workers_alive())
        self.assertTrue(self.app._creation_idle_reason())
        for action in ('creation_retry', 'creation_resume_unfinished', 'creation_clear_stuck_state'):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.action(action, queue_id=row['queue_id'])
            self.assertEqual(before, self.queue.path.read_bytes())
        self.app._schedule_next_story_queue_item.assert_not_called()
        self.app.bridge.queue_extension_command.assert_not_called()

    def test_finished_scene_workers_do_not_block_explicit_retry(self):
        row = self.row('story', 'STORY-OLD', 'cancelled')
        self.app._story_scene_threads = {
            ('STORY-OLD', 7): Mock(is_alive=Mock(return_value=False)),
            ('STORY-OLD', 8): Mock(is_alive=Mock(return_value=False)),
        }
        self.assertFalse(self.app._creation_workers_alive())
        self.assertEqual(self.app._creation_idle_reason(), '')
        self.action('creation_retry', queue_id=row['queue_id'])
        self.assertEqual(self.queue.get_item(row['queue_id'])['status'], 'queued')
        self.app._schedule_next_story_queue_item.assert_called_once_with(200)

    def test_clear_refuses_active_remote_evidence_even_without_local_thread(self):
        self.row(status="running")
        self.app.bridge.extension_status.return_value = {"connected": True, "clients": [
            {"flow_job_id": "JOB-OLD", "flow_step": "generation_in_progress"}]}
        with self.assertRaises(ValueError):
            self.action("creation_clear_stuck_state")

    def test_clear_refuses_untracked_active_story_or_manual_flow(self):
        self.job("STORY-LIVE", status="running")
        self.app._story_pipeline_job_id = "STORY-LIVE"
        with self.assertRaises(ValueError):
            self.action("creation_clear_stuck_state")
        self.app._story_pipeline_job_id = ""
        self.app._manual_multi_flow_job_id = "JOB-MANUAL"
        with self.assertRaises(ValueError):
            self.action("creation_clear_stuck_state")

    def test_clear_only_stale_references_keeps_files_receipts_and_pause(self):
        folder = self.job()
        before = (folder / "job.json").read_bytes()
        row = self.row(status="running")
        self.app._product_pipeline_job_id = row["job_id"]
        self.app._creation_tick_after = "timer-old"
        self.app._product_cancel_event = threading.Event()
        old_receipts = {"RUN-KEEP": {"submitted": True}}
        self.app.bridge._extension_runs = old_receipts
        result = self.action("creation_clear_stuck_state")
        self.assertEqual(self.app._product_pipeline_job_id, "")
        self.assertIsNone(self.app._product_cancel_event)
        self.assertEqual(self.queue.get_item(row["queue_id"])["job_id"], "JOB-OLD")
        self.assertEqual(self.queue.get_item(row["queue_id"])["status"], "queued")
        self.assertTrue(result["creation_queue"]["paused"])
        self.assertEqual(before, (folder / "job.json").read_bytes())
        self.assertIs(self.app.bridge._extension_runs, old_receipts)
        self.app.bridge.clear_flow_progress.assert_not_called()
        self.app.bridge.clear_ai_progress.assert_not_called()
        self.app._schedule_next_story_queue_item.assert_not_called()

    def test_existing_job_inventory_is_read_only_and_excludes_unsafe_jobs(self):
        folder = self.job()
        self.job("JOB-DONE", automation_status="completed")
        self.job("JOB-CANCEL", automation_status="cancelled")
        self.job("STORY-DRAMA", job_type="drama_episode")
        before = (folder / "job.json").read_bytes()
        state = self.app._creation_queue_state()
        self.assertEqual([r["job_id"] for r in state["recoverable_jobs"]], ["JOB-OLD"])
        self.assertEqual(before, (folder / "job.json").read_bytes())
        self.assertNotIn("PAID-VOICE", json.dumps(state))

    def test_selected_existing_job_binds_once_preserves_provider_voice_and_media(self):
        folder = self.job(subtitle_requested=False, visual_style="anime")
        before = (folder / "job.json").read_bytes()
        self.action("creation_resume_jobs", job_ids=["JOB-OLD"])
        row = self.queue.claim_next()
        self.assertEqual(row["job_id"], "JOB-OLD")
        self.assertEqual(row["provider"], "gemini")
        self.assertEqual(row["ai_web_model"], "pro")
        self.assertEqual(row["settings"]["voice_reference_id"], "old-voice")
        self.assertFalse(row["settings"]["subtitle_enabled"])
        self.assertEqual(before, (folder / "job.json").read_bytes())
        self.assertEqual((folder / "keep.mp4").read_bytes(), b"existing-user-video")
        with self.assertRaises(ValueError):
            self.action("creation_resume_jobs", job_ids=["JOB-OLD"])
        self.assertEqual(self.queue.snapshot()["total_count"], 1)

    def test_existing_selection_validation_is_atomic_and_rejects_paths(self):
        self.job()
        for job_ids in (["JOB-OLD", "STORY-MISSING"], ["JOB-../escape"]):
            with self.subTest(job_ids=job_ids), self.assertRaises((ValueError, FileNotFoundError)):
                self.action("creation_resume_jobs", job_ids=job_ids)
        self.assertEqual(self.queue.snapshot()["total_count"], 0)

    def test_counts_describe_recoverable_queue_and_clear_guard(self):
        self.row()
        self.row("story", "STORY-CANCEL", "cancelled")
        state = self.app._creation_queue_state()
        self.assertEqual(state["unfinished_count"], 1)
        self.assertEqual(state["cancelable_count"], 1)
        self.assertTrue(state["can_clear_stuck_state"])


if __name__ == "__main__":
    unittest.main()
