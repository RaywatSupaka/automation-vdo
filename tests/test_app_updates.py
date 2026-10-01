import base64
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from core.app_updates import canonical, safe_patch_name, safe_url, verify_release, version
from tools.customer_updater import apply_patch, rollback, validate_archive


class AppUpdateTests(unittest.TestCase):
    def test_versions(self):
        self.assertLess(version("0.3.0-beta.1"), version("0.3.0-beta.2"))
        self.assertLess(version("0.3.0-beta.9"), version("0.3.0"))

    def test_signature_and_identity(self):
        key = Ed25519PrivateKey.generate()
        public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
        release = {"app_id": "smartflow", "channel": "beta", "version": "0.3.0-beta.1", "extension_version": "0.15.276", "platform": "windows-x64"}
        envelope = {"release": release, "signature": base64.b64encode(key.sign(canonical(release))).decode()}
        self.assertEqual(verify_release(envelope, public), release)
        release["version"] = "9.0.0"
        with self.assertRaises(Exception):
            verify_release(envelope, public)

    def test_unsafe_paths_and_urls(self):
        for path in ("../evil", "/evil", "C:/evil", "foo\\bar", "config.json", "workspace/job", "foo/NUL.txt", "foo/../x", "foo. /x"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_patch_name(path)
        for url in ("http://www.catfufu.com/api/smartflow-updates/files/a", "https://evil.com/api/smartflow-updates/a", "https://www.catfufu.com/admin3s/", "https://user@www.catfufu.com/api/smartflow-updates/a"):
            with self.assertRaises(ValueError):
                safe_url(url)

    def test_patch_and_exact_rollback_preserve_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, backup = Path(tmp) / "app", Path(tmp) / "backup"
            root.mkdir()
            old = {"app_id": "smartflow", "version": "0.3.0-beta.1", "extension_version": "0.15.276"}
            new = dict(old, version="0.3.0-beta.2")
            (root / "customer-release.json").write_text(json.dumps(old))
            (root / "SmartFlow AI.exe").write_bytes(b"old")
            (root / "workspace").mkdir()
            (root / "workspace/job").write_bytes(b"keep")
            patch = Path(tmp) / "patch.zip"
            with zipfile.ZipFile(patch, "w") as archive:
                archive.writestr("SmartFlow AI.exe", b"new")
                archive.writestr("customer-release.json", json.dumps(new))
                archive.writestr("new.dll", b"new")
            release = dict(new, supported_from=[old["version"]], patch={"size": patch.stat().st_size, "sha256": hashlib.sha256(patch.read_bytes()).hexdigest()})
            apply_patch(root, patch, release, backup)
            self.assertEqual((root / "SmartFlow AI.exe").read_bytes(), b"new")
            rollback(root, backup)
            self.assertEqual((root / "SmartFlow AI.exe").read_bytes(), b"old")
            self.assertFalse((root / "new.dll").exists())
            self.assertEqual((root / "workspace/job").read_bytes(), b"keep")

    def test_duplicate_entries_rejected(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("SmartFlow AI.exe", "a")
            archive.writestr("SMARTFLOW AI.EXE", "b")
        with zipfile.ZipFile(data) as archive, self.assertRaises(ValueError):
            validate_archive(archive)
