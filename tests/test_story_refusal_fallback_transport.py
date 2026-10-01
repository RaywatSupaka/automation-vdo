"""Confirmed-refusal reuse remains bound to the current Story owner. No live provider."""
import json
import logging
from pathlib import Path
import subprocess
import time
import unittest
from unittest.mock import Mock

from core.local_bridge import LocalBridge


class StoryRefusalFallbackTransportTests(unittest.TestCase):
    def setUp(self):
        self.manager = Mock()
        self.manager.get.return_value = {"id": "STORY-REFUSAL-TRANSPORT", "image_ai_provider": "gemini", "scene_count": 10}
        self.bridge = LocalBridge("127.0.0.1", 0, Mock(), logging.getLogger("refusal-transport-test"), stories=self.manager)
        self.bridge._extension_runs[("ai", "STORY-REFUSAL-TRANSPORT", 0)] = {"run_id": "RUN-CURRENT"}
        self.payload = {"job_id": "STORY-REFUSAL-TRANSPORT", "run_id": "RUN-CURRENT", "provider": "gemini",
                        "index": 7, "source_index": 6, "reason": "STORY_IMAGE_REFUSED", "policy": "reuse_saved_local_v1",
                        "response_excerpt": "ยืนยันการปฏิเสธ" * 200,
                        "receipt_proof": {"original_run_id": "RUN-ORIGINAL", "review_revision": 0, "created_at": time.time() * 1000}}

    def test_current_owned_run_preserves_original_receipt_proof_and_bounded_excerpt(self):
        expected = {"ok": True, "image": "data:image/png;base64,saved", "metadata": {"scene_index": 7}}

        def save(job_id, index, source_index, excerpt, receipt_proof):
            self.assertTrue(self.bridge._extension_lock._is_owned())
            self.assertEqual((job_id, index, source_index), (self.payload["job_id"], 7, 6))
            self.assertEqual(excerpt, self.payload["response_excerpt"][:1200])
            self.assertEqual(receipt_proof, self.payload["receipt_proof"])
            return expected

        self.manager.save_refused_image_fallback.side_effect = save
        self.assertEqual(self.bridge._accept_story_image_fallback(self.payload), expected)
        self.assertFalse(self.bridge._extension_lock._is_owned())

    def test_stale_missing_or_unowned_current_run_does_not_reach_manager(self):
        for run in ["RUN-OLD", "", None]:
            with self.subTest(run=run), self.assertRaises(ValueError):
                self.bridge._accept_story_image_fallback({**self.payload, "run_id": run})
        self.bridge._extension_runs.clear()
        with self.assertRaises(ValueError):
            self.bridge._accept_story_image_fallback(self.payload)
        self.manager.save_refused_image_fallback.assert_not_called()

    def test_unknown_disposition_wrong_provider_and_invalid_indices_cannot_fallback(self):
        for change in [{"reason": "CHATGPT_NO_RESPONSE"}, {"policy": "unknown"}, {"provider": "chatgpt"},
                       {"index": True}, {"index": "7"}, {"index": 16}, {"source_index": 0}, {"source_index": 7}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.bridge._accept_story_image_fallback({**self.payload, **change})
        self.manager.save_refused_image_fallback.assert_not_called()

    def test_long_job_fallback_accepts_scene_16_but_rejects_scene_51(self):
        self.manager.get.return_value = {"id": self.payload["job_id"], "image_ai_provider": "gemini",
                                         "scene_count": 50, "long_video": {"version": 2, "scene_count": 50}}
        self.manager.save_refused_image_fallback.return_value = {"ok": True}
        self.assertEqual(self.bridge._accept_story_image_fallback({**self.payload,
            "index": 16, "source_index": 15}), {"ok": True})
        with self.assertRaises(ValueError):
            self.bridge._accept_story_image_fallback({**self.payload, "index": 51, "source_index": 50})

    def test_narrow_refusal_proof_rejects_missing_unknown_fields_or_invalid_values(self):
        proof = self.payload["receipt_proof"]
        for broken in [None, {}, {**proof, "token": "must-not-pass"}, {**proof, "original_run_id": ""},
                       {**proof, "review_revision": True}, {**proof, "review_revision": -1},
                       {**proof, "created_at": float("nan")}, {**proof, "created_at": 0},
                       {**proof, "created_at": time.time() * 1000 + 120000}]:
            with self.subTest(proof=broken), self.assertRaises(ValueError):
                self.bridge._accept_story_image_fallback({**self.payload, "receipt_proof": broken})
        self.manager.save_refused_image_fallback.assert_not_called()

    def test_manager_failure_propagates_without_success_ack(self):
        self.manager.save_refused_image_fallback.side_effect = ValueError("cancelled or unreadable donor")
        with self.assertRaisesRegex(ValueError, "cancelled or unreadable donor"):
            self.bridge._accept_story_image_fallback(self.payload)

    def test_actual_extension_refusal_receipt_resume_and_transport_harness(self):
        result = subprocess.run(["node", str(Path(__file__).with_name("story_refusal_fallback_harness.js"))],
                                capture_output=True, text=True, encoding="utf-8", timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        outcome = json.loads(result.stdout)
        self.assertTrue(outcome["ok"])
        self.assertGreaterEqual(outcome["cases"], 38)


if __name__ == "__main__":
    unittest.main()
