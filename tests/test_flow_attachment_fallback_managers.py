import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core.flow_fallback import FLOW_ATTACHMENT_UNCONFIRMED, validated_attachment_failure_evidence
from core.product_manager import ProductManager
from core.story_manager import StoryManager


def attachment_evidence(run_id="ATTACH-RUN"):
    return {
        "schema_version": 1, "phase": "before_submit", "run_id": run_id,
        "attempt_key": "job:shot:project", "project_id": "PROJECT-ATTACH",
        "attempt_started_at": 1000, "grace_started_at": 2000, "grace_elapsed_ms": 30000,
        "attachment_attempt_count": 1, "submission_absent": True, "generation_absent": True,
        "result_absent": True, "confirmation_absent": True, "terminal_latched": True,
    }


class FlowAttachmentFallbackManagerTests(unittest.TestCase):
    @staticmethod
    def _clip(root, name):
        target = Path(root) / name
        target.write_bytes(b"\x00\x00\x00\x18ftypisom" + name.encode() + bytes(72 * 1024))
        return target

    @staticmethod
    def _product(root):
        manager = ProductManager(root)
        folder = manager.root / "JOB-ATTACHMENT-MANAGER"
        (folder / "generated").mkdir(parents=True)
        (folder / "videos" / ".working").mkdir(parents=True)
        image_files = []
        for index in range(1, 4):
            image = folder / "generated" / f"selling_image_{index:02d}.png"
            Image.new("RGB", (64, 96), (index * 50, 60, 70)).save(image)
            image_files.append(str(image.relative_to(folder)))
        manifest = {
            "id": folder.name, "generated_images": image_files,
            "flow_target_clip_count": 3, "flow_shot_prompts": ["one", "two", "three"],
            "flow_clips": {}, "flow_local_motion_clips": {},
            "flow_source_image_map": {"1": 1, "2": 2, "3": 3},
            "flow_source_variant_map": {"1": 1, "2": 1, "3": 1},
        }
        (folder / "job.json").write_text(json.dumps(manifest), encoding="utf-8")
        (folder / "ai_request.json").write_text('{"schema_version":7}', encoding="utf-8")
        return manager, folder

    @staticmethod
    def _story(root, drama=False):
        manager = StoryManager(root)
        manifest = manager.create("การเดินทางของแมวน้อย", scene_count=6, video_generation_mode="google_flow")
        folder = manager.root / manifest["id"]
        image_files = []
        for index in range(1, 7):
            image = folder / "generated" / f"scene_{index:02d}.png"
            Image.new("RGB", (64, 96), (index * 30, 80, 90)).save(image)
            image_files.append(str(image.relative_to(folder)))
        manifest.update({
            "generated_images": image_files,
            "scene_prompts": [f"Scene {index}" for index in range(1, 7)],
            "scene_narrations": ["แมวน้อยเดินทาง"] * 6,
            "scene_durations": [4] * 6,
        })
        if drama:
            manifest["content_mode"] = "drama"
            manifest["drama_series_id"] = "SERIES-TEST"
        manager._save(manifest)
        return manager, folder

    def test_structured_proof_rejects_grace_active_generation_confirmation_and_text(self):
        self.assertEqual(
            validated_attachment_failure_evidence(attachment_evidence(), "ATTACH-RUN", "ATTACH-FP")["phase"],
            "before_submit",
        )
        for field, value in (
            ("submission_absent", False), ("generation_absent", False), ("result_absent", False),
            ("confirmation_absent", False), ("terminal_latched", False),
            ("grace_elapsed_ms", 29999), ("grace_elapsed_ms", "30000"),
            ("grace_started_at", 999), ("phase", "rendering"),
            ("run_id", "STALE-RUN"), ("attachment_attempt_count", 2),
            ("project_id", ""), ("attempt_key", ""),
        ):
            with self.subTest(field=field, value=value):
                proof = attachment_evidence()
                proof[field] = value
                with self.assertRaises(ValueError):
                    validated_attachment_failure_evidence(proof, "ATTACH-RUN", "ATTACH-FP")
        with self.assertRaises(ValueError):
            validated_attachment_failure_evidence("attachment_waiting_manual", "ATTACH-RUN", "ATTACH-FP")

    def test_product_pending_checkpoint_resumes_same_image_and_counts_sources_truthfully(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager, folder = self._product(root)
            job_id = folder.name
            canonical = folder / "generated" / "selling_image_02.png"
            image_hash = StoryManager._sha256_file(canonical)
            original = manager.get_job(job_id)
            for shot in (1, 3):
                manager.attach_flow_clip(job_id, shot, self._clip(root, f"remote-{shot}.mp4"))
            pending = manager.mark_flow_attachment_fallback(
                job_id, 2, 2, "แนบรูปไม่สำเร็จก่อนส่งงาน", fingerprint="ATTACH-FP",
                flow_run_id="ATTACH-RUN", evidence=attachment_evidence(),
            )
            checkpoint = pending["flow_attachment_fallbacks"]["2"]
            self.assertEqual(checkpoint["status"], "render_pending")
            self.assertEqual(checkpoint["source_image"], original["generated_images"][1])
            self.assertEqual(checkpoint["failure_code"], FLOW_ATTACHMENT_UNCONFIRMED)
            self.assertNotIn("policy_category", checkpoint)
            self.assertFalse(pending.get("flow_policy_fallbacks"))
            manager = ProductManager(root)
            resumed = manager.get_job(job_id)
            self.assertEqual(manager.flow_local_fallback_checkpoint(resumed, 2), checkpoint)
            with self.assertRaisesRegex(ValueError, "FLOW_ATTACHMENT_LOCAL_FALLBACK_CHECKPOINT"):
                manager.flow_package(job_id, 2)
            with self.assertRaises(ValueError):
                manager.attach_flow_clip(job_id, 2, self._clip(root, "late-remote.mp4"))
            duplicate = manager.mark_flow_attachment_fallback(
                job_id, 2, 2, "different heartbeat", fingerprint="ATTACH-FP-NEW",
                flow_run_id="ATTACH-RUN", evidence=attachment_evidence(),
            )
            self.assertEqual(len(duplicate["flow_attachment_fallback_history"]), 1)
            self.assertEqual(duplicate["flow_attachment_fallbacks"]["2"], checkpoint)
            saved = manager.attach_flow_local_motion_clip(job_id, 2, self._clip(root, "local-2.mp4"))
            self.assertEqual(saved["flow_clip_count"], 2)
            self.assertEqual(saved["flow_remote_clip_count"], 2)
            self.assertEqual(saved["flow_local_motion_clip_count"], 1)
            self.assertEqual(saved["flow_segment_count"], 3)
            self.assertEqual(saved["video_source_type"], "google_flow_hybrid_clips")
            provenance = saved["flow_segment_provenance"]["2"]
            self.assertEqual(provenance["source_type"], "product_local_motion_attachment_fallback")
            self.assertEqual(provenance["source_image"], original["generated_images"][1])
            self.assertEqual(saved["flow_source_image_map"], original["flow_source_image_map"])
            self.assertEqual(StoryManager._sha256_file(canonical), image_hash)

    def test_story_and_drama_restart_keep_attachment_fallback_separate_from_policy(self):
        for drama in (False, True):
            with self.subTest(drama=drama), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                manager, folder = self._story(root, drama)
                job_id = folder.name
                canonical = folder / "generated" / "scene_02.png"
                image_hash = manager._sha256_file(canonical)
                for shot in (1, 3, 4, 5, 6):
                    manager.attach_flow_clip(job_id, shot, self._clip(root, f"remote-{shot}.mp4"))
                result = manager.register_flow_attachment_failure(
                    job_id, 2, "แนบรูปไม่สำเร็จก่อนส่งงาน", flow_run_id="ATTACH-RUN",
                    failure_card_fingerprint="ATTACH-FP", evidence=attachment_evidence(),
                )
                self.assertEqual(result["action"], "local_motion_fallback")
                self.assertEqual(result["record"]["image_sha256"], image_hash)
                self.assertFalse(result["job"].get("flow_policy_failure_history"))
                manager = StoryManager(root)
                resumed = manager.get(job_id)
                history = manager._authenticated_flow_local_fallback_history(resumed, 2)
                self.assertEqual(history, [result["record"]])
                self.assertFalse(manager._authenticated_flow_policy_history(resumed, 2))
                with self.assertRaisesRegex(ValueError, "FLOW_ATTACHMENT_LOCAL_FALLBACK_CHECKPOINT"):
                    manager.flow_package(job_id, 2)
                with self.assertRaises(ValueError):
                    manager.attach_flow_clip(job_id, 2, self._clip(root, "late-remote.mp4"))
                duplicate = manager.register_flow_attachment_failure(
                    job_id, 2, flow_run_id="ATTACH-RUN", failure_card_fingerprint="NEW-FP",
                    evidence=attachment_evidence(),
                )
                self.assertEqual(duplicate["action"], "duplicate_attachment_event")
                self.assertEqual(len(duplicate["job"]["flow_attachment_failure_history"]["2"]), 1)
                saved = manager.attach_flow_fallback_clip(job_id, 2, self._clip(root, "local-2.mp4"))
                metadata = saved["flow_fallback_metadata"]["2"]
                self.assertEqual(metadata["failure_code"], FLOW_ATTACHMENT_UNCONFIRMED)
                self.assertNotIn("policy_attempt", metadata)
                self.assertEqual(metadata["attachment_attempt"], 1)
                self.assertEqual(metadata["image_sha256"], image_hash)
                self.assertEqual(saved["flow_clip_count"], 5)
                self.assertEqual(saved["flow_fallback_count"], 1)
                self.assertEqual(saved["flow_scene_count"], 6)
                self.assertEqual(saved["flow_video_status"], "ready")
                self.assertEqual(manager._sha256_file(canonical), image_hash)
                if drama:
                    self.assertEqual(saved["drama_series_id"], "SERIES-TEST")

    def test_manager_registration_rejects_unstructured_attachment_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            products, product_folder = self._product(root)
            stories, story_folder = self._story(root)
            with self.assertRaises(ValueError):
                products.mark_flow_attachment_fallback(
                    product_folder.name, 2, 2, "attachment_waiting_manual FLOW_ATTACHMENT_UNCONFIRMED",
                    fingerprint="FP", flow_run_id="ATTACH-RUN",
                )
            with self.assertRaises(ValueError):
                stories.register_flow_attachment_failure(
                    story_folder.name, 2, "whole page says attachment failed", flow_run_id="ATTACH-RUN",
                    failure_card_fingerprint="FP",
                )
            self.assertFalse(products.get_job(product_folder.name).get("flow_attachment_fallbacks"))
            self.assertFalse(stories.get(story_folder.name).get("flow_attachment_failure_history"))


if __name__ == "__main__":
    unittest.main()
