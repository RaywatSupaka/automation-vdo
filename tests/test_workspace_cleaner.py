import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.workspace_cleaner import FinalVideoValidator, WorkspaceCleaner, working_video_folder


class WorkspaceCleanerTests(unittest.TestCase):
    class Validator:
        def __init__(self, error=""):
            self.error = error

        def validate(self, path, manifest=None):
            if self.error:
                raise ValueError(self.error)
            return {
                "valid": True, "has_video": True, "has_audio": True,
                "duration": 30.0, "width": 1080, "height": 1920,
                "video_codec": "h264", "audio_codec": "aac", "validated_at": "test",
            }

    @staticmethod
    def _recycler(path):
        Path(path).unlink()

    @staticmethod
    def _ready_job(root, section="products", job_id="JOB-CLEAN"):
        folder = Path(root) / "workspace" / section / job_id
        videos = folder / "videos"
        videos.mkdir(parents=True)
        final = videos / "final.mp4"
        first = videos / "flow_01.mp4"
        second = videos / "with_subtitles.mp4"
        final.write_bytes(b"final-video")
        first.write_bytes(b"flow-video")
        second.write_bytes(b"subtitle-video")
        manifest = {
            "id": job_id,
            "status": "ready_for_phone",
            "video_status": "ready",
            "video_path": "videos/final.mp4",
            "flow_video_status": "ready",
            "flow_video_path": "videos/flow_01.mp4",
            "flow_clips": {"1": "videos/flow_01.mp4"},
            "flow_clip_count": 1,
            "subtitle_video_status": "ready",
            "subtitle_video_path": "videos/with_subtitles.mp4",
        }
        (folder / "job.json").write_text(json.dumps(manifest), encoding="utf-8")
        return folder, final, first, second

    def test_scan_keeps_final_and_finds_only_regenerable_files(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, final, first, second = self._ready_job(temp)
            cache = Path(temp) / "workspace" / "preview"
            cache.mkdir()
            preview = cache / "preview.png"
            preview.write_bytes(b"preview")
            imports = Path(temp) / "workspace" / "imports"
            imports.mkdir()
            source = imports / "customer.png"
            source.write_bytes(b"source")

            summary = WorkspaceCleaner(temp, self._recycler, validator=self.Validator()).scan()

            self.assertEqual(summary["file_count"], 3)
            self.assertEqual(summary["job_count"], 1)
            self.assertEqual(summary["protected_final_count"], 1)
            self.assertTrue(final.exists())
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertTrue(preview.exists())
            self.assertTrue(source.exists())
            self.assertTrue((folder / "job.json").exists())

    def test_clean_recycles_intermediates_and_updates_manifest_but_preserves_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, final, first, second = self._ready_job(temp)
            generated = folder / "generated"
            generated.mkdir()
            image = generated / "selling.png"
            image.write_bytes(b"source-image")
            cleaner = WorkspaceCleaner(temp, self._recycler, validator=self.Validator())
            summary = cleaner.scan()

            result = cleaner.clean(summary["scan_id"])

            self.assertEqual(result["deleted_count"], 2)
            self.assertEqual(result["failed_count"], 0)
            self.assertTrue(final.exists())
            self.assertTrue(image.exists())
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            saved = json.loads((folder / "job.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["video_status"], "ready")
            self.assertEqual(saved["video_path"], "videos\\final.mp4" if os.name == "nt" else "videos/final.mp4")
            self.assertEqual(saved["flow_clips"], {})
            self.assertEqual(saved["flow_video_path"], saved["video_path"])
            self.assertEqual(saved["subtitle_video_path"], saved["video_path"])
            self.assertEqual(saved["cleanup_status"], "final_only")
            self.assertEqual(saved["final_validation_status"], "passed")

    def test_active_and_incomplete_jobs_are_never_cleanup_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            _, _, active_intermediate, _ = self._ready_job(temp, job_id="JOB-ACTIVE")
            failed, _, failed_intermediate, _ = self._ready_job(temp, job_id="JOB-FAILED")
            manifest_path = failed / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"status": "error", "video_status": "error"})
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            summary = WorkspaceCleaner(temp, self._recycler, validator=self.Validator()).scan({"JOB-ACTIVE"})

            self.assertEqual(summary["file_count"], 0)
            self.assertEqual(summary["skipped_active_jobs"], 1)
            self.assertTrue(active_intermediate.exists())
            self.assertTrue(failed_intermediate.exists())

    def test_imports_are_protected_and_old_logs_or_stale_partial_files_are_found(self):
        with tempfile.TemporaryDirectory() as temp:
            imports = Path(temp) / "workspace" / "imports"
            imports.mkdir(parents=True)
            source = imports / "upload.part"
            source.write_bytes(b"customer-upload")
            stale = Path(temp) / "workspace" / "orphan.part"
            stale.write_bytes(b"stale")
            logs = Path(temp) / "logs"
            logs.mkdir()
            old_log = logs / "old.log"
            old_log.write_bytes(b"old-log")
            old_time = time.time() - 9 * 24 * 60 * 60
            os.utime(stale, (old_time, old_time))
            os.utime(old_log, (old_time, old_time))

            summary = WorkspaceCleaner(temp, self._recycler, validator=self.Validator()).scan()

            self.assertEqual(summary["file_count"], 2)
            self.assertTrue(source.exists())

    def test_changed_scan_requires_a_fresh_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            preview = Path(temp) / "workspace" / "preview"
            preview.mkdir(parents=True)
            (preview / "one.png").write_bytes(b"one")
            cleaner = WorkspaceCleaner(temp, self._recycler, validator=self.Validator())
            summary = cleaner.scan()
            (preview / "two.png").write_bytes(b"two")

            with self.assertRaisesRegex(ValueError, "สแกนใหม่"):
                cleaner.clean(summary["scan_id"])

    def test_invalid_final_protects_all_intermediate_video_files(self):
        with tempfile.TemporaryDirectory() as temp:
            _, final, first, second = self._ready_job(temp)
            summary = WorkspaceCleaner(
                temp, self._recycler, validator=self.Validator("ไม่มีเสียง")
            ).scan()
            self.assertEqual(summary["file_count"], 0)
            self.assertEqual(summary["invalid_final_jobs"], 1)
            self.assertTrue(final.exists())
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

    def test_story_requires_canonical_complete_final(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, final, first, _ = self._ready_job(temp, section="stories", job_id="STORY-CLEAN")
            manifest_path = folder / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"status": "ready", "pipeline_stage": "complete"})
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            summary = WorkspaceCleaner(temp, self._recycler, validator=self.Validator()).scan()
            self.assertEqual(summary["file_count"], 0)
            self.assertEqual(summary["invalid_final_jobs"], 1)
            self.assertTrue(final.exists())
            self.assertTrue(first.exists())

    def test_auto_cleanup_reports_locked_file_and_keeps_its_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, final, first, second = self._ready_job(temp)

            def locked_recycler(path):
                if Path(path) == first:
                    raise PermissionError("ไฟล์กำลังถูกใช้งาน")
                Path(path).unlink()

            cleaner = WorkspaceCleaner(temp, locked_recycler, validator=self.Validator())
            result = cleaner.cleanup_completed_job("JOB-CLEAN")
            saved = json.loads((folder / "job.json").read_text(encoding="utf-8"))
            self.assertEqual(result["deleted_count"], 1)
            self.assertEqual(result["failed_count"], 1)
            self.assertTrue(first.exists())
            self.assertFalse(second.exists())
            self.assertEqual(saved["flow_video_path"], "videos/flow_01.mp4")
            self.assertEqual(saved["subtitle_video_path"], saved["video_path"])
            self.assertTrue(final.exists())

    def test_working_folder_is_inside_job_video_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "workspace" / "products" / "JOB-WORKING"
            working = working_video_folder(folder)
            self.assertEqual(working, (folder / "videos" / ".working").resolve())
            self.assertTrue(working.is_dir())

    def test_auto_cleanup_prunes_empty_working_folder_after_final_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, final, first, second = self._ready_job(temp)
            working = working_video_folder(folder)
            checkpoint = working / "flow_shot_03.mp4"
            checkpoint.write_bytes(b"checkpoint")
            manifest_path = folder / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["flow_clips"]["3"] = str(checkpoint.relative_to(folder))
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = WorkspaceCleaner(
                temp, self._recycler, validator=self.Validator()
            ).cleanup_completed_job("JOB-CLEAN")

            self.assertEqual(result["deleted_count"], 3)
            self.assertTrue(final.exists())
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            self.assertFalse(checkpoint.exists())
            self.assertFalse(working.exists())

    def test_final_only_cleanup_preserves_product_hybrid_provenance_without_stale_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, final, first, second = self._ready_job(temp)
            local = folder / "videos" / "local_motion_02.mp4"
            third = folder / "videos" / "flow_03.mp4"
            local.write_bytes(b"local-motion")
            third.write_bytes(b"flow-three")
            manifest_path = folder / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            history = [{"shot_index": 2, "failure_card_fingerprint": "policy-card"}]
            manifest.update({
                "flow_clips": {"1": "videos/flow_01.mp4", "3": "videos/flow_03.mp4"},
                "flow_clip_count": 2,
                "flow_remote_clip_count": 2,
                "flow_local_motion_clips": {"2": "videos/local_motion_02.mp4"},
                "flow_local_motion_clip_count": 1,
                "flow_segment_count": 3,
                "flow_target_clip_count": 3,
                "video_source_type": "google_flow_hybrid_composite",
                "flow_policy_fallbacks": {
                    "2": {
                        "failure_code": "FLOW_POLICY_BLOCKED",
                        "status": "ready",
                        "clip_path": "videos/local_motion_02.mp4",
                        "render_plan": {"output": "videos/local_motion_02.mp4"},
                    }
                },
                "flow_policy_fallback_history": history,
                "flow_segment_provenance": {
                    "1": {"source_type": "google_flow", "clip_path": "videos/flow_01.mp4"},
                    "2": {"source_type": "product_local_motion_policy_fallback", "clip_path": "videos/local_motion_02.mp4"},
                    "3": {"source_type": "google_flow", "clip_path": "videos/flow_03.mp4"},
                },
            })
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = WorkspaceCleaner(
                temp, self._recycler, validator=self.Validator()
            ).cleanup_completed_job("JOB-CLEAN")

            self.assertEqual(result["failed_count"], 0)
            self.assertTrue(final.exists())
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            self.assertFalse(local.exists())
            self.assertFalse(third.exists())
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["flow_clips"], {})
            self.assertEqual(saved["flow_local_motion_clips"], {})
            self.assertEqual(saved["flow_remote_clip_count"], 2)
            self.assertEqual(saved["flow_local_motion_clip_count"], 1)
            self.assertEqual(saved["flow_segment_count"], 3)
            self.assertEqual(saved["video_source_type"], "google_flow_hybrid_composite")
            self.assertEqual(saved["flow_policy_fallback_history"], history)
            self.assertEqual(saved["flow_policy_fallbacks"]["2"]["status"], "finalized")
            self.assertNotIn("clip_path", saved["flow_policy_fallbacks"]["2"])
            self.assertNotIn("render_plan", saved["flow_policy_fallbacks"]["2"])
            self.assertNotIn("clip_path", saved["flow_segment_provenance"]["2"])

    def test_final_only_cleanup_preserves_story_hybrid_counts_and_policy_history(self):
        with tempfile.TemporaryDirectory() as temp:
            folder, final, first, second = self._ready_job(
                temp, section="stories", job_id="STORY-HYBRID-CLEAN"
            )
            final.rename(folder / "videos" / "story_short_complete.mp4")
            final = folder / "videos" / "story_short_complete.mp4"
            fallback = folder / "videos" / "local_motion_scene_02.mp4"
            fallback.write_bytes(b"story-local-motion")
            manifest_path = folder / "job.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            policy_history = {"2": [{"failure_code": "FLOW_POLICY_BLOCKED", "failure_card_fingerprint": "story-card"}]}
            manifest.update({
                "status": "ready",
                "pipeline_stage": "complete",
                "scene_count": 2,
                "video_path": "videos/story_short_complete.mp4",
                "flow_clips": {"1": "videos/flow_01.mp4"},
                "flow_clip_count": 1,
                "flow_fallback_clips": {"2": "videos/local_motion_scene_02.mp4"},
                "flow_fallback_count": 1,
                "flow_scene_count": 2,
                "video_generation_mode": "google_flow",
                "video_source_type": "google_flow_story_hybrid_fallback",
                "flow_policy_failure_history": policy_history,
                "flow_prompt_retries": {
                    "2": {
                        "status": "local_motion_fallback_ready",
                        "fallback_clip_path": "videos/local_motion_scene_02.mp4",
                        "fallback_saved_at": "now",
                    }
                },
            })
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = WorkspaceCleaner(
                temp, self._recycler, validator=self.Validator()
            ).cleanup_completed_job("STORY-HYBRID-CLEAN")

            self.assertEqual(result["failed_count"], 0)
            self.assertTrue(final.exists())
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            self.assertFalse(fallback.exists())
            saved = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["flow_clips"], {})
            self.assertEqual(saved["flow_fallback_clips"], {})
            self.assertEqual(saved["flow_clip_count"], 1)
            self.assertEqual(saved["flow_fallback_count"], 1)
            self.assertEqual(saved["flow_scene_count"], 2)
            self.assertEqual(saved["video_source_type"], "google_flow_story_hybrid_fallback")
            self.assertEqual(saved["flow_policy_failure_history"], policy_history)
            self.assertEqual(saved["flow_prompt_retries"]["2"]["status"], "finalized")
            self.assertNotIn("fallback_clip_path", saved["flow_prompt_retries"]["2"])

    def test_ffprobe_validator_rejects_video_without_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            video = Path(temp) / "final.mp4"
            video.write_bytes(b"not-empty")

            def runner(*_args, **_kwargs):
                return SimpleNamespace(
                    returncode=0,
                    stderr="",
                    stdout=json.dumps({
                        "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920}],
                        "format": {"duration": "30.0"},
                    }),
                )

            validator = FinalVideoValidator(runner=runner)
            with self.assertRaisesRegex(ValueError, "ไม่มีเสียง"):
                validator.validate(video)


if __name__ == "__main__":
    unittest.main()
