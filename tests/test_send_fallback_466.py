"""Focused native prepress point checks: synthetic documents and no provider traffic."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUNDLED_NODE_MODULES = Path(
    'C:/Users/keera/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'
)


class SendFallbackNative466(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for native Chromium fixture')
    def test_bounded_chatgpt_send_points_and_unchanged_gemini_guards(self):
        env = dict(os.environ)
        if BUNDLED_NODE_MODULES.is_dir():
            env['NODE_PATH'] = os.pathsep.join(filter(None, (
                str(BUNDLED_NODE_MODULES), env.get('NODE_PATH', ''),
            )))
        result = subprocess.run(
            ['node', 'tests/send_fallback_466.cjs'], cwd=ROOT, env=env,
            capture_output=True, text=True, encoding='utf-8', timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        proof = json.loads(result.stdout)
        self.assertTrue(proof['ok'])
        self.assertTrue(proof['nativeDom'])
        self.assertEqual(proof['scenarios'], 14)
        self.assertGreaterEqual(proof['checks'], 100)
        self.assertEqual(proof['fulfilledDocuments'], proof['scenarios'])
        self.assertEqual(proof['blockedRequests'], 0)
        self.assertEqual(proof['providerNetworkRequests'], 0)
        self.assertEqual(proof['providerActions'], 0)
        self.assertTrue(proof['ownedBrowserClosed'])
