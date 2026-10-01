"""No live app/provider traffic; exact send receipts and paired neighbors."""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ProviderSendReceipt466(unittest.TestCase):
    def test_bridge_keeps_typed_receipt_evidence_without_prompt(self):
        from core.local_bridge import LocalBridge
        for provider in ('chatgpt', 'gemini'):
            proof = 'owned_' + provider + '_user_turn'
            self.assertEqual(LocalBridge._safe_ai_send_diagnostics({'submission_proof': proof, 'prompt': 'SECRET'}),
                             {'submission_proof': proof})

    def test_chatgpt_and_gemini_native_receipts(self):
        result = subprocess.run(['node', 'tests/provider_send_receipt_466.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['native_receipt_cases'], 26)

    def test_flow_unknown_continuous_send_not_generation(self):
        result = subprocess.run(['node', 'tests/flow_snapshot_harness.js'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_meta_draft_echo_waits_and_keeps_single_dispatch(self):
        result = subprocess.run(['node', 'tests/meta_video_harness.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
