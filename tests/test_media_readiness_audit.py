import unittest

from tests.media_readiness_audit_probe import run


class MediaReadinessAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = run()

    def test_story_late_encoder_cancellation_preserves_previous_outputs(self):
        for method in ("compose", "render_scene_motion_clip"):
            with self.subTest(method=method):
                self.assertEqual(self.evidence[method + "_late_cancel"], {
                    "cancel_requested": True, "raised": "OperationCancelled", "previous_output_preserved": True,
                })

    def test_native_mode_applies_saved_frame_rate_and_encoder_quality(self):
        self.assertEqual(self.evidence["native_render_choices"], {
            "requested_fps": 24, "actual_fps": 24.0, "encoder_crf": ["23"], "plan_fps": 24, "plan_crf": 23,
        })

    def test_failed_green_manifest_promotion_preserves_previous_final(self):
        self.assertEqual(self.evidence["product_green_manifest_failure"], {
            "raised": "OSError", "previous_output_preserved": True, "manifest_opacity": .3,
            "previous_opacity": .3, "unreferenced_candidates": [],
        })

    def test_green_cancellation_before_promotion_cleans_only_new_candidate(self):
        self.assertEqual(self.evidence["product_green_late_cancel"], {
            "raised": "OperationCancelled", "previous_output_preserved": True,
            "manifest_output_unchanged": True, "unreferenced_candidates": [],
        })

    def test_lost_green_manifest_ack_retains_the_committed_file(self):
        self.assertEqual(self.evidence["product_green_committed_ack_lost"], {
            "raised": "OSError", "previous_output_preserved": True, "promoted_output_retained": True,
            "promoted_is_new_version": True, "manifest_matches_promoted": True,
        })


if __name__ == "__main__":
    unittest.main()
