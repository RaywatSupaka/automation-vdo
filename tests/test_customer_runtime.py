import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.customer_runtime import DEFAULTS, prepare_customer_root, resolve_customer_tools


class CustomerRuntimeTests(unittest.TestCase):
    def test_source_checkout_unchanged(self):
        with patch("sys.frozen", False, create=True):
            self.assertEqual(prepare_customer_root("example"), Path("example"))

    def test_clean_customer_and_preserved_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, state = Path(tmp) / "package", Path(tmp) / "state"
            (source / "web_ui").mkdir(parents=True)
            (source / "web_ui/index.html").write_text("ui")
            (source / "browser_extension").mkdir()
            (source / "browser_extension/manifest.json").write_text('{"version":"0.15.276"}')
            (source / "assets/fonts/user").mkdir(parents=True)
            (source / "assets/fonts/user/private.ttf").write_text("private")
            with patch("sys.frozen", True, create=True), patch.dict("os.environ", {"SMARTFLOW_TEST_DATA_ROOT": str(state)}):
                self.assertEqual(prepare_customer_root(source), state)
                config = json.loads((state / "config.json").read_text())
                self.assertEqual(config["bridge_port"], 19065)
                self.assertEqual(Path(config['adb_path']),source/'tools/android/adb.exe')
                self.assertEqual(Path(config['scrcpy_path']),source/'tools/android/scrcpy.exe')
                self.assertTrue((state/'screenshots').is_dir())
                self.assertFalse((state / "assets/fonts/user/private.ttf").exists())
                self.assertTrue((state / "browser_extension/manifest.json").is_file())
                (state / "browser_extension/manifest.json").write_text('keep-loaded-extension')
                (state / "config.json").write_text('{"user": true}')
                (state / "workspace").mkdir(exist_ok=True)
                (state / "workspace/job.json").write_text("job")
                prepare_customer_root(source)
                self.assertEqual((state / "config.json").read_text(), '{"user": true}')
                self.assertEqual((state / "workspace/job.json").read_text(), "job")
                self.assertEqual((state / "browser_extension/manifest.json").read_text(), 'keep-loaded-extension')

    def test_defaults_have_no_credentials_or_personal_paths(self):
        for key, value in DEFAULTS.items():
            self.assertNotIn("token", key)
            self.assertNotIn("api_key", key)
            self.assertNotIn("keera", str(value))

    def test_bundled_audio_seeds_and_preserves_customer_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, state = Path(tmp) / "package", Path(tmp) / "state"
            for kind, name in (("background", "เพลง.mp3"), ("sfx", "ป๊อบ.MP3")):
                folder = source / "assets/audio" / kind
                folder.mkdir(parents=True)
                (folder / name).write_bytes(b"bundled-audio")
                (folder / "private.json").write_text("do not seed")
            with patch("sys.frozen", True, create=True), patch.dict("os.environ", {"SMARTFLOW_TEST_DATA_ROOT": str(state)}):
                prepare_customer_root(source)
                self.assertEqual((state / "assets/audio/background/เพลง.mp3").read_bytes(), b"bundled-audio")
                self.assertEqual((state / "assets/audio/sfx/ป๊อบ.MP3").read_bytes(), b"bundled-audio")
                self.assertFalse((state / "assets/audio/sfx/private.json").exists())
                (state / "assets/audio/background/เพลง.mp3").write_bytes(b"customer-edited")
                (state / "assets/audio/sfx/my.wav").write_bytes(b"customer-added")
                (source / "assets/audio/sfx/new.wav").write_bytes(b"new-bundled")
                prepare_customer_root(source)
                self.assertEqual((state / "assets/audio/background/เพลง.mp3").read_bytes(), b"customer-edited")
                self.assertEqual((state / "assets/audio/sfx/my.wav").read_bytes(), b"customer-added")
                self.assertEqual((state / "assets/audio/sfx/new.wav").read_bytes(), b"new-bundled")

    def test_frozen_legacy_android_defaults_use_bundled_tools_without_saving_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'tools/android').mkdir(parents=True)
            for name in ['adb.exe','scrcpy.exe']:
                (root/'tools/android'/name).write_bytes(b'fixture')
            original={'adb_path':'tools/adb/adb.exe','scrcpy_path':'tools/scrcpy/scrcpy.exe'}
            with patch('sys.frozen',True,create=True):
                resolved=resolve_customer_tools(original,root)
                self.assertEqual(Path(resolved['adb_path']),root/'tools/android/adb.exe')
                self.assertEqual(Path(resolved['scrcpy_path']),root/'tools/android/scrcpy.exe')
            self.assertEqual(original['adb_path'],'tools/adb/adb.exe')

    def test_custom_tool_paths_and_source_mode_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);custom=root/'custom-adb.exe';custom.write_bytes(b'custom')
            original={'adb_path':str(custom),'scrcpy_path':'my-tools/scrcpy.exe'}
            with patch('sys.frozen',True,create=True):
                self.assertEqual(resolve_customer_tools(original,root),original)
            with patch('sys.frozen',False,create=True):
                self.assertIs(resolve_customer_tools(original,root),original)
