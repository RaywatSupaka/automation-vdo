"""Build preflight and payload privacy against isolated files, without bundling."""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import build_customer as builder


class CustomerBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='smartflow-build-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.ffmpeg = Path(self.temp.name) / 'media/bin'
        self.android = Path(self.temp.name) / 'android'
        self.app = Path(self.temp.name) / 'payload'
        self.extension = '0.15.398'
        for folder in builder.RESOURCE_FOLDERS:
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        self.write(self.root / 'web_ui/index.html', '<html>fixture</html>')
        self.write(self.root / 'assets/fonts/smartsubai/font.ttf', b'fixture-font')
        self.write(self.root / 'browser_extension/manifest.json', json.dumps({'version': self.extension}))
        for name in builder.BRAND_FILES:
            self.write(self.root / 'assets' / name, b'fixture-brand')
        self.write(self.root / 'assets/update-public-key.txt', base64.b64encode(b'x' * 32))
        self.write(self.root / 'launcher/CUSTOMER_README.html', 'fixture instructions')
        for name in ('ffmpeg.exe', 'ffprobe.exe', 'codec.dll'):
            self.write(self.ffmpeg / name, b'fixture-media')
        for name in ('LICENSE', 'README.txt'):
            self.write(self.ffmpeg.parent / name, 'fixture license')
        for name in builder.ANDROID_REQUIRED + ('extra.dll',):
            self.write(self.android / name, b'fixture-android')
        self.write(self.root / 'CURRENT_RELEASE.json', json.dumps({'runtime': {'extension_version': self.extension}}))
        self.write(self.root / 'core/local_bridge.py', f'REQUIRED_EXTENSION_VERSION = "{self.extension}"\n')

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else value.encode('utf-8'))

    def sources(self):
        return builder.payload_sources(self.root, self.ffmpeg, self.android)

    def payload(self):
        for name, source in self.sources().items():
            self.write(self.app / name, source.read_bytes())
        for name in ('SmartFlow AI.exe', 'SmartFlow Updater.exe', 'python311.dll', 'licenses/Fonts-OFL.txt'):
            self.write(self.app / name, b'fixture dependency')

    def preflight(self, version='0.3.0-beta.7'):
        with patch.object(builder.importlib.metadata, 'version', return_value='1.0-fixture'):
            return builder.preflight(self.root, self.ffmpeg, self.android, version)

    def test_allowlist_bundles_tools_ui_fonts_pairing_but_not_workstation_data(self):
        for name in ('workspace/job.json', 'config.json', 'assets/audio/background/private.mp3',
                     'assets/fonts/user/private.ttf', 'screenshots/private.png', 'logs/private.log'):
            self.write(self.root / name, b'not for customers')
        sources = self.sources()
        for name in ('web_ui/index.html', 'browser_extension/manifest.json', 'assets/update-public-key.txt',
                     'tools/android/adb.exe', 'tools/android/scrcpy-server', 'tools/android/extra.dll',
                     'ffmpeg/ffmpeg.exe', 'ffmpeg/ffprobe.exe', 'ffmpeg/codec.dll', 'ffmpeg/LICENSE', 'READ-ME.html'):
            self.assertIn(name, sources)
        self.assertFalse(any('private' in name or name.startswith(('workspace/', 'logs/', 'screenshots/', 'assets/audio/'))
                             or name == 'config.json' for name in sources))

    def test_missing_required_resource_or_tool_rejected_before_build(self):
        for path in (self.root / 'assets/update-public-key.txt', self.ffmpeg / 'ffprobe.exe', self.android / 'scrcpy-server'):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.unlink()
                with self.assertRaisesRegex(ValueError, 'Missing or linked build resource'):
                    self.sources()
                self.write(path, original)

    def test_user_state_inside_allowlisted_folder_rejected(self):
        self.write(self.root / 'web_ui/workspace/job.json', '{}')
        with self.assertRaisesRegex(ValueError, 'User state'):
            self.sources()

    def test_windows_case_variants_of_private_paths_are_rejected(self):
        target = self.root / 'web_ui/LoGs/private.txt'
        self.write(target, b'not for customers')
        with self.assertRaisesRegex(ValueError, 'User state'):
            self.sources()
        target.unlink()
        target.parent.rmdir()
        self.payload()
        for name in ('Config.json', 'LoGs/private.txt', 'Workspace/job.json', 'nested/MEMBERSHIP.JSON'):
            with self.subTest(name=name):
                target = self.app / name
                self.write(target, b'do not ship')
                with self.assertRaisesRegex(ValueError, 'Unsafe packaged path|Private state packaged'):
                    builder.validate_payload(self.app, self.extension)
                target.unlink()
                parent = target.parent
                while parent != self.app and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent

    def test_linked_resource_rejected(self):
        external = Path(self.temp.name) / 'external-secret.txt'
        self.write(external, b'not for customers')
        link = self.root / 'web_ui/linked.txt'
        try:
            link.symlink_to(external)
        except OSError:
            self.skipTest('Filesystem does not permit fixture symlinks')
        with self.assertRaisesRegex(ValueError, 'Linked resource'):
            self.sources()

    def test_preflight_pairs_desktop_extension_and_inventory(self):
        sources, extension, versions = self.preflight()
        self.assertEqual(extension, self.extension)
        self.assertEqual(set(versions), set(builder.PACKAGES + ('PyInstaller',)))
        self.assertEqual(set(sources), set(self.sources()))
        self.assertFalse(self.app.exists())

    def test_invalid_release_version_rejected(self):
        for version in ('../output', '', 'next', '0.3', '0.3.0-beta.7/other', '0.3.0;run'):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, 'Invalid customer version'):
                self.preflight(version)

    def test_unpaired_release_or_desktop_rejected(self):
        release = self.root / 'CURRENT_RELEASE.json'
        self.write(release, json.dumps({'runtime': {'extension_version': '0.15.1'}}))
        with self.assertRaisesRegex(ValueError, 'not paired'):
            self.preflight()
        self.write(release, json.dumps({'runtime': {'extension_version': self.extension}}))
        self.write(self.root / 'core/local_bridge.py', 'REQUIRED_EXTENSION_VERSION = "0.15.1"')
        with self.assertRaisesRegex(ValueError, 'not paired'):
            self.preflight()

    def test_wrong_size_public_key_rejected(self):
        self.write(self.root / 'assets/update-public-key.txt', base64.b64encode(b'x' * 31))
        with self.assertRaisesRegex(ValueError, 'verification key'):
            self.preflight()

    def test_payload_requires_all_dependencies_and_exact_extension(self):
        self.payload()
        builder.validate_payload(self.app, self.extension)
        probe = self.app / 'ffmpeg/ffprobe.exe'
        probe.unlink()
        with self.assertRaisesRegex(ValueError, 'Missing packaged dependency'):
            builder.validate_payload(self.app, self.extension)
        self.write(probe, b'fixture-media')
        self.write(self.app / 'browser_extension/manifest.json', '{"version":"0.15.1"}')
        with self.assertRaisesRegex(ValueError, 'Extension mismatch'):
            builder.validate_payload(self.app, self.extension)

    def test_payload_rejects_private_files_user_state_and_unapproved_audio(self):
        self.payload()
        for name in ('config.json', 'nested/adbkey', 'nested/adbkey.pub', 'nested/membership.json',
                     'private.pem', 'private.key', 'workspace/job.json', 'logs/private.txt',
                     'assets/audio/private.mp3'):
            with self.subTest(name=name):
                target = self.app / name
                self.write(target, b'do not ship')
                with self.assertRaisesRegex(ValueError, 'Unsafe packaged path|Private state packaged|Unapproved media'):
                    builder.validate_payload(self.app, self.extension)
                target.unlink()
                parent = target.parent
                while parent != self.app and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent


if __name__ == '__main__':
    unittest.main()
