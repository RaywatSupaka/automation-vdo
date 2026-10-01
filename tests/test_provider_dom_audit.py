import json
import os
from pathlib import Path
import subprocess
import unittest
from core.cancellable_process import hidden_process_kwargs


class ProviderDOMAuditTests(unittest.TestCase):
    def test_observed_chatgpt_controls_and_upload_status_scope(self):
        env = dict(os.environ)
        env.setdefault('NODE_PATH', str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result = subprocess.run(['node', str(Path(__file__).with_name('provider_dom_audit_harness.js'))],
                                capture_output=True, text=True, encoding='utf-8', env=env, timeout=30,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {'ok': True, 'cases': 6})
