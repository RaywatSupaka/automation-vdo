import json
import os
import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs


class SceneVideoPlanUiTests(unittest.TestCase):
    def test_saved_scene_editor_offline_browser(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        env.setdefault('NODE_PATH', str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result = subprocess.run(['node', str(root/'tests/scene_video_plan_ui_457.cjs')], cwd=root,
                                env=env, capture_output=True, text=True, encoding='utf-8', timeout=70,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence['ok'])
        self.assertEqual(evidence['providerRequests'], 0)
