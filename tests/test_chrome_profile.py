import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock
from core.chrome_profile import resolve_profile, launch_arguments


class ChromeProfileTests(unittest.TestCase):
    def test_extension_profile_focus_runtime_and_router(self):
        import subprocess
        result = subprocess.run(['node', str(Path(__file__).with_name('chrome_focus_357.js'))], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_connected_extension_focuses_its_own_profile_without_new_tab(self):
        from ui.main_window import MainWindow
        window = MainWindow.__new__(MainWindow)
        window.bridge = Mock()
        window._compatible_extension = lambda: ({}, {'version': 'current'})
        with patch.object(window, '_chrome_window_available', return_value=True), patch.object(window, '_open_url') as launch:
            self.assertEqual(window._activate_or_launch_chrome('https://gemini.google.com/'), 'focus_requested')
            window.bridge.queue_extension_command.assert_called_once_with('focus_browser')
            launch.assert_not_called()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def profile(self, name, disabled=False, state=1):
        folder = self.root / name
        folder.mkdir()
        entry = {'manifest': {'name': 'SmartFlow AI'}, 'disable_reasons': [1] if disabled else []}
        if state is not None:
            entry['state'] = state
        (folder / 'Secure Preferences').write_text(json.dumps({'extensions': {'settings': {'id': entry}}}), encoding='utf-8')

    def test_unique_enabled_profile_and_explicit_launch(self):
        self.profile('Default', disabled=True)
        self.profile('Profile 2', state=None)
        result = resolve_profile({}, self.root)
        self.assertEqual(result['chrome_profile_directory'], 'Profile 2')
        self.assertIn('--profile-directory=Profile 2', launch_arguments(result))

    def test_ambiguous_requires_choice_and_remembers_explicit(self):
        self.profile('Default'); self.profile('Profile 1')
        with self.assertRaisesRegex(RuntimeError, 'หลายโปรไฟล์'):
            resolve_profile({}, self.root)
        self.assertEqual(resolve_profile({'chrome_profile_directory': 'Default'}, self.root)['chrome_profile_directory'], 'Default')

    def test_missing_or_disabled_never_launches_wrong_profile(self):
        self.profile('Default', disabled=True)
        with self.assertRaises(RuntimeError):
            resolve_profile({}, self.root)
        with self.assertRaises(RuntimeError):
            resolve_profile({'chrome_profile_directory': '../Elsewhere'}, self.root)

    def test_existing_wrong_browser_does_not_prevent_bootstrap(self):
        from ui.main_window import MainWindow
        window = MainWindow.__new__(MainWindow)
        window.bridge = object()
        window._compatible_extension = lambda: ({}, None)
        with patch.object(window, '_chrome_window_available', return_value=True), patch.object(window, '_open_url') as launch:
            self.assertEqual(window._activate_or_launch_chrome('https://chatgpt.com/'), 'launched')
            self.assertEqual(window._activate_or_launch_chrome('https://chatgpt.com/'), 'launching')
            launch.assert_called_once()
