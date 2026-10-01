"""Installer source contracts and real Inno compilation; never runs Setup."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'launcher/customer.iss'


class CustomerInstallerGuardTests(unittest.TestCase):
    def setUp(self):
        self.source = SCRIPT.read_text(encoding='utf-8-sig')

    def test_webview_is_a_checked_pre_copy_prerequisite_not_unchecked_run(self):
        run_section = self.source.split('[Run]', 1)[1].split('[Code]', 1)[0]
        self.assertNotIn('MicrosoftEdgeWebview2Setup', run_section)
        prepare = self.source.split('function PrepareToInstall', 1)[1]
        self.assertIn("ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe')", prepare)
        self.assertIn('ewWaitUntilTerminated, ResultCode', prepare)
        self.assertIn('if ResultCode <> 0 then begin', prepare)
        self.assertIn('if (ResultCode = 3010) or (ResultCode = 1641)', prepare)
        self.assertIn('NeedsRestart := True', prepare)
        self.assertEqual(prepare.count('if NeedsWebView() then begin'), 2)
        self.assertEqual(prepare.count('if InstallationRunning() then begin'), 2)
        self.assertIn('Flags: dontcopy noencryption', self.source)

    def test_webview_user_machine_detection_independent(self):
        detection = self.source.split('function NeedsWebView()', 1)[1].split('function InstallationRunning', 1)[0]
        self.assertIn('HasWebViewAt(HKLM32) or HasWebViewAt(HKCU)', detection)
        self.assertIn("RuntimeVersion <> '0.0.0.0'", self.source)

    def test_running_guard_uses_executable_path_and_never_terminates(self):
        detection = self.source.split('function InstallationRunning()', 1)[1].split('function PrepareToInstall', 1)[0]
        self.assertIn('Win32_Process WHERE Name="SmartFlow AI.exe"', detection)
        self.assertIn('CompareText(ExpandFileName(ExecutablePath), TargetPath) = 0', detection)
        self.assertIn('FileExists(TargetPath) and UnknownOwner', detection)
        self.assertIn("FindWindowByWindowName('SmartFlow AI — AI Clip Creator')", detection)
        for forbidden in ('taskkill', 'TerminateProcess', '.Terminate(', 'CloseWindow('):
            self.assertNotIn(forbidden, self.source)
        self.assertIn('CloseApplications=no', self.source)
        self.assertIn('RestartApplications=no', self.source)

    def test_smoke_installer_identity_and_paths_are_separate(self):
        smoke, normal = self.source.split('#ifdef SmokeTest', 1)[1].split('#endif', 1)[0].split('#else')
        fields = ('SetupAppId', 'SetupAppName', 'SetupFolder', 'SetupSuffix')
        for field in fields:
            left = re.search(r'#define ' + field + r' "([^"]*)"', smoke).group(1)
            right = re.search(r'#define ' + field + r' "([^"]*)"', normal).group(1)
            self.assertNotEqual(left, right, field)
        self.assertIn('AppId={#SetupAppId}', self.source)
        self.assertIn('DefaultDirName={localappdata}\\Programs\\{#SetupFolder}', self.source)
        self.assertIn('DefaultGroupName={#SetupAppName}', self.source)
        self.assertIn('OutputBaseFilename=SmartFlow-AI-Setup-{#ReleaseVersion}{#SetupSuffix}', self.source)
        self.assertNotIn('[UninstallDelete]', self.source)

    def test_actual_inno_compiles_customer_and_isolated_smoke_variants(self):
        compiler = ROOT / 'build/installer-tools/inno/ISCC.exe'
        if not compiler.is_file():
            compiler = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Inno Setup 6/ISCC.exe'
        bootstrap = ROOT / 'build/installer-tools/MicrosoftEdgeWebview2Setup.exe'
        if not compiler.is_file() or not bootstrap.is_file():
            self.skipTest('Inno compiler or verified build prerequisite unavailable')
        with tempfile.TemporaryDirectory(prefix='smartflow-installer-fixture-') as tmp:
            root = Path(tmp)
            app = root / 'SmartFlow AI'
            app.mkdir()
            (app / 'SmartFlow AI.exe').write_bytes(b'Fixture only; do not execute')
            (root / 'SmartFlow-Extension-fixture.zip').write_bytes(b'Fixture archive')
            for smoke in (False, True):
                with self.subTest(smoke=smoke):
                    command = [str(compiler), '/Q', '/DBuildRoot=' + str(root),
                               '/DReleaseVersion=0.0.0-test']
                    if smoke:
                        command.append('/DSmokeTest')
                    command.append(str(SCRIPT))
                    result = subprocess.run(command, capture_output=True, text=True,
                                            encoding='utf-8', errors='replace', timeout=90)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    suffix = '-SmokeTest' if smoke else ''
                    self.assertTrue((root / f'SmartFlow-AI-Setup-0.0.0-test{suffix}.exe').is_file())


if __name__ == '__main__':
    unittest.main()
