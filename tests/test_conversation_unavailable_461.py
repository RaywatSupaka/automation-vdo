import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ConversationUnavailable461Tests(unittest.TestCase):
    def test_explicit_fresh_pending_step_keeps_saved_scenes_and_is_idempotent(self):
        result = subprocess.run(['node', 'tests/conversation_fresh_461.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreaterEqual(json.loads(result.stdout)['cases'], 25)

    def test_actual_background_owner_transfer_and_saved_receipt(self):
        result = subprocess.run(['node', 'tests/conversation_unavailable_background_461.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreaterEqual(json.loads(result.stdout)['checks'], 17)

    def test_native_panel_and_durable_reload_tab_read_state_machine(self):
        result = subprocess.run(['node', 'tests/conversation_unavailable_461.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertGreaterEqual(report['cases'], 30)
        self.assertEqual(report['provider_sends'], 0)

    def test_recovery_is_loaded_in_worker_and_chatgpt_not_gemini(self):
        manifest = json.loads((ROOT / 'browser_extension/manifest.json').read_text(encoding='utf-8'))
        for item in manifest['content_scripts']:
            if 'https://chatgpt.com/*' in item['matches']:
                self.assertIn('conversation_recovery.js', item['js'])
            if 'https://gemini.google.com/*' in item['matches']:
                self.assertNotIn('conversation_recovery.js', item['js'])
        self.assertIn('conversation_recovery.js', (ROOT / 'browser_extension/src/background/service-worker.js').read_text())


if __name__ == '__main__':
    unittest.main()
