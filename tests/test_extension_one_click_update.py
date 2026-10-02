"""Isolated Extension update tests; no Chrome profile or live jobs are changed."""
import hashlib
import json
import logging
import tempfile
import types
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from core.extension_updater import installed_extension_id, install_archive, verify_bundled_package
from desktop.update_api import UpdateApi
from core.local_bridge import LocalBridge
from core.product_manager import ProductManager


class ExtensionOneClickUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local = self.root / "local"
        self.folder = self.local / "SmartFlowAI/data/browser_extension"
        self.folder.mkdir(parents=True)
        (self.folder / "manifest.json").write_text(json.dumps({"name": "SmartFlow AI", "version": "0.15.485"}), encoding="utf-8")
        (self.folder / "background.js").write_text("old", encoding="utf-8")
        self.chrome = self.root / "chrome"
        profile = self.chrome / "Default"
        profile.mkdir(parents=True)
        self.ident = "a" * 32
        (profile / "Preferences").write_text(json.dumps({"extensions": {"settings": {
            self.ident: {"path": str(self.folder), "state": 1, "manifest": {"name": "SmartFlow AI"}}
        }}}), encoding="utf-8")
        (self.folder.parent / "config.json").write_text(json.dumps({"chrome_user_data_dir": str(self.chrome)}), encoding="utf-8")
        self.archive = self.root / "extension.zip"
        with zipfile.ZipFile(self.archive, "w") as packed:
            packed.writestr("manifest.json", json.dumps({"manifest_version": 3, "name": "SmartFlow AI", "version": "0.15.486"}))
            packed.writestr("background.js", "new")
        bundled = self.root / "app/browser_extension"
        bundled.mkdir(parents=True)
        with zipfile.ZipFile(self.archive) as packed:
            for name in ("manifest.json", "background.js"):
                (bundled / name).write_bytes(packed.read(name))

    def test_swap_keeps_exact_loaded_path_and_recoverable_previous_files(self):
        self.assertEqual(installed_extension_id(self.folder, self.chrome), self.ident)
        backup = install_archive(self.archive, self.folder, "0.15.486")
        self.assertEqual((self.folder / "background.js").read_text(), "new")
        self.assertEqual((backup / "background.js").read_text(), "old")
        self.assertEqual(installed_extension_id(self.folder, self.chrome), self.ident)

    def test_wrong_folder_or_unsafe_zip_never_changes_installed_files(self):
        with self.assertRaises(ValueError):
            installed_extension_id(self.folder / "other", self.chrome)
        with zipfile.ZipFile(self.archive, "w") as packed:
            packed.writestr("../escape", "bad")
            packed.writestr("manifest.json", "{}")
        with self.assertRaises(ValueError):
            install_archive(self.archive, self.folder, "0.15.486")
        self.assertEqual((self.folder / "background.js").read_text(), "old")
        self.assertFalse((self.root / "escape").exists())

    def test_ambiguous_chrome_profiles_are_rejected(self):
        second = self.chrome / "Profile 1"
        second.mkdir()
        (second / "Preferences").write_text(json.dumps({"extensions": {"settings": {
            self.ident: {"path": str(self.folder), "state": 1, "manifest": {"name": "SmartFlow AI"}}
        }}}), encoding="utf-8")
        with self.assertRaises(ValueError):
            installed_extension_id(self.folder, self.chrome)
        self.assertEqual(installed_extension_id(self.folder, self.chrome, "Default"), self.ident)

    def test_signed_package_must_match_the_bundled_pair(self):
        bundled = self.root / "app/browser_extension"
        verify_bundled_package(self.archive, bundled)
        (bundled / "background.js").write_text("other", encoding="utf-8")
        with self.assertRaises(ValueError):
            verify_bundled_package(self.archive, bundled)
        self.assertEqual((self.folder / "background.js").read_text(), "old")

    def test_native_button_checks_release_idle_and_identity_before_reload(self):
        asset = {"size": self.archive.stat().st_size,
                 "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest()}
        release = {"extension_version": "0.15.486", "extension": asset}
        api = UpdateApi(types.SimpleNamespace(base_url="http://127.0.0.1:0"))
        api._envelope = {"release": release}
        api._downloaded["extension"] = self.archive
        api._read_local = Mock(side_effect=lambda path: (
            {"extension_version_required": "0.15.486"} if path == "/health" else
            {"clients": [{"client_id": self.ident}]}))
        api._update_barrier = Mock(side_effect=[{"ok": True, "nonce": "fixture-nonce"}, {"ok": True}])
        api._desktop_update_action = Mock(return_value={"ok": True})
        with patch("desktop.update_api.verify_release", return_value=release), \
                patch("desktop.update_api.RESOURCE_ROOT", self.root / "app"), \
                patch("sys.frozen", True, create=True), \
                patch.dict("os.environ", {"LOCALAPPDATA": str(self.local)}):
            result = api.update_install_extension()
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["reload_requested"])
        self.assertEqual((self.folder / "background.js").read_text(), "new")
        self.assertEqual(api._update_barrier.call_args_list[-1].args[0],
                         {"cancel": True, "nonce": "fixture-nonce"})
        api._desktop_update_action.assert_called_once_with("reload_extension_after_update", {
            "nonce": "fixture-nonce", "client_id": self.ident, "target_version": "0.15.486"})

    def test_busy_barrier_prevents_file_changes(self):
        asset = {"size": self.archive.stat().st_size,
                 "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest()}
        release = {"extension_version": "0.15.486", "extension": asset}
        api = UpdateApi(types.SimpleNamespace(base_url="http://127.0.0.1:0"))
        api._envelope = {"release": release}
        api._downloaded["extension"] = self.archive
        api._read_local = Mock(side_effect=lambda path: (
            {"extension_version_required": "0.15.486"} if path == "/health" else
            {"clients": [{"client_id": self.ident}]}))
        api._update_barrier = Mock(return_value={"ok": False, "error": "งานกำลังทำอยู่"})
        with patch("desktop.update_api.verify_release", return_value=release), \
                patch("desktop.update_api.RESOURCE_ROOT", self.root / "app"), \
                patch("sys.frozen", True, create=True), \
                patch.dict("os.environ", {"LOCALAPPDATA": str(self.local)}):
            reply = api.update_install_extension()
        self.assertFalse(reply["ok"])
        self.assertIn("งานกำลังทำ", reply["error"])
        self.assertEqual((self.folder / "background.js").read_text(), "old")

    def test_bridge_delivers_reload_only_once_to_the_paired_worker(self):
        bridge = LocalBridge("127.0.0.1", 0, ProductManager(self.root), logging.getLogger("extension-update-test")).start()
        self.addCleanup(bridge.stop)
        url = f"http://127.0.0.1:{bridge.server.server_address[1]}/api/extension/heartbeat"
        def heartbeat(version="0.15.485", protocol=1):
            request = urllib.request.Request(url, data=json.dumps({
                "client_id": self.ident, "version": version, "extension_update_protocol": protocol
            }).encode(), headers={"Content-Type": "application/json", "Origin": "chrome-extension://" + self.ident})
            with urllib.request.urlopen(request, timeout=3) as response:
                return json.load(response)
        with patch.object(bridge._extension_identity, "allowed", return_value=True):
            self.assertIsNone(heartbeat().get("extension_reload_request"))
            bridge.request_extension_reload(self.ident, bridge.REQUIRED_EXTENSION_VERSION)
            request = heartbeat()["extension_reload_request"]
            self.assertEqual(request["target_version"], bridge.REQUIRED_EXTENSION_VERSION)
            self.assertIsNone(heartbeat().get("extension_reload_request"))
            self.assertIsNone(heartbeat(bridge.REQUIRED_EXTENSION_VERSION).get("extension_reload_request"))
            with self.assertRaises(ValueError):
                bridge.request_extension_reload("b" * 32, bridge.REQUIRED_EXTENSION_VERSION)
            heartbeat("0.15.485", protocol=0)
            with self.assertRaises(ValueError):
                bridge.request_extension_reload(self.ident, bridge.REQUIRED_EXTENSION_VERSION)


if __name__ == "__main__":
    unittest.main()
