import base64
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from core.app_updates import canonical, verify_release
from tools.sign_customer_release import make_upload_bundle


def fixture_bundle(folder):
    folder = Path(folder)
    patch = folder / "patch.zip"
    with zipfile.ZipFile(patch, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("fixture.txt", "ISOLATED TEST ONLY - NOT A CUSTOMER RELEASE")
    extension = folder / "extension.zip"
    with zipfile.ZipFile(extension, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"manifest_version": 3, "version": "0.15.415", "name": "Isolated fixture"}))
    release = {"app_id": "smartflow", "platform": "windows-x64", "version": "99.0.0-beta.1", "extension_version": "0.15.415",
               "channel": "beta", "supported_from": ["0.3.0-beta.12"]}
    for kind, file in [("patch", patch), ("extension", extension)]:
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        release[kind] = {"name": file.name, "size": file.stat().st_size, "sha256": digest,
            "url": "https://www.catfufu.com/api/smartflow-updates/files/" + digest}
    key = Ed25519PrivateKey.generate()  # Never load the real publisher key.
    envelope = {"release": release, "signature": base64.b64encode(key.sign(canonical(release))).decode()}
    public = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    bundle = make_upload_bundle(envelope, patch, folder / "admin-bundle.zip")
    return envelope, public, patch, bundle


class AdminUpdateBundleTests(unittest.TestCase):
    def test_signed_envelope_and_payload_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            envelope, public, patch, bundle = fixture_bundle(temp)
            with zipfile.ZipFile(bundle) as archive:
                self.assertEqual(archive.namelist(), ["release.json", "patch.zip"])
                self.assertTrue(all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist()))
                self.assertEqual(archive.read("patch.zip"), patch.read_bytes())
                self.assertEqual(verify_release(json.loads(archive.read("release.json")), public), envelope["release"])
            with self.assertRaises(FileExistsError): make_upload_bundle(envelope, patch, bundle)
            patch.write_bytes(b"corrupt")
            with self.assertRaises(ValueError): make_upload_bundle(envelope, patch, Path(temp) / "bad.zip")

    def test_requires_update_only_and_supported_versions(self):
        for change in [{"installer": {"name": "setup.exe"}}, {"supported_from": []}, {"supported_from": ["99.0.0"]}]:
            with tempfile.TemporaryDirectory() as temp:
                envelope, _, patch, _ = fixture_bundle(temp)
                envelope["release"].update(change)
                with self.assertRaises(ValueError): make_upload_bundle(envelope, patch, Path(temp) / "invalid.zip")

    def test_update_notification_browser_fixture(self):
        result = subprocess.run(["node", "tests/update_notifications_admin_20260922.cjs"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__": unittest.main()
