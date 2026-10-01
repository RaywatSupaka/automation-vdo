import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectReleaseContractTests(unittest.TestCase):
    def setUp(self):
        self.release = json.loads((ROOT / "CURRENT_RELEASE.json").read_text(encoding="utf-8"))
        self.manifest = json.loads((ROOT / "browser_extension" / "manifest.json").read_text(encoding="utf-8"))

    def test_runtime_version_is_synchronized(self):
        version = self.release["runtime"]["extension_version"]
        self.assertEqual(self.manifest["version"], version)
        bridge = (ROOT / "core" / "local_bridge.py").read_text(encoding="utf-8")
        self.assertIn(f'REQUIRED_EXTENSION_VERSION = "{version}"', bridge)
        self.assertIn(f"flow-{version}-", (ROOT / "browser_extension" / "flow.js").read_text(encoding="utf-8"))
        self.assertIn(f"flow-{version}-", (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8"))

    def test_current_candidate_is_not_mislabeled_as_golden(self):
        self.assertTrue(self.release["runtime"]["status"].startswith("candidate_"))
        self.assertEqual(self.release["proven_baselines"]["reproducible_golden_flow"]["extension_version"], "0.15.112")
        self.assertEqual(self.release["proven_baselines"]["verified_three_shot_0_15_231"]["extension_version"], "0.15.231")
        self.assertEqual(self.release["proven_baselines"]["modern_extension_e2e"]["extension_version"], "0.15.216")

    def test_runtime_extension_is_not_older_than_packaged_release(self):
        from tools.build_installer_one_click import paired_extension_version

        self.assertEqual(paired_extension_version(ROOT), self.manifest["version"])

    def test_codex_entrypoint_declares_authority_order(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("CURRENT_RELEASE.json", agents)
        self.assertIn("PROJECT_STATE.md", agents)
        self.assertIn("never edit or copy source back from `deliverables/`", agents)

    def test_policy_terminal_uses_truthful_local_motion_without_flow_retry(self):
        for name in ("CODEX_START_HERE.md", "EXTENSION_BLUEPRINT.md", "PROJECT_STATE.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertRegex(text, re.compile(r"local motion", re.IGNORECASE), name)
            self.assertRegex(text, re.compile(r"รูป canonical เดิม|รูปเดิม"), name)
            self.assertRegex(text, re.compile(r"ห้าม.*(?:Retry|retry|reupload|ส่ง.*ซ้ำ)"), name)
        state = (ROOT / "PROJECT_STATE.md").read_text(encoding="utf-8")
        self.assertIn("all-Flow 3 คลิปจริง", state)
        self.assertIn("นับ Flow จริงกับ local motion แยกกัน", state)

    def test_service_worker_entry_exists(self):
        worker = self.manifest["background"]["service_worker"]
        self.assertTrue((ROOT / "browser_extension" / worker).is_file())

    def test_installer_uses_canonical_folder_without_a_pinned_version(self):
        installer = (ROOT / "INSTALL_EXTENSION.bat").read_text(encoding="utf-8")
        self.assertIn("'browser_extension'", installer)
        self.assertIn("CURRENT_RELEASE.json", installer)
        self.assertIn("REQUIRED_EXTENSION_VERSION", installer)
        self.assertNotIn("deliverables", installer)
        self.assertNotRegex(installer, r"0\.15\.\d+")

    def _run_installer_validation(self, root):
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
        if not powershell:
            self.skipTest("Installer validation requires Windows PowerShell or pwsh")
        installer = (ROOT / "INSTALL_EXTENSION.bat").read_text(encoding="utf-8")
        command = re.search(r'^powershell\.exe -NoLogo -NoProfile -Command "(.*)"$', installer, re.MULTILINE)
        self.assertIsNotNone(command, "Execute the installer validation itself, not a copied implementation")
        # All actual browser and Explorer launches are intercepted in this process.
        mock_launch = "function Start-Process { param($FilePath, $ArgumentList) Write-Output ('OPEN:' + $FilePath + '|' + $ArgumentList) }; "
        return subprocess.run(
            [powershell, "-NoLogo", "-NoProfile", "-Command", mock_launch + command.group(1)],
            env={**os.environ, "SMARTFLOW_INSTALL_ROOT": str(root)},
            capture_output=True, text=True, timeout=30,
        )

    def _installer_fixture(self, root, source_version, desktop_version, release_version):
        extension = root / "browser_extension"
        extension.mkdir()
        (extension / "manifest.json").write_text(json.dumps({"version": source_version}), encoding="utf-8")
        (root / "CURRENT_RELEASE.json").write_text(
            json.dumps({"runtime": {"extension_version": release_version}}), encoding="utf-8",
        )
        (root / "core").mkdir()
        (root / "core" / "local_bridge.py").write_text(
            f'class LocalBridge:\n    REQUIRED_EXTENSION_VERSION = "{desktop_version}"\n', encoding="utf-8",
        )

    def test_installer_validates_current_source_before_opening(self):
        result = self._run_installer_validation(ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(self.manifest["version"], result.stdout)
        self.assertIn(str(ROOT / "browser_extension"), result.stdout)
        self.assertIn("OPEN:chrome.exe|chrome://extensions", result.stdout)
        self.assertNotIn("OPEN:chrome://extensions|", result.stdout)
        self.assertIn("OPEN:explorer.exe|", result.stdout)

    def test_installer_follows_future_versions_and_rejects_inconsistent_or_missing_files(self):
        cases = [
            ("next matching release", "9.8.7", "9.8.7", "9.8.7", None, True),
            ("stale extension", "9.8.6", "9.8.7", "9.8.7", None, False),
            ("stale desktop", "9.8.7", "9.8.6", "9.8.7", None, False),
            ("stale release", "9.8.7", "9.8.7", "9.8.6", None, False),
            ("missing manifest", "9.8.7", "9.8.7", "9.8.7", "browser_extension/manifest.json", False),
            ("missing bridge", "9.8.7", "9.8.7", "9.8.7", "core/local_bridge.py", False),
        ]
        for name, source, desktop, release, missing, success in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix="SmartFlow installer ") as tmp:
                root = Path(tmp)
                self._installer_fixture(root, source, desktop, release)
                if missing:
                    (root / missing).unlink()
                result = self._run_installer_validation(root)
                self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
                if success:
                    self.assertIn("SmartFlow AI Extension version: 9.8.7", result.stdout)
                    self.assertIn(str(root / "browser_extension"), result.stdout)
                    self.assertEqual(result.stdout.count("OPEN:"), 2)
                else:
                    self.assertIn("ERROR:", result.stdout)
                    self.assertNotIn("OPEN:", result.stdout)
                    self.assertNotIn("Select this folder:", result.stdout)


if __name__ == "__main__":
    unittest.main()
