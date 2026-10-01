import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FlowApprovalOverlayErrorLogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        cls.flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8")
        cls.bridge = (ROOT / "core" / "local_bridge.py").read_text(encoding="utf-8")
        cls.main_window = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8")
        cls.web_html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        cls.web_js = (ROOT / "web_ui" / "app.js").read_text(encoding="utf-8")

    def test_credit_approval_prefers_persistent_radio(self):
        self.assertIn('[role="radio"]', self.background)
        self.assertIn("อนุมัติเสมอ|always approve|approve always", self.background)
        persistent = self.background.index("อนุมัติเสมอ|always approve|approve always")
        plain = self.background.index("อนุมัติ|approve", persistent)
        self.assertLess(persistent, plain)

    def test_finished_scene_download_is_detected_and_scoped(self):
        self.assertIn("ดาวน์โหลด(?:วิดีโอ|ฉาก)", self.background)
        self.assertIn("directSceneDownload", self.background)
        self.assertIn("watchNativeFlowDownload", self.background)
        self.assertIn("findUnambiguousFinishedFlowVideoTab", self.background)
        self.assertIn("hasFinishedVideoEditor", self.background)
        self.assertIn("recoveredFinishedResult", self.background)
        self.assertIn("flow_download_path", self.bridge)
        self.assertIn("flow_download_path", self.main_window)

    def test_native_flow_download_accepts_generated_video_cdn(self):
        watcher = self.background.split("const watchNativeFlowDownload", 1)[1].split(
            "const normaliseNativeDownload", 1
        )[0]
        self.assertIn("flowDownloadMatchesItem(pending, item)", watcher)
        matcher = self.background.split("function flowDownloadMatchesItem", 1)[1].split(
            "function flowDownloadRecordMatches", 1
        )[0]
        self.assertIn('hostname === "flow-content.google"', matcher)
        # Real matching success/failure cases run in the isolated lifecycle
        # harness, including CDN video, unrelated PDF, and spoofed hosts.
        self.assertIn(
            "Flow เตรียมไฟล์แล้ว แต่ Chrome ยังไม่เริ่มดาวน์โหลดภายใน 15 วินาที",
            watcher,
        )
        self.assertIn("const FLOW_NATIVE_DOWNLOAD_START_TIMEOUT_MS = 15000;", self.background)
        self.assertIn("FLOW_NATIVE_DOWNLOAD_START_TIMEOUT_MS", watcher)

    def test_video_edit_route_is_not_misclassified_as_a_still_image(self):
        self.assertIn("Flow now uses `/project/<id>/edit/<media-id>`", self.background)
        self.assertIn("isFinishedVideoEditor", self.flow)
        self.assertIn("พบวิดีโอเดิมและดาวน์โหลดแล้ว", self.flow)
        self.assertIn("A non-video `/edit/` route", self.flow)

    def test_flow_overlay_is_collapsed_and_has_copyable_log(self):
        self.assertIn('class="panel collapsed"', self.flow)
        self.assertIn('class="log copy-log"', self.flow)
        self.assertIn("right:14px;top:72px;bottom:auto", self.flow)
        status = self.flow.split("const setStatus = (text) => {", 1)[1].split("};", 1)[0]
        self.assertNotIn("setExpanded(true)", status)
        self.assertIn("SmartFlow AI • Google Flow Extension Log", self.flow)

    def test_program_exposes_copy_ready_failure_popup(self):
        self.assertIn('id="automation-error-modal"', self.web_html)
        self.assertIn('id="automation-error-copy"', self.web_html)
        self.assertIn("renderAutomationError", self.web_js)
        self.assertIn("_capture_automation_error_log", self.main_window)

    def test_recovered_job_clears_stale_failure_popup(self):
        self.assertIn("_clear_automation_error_log(selected_job_id)", self.main_window)
        self.assertIn("if (modal.open) modal.close();", self.web_js)


if __name__ == "__main__":
    unittest.main()
