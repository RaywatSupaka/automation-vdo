"""Execute only the real capture method: no GUI, engine, browser or Job writes."""
import ast
import json
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from core.local_bridge import LocalBridge


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PREFIX = "หลักฐานการส่ง AI: "


class AISendErrorLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ast.parse((ROOT / "ui/main_window.py").read_text(encoding="utf-8"))
        window = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == "MainWindow")
        method = next(node for node in window.body if isinstance(node, ast.FunctionDef)
                      and node.name == "_capture_automation_error_log")
        namespace = {"datetime": datetime, "LocalBridge": LocalBridge}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "capture-error-log", "exec"), namespace)
        cls.capture = staticmethod(namespace[method.name])

    def capture_text(self, diagnostics, *, service="ChatGPT Web", job_id="JOB-TEST", **client_fields):
        client = {
            "ai_job_id": "JOB-TEST", "version": LocalBridge.REQUIRED_EXTENSION_VERSION,
            "ai_step": "error", "ai_message": "Send not acknowledged",
            "ai_send_diagnostics": diagnostics, **client_fields,
        }
        window = SimpleNamespace(
            bridge=SimpleNamespace(extension_status=lambda: {"clients": [client], "client": client}),
            log=Mock(), _desktop_set_notice=Mock(),
        )
        self.capture(window, job_id, "Send failed", service)
        window._desktop_set_notice.assert_called_once()
        return window._automation_error_log["text"]

    def evidence(self, text):
        return json.loads(next(line[len(EVIDENCE_PREFIX):] for line in text.splitlines()
                               if line.startswith(EVIDENCE_PREFIX)))

    def test_exact_ai_job_copies_valid_evidence_and_preserves_false(self):
        detail = {"send_method": "single_trusted_ai_send_unconfirmed", "prompt_length": 357,
                  "dispatch_completed": True, "trusted_click_seen": False,
                  "draft_still_present": False,
                  "gesture_phase": "released", "target_changed": True,
                  "release_on_send_target": False, "target_stable_before_press": True,
                  "click_events": [{"type": "mouseup", "trusted": True}]}
        self.assertEqual(self.evidence(self.capture_text(detail)), detail)

    def test_unknown_evidence_is_not_invented_as_false(self):
        detail = {"submission_proof": "new_user_turn"}
        actual = self.evidence(self.capture_text(detail, service="Gemini Web"))
        self.assertEqual(actual, detail)
        self.assertNotIn("trusted_click_seen", actual)
        self.assertNotIn(EVIDENCE_PREFIX, self.capture_text(None))

    def test_meta_error_never_borrows_completed_chatgpt_status(self):
        from unittest.mock import patch
        from core.meta_error_report import story_service_label
        service = story_service_label({'long_video':True, 'video_generation_mode':'meta_ai'})
        self.assertEqual(service, 'คลิปยาว / ChatGPT Web / Meta AI')
        window = SimpleNamespace(stories=object(), log=Mock(), _desktop_set_notice=Mock(),
            bridge=SimpleNamespace(extension_status=lambda:{'clients':[{
                'ai_job_id':'STORY-TEST', 'ai_step':'complete', 'ai_message':'ส่งภาพครบ 23 ฉาก',
                'ai_page_url':'https://chatgpt.com/c/old', 'ai_page_excerpt':'old-image-page'}]}))
        with patch('core.meta_error_report.read_meta_error', return_value={
                'index':13, 'stage':'needs_attention', 'message':'หน้า Meta ไม่ตรงบทสนทนา',
                'expected_url':'https://www.meta.ai/prompt/saved', 'observed_url':'https://www.meta.ai/'}):
            self.capture(window, 'STORY-TEST', 'META_VIDEO_REVIEW • หน้า Meta ไม่ตรงบทสนทนา', service)
        text = window._automation_error_log['text']
        self.assertIn('ฉาก 13', text); self.assertIn('หน้าเว็บ: https://www.meta.ai/', text)
        self.assertIn('ลิงก์ฉาก Meta ที่บันทึกไว้:', text)
        for stale in ('chatgpt.com/c/old','ส่งภาพครบ 23 ฉาก','old-image-page','ประกอบวิดีโอในเครื่อง'):
            self.assertNotIn(stale, text)

    def test_meta_without_receipt_does_not_invent_scene_or_current_url(self):
        window = SimpleNamespace(log=Mock(), _desktop_set_notice=Mock(),
            bridge=SimpleNamespace(extension_status=lambda:{'client':{
                'ai_step':'complete','ai_page_url':'https://chatgpt.com/c/old'}}))
        self.capture(window, 'STORY-TEST', 'META_VIDEO_REVIEW • failure', 'Meta AI')
        text = window._automation_error_log['text']
        self.assertNotIn('chatgpt.com', text)
        self.assertIn('ไม่พบใบรับฉาก', text)

    def test_missing_request_is_not_explained_as_completed_or_unsent(self):
        detail = {"request_owner_found": False, "request_matches": False,
                  "draft_still_present": True, "request_hash": "8367a959",
                  "draft_hash": "8367a959", "request_recovery_wait_ms": 30000}
        text = self.capture_text(detail, service="Story Shorts / AI Web / Google Flow")
        self.assertEqual(self.evidence(text), detail)
        self.assertIn("ยังยืนยันคำถามของฉากนี้ในแชตไม่ได้", text)
        self.assertIn("ไม่ใช้คำตอบฉากก่อน", text)
        self.assertIn("ยังอยู่ในช่องพิมพ์", text)
        self.assertNotIn("ยังไม่ได้กดส่ง", text)

    def test_gemini_owned_acceptance_and_diagnostic_changes_reach_copyable_log(self):
        detail = {"submission_proof": "owned_motion_user_turn", "target_node_changes_prepress": 1,
                  "target_geometry_changes_prepress": 0, "target_node_changes_during_gesture": 0,
                  "target_geometry_changes_during_gesture": 1, "wait_changed_fields": ["sourceSignature"],
                  "click_events": [{"type": "mouseup", "trusted": True, "on_target": False,
                                    "elapsed_ms": 123, "phase": "released"}]}
        self.assertEqual(self.evidence(self.capture_text(detail, service="Gemini Web")), detail)

    def test_zero_click_preflight_is_explained_without_inventing_cancellation(self):
        detail = {"gesture_phase": "not_started", "preflight_reason": "text_guard_changed",
                  "changed_fields": ["sourceSignature"], "claim_match": True, "accepted": False}
        text = self.capture_text(detail, service="Story Shorts / AI Web / Google Flow")
        self.assertEqual(self.evidence(text), detail)
        self.assertIn("ยังไม่ได้กดส่ง", text)
        self.assertIn("รูปแนบในช่องพิมพ์", text)
        self.assertNotIn("ยกเลิก", text)

    def test_preflight_fields_drop_unknown_text_and_invalid_boolean(self):
        text = self.capture_text({"preflight_reason": "SECRET", "claim_match": "true",
                                  "changed_fields": ["prompt", "SECRET", {}, "prompt", "upload_busy"]})
        self.assertNotIn("SECRET", text)
        self.assertEqual(self.evidence(text), {"changed_fields": ["prompt", "upload_busy"]})
        self.assertNotIn("ยังไม่ได้กดส่ง", text)

    def test_arbitrary_values_and_secrets_are_sanitized_before_copy(self):
        secret = "SECRET_COOKIE_FULL_PROMPT"
        text = self.capture_text({
            "prompt": secret, "cookie": secret, "arbitrary": {"token": secret},
            "send_method": secret, "submission_proof": secret,
            "gesture_phase": secret, "target_changed": "true",
            "release_on_send_target": 0, "target_stable_before_press": {"token": secret},
            "trusted_click_seen": "false", "dispatch_completed": True,
            "click_events": [{"type": "click", "trusted": False, "target": secret}],
        })
        self.assertNotIn(secret, text)
        self.assertEqual(self.evidence(text), {"dispatch_completed": True,
                         "click_events": [{"type": "click", "trusted": False}]})

    def test_other_job_fallback_or_flow_match_never_copies_ai_proof(self):
        for fields in ({"ai_job_id": "JOB-OTHER"},
                       {"ai_job_id": "JOB-OTHER", "flow_job_id": "JOB-TEST"}):
            with self.subTest(fields=fields):
                self.assertNotIn(EVIDENCE_PREFIX, self.capture_text({"trusted_click_seen": True}, **fields))
        self.assertNotIn(EVIDENCE_PREFIX, self.capture_text({"trusted_click_seen": True}, job_id=""))

    def test_non_ai_error_does_not_copy_ai_diagnostics(self):
        for service in ("Google Flow", "automation", "Voice"):
            with self.subTest(service=service):
                self.assertNotIn(EVIDENCE_PREFIX, self.capture_text({"trusted_click_seen": True}, service=service))

    def test_incompatible_or_unversioned_client_proof_is_omitted(self):
        for version in ("0.0.1", "", None):
            with self.subTest(version=version):
                self.assertNotIn(EVIDENCE_PREFIX, self.capture_text({"trusted_click_seen": True}, version=version))


if __name__ == "__main__":
    unittest.main()
