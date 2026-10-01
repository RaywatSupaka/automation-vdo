import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WebLoginGateContractTests(unittest.TestCase):
    def test_extension_detects_all_three_login_services(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        ai_web = (ROOT / "browser_extension" / "chatgpt.js").read_text(encoding="utf-8")
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        manifest = (ROOT / "browser_extension" / "manifest.json").read_text(encoding="utf-8")
        self.assertIn("function isWebLoginUrl", background)
        self.assertIn("accounts\\.google\\.com", background)
        self.assertIn("auth\\.openai\\.com", background)
        self.assertIn("function resolvePendingWebAction", background)
        self.assertIn('step: "user_action_resolved"', background)
        self.assertIn('action_kind: error.actionKind', ai_web)
        self.assertIn("function loginRequired", ai_web)
        self.assertIn("function loginRequired", flow)
        self.assertIn('report("user_action_required"', flow)
        self.assertIn('"https://accounts.google.com/*"', manifest)
        self.assertIn('"https://auth.openai.com/*"', manifest)

    def test_engine_pauses_without_consuming_timeout_and_resumes_checkpoint(self):
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        bridge = (ROOT / "core" / "local_bridge.py").read_text(encoding="utf-8")
        web = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Manual login/verification time must not consume the AI timeout", engine)
        self.assertIn("Login time must not consume the Flow timeout", engine)
        self.assertIn('step == "user_action_resolved"', engine)
        self.assertIn('queue_extension_command("resume_chatgpt"', engine)
        self.assertIn('queue_extension_command("open_flow"', engine)
        self.assertIn('"focus_flow_web"', bridge)
        self.assertIn('"flow_action_kind"', bridge)
        self.assertIn('"ai_action_kind"', bridge)
        self.assertIn("current.action_button", web)
        self.assertIn("service:progress.action_service", web)

    def test_flow_upload_waits_for_real_media_and_never_repeats_a_missing_attachment(self):
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        engine = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn("let mediaReady = false", background)
        self.assertIn("attempt < 90 && !mediaReady", background)
        self.assertIn("Keep its picker open and wait for a real", background)
        self.assertIn("mediaReadyStreak >= 3", background)
        self.assertIn("if (!uploadDebug.mediaReady) return false;", flow)
        self.assertIn('if step == "prepare_incomplete":', engine)
        self.assertIn("ช่อง Prompt ยังโหลดไม่ครบ", engine)
        self.assertIn('if step == "image_upload_missing":', engine)
        self.assertIn('if step == "attachment_needs_review":', engine)
        upload_missing = engine.split('if step == "image_upload_missing":', 1)[1].split(
            'if step == "attachment_needs_review":', 1
        )[0]
        self.assertNotIn('queue_extension_command("resume_flow_workspace"', upload_missing)
        self.assertIn('queue_extension_command("resume_flow_workspace", job_id, shot_index)', engine)


if __name__ == "__main__":
    unittest.main()
