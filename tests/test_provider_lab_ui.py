"""DEV-only embedded ChatGPT page and native bridge contract."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.embedded_provider import bounds_from_css
from desktop.update_api import UpdateApi


ROOT = Path(__file__).resolve().parents[1]


class ProviderLabUiTests(unittest.TestCase):
    def test_unavailable_outside_dev_mode(self):
        api = UpdateApi(None)
        with patch.dict(os.environ, {"SMARTFLOW_DEV_BYPASS_MEMBERSHIP": "0"}):
            self.assertFalse(api.provider_lab_available())
            self.assertFalse(api.provider_lab_show({})["ok"])

    def test_native_show_reuses_child_and_hides(self):
        api = UpdateApi(object())
        api._window = object()
        rect = {"left": 1, "top": 2, "width": 3, "height": 4,
                "viewport_width": 100, "viewport_height": 100}
        with patch.object(api, "provider_lab_available", return_value=True), \
                patch("desktop.embedded_provider.EmbeddedProvider") as child:
            self.assertEqual(api.provider_lab_show(rect), child.return_value.show.return_value)
            api.provider_lab_show(rect)
            child.assert_called_once_with(api._window)
            self.assertEqual(api.provider_lab_hide(), child.return_value.hide.return_value)

    def test_css_bounds_scale_and_clip(self):
        rect = {"left": 20, "top": 10, "width": 80, "height": 70,
                "viewport_width": 100, "viewport_height": 100}
        self.assertEqual(bounds_from_css(rect, 200, 150), (40, 15, 160, 105))
        rect["left"] = -20
        self.assertEqual(bounds_from_css(rect, 200, 150), (0, 15, 120, 105))
        rect["width"] = float("nan")
        with self.assertRaises(ValueError):
            bounds_from_css(rect, 200, 150)

    def test_menu_and_provider_control_are_isolated(self):
        html = (ROOT / "web_ui" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web_ui" / "provider_lab.js").read_text(encoding="utf-8")
        child = (ROOT / "desktop" / "embedded_provider.py").read_text(encoding="utf-8")
        self.assertIn('id="ai-chat-nav" data-page="ai-chat"', html)
        self.assertIn('id="ai-chat-host"', html)
        self.assertIn("provider_lab_show(bounds)", script)
        self.assertIn("provider_lab_hide()", script)
        self.assertNotIn("open_provider_lab", script)
        self.assertIn("form.Controls.Add(control)", child)
        self.assertNotIn("js_api=", child)
        self.assertNotIn("WebMessageReceived", child)


if __name__ == "__main__":
    unittest.main()
