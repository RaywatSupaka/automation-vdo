import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from core import config as config_module
from core.atomic_json import JsonPersistenceError
from core.customer_runtime import DEFAULTS


class ConfigDefaultsTests(unittest.TestCase):
    def test_clean_source_checkout_loads_safe_defaults_without_creating_user_file(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(config_module, "ROOT", Path(temporary)):
            loaded = config_module.load_config()
            self.assertEqual(loaded["bridge_port"], DEFAULTS["bridge_port"])
            self.assertEqual(loaded["video_resolution"], "720x1280")
            self.assertEqual(loaded["video_fps"], 30)
            self.assertEqual(loaded["logo_file"], str(Path(temporary) / "assets/smartflow_logo.png"))
            self.assertEqual(loaded["adb_path"], Path(temporary) / DEFAULTS["adb_path"])
            self.assertFalse((Path(temporary) / "config.json").exists())

    def test_clean_source_checkout_reaches_hybrid_startup(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(config_module, "ROOT", Path(temporary)):
            with patch("sys.argv", ["app.py"]), patch("desktop.hybrid.run_hybrid", return_value=True) as run_hybrid:
                app.main()
            run_hybrid.assert_called_once_with(page="dashboard", port=DEFAULTS["bridge_port"])
            self.assertFalse((Path(temporary) / "config.json").exists())

    def test_first_settings_save_creates_config_without_user_secrets(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(config_module, "ROOT", Path(temporary)):
            config_module.save_video_settings({"video_fps": 24})
            saved = json.loads((Path(temporary) / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["video_fps"], 24)
            self.assertEqual(saved["bridge_port"], DEFAULTS["bridge_port"])
            self.assertNotIn("api_key", saved)

    def test_existing_values_survive_missing_default_keys_and_save(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(config_module, "ROOT", Path(temporary)):
            path = Path(temporary) / "config.json"
            path.write_text('{"bridge_port": 9988, "custom_user_option": "keep"}', encoding="utf-8")
            self.assertEqual(config_module.load_config()["bridge_port"], 9988)
            config_module.save_video_settings({"video_fps": 24})
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["custom_user_option"], "keep")
            self.assertEqual(saved["bridge_port"], 9988)
            self.assertEqual(config_module.load_config()["video_fps"], 24)

    def test_corrupt_existing_config_is_not_replaced_by_defaults(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(config_module, "ROOT", Path(temporary)):
            path = Path(temporary) / "config.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(JsonPersistenceError):
                config_module.load_config()
            with self.assertRaises(JsonPersistenceError):
                config_module.save_video_settings({"video_fps": 24})
            self.assertEqual(path.read_text(encoding="utf-8"), "{broken")


if __name__ == "__main__":
    unittest.main()
