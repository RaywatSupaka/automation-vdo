import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.bridge_diagnostics import safe_ai_send_diagnostics
from core.local_bridge import LocalBridge
from tools.verify_pair_contract import PairContractError, verify_source_pair
from ui.main_window import MainWindow, STORY_VIDEO_MODES, VIDEO_RESOLUTIONS
from ui.state_rules import credit_state, story_video_mode_key, video_render_settings


ROOT = Path(__file__).resolve().parents[1]
PAIR_FILES = (
    "CURRENT_RELEASE.json", "browser_extension/manifest.json",
    "browser_extension/background.js", "browser_extension/flow.js",
    "core/local_bridge.py", "launcher/SmartFlowLauncher.cs",
)


class LowImpactRefactorTests(unittest.TestCase):
    def test_ui_wrappers_keep_the_same_values(self):
        for label in ("Google Flow ทุกฉาก", "ภาพเคลื่อนไหวอัตโนมัติ", "unknown"):
            self.assertEqual(MainWindow._story_video_mode_key(label),
                             story_video_mode_key(label, modes=STORY_VIDEO_MODES))
        self.assertEqual(MainWindow._credit_state(True, "ready", credits=5),
                         credit_state(True, "ready", credits=5))

    def test_bridge_wrapper_filters_private_values(self):
        payload = {"detail": {"gesture_phase": "not_started", "prompt": "SECRET",
                              "preflight_reason": "chatgpt_image_tool"}}
        expected = {"gesture_phase": "not_started", "preflight_reason": "chatgpt_image_tool"}
        self.assertEqual(safe_ai_send_diagnostics(payload), expected)
        self.assertEqual(LocalBridge._safe_ai_send_diagnostics(payload), expected)

    def test_render_settings_wrapper_preserves_limits(self):
        config = {"video_resolution": "unknown", "video_fps": 999, "video_quality": "maximum",
                  "video_motion_strength": 3, "video_transition_sec": -1}
        window = MainWindow.__new__(MainWindow)
        window.cfg = config
        expected = video_render_settings(config, VIDEO_RESOLUTIONS)
        self.assertEqual(window._video_render_settings(), expected)
        self.assertEqual((expected["width"], expected["height"], expected["fps"], expected["crf"]),
                         (720, 1280, 30, 16))
        self.assertEqual((expected["motion_strength"], expected["transition_sec"]), (1.5, 0.0))

    def test_pair_preflight_rejects_helper_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in PAIR_FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, target)
            version = json.loads((ROOT / "browser_extension/manifest.json").read_text(encoding="utf-8"))["version"]
            self.assertEqual(verify_source_pair(root)["version"], version)
            flow = root / "browser_extension/flow.js"
            flow.write_text(flow.read_text(encoding="utf-8").replace(f"flow-{version}-", "flow-0.0.0-"), encoding="utf-8")
            with self.assertRaisesRegex(PairContractError, "helper mismatch"):
                verify_source_pair(root)
            tools = root / "tools"
            tools.mkdir()
            for name in ("verify_pair_contract.py", "package_current_extension.py"):
                shutil.copy2(ROOT / "tools" / name, tools / name)
            result = subprocess.run([sys.executable, str(tools / "package_current_extension.py")],
                                    cwd=root, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "deliverables").exists())


if __name__ == "__main__":
    unittest.main()
