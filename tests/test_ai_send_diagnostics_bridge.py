import json
import logging
import tempfile
import unittest
import urllib.request
from pathlib import Path

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.story_manager import StoryManager


class AISendDiagnosticsBridgeTests(unittest.TestCase):
    """Exercise HTTP/state/trace on an ephemeral bridge, never the user's engine."""

    def test_image_tool_preflight_reason_survives_error_and_saved_trace(self):
        detail = {"gesture_phase": "not_started", "dispatch_completed": False,
                  "preflight_reason": "chatgpt_image_tool", "tool_reason": "chip_unconfirmed"}
        response = self.progress("error", detail={**detail, "prompt": "PRIVATE DRAFT",
                                                 "cookie": "PRIVATE COOKIE"})
        self.assert_evidence(response, detail)

    def test_image_tool_preflight_rejects_private_and_unknown_reasons(self):
        for value in ("PRIVATE DRAFT", "https://secret/", "unknown", True):
            with self.subTest(value=value):
                self.assertEqual(LocalBridge._safe_ai_send_diagnostics({"detail": {
                    "tool_reason": value, "prompt": "PRIVATE DRAFT", "cookie": "PRIVATE COOKIE"
                }}), {})

    def test_submit_target_rejection_survives_error_and_saved_trace(self):
        for reason in ("send_target_ambiguous", "composer_form_changed"):
            with self.subTest(reason=reason):
                detail = {"gesture_phase": "not_started", "dispatch_completed": False,
                          "preflight_reason": reason}
                self.assert_evidence(self.progress("error", detail=detail), detail)

    def test_transient_send_rechecks_keep_only_bounded_reasons(self):
        detail = {"gesture_phase": "not_started", "preflight_reason": "send_target_ambiguous",
                  "preflight_stage": "after_attach",
                  "preflight_rechecks": 3,
                  "preflight_reasons": ["send_target_ambiguous", "response_active", "send_not_ready"]}
        self.assert_evidence(self.progress("error", detail={**detail, "prompt": "PRIVATE PROMPT"}), detail)
        self.assertEqual(LocalBridge._safe_ai_send_diagnostics({"detail": {
            "preflight_stage": "after_claim"}}), {"preflight_stage": "after_claim"})
        self.assertEqual(LocalBridge._safe_ai_send_diagnostics({"detail": {
            "preflight_rechecks": 99,
            "preflight_stage": "PRIVATE PROMPT",
            "preflight_reasons": ["PRIVATE PROMPT", "send_not_ready", "https://secret/", "response_active"],
        }}), {"preflight_reasons": ["send_not_ready"]})

    def test_send_point_strategy_and_prepress_reason_survive_safe_routes(self):
        for strategy in ("center", "viewport_scroll", "interior_point"):
            with self.subTest(strategy=strategy):
                detail = {"gesture_phase": "released", "send_target_strategy": strategy}
                self.assert_evidence(self.progress("ai_send_dispatched", detail=detail), detail)
                self.heartbeat()
                self.assertEqual(self.status()["client"]["ai_send_diagnostics"], detail)
        for reason in ("draft_mismatch", "send_not_ready", "capture_missing", "target_changed",
                       "readiness_changed", "target_blocked", "rejected_before_press",
                       "input_not_delivered", "send_surface_changed"):
            with self.subTest(reason=reason):
                detail = {"gesture_phase": "not_started", "preflight_reason": reason}
                self.assert_evidence(self.progress("error", **detail), detail)

    def test_send_point_diagnostics_reject_unknown_values_and_private_detail(self):
        secret = "PRIVATE_PROMPT_COOKIE_TOKEN"
        for value in (secret, True, 1, [], {"token": secret}):
            with self.subTest(value=value):
                self.assertEqual(LocalBridge._safe_ai_send_diagnostics({"detail": {
                    "send_target_strategy": value, "preflight_reason": value,
                    "prompt": secret, "button": {"expected": secret}, "cookie": secret,
                }}), {})

    def test_viewport_recovery_evidence_is_bounded_and_prompt_free(self):
        detail = {"gesture_phase": "released", "send_target_strategy": "viewport_scroll",
                  "viewport_width": 360, "viewport_height": 340, "scroll_attempts": 2}
        self.assert_evidence(self.progress("ai_send_dispatched", detail=detail), detail)
        self.assertEqual(LocalBridge._safe_ai_send_diagnostics({"detail": {
            "viewport_width": 10001, "viewport_height": -1, "scroll_attempts": 3,
            "prompt": "PRIVATE PROMPT"}}), {})

    def test_request_owner_recovery_evidence_survives_http_state_trace(self):
        detail = {"request_owner_found": False, "request_matches": False,
                  "draft_still_present": True, "request_hash": "8367a959",
                  "draft_hash": "8367a959", "request_recovery_wait_ms": 30000}
        response = self.progress("error", provider="gemini", detail=detail)
        self.assert_evidence(response, detail)

    def test_request_owner_recovery_evidence_filters_types_and_secrets(self):
        self.assertEqual(LocalBridge._safe_ai_send_diagnostics({"detail": {
            "request_owner_found": "false", "request_matches": 0,
            "request_hash": "SECRET_PROMPT", "draft_hash": "https://secret/",
            "request_recovery_wait_ms": True, "request_text": "SECRET_PROMPT"}}), {})
        for value in (-1, 360001, 1.5, "30000"):
            self.assertEqual(LocalBridge._safe_ai_send_diagnostics(
                {"request_recovery_wait_ms": value}), {})

    def test_owned_story_send_evidence_is_bounded(self):
        value=LocalBridge._safe_ai_send_diagnostics({'submission_proof':'owned_story_user_turn',
            'request_turn_id':'conversation-turn-13','request_message_id':'message-13','prompt':'not logged'})
        self.assertEqual(value,{'submission_proof':'owned_story_user_turn',
            'request_turn_id':'conversation-turn-13','request_message_id':'message-13'})
        self.assertEqual(LocalBridge._safe_ai_send_diagnostics({'request_message_id':'https://secret/?token=x',
            'request_turn_id':'arbitrary text'}),{})

    def test_semantic_request_turn_evidence_is_bounded(self):
        turn_id = 'fallback-turn-0:0:user'
        self.assertEqual(LocalBridge._safe_ai_send_diagnostics({'request_turn_id': turn_id}),
                         {'request_turn_id': turn_id})
        for value in ('fallback-turn-0:2:assistant', 'fallback-turn-secret:0:user',
                      'fallback-turn-123456789:0:user', 'fallback-turn-0:0:user?token=x'):
            self.assertEqual(LocalBridge._safe_ai_send_diagnostics({'request_turn_id': value}), {})

    def test_story_image_wait_facts_survive_http_status_and_durable_trace(self):
        facts = {"scene_index": 2, "result_reason": "waiting_response", "candidate_count": 0,
                 "response_active": False, "response_signature": "abc123",
                 "stop_visible": False, "progress_count": 1, "stale_progress": False,
                 "refresh_outcome": "rejected_preclaim", "refresh_reason": "live_guard_changed",
                 "refresh_attempts": 1}
        response = self.progress("waiting_for_image", **facts, prompt="PRIVATE PROMPT")
        self.assertEqual(response["progress"]["ai_image_observation"], facts)
        self.assertEqual(self.status()["client"]["ai_image_observation"], facts)
        self.assertEqual(self.status()["trace"][-1]["detail"], facts)
        self.assertEqual(self.saved_trace()[-1]["detail"], facts)
        self.assertNotIn("PRIVATE PROMPT", json.dumps(self.saved_trace()[-1]))

    def test_story_image_wait_facts_reject_text_and_unbounded_values(self):
        facts = LocalBridge._safe_ai_image_observation({
            "step": "waiting_for_image", "scene_index": True, "candidate_count": 200,
            "result_reason": "PRIVATE PROMPT", "refresh_outcome": "unknown-state",
            "refresh_reason": "https://secret/", "refresh_attempts": 4,
            "response_active": "false", "response_signature": "private text", "prompt": "PRIVATE PROMPT",
        })
        self.assertEqual(facts, {})
        self.assertEqual(LocalBridge._safe_ai_image_observation({
            "step": "ai_send_dispatched", "scene_index": 2, "candidate_count": 1}), {})

    def test_story_image_busy_sources_reject_unbounded_values(self):
        self.assertEqual(LocalBridge._safe_ai_image_observation({
            "step": "waiting_for_image", "stop_visible": "false", "progress_count": 999,
            "stale_progress": 1, "prompt": "PRIVATE PROMPT"}), {})

    def test_post_refresh_recovery_identity_survives_durable_trace_without_prompt(self):
        facts = {"scene_index": 4, "recovery_kind": "missing_after_refresh", "recovery_phase": "checking",
                 "send_nonce": "01234567-89ab-cdef-0123-456789abcdef", "stable_samples": 3,
                 "refreshed_check_ms": 30000, "request_message_id": "owned-message",
                 "request_turn_id": "fallback-turn-4:0:user"}
        response = self.progress("image_refresh_check", **facts, receipt_identity="PRIVATE PROMPT")
        self.assertEqual(response["progress"]["ai_image_observation"], facts)
        self.assertEqual(self.saved_trace()[-1]["detail"], facts)
        self.assertNotIn("PRIVATE PROMPT", json.dumps(self.saved_trace()[-1]))

    def test_post_refresh_recovery_rejects_unbounded_or_private_fields(self):
        self.assertEqual(LocalBridge._safe_ai_image_observation({"step": "image_restart_pending",
            "send_nonce": "https://secret", "refreshed_check_ms": True, "stable_samples": -1,
            "recovery_kind": "PRIVATE PROMPT", "recovery_phase": "unknown",
            "request_message_id": "https://secret", "receipt_identity": "PRIVATE PROMPT"}), {})

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.products = ProductManager(Path(temporary.name))
        self.bridge = LocalBridge(
            "127.0.0.1", 0, self.products, logging.getLogger("ai-send-diagnostics-test")
        ).start()
        self.addCleanup(self.bridge.stop)
        self.base_url = f"http://127.0.0.1:{self.bridge.server.server_address[1]}"
        self.client_id = "diagnostics-client"
        self.job_id = "JOB-SEND-DIAGNOSTICS"
        self.run_id = "RUN-SEND-DIAGNOSTICS"
        self.heartbeat()

    def post(self, route, payload):
        request = urllib.request.Request(
            self.base_url + route, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    def heartbeat(self):
        return self.post("/api/extension/heartbeat", {
            "client_id": self.client_id,
            "version": LocalBridge.REQUIRED_EXTENSION_VERSION,
            "browser": "Google Chrome", "page": "chatgpt",
        })

    def progress(self, step, **extra):
        return self.post("/api/extension/progress", {
            "scope": "chatgpt", "client_id": self.client_id,
            "job_id": self.job_id, "run_id": self.run_id, "tab_id": 42,
            "provider": "chatgpt", "step": step, "message": step, **extra,
        })

    def status(self):
        with urllib.request.urlopen(self.base_url + "/api/extension/status", timeout=5) as response:
            return json.load(response)

    def saved_trace(self):
        path = self.products.root / self.job_id / "logs" / "extension_trace.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def assert_evidence(self, response, expected):
        self.assertEqual(response["progress"]["ai_send_diagnostics"], expected)
        status = self.status()
        self.assertEqual(status["client"]["ai_send_diagnostics"], expected)
        self.assertEqual(status["trace"][-1]["detail"], expected or None)
        self.assertEqual(self.saved_trace()[-1]["detail"], expected or None)

    def test_dispatched_evidence_survives_route_state_and_persistent_trace(self):
        detail = {
            "send_method": "single_trusted_ai_send_unconfirmed",
            "dispatch_completed": True, "trusted_click_seen": False,
            "click_events": [{"type": "mousedown", "trusted": True}],
        }
        response = self.progress(
            "ai_send_dispatched", send_method=detail["send_method"],
            prompt_length=1234, detail=detail,
        )
        self.assert_evidence(response, {**detail, "prompt_length": 1234})
        self.heartbeat()
        self.assertEqual(self.status()["client"]["ai_send_diagnostics"], {
            **detail, "prompt_length": 1234,
        })

    def test_preflight_evidence_survives_route_state_trace_and_heartbeat(self):
        detail = {"gesture_phase": "not_started", "preflight_reason": "text_guard_changed",
                  "changed_fields": ["sourceSignature"], "claim_match": True, "accepted": False}
        response = self.progress("error", provider="gemini", detail=detail)
        self.assert_evidence(response, detail)
        self.heartbeat()
        self.assertEqual(self.status()["client"]["ai_send_diagnostics"], detail)

    def test_story_image_attempt_message_persists_without_image_specific_detail(self):
        stories = StoryManager(self.products.project_root)
        self.bridge.stories = stories
        job = stories.create("เรื่องชั่วคราวสำหรับตรวจข้อความ", scene_count=6)
        self.job_id = job["id"]
        self.run_id = self.bridge._resolve_extension_run_id("open_story_chatgpt", self.job_id, 0)
        manifest = stories.root / self.job_id / "job.json"
        before = manifest.read_bytes()
        provider_text = "ระบบกำลังตีความคำขอนี้เป็นงานแก้ไขภาพเดิม และยังไม่มีภาพเป้าหมายในแชตนี้"
        code = "CHATGPT_NO_IMAGE"
        category = "reference_required"
        message = f"ภาพ 1 • ครั้ง 2 • {code} • {category} • {provider_text}"
        with self.assertLogs(self.bridge.logger, level="INFO") as captured:
            response = self.progress(
                "image_attempt_result", message=message, image_index=1, attempt=2,
                error_code=code, failure_category=category, response_excerpt=provider_text,
            )
        self.assertEqual(response["progress"]["ai_message"], message)
        self.assertEqual(response["progress"]["ai_send_diagnostics"], {})
        status = self.status()
        self.assertEqual(status["client"]["ai_message"], message)
        trace = status["trace"][-1]
        self.assertEqual(trace["action"], "image_attempt_result")
        self.assertEqual(trace["job_id"], self.job_id)
        self.assertEqual(trace["run_id"], self.run_id)
        self.assertIsNone(trace["detail"])
        self.assertEqual(trace["message"], message)
        trace_file = stories.root / self.job_id / "logs" / "extension_trace.jsonl"
        persisted = [json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(persisted), 1)
        self.assertEqual(persisted[0]["message"], message)
        self.assertIsNone(persisted[0]["detail"])
        self.assertTrue(any(message in line for line in captured.output))
        for expected in ("ภาพ 1", "ครั้ง 2", code, category, provider_text):
            self.assertIn(expected, persisted[0]["message"])
        self.assertEqual(manifest.read_bytes(), before)

    def test_accepted_records_exact_proof_without_inventing_trusted_click(self):
        response = self.progress(
            "ai_send_accepted", submission_proof="new_user_turn", prompt_length=4321,
        )
        self.assert_evidence(response, {"submission_proof": "new_user_turn", "prompt_length": 4321})
        self.assertNotIn("trusted_click_seen", self.status()["client"]["ai_send_diagnostics"])

    def test_owned_motion_proof_survives_gemini_route_state_and_saved_trace(self):
        detail = {"submission_proof": "owned_motion_user_turn", "prompt_length": 1174}
        response = self.progress("ai_send_accepted", provider="gemini", **detail)
        self.assert_evidence(response, detail)

    def test_image_preflight_and_latched_wait_changes_survive_without_raw_values(self):
        detail = {"gesture_phase": "not_started", "preflight_reason": "gemini_image_preflight",
                  "changed_fields": ["upload_busy"], "wait_changed_fields": ["prompt", "sourceSignature"]}
        self.assert_evidence(self.progress("error", provider="gemini", detail=detail), detail)
        self.heartbeat()
        self.assertEqual(self.status()["client"]["ai_send_diagnostics"], detail)

    def test_split_target_counters_and_timed_events_survive_all_diagnostics_routes(self):
        detail = {
            "target_node_changes_prepress": 1, "target_geometry_changes_prepress": 2,
            "target_node_changes_during_gesture": 0, "target_geometry_changes_during_gesture": 1,
            "click_events": [
                {"type": "pointerdown", "trusted": True, "on_target": True, "elapsed_ms": 0, "phase": "pressed"},
                {"type": "mouseup", "trusted": True, "on_target": False, "elapsed_ms": 60000, "phase": "released"},
            ],
        }
        self.assert_evidence(self.progress("ai_send_dispatched", detail=detail), detail)
        self.assert_evidence(self.progress("error", **detail), detail)

    def test_new_diagnostics_reject_coercions_unbounded_times_and_arbitrary_strings(self):
        for invalid in (-1, 1001, True, 1.5, "SECRET", {"token": "SECRET"}):
            with self.subTest(invalid=invalid):
                value = LocalBridge._safe_ai_send_diagnostics({
                    "target_node_changes_prepress": invalid, "target_geometry_changes_prepress": invalid,
                    "target_node_changes_during_gesture": invalid, "target_geometry_changes_during_gesture": invalid,
                })
                self.assertEqual(value, {})
        for invalid in (-1, 60001, True, 1.5, "SECRET", {"token": "SECRET"}):
            with self.subTest(invalid=invalid):
                value = LocalBridge._safe_ai_send_diagnostics({
                    "click_events": [{"type": "click", "trusted": True, "on_target": "false",
                                      "elapsed_ms": invalid, "phase": "SECRET", "target": "SECRET"}],
                    "wait_changed_fields": ["prompt", "SECRET", {}, "prompt", "upload_busy"],
                })
                self.assertEqual(value, {"click_events": [{"type": "click", "trusted": True}],
                                         "wait_changed_fields": ["prompt", "upload_busy"]})

    def test_gesture_evidence_survives_top_level_progress_state_and_trace(self):
        detail = {
            "gesture_phase": "released",
            "target_changed": True,
            "release_on_send_target": False,
            "target_stable_before_press": True,
            "dispatch_completed": True,
            "trusted_click_seen": False,
            "click_events": [
                {"type": "pointerdown", "trusted": True},
                {"type": "mousedown", "trusted": True},
            ],
        }
        self.assert_evidence(self.progress("ai_send_dispatched", **detail), detail)
        self.heartbeat()
        self.assertEqual(self.status()["client"]["ai_send_diagnostics"], detail)
        detail["draft_still_present"] = True
        self.assert_evidence(self.progress("error", detail=detail), detail)

    def test_gesture_phases_and_false_flags_are_preserved_without_dedup_loss(self):
        for phase in ("not_started", "pressed", "released", "release_uncertain"):
            detail = {
                "gesture_phase": phase,
                "target_changed": False,
                "release_on_send_target": False,
                "target_stable_before_press": False,
            }
            with self.subTest(phase=phase):
                self.assert_evidence(self.progress("ai_send_dispatched", detail=detail), detail)
        self.assertEqual(len(self.saved_trace()), 4)
        self.progress("ai_send_dispatched", detail=detail)
        self.assertEqual(len(self.saved_trace()), 4)

    def test_gesture_evidence_rejects_unknown_phases_coerced_flags_and_nested_data(self):
        for value in ("SECRET_PROMPT_COOKIE", True, 1, [], {"token": "SECRET_PROMPT_COOKIE"}):
            detail = {
                "gesture_phase": value,
                "target_changed": "false",
                "release_on_send_target": 1,
                "target_stable_before_press": {"token": "SECRET_PROMPT_COOKIE"},
                "click_events": [{"type": "mouseup", "trusted": True,
                                  "target": "SECRET_PROMPT_COOKIE", "target_changed": True}],
            }
            with self.subTest(value=value):
                response = self.progress("error", detail=detail)
                self.assert_evidence(response, {"click_events": [{"type": "mouseup", "trusted": True}]})
                self.assertNotIn("SECRET_PROMPT_COOKIE", json.dumps((response, self.status(), self.saved_trace())))

    def test_error_keeps_supplied_send_diagnostics_but_never_extra_strings(self):
        secret = "PRIVATE_PROMPT_COOKIE_TOKEN_DO_NOT_PERSIST"
        detail = {
            "send_method": "single_trusted_ai_send_unconfirmed",
            "dispatch_completed": True, "trusted_click_seen": False,
            "prompt_length": 357, "draft_still_present": True,
            "click_events": [{"type": "click", "trusted": False, "target": secret}],
            "prompt": secret, "cookie": secret, "token": secret,
            "arbitrary": {"password": secret},
        }
        response = self.progress("error", detail=detail, prompt=secret, token=secret)
        expected = {
            "send_method": detail["send_method"], "dispatch_completed": True,
            "trusted_click_seen": False, "prompt_length": 357,
            "draft_still_present": True,
            "click_events": [{"type": "click", "trusted": False}],
        }
        self.assert_evidence(response, expected)
        self.assertEqual(self.saved_trace()[-1]["level"], "error")
        for value in (response, self.status(), self.saved_trace()):
            self.assertNotIn(secret, json.dumps(value))

    def test_only_known_types_and_bounded_click_evidence_are_allowed(self):
        clicks = [{"type": "click", "trusted": bool(index % 2), "secret": "omit"} for index in range(30)]
        response = self.progress("ai_send_dispatched", detail={
            "send_method": "trusted_ai_send", "click_events": clicks,
            "prompt_length": 1_000_000, "dispatch_completed": False,
        })
        self.assert_evidence(response, {
            "send_method": "trusted_ai_send", "prompt_length": 1_000_000,
            "dispatch_completed": False,
            "click_events": [{"type": row["type"], "trusted": row["trusted"]} for row in clicks[-10:]],
        })
        invalid = self.progress("error", detail={
            "send_method": "token=SECRET", "submission_proof": "SECRET",
            "prompt_length": 1_000_001, "dispatch_completed": "false",
            "trusted_click_seen": 1, "draft_still_present": [],
            "click_events": [None, {"type": "SECRET", "trusted": True},
                             {"type": "click", "trusted": "false"}],
        })
        self.assert_evidence(invalid, {"click_events": []})

    def test_malformed_optional_evidence_is_ignored_without_breaking_legacy_progress(self):
        for detail in (None, [], "SECRET", 42):
            with self.subTest(detail=detail):
                response = self.progress("waiting_for_analysis", detail=detail, prompt_length=True)
                self.assert_evidence(response, {})
        for length in (-1, "123", 1.5):
            with self.subTest(length=length):
                self.assert_evidence(self.progress("error", prompt_length=length), {})

    def test_changed_evidence_is_not_lost_to_transition_or_trace_deduplication(self):
        first = self.progress("ai_send_dispatched", detail={"trusted_click_seen": False})
        self.assert_evidence(first, {"trusted_click_seen": False})
        second = self.progress("ai_send_dispatched", detail={"trusted_click_seen": True})
        self.assert_evidence(second, {"trusted_click_seen": True})
        self.assertEqual(len(self.saved_trace()), 2)
        self.progress("ai_send_dispatched", detail={"trusted_click_seen": True})
        self.assertEqual(len(self.saved_trace()), 2)

    def test_new_progress_and_explicit_clear_do_not_retain_stale_send_proof(self):
        self.progress("ai_send_accepted", submission_proof="composer_cleared")
        self.assert_evidence(self.progress("waiting_for_analysis"), {})
        self.progress("ai_send_dispatched", detail={"dispatch_completed": True})
        self.bridge.clear_ai_progress(self.job_id)
        self.assertNotIn("ai_send_diagnostics", self.status()["client"])

    def test_stale_run_cannot_replace_or_persist_current_send_evidence(self):
        self.run_id = self.bridge._resolve_extension_run_id("open_chatgpt", self.job_id, 0)
        self.progress("ai_send_accepted", submission_proof="new_user_turn")
        self.run_id = "RUN-STALE-DIAGNOSTICS"
        stale = self.progress("error", detail={
            "trusted_click_seen": False, "gesture_phase": "release_uncertain",
            "target_changed": True, "release_on_send_target": False,
            "target_stable_before_press": True,
        })
        self.assertTrue(stale["ignored"])
        self.assertEqual(stale["reason"], "stale_ai_run")
        self.assertEqual(self.status()["client"]["ai_send_diagnostics"], {"submission_proof": "new_user_turn"})
        self.assertEqual(len(self.saved_trace()), 1)


if __name__ == "__main__":
    unittest.main()
