"""Offline guards for the double-click customer installer entry point."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools import build_installer_one_click as click


class OneClickBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="smartflow-one-click-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "browser_extension").mkdir()
        (self.root / "core").mkdir()
        (self.root / "deliverables").mkdir()
        (self.root / "browser_extension/manifest.json").write_text(
            json.dumps({"version": "0.15.420"}), encoding="utf-8")
        (self.root / "browser_extension/background.js").write_text("current", encoding="utf-8")
        (self.root / "core/local_bridge.py").write_text(
            'REQUIRED_EXTENSION_VERSION = "0.15.420"', encoding="utf-8")
        (self.root / "CURRENT_RELEASE.json").write_text(json.dumps({
            "runtime": {"extension_version": "0.15.420"},
            "customer_distribution": {"version": "0.3.0-beta.13"},
        }), encoding="utf-8")

    def archive(self, version, background):
        path = self.root / "deliverables" / f"SmartFlow_AI_Extension_{version}.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"version": version}))
            archive.writestr("background.js", background)
        return path

    def test_next_beta_is_derived_not_hardcoded(self):
        self.assertEqual(click.next_beta_version(self.root), "0.3.0-beta.14")
        self.assertEqual(click.paired_extension_version(self.root), "0.15.420")
        click.assert_new_customer_version(self.root, "0.3.0-beta.14")

    def test_stable_or_older_customer_version_cannot_be_built(self):
        for version in ("0.3.0", "0.3.0-beta.13", "0.3.0-beta.12", "0.2.9-beta.99"):
            with self.subTest(version=version), self.assertRaises(click.BuildGateError):
                click.assert_new_customer_version(self.root, version)
        click.assert_new_customer_version(self.root, "0.3.1-beta.1")

    def test_existing_extension_version_cannot_change_bytes(self):
        self.archive("0.15.420", "old code")
        with self.assertRaisesRegex(click.BuildGateError, "Bump the paired Extension version"):
            click.assert_extension_version_not_reused(self.root, "0.15.420")

    def test_new_extension_version_can_proceed_and_old_version_is_untouched(self):
        self.archive("0.15.419", "old code")
        click.assert_extension_version_not_reused(self.root, "0.15.420")
        self.assertTrue((self.root / "deliverables/SmartFlow_AI_Extension_0.15.419.zip").is_file())

    def test_frozen_folder_mismatch_also_blocks_build(self):
        folder = self.root / "deliverables/SmartFlow_AI_Extension_0.15.420"
        folder.mkdir()
        (folder / "manifest.json").write_text('{"version":"0.15.420"}', encoding="utf-8")
        (folder / "background.js").write_text("old code", encoding="utf-8")
        with self.assertRaisesRegex(click.BuildGateError, "Bump the paired Extension version"):
            click.assert_extension_version_not_reused(self.root, "0.15.420")

    def test_version_pair_mismatch_blocks_build(self):
        (self.root / "core/local_bridge.py").write_text(
            'REQUIRED_EXTENSION_VERSION = "0.15.419"', encoding="utf-8")
        with self.assertRaisesRegex(click.BuildGateError, "different versions"):
            click.paired_extension_version(self.root)

    def packaged(self, root, kind, version, manifest=None):
        deliverables = root / "deliverables"
        deliverables.mkdir(parents=True, exist_ok=True)
        value = {"version": version} if manifest is None else manifest
        if kind == "folder":
            artifact = deliverables / f"SmartFlow_AI_Extension_{version}"
            artifact.mkdir()
            (artifact / "manifest.json").write_text(json.dumps(value), encoding="utf-8")
        else:
            if kind == "customer":
                deliverables = deliverables / "customer-0.3.0-beta.99"
                deliverables.mkdir()
                name = f"SmartFlow-Extension-{version}.zip"
            else:
                name = f"SmartFlow_AI_Extension_{version}.zip"
            artifact = deliverables / name
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("manifest.json", json.dumps(value))
        return artifact

    def snapshot(self, root):
        return {p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                if p.is_file() else None for p in root.rglob("*")}

    def test_paired_version_rejects_a_newer_packaged_extension_without_writes(self):
        self.packaged(self.root, "zip", "0.15.456")
        before = self.snapshot(self.root)
        with self.assertRaisesRegex(click.BuildGateError, "0.15.420 is older than packaged 0.15.456"):
            click.paired_extension_version(self.root)
        self.assertEqual(self.snapshot(self.root), before)

    def test_all_artifact_kinds_use_numeric_versions_and_allow_same_or_older(self):
        cases = [("0.15.9", "0.15.10", False), ("0.15.10", "0.15.9", True),
                 ("0.15.10", "0.15.10", True), ("0.9.99", "0.10.0", False),
                 ("9.99.99", "10.0.0", False)]
        for kind in ("folder", "zip", "customer"):
            for current, packaged, allowed in cases:
                with self.subTest(kind=kind, current=current, packaged=packaged):
                    root = self.root / f"{kind}-{current}-{packaged}"
                    self.packaged(root, kind, packaged)
                    before = self.snapshot(root)
                    if allowed:
                        click.assert_extension_not_older_than_packaged(root, current)
                    else:
                        with self.assertRaisesRegex(click.BuildGateError, "older than packaged"):
                            click.assert_extension_not_older_than_packaged(root, current)
                    self.assertEqual(self.snapshot(root), before)

    def test_exact_artifact_bad_or_mismatched_manifest_fails_closed(self):
        for kind in ("folder", "zip", "customer"):
            for label, manifest in (("mismatch", {"version": "0.15.419"}),
                                    ("invalid-version", {"version": "not-a-version"}),
                                    ("missing-version", {}), ("non-object", []),
                                    ("non-string", {"version": 456})):
                with self.subTest(kind=kind, label=label):
                    root = self.root / f"bad-{kind}-{label}"
                    artifact = self.packaged(root, kind, "0.15.456", manifest)
                    before = self.snapshot(root)
                    with self.assertRaisesRegex(click.BuildGateError, "Cannot verify Extension artifact") as error:
                        click.assert_extension_not_older_than_packaged(root, "0.15.420")
                    self.assertIn(str(artifact), str(error.exception))
                    self.assertEqual(self.snapshot(root), before)

    def test_unreadable_exact_artifacts_do_not_disappear_from_downgrade_check(self):
        for kind in ("folder", "zip", "customer"):
            for defect in ("missing", "invalid-json", "invalid-utf8", "corrupt"):
                with self.subTest(kind=kind, defect=defect):
                    root = self.root / f"unreadable-{kind}-{defect}"
                    artifact = self.packaged(root, kind, "0.15.456")
                    data = b"\xff" if defect == "invalid-utf8" else b"not json"
                    if kind == "folder":
                        manifest = artifact / "manifest.json"
                        if defect == "missing":
                            manifest.unlink()
                        else:
                            manifest.write_bytes(data)
                    elif defect == "corrupt":
                        artifact.write_bytes(b"not a zip")
                    else:
                        with zipfile.ZipFile(artifact, "w") as archive:
                            archive.writestr("other.json" if defect == "missing" else "manifest.json", data)
                    before = self.snapshot(root)
                    with self.assertRaisesRegex(click.BuildGateError, "Cannot verify Extension artifact"):
                        click.assert_extension_not_older_than_packaged(root, "0.15.420")
                    self.assertEqual(self.snapshot(root), before)

    def test_unrelated_backup_names_are_not_release_authority(self):
        deliverables = self.root / "deliverables"
        for name in ("SmartFlow_AI_Extension_99.0.0.zip.bak", "SmartFlow_AI_Extension_99.0.0-preview",
                     "SmartFlow_AI_Extension_notes.zip", "other-extension-99.0.0.zip"):
            (deliverables / name).write_bytes(b"not a release")
        before = self.snapshot(self.root)
        self.assertEqual(click.paired_extension_version(self.root), "0.15.420")
        self.assertEqual(self.snapshot(self.root), before)

    def test_older_legacy_zip_is_not_read_but_newer_legacy_zip_fails_closed(self):
        older = self.root / "deliverables/SmartFlow_AI_Extension_0.15.419.zip"
        with zipfile.ZipFile(older, "w") as archive:
            archive.writestr("SmartFlow_AI_Extension_0.15.419/manifest.json", '{"version":"0.15.419"}')
        before = self.snapshot(self.root)
        with patch.object(click.zipfile, "ZipFile", side_effect=AssertionError("Older ZIP must not be opened")):
            self.assertEqual(click.paired_extension_version(self.root), "0.15.420")
        self.assertEqual(self.snapshot(self.root), before)
        newer = self.root / "deliverables/SmartFlow_AI_Extension_0.15.421.zip"
        with zipfile.ZipFile(newer, "w") as archive:
            archive.writestr("SmartFlow_AI_Extension_0.15.421/manifest.json", '{"version":"0.15.421"}')
        before = self.snapshot(self.root)
        with self.assertRaisesRegex(click.BuildGateError, "Cannot verify Extension artifact"):
            click.paired_extension_version(self.root)
        self.assertEqual(self.snapshot(self.root), before)

    def test_invalid_canonical_version_and_duplicate_manifest_are_rejected(self):
        with self.assertRaisesRegex(click.BuildGateError, "Invalid canonical Extension version"):
            click.assert_extension_not_older_than_packaged(self.root, "not-a-version")
        path = self.root / "deliverables/SmartFlow_AI_Extension_0.15.456.zip"
        with zipfile.ZipFile(path, "w") as archive, self.assertWarns(UserWarning):
            archive.writestr("manifest.json", '{"version":"0.15.456"}')
            archive.writestr("manifest.json", '{"version":"0.15.456"}')
        before = self.snapshot(self.root)
        with self.assertRaisesRegex(click.BuildGateError, "Cannot verify Extension artifact"):
            click.assert_extension_not_older_than_packaged(self.root, "0.15.420")
        self.assertEqual(self.snapshot(self.root), before)

    def test_payload_and_extension_hash_are_checked_before_setup_compile(self):
        output = self.root / "deliverables/customer-0.3.0-beta.14"
        app = output / "SmartFlow AI"
        app.mkdir(parents=True)
        binary = app / "SmartFlow AI.exe"
        binary.write_bytes(b"fixture-program")
        extension = output / "SmartFlow-Extension-0.15.420.zip"
        with zipfile.ZipFile(extension, "w") as archive:
            for name, source in click.extension_sources(self.root).items():
                archive.write(source, name)
        (output / "BUILD.json").write_text(json.dumps({
            "version": "0.3.0-beta.14", "extension_version": "0.15.420",
            "extension_sha256": click.sha256(extension),
        }), encoding="utf-8")
        (output / "PAYLOAD.json").write_text(json.dumps({
            "SmartFlow AI.exe": {"size": binary.stat().st_size, "sha256": click.sha256(binary)},
        }), encoding="utf-8")
        with patch.object(click, "ROOT", self.root):
            self.assertEqual(click.verify_payload(output, "0.3.0-beta.14", "0.15.420"), 1)
            binary.write_bytes(b"corrupt")
            with self.assertRaisesRegex(click.BuildGateError, "Payload hash mismatch"):
                click.verify_payload(output, "0.3.0-beta.14", "0.15.420")

    def test_source_fingerprint_change_after_build_blocks_setup(self):
        output = self.root / "deliverables/customer-0.3.0-beta.14"
        output.mkdir()
        source = self.root / "core/local_bridge.py"
        ffmpeg_bin = self.root / "media/bin"
        ffmpeg_bin.mkdir(parents=True)
        (ffmpeg_bin.parent / "LICENSE").write_text("fixture-license", encoding="utf-8")
        android = self.root / "android"
        android.mkdir()
        (android / "adb.exe").write_bytes(b"fixture-adb")
        (self.root / "launcher").mkdir()
        (self.root / "launcher/CUSTOMER_README.html").write_text("fixture-readme", encoding="utf-8")
        (output / "BUILD.json").write_text(json.dumps({
            "source_sha256": {
                "core/local_bridge.py": click.sha256(source),
                "ffmpeg/LICENSE": click.sha256(ffmpeg_bin.parent / "LICENSE"),
                "tools/android/adb.exe": click.sha256(android / "adb.exe"),
                "READ-ME.html": click.sha256(self.root / "launcher/CUSTOMER_README.html"),
            },
        }), encoding="utf-8")
        click.verify_build_sources(output, self.root, ffmpeg_bin, android)
        source.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(click.BuildGateError, "Build input changed"):
            click.verify_build_sources(output, self.root, ffmpeg_bin, android)


if __name__ == "__main__":
    unittest.main()
