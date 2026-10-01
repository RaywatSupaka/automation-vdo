import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FlowManualAttachmentHandoffTests(unittest.TestCase):
    def test_current_flow_submit_button_targets_the_button_not_touch_span(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        selector = 'button[type="submit"][aria-label="เริ่มสร้าง"]'
        self.assertIn(selector, flow)
        self.assertIn(selector, background)
        generate = background.split('message?.type === "CLICK_FLOW_GENERATE"', 1)[1]
        self.assertNotIn('querySelector(".mat-mdc-button-touch-target")', generate)
        self.assertIn('method: "single_cdp_mouse_click"', generate)

    def test_manual_attachment_resumes_same_guarded_flow_without_uploading_again(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        watcher = flow.split("async function resumeAfterManualAttachment", 1)[1].split(
            "function flowAttachmentAttemptKey", 1
        )[0]
        self.assertIn("new MutationObserver(scheduleCheck)", watcher)
        self.assertIn("waitingForManualAttachment", watcher)
        self.assertIn('type: "IS_ACTIVE_FLOW_TAB"', watcher)
        self.assertIn("promptHasAttachedMedia()", watcher)
        self.assertIn("findGenerateButton()", watcher)
        self.assertIn("runAutoPrepareOnce()", watcher)
        self.assertNotIn("ATTACH_LATEST_FLOW_MEDIA", watcher)
        self.assertNotIn("OPEN_FLOW_MEDIA_UPLOAD", watcher)
        self.assertNotIn("CLICK_FLOW_GENERATE", watcher)

    def test_safe_stop_keeps_manual_handoff_alive_instead_of_discarding_request(self):
        flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        tail = flow.split('await report(step, message, {', 1)[1].split(
            "function stopGenerationMonitor", 1
        )[0]
        self.assertIn("!imageReady && promptReady && !hasRightsDialog", tail)
        self.assertIn("await watchForManualAttachment(request)", tail)
        self.assertLess(
            tail.index("await watchForManualAttachment(request)"),
            tail.index('chrome.storage.local.remove("smartpostAutoFlow")'),
        )

    def test_desktop_waiter_waits_passively_for_latched_attachment_terminal(self):
        desktop = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        waiter = desktop.split("def _wait_flow_step", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("manual_attachment_wait_started", waiter)
        self.assertIn("manual_handoff_pending", waiter)
        persistent = waiter.split('if step == "attachment_waiting_manual":', 1)[1].split(
            'if step == "attachment_needs_review":', 1
        )[0]
        self.assertIn("หยุดอย่างปลอดภัยหลังลองแนบรูปหนึ่งครั้ง", persistent)
        self.assertIn("ไม่อัปโหลดรูปซ้ำ", persistent)
        self.assertNotIn('queue_extension_command(', persistent)
        review = waiter.split('if step == "attachment_needs_review":', 1)[1].split(
            'if step == "error"', 1
        )[0]
        self.assertIn("FLOW_ATTACH_PROOF_MISSING_AFTER_SINGLE_ACTION", review)
        self.assertIn("FLOW_ATTACH_SAFE_TARGET_MISSING", review)
        self.assertIn("manual_attachment_wait_started < 75", review)
        self.assertIn("validated_attachment_failure_evidence", waiter)
        self.assertIn('step == "attachment_failed"', waiter)
        self.assertNotIn('queue_extension_command("inspect_flow"', review)


if __name__ == "__main__":
    unittest.main()
