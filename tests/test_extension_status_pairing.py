"""Offline regressions for primary status selection; no server or browser starts."""

import copy
import threading
import unittest
from unittest.mock import patch

from core.local_bridge import LocalBridge


class ExtensionStatusPairingTests(unittest.TestCase):
    def setUp(self):
        # Avoid constructing stores, identity files, sockets or real job managers.
        self.bridge = LocalBridge.__new__(LocalBridge)
        self.bridge.REQUIRED_EXTENSION_VERSION = "0.15.458"
        self.bridge._extension_lock = threading.Lock()
        self.bridge._extension_trace_lock = threading.Lock()
        self.bridge._extension_clients = {}
        self.bridge._extension_trace = []
        self.bridge._extension_commands = [{
            "id": "CMD-CANCELLED", "status": "cancelled", "job_id": "STORY-OWNED",
            "client_id": "old-profile", "min_version": "0.15.458",
        }]
        self.bridge._extension_runs = {("ai", "STORY-OWNED", 0): {"run_id": "RUN-OWNED"}}

    def client(self, client_id, version="0.15.458", seen=990, **fields):
        item = {"client_id": client_id, "version": version, "last_seen_epoch": seen,
                "last_seen": f"observed-{seen}", **fields}
        self.bridge._extension_clients[client_id] = item
        return item

    def status(self, now=1000):
        with patch("core.local_bridge.time.time", return_value=now):
            return self.bridge.extension_status()

    def test_newer_457_cannot_mask_fresh_458_in_either_insertion_order(self):
        for order in (("paired", "old"), ("old", "paired")):
            with self.subTest(order=order):
                self.bridge._extension_clients.clear()
                for client_id in order:
                    self.client(client_id, "0.15.458" if client_id == "paired" else "0.15.457",
                                980 if client_id == "paired" else 999)
                status = self.status()
                self.assertTrue(status["connected"])
                self.assertEqual(status["client"]["client_id"], "paired")
                self.assertEqual([item["client_id"] for item in status["clients"]], ["old", "paired"])

    def test_both_fresh_heartbeat_orders_prefer_paired_client(self):
        for paired_seen, old_seen in ((980, 999), (999, 980), (995, 995)):
            with self.subTest(paired_seen=paired_seen, old_seen=old_seen):
                self.bridge._extension_clients.clear()
                self.client("old", "0.15.457", old_seen)
                self.client("paired", "0.15.458", paired_seen)
                self.assertEqual(self.status()["client"]["client_id"], "paired")

    def test_newest_of_multiple_compatible_profiles_is_primary(self):
        self.client("paired-a", seen=980, profile_id="profile-a")
        self.client("paired-b", seen=990, profile_id="profile-b")
        self.client("old", "0.15.457", 999, profile_id="profile-old")
        status = self.status()
        self.assertEqual(status["client"]["client_id"], "paired-b")
        self.assertEqual([item["profile_id"] for item in status["clients"]],
                         ["profile-old", "profile-b", "profile-a"])

    def test_expired_paired_client_does_not_mask_fresh_mismatch(self):
        self.client("expired-paired", seen=929.999)
        self.client("old", "0.15.457", 999)
        status = self.status()
        self.assertTrue(status["connected"])
        self.assertEqual(status["client"]["version"], "0.15.457")
        self.assertEqual(len(status["clients"]), 1)

    def test_seventy_second_boundary_is_unchanged(self):
        self.client("paired", seen=930)
        self.client("old", "0.15.457", 999)
        self.assertEqual(self.status()["client"]["client_id"], "paired")
        self.assertEqual(self.status(now=1000.001)["client"]["client_id"], "old")

    def test_no_fresh_clients_retains_disconnected_shape_and_trace(self):
        for with_expired in (False, True):
            with self.subTest(with_expired=with_expired):
                self.bridge._extension_clients.clear()
                if with_expired:
                    self.client("expired", seen=900)
                self.bridge._extension_trace = [{"sequence": value} for value in range(205)]
                status = self.status()
                self.assertEqual(set(status), {"connected", "clients", "trace"})
                self.assertFalse(status["connected"])
                self.assertEqual(status["clients"], [])
                self.assertEqual(status["trace"], [{"sequence": value} for value in range(5, 205)])

    def test_no_exact_match_truthfully_exposes_newest_mismatch(self):
        for version in ("0.15.457", "0.15.459", "", None):
            with self.subTest(version=version):
                self.bridge._extension_clients.clear()
                self.client("older", "0.15.450", 980)
                self.client("newest", version, 999)
                status = self.status()
                self.assertEqual(status["client"]["client_id"], "newest")
                self.assertNotEqual(status["client"]["version"], self.bridge.REQUIRED_EXTENSION_VERSION)

    def test_old_client_expiry_does_not_disconnect_fresh_pair(self):
        self.client("old", "0.15.457", 900)
        self.client("paired", seen=999)
        status = self.status()
        self.assertTrue(status["connected"])
        self.assertEqual([item["client_id"] for item in status["clients"]], ["paired"])

    def test_progress_and_observation_timestamps_stay_with_each_client(self):
        paired = self.client("paired", seen=980, ai_job_id="STORY-OWNED", ai_run_id="RUN-OWNED",
                             ai_step="image_checkpoint_saved", ai_image_count=7,
                             ai_updated_at="paired-progress-time", page="chatgpt")
        old = self.client("old", "0.15.457", 999, ai_job_id="STORY-OTHER",
                          ai_run_id="RUN-OTHER", ai_step="cancelled", ai_image_count=2,
                          ai_updated_at="old-progress-time", page="flow")
        status = self.status()
        for actual, expected in ((status["client"], paired), (status["clients"][0], old)):
            self.assertEqual(actual, {key: value for key, value in expected.items() if key != "last_seen_epoch"})
        self.assertEqual(status["clients"][0]["last_seen"], "observed-999")
        self.assertEqual(status["client"]["last_seen"], "observed-980")

    def test_status_does_not_mutate_clients_commands_cancel_or_run_ownership(self):
        self.client("paired", seen=980, profile_id="paired-profile", ai_step="cancelled")
        self.client("old", "0.15.457", 999, profile_id="old-profile", ai_step="waiting_response")
        before = copy.deepcopy((self.bridge._extension_clients, self.bridge._extension_commands,
                                self.bridge._extension_runs))
        self.status()
        self.assertEqual((self.bridge._extension_clients, self.bridge._extension_commands,
                          self.bridge._extension_runs), before)

    def test_public_status_top_level_edits_do_not_mutate_stored_client(self):
        self.client("paired", ai_step="image_checkpoint_saved")
        self.bridge._extension_trace = [{"sequence": 1}]
        status = self.status()
        status["client"]["ai_step"] = "changed-by-reader"
        status["trace"][0]["sequence"] = 99
        self.assertEqual(self.bridge._extension_clients["paired"]["ai_step"], "image_checkpoint_saved")
        self.assertEqual(self.bridge._extension_trace[0]["sequence"], 1)

    def test_ai_clear_preserves_other_jobs_and_all_profile_records(self):
        self.client("paired", seen=980, ai_job_id="STORY-OWNED", ai_step="cancelled")
        self.client("old", "0.15.457", 999, ai_job_id="STORY-OTHER", ai_step="waiting_response")
        self.bridge.clear_ai_progress("STORY-OWNED")
        status = self.status()
        self.assertEqual(status["client"]["client_id"], "paired")
        self.assertNotIn("ai_step", status["client"])
        self.assertEqual(status["clients"][0]["ai_step"], "waiting_response")
        self.assertEqual(len(status["clients"]), 2)

    def test_flow_clear_remains_job_and_shot_scoped(self):
        self.client("paired", seen=980, flow_job_id="STORY-OWNED", flow_shot_index=8, flow_step="cancelled")
        self.client("old", "0.15.457", 999, flow_job_id="STORY-OWNED", flow_shot_index=9,
                    flow_step="generation_started")
        self.bridge.clear_flow_progress("STORY-OWNED", 8)
        status = self.status()
        self.assertEqual(status["client"]["client_id"], "paired")
        self.assertNotIn("flow_step", status["client"])
        self.assertEqual(status["clients"][0]["flow_step"], "generation_started")


if __name__ == "__main__":
    unittest.main()
