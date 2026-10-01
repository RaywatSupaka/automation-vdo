"""Offline actual-source extension identity regression; no user browser or bridge."""
import json
import subprocess
import unittest
from pathlib import Path

from core.cancellable_process import hidden_process_kwargs


class SceneVideoPlanExtensionTests(unittest.TestCase):
    def test_original_scene_attempt_and_settings_fences(self):
        script = Path(__file__).with_name('scene_video_plan_extension_harness.cjs')
        result = subprocess.run(['node', str(script)], cwd=script.parent.parent,
                                capture_output=True, text=True, encoding='utf-8', timeout=30,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['ok'])
        self.assertGreaterEqual(report['checks'], 40)
