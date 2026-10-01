import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExtensionReliabilitySourceTests(unittest.TestCase):
    def setUp(self):
        self.background = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8-sig")
        self.flow = (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8-sig")
        self.popup = (ROOT / "browser_extension" / "popup.js").read_text(encoding="utf-8-sig")
        self.bridge = (ROOT / "core" / "local_bridge.py").read_text(encoding="utf-8-sig")
        self.ui = (ROOT / "ui" / "main_window.py").read_text(encoding="utf-8-sig")

    def test_manifest_and_bridge_versions_match(self):
        manifest = json.loads((ROOT / "browser_extension" / "manifest.json").read_text(encoding="utf-8-sig"))
        self.assertIn(f'REQUIRED_EXTENSION_VERSION = "{manifest["version"]}"', self.bridge)

    def test_command_tick_and_debugger_are_serialized(self):
        self.assertIn("extensionTickPromise", self.background)
        self.assertIn("if (extensionTickPromise) return extensionTickPromise", self.background)
        self.assertIn("flowHelperInstallPromises", self.background)
        self.assertIn("flowGenerateInFlight", self.background)

    def test_stale_flow_tabs_cannot_report_or_monitor_another_shot(self):
        self.assertIn("flowProgressOwnership", self.background)
        self.assertIn("stale_flow_tab", self.background)
        self.assertIn('type: "IS_ACTIVE_FLOW_TAB"', self.flow)
        self.assertIn("if (!ownership?.active)", self.flow)
        self.assertIn("generationMonitorActive", self.flow)

    def test_attachment_requires_confirmed_composer_proof(self):
        self.assertIn("const imageReady = Boolean(imageAttachAttempted && promptHasAttachedMedia())", self.flow)
        self.assertNotIn("promptHasAttachedMedia() || attachDebug?.composerProof === true", self.flow)
        self.assertNotIn("attachmentLikely", self.flow)

    def test_result_detection_uses_unique_media_fingerprints(self):
        for token in ("resultFingerprints", "videoSources", "snapshot.resultCardCount >", "videoCount > Number(generationBaseline.videoCount"):
            self.assertIn(token, self.flow)

    def test_all_supported_flow_hosts_are_detected(self):
        self.assertIn("flow\\.google\\.com", self.background)
        self.assertIn("flow\\.google\\.com", self.popup)
        self.assertIn("(?:fx|flow)", self.popup)

    def test_resume_and_stop_require_registered_flow_tab(self):
        self.assertIn("no_registered_flow_tab", self.background)
        self.assertIn("flowTabForJob(jobId, shotIndex)", self.background)
        self.assertIn("pickHealthyFlowProjectTab(preferredTabs, preferredTabs)", self.background)

    def test_download_recovery_is_scoped_to_exact_job_and_shot(self):
        self.assertIn('target.parent.glob(f"{target.stem}*.mp4")', self.ui)
        self.assertNotIn('downloads.glob("*.mp4")', self.ui)

    def test_bridge_uses_long_command_lease_and_result_metadata(self):
        self.assertIn("COMMAND_LEASE_SECONDS = 180", self.bridge)
        self.assertIn('ignored_reason = "stale_flow_run"', self.bridge)
        self.assertIn('"lease_expires_at"', self.bridge)


if __name__ == "__main__":
    unittest.main()
