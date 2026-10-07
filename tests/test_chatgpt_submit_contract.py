"""Native synthetic form-submit contract, including exact production acceptance."""
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


class ChatGPTSubmitContract(unittest.TestCase):
    def run_fixture(self, baseline=False):
        env = dict(os.environ)
        if BUNDLED_NODE_MODULES.is_dir():
            env['NODE_PATH'] = os.pathsep.join(filter(None, (
                str(BUNDLED_NODE_MODULES), env.get('NODE_PATH', ''),
            )))
        args = ['node', 'tests/chatgpt_submit_contract.cjs']
        if baseline:
            args.append('--baseline')
        result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True,
                                text=True, encoding='utf-8', timeout=60)
        self.assertTrue(result.stdout.strip(), result.stderr)
        proof = json.loads(result.stdout)
        self.assertTrue(proof['nativeDom'])
        self.assertEqual(proof['scenarios'], 20)
        self.assertEqual(proof['fulfilledDocuments'], proof['scenarios'])
        self.assertEqual(proof['blockedRequests'], 0)
        self.assertEqual(proof['providerNetworkRequests'], 0)
        self.assertEqual(proof['providerActions'], 0)
        self.assertTrue(proof['ownedBrowserClosed'])
        print(json.dumps({
            'phase': 'baseline484_RED' if baseline else 'candidate485_GREEN',
            'ok': proof['ok'], 'scenarios': proof['scenarios'], 'passed': proof['passed'],
            'checks': proof['checks'],
            'violations': [item['scenario'] for item in proof['violations']],
            'nativeGestures': proof['nativeGestures'],
            'nativeFormSubmits': proof['nativeFormSubmits'],
            'exactAcceptedRequests': proof['exactAcceptedRequests'],
            'providerNetworkRequests': proof['providerNetworkRequests'],
            'providerActions': proof['providerActions'], 'ownedBrowserClosed': True,
        }), flush=True)
        return result, proof

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_484_baseline_exposes_uncovered_submit_contract(self):
        if not (ROOT.parent / 'before-runtime' / 'chatgpt.js').is_file():
            self.skipTest('Historical 484 baseline source is not available in this checkout')
        result, proof = self.run_fixture(baseline=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(proof['ok'])
        self.assertTrue(proof['baselineRegression'])
        failures = {failure['scenario'] for failure in proof['violations']}
        self.assertIn('bare_owned_submit_native_acceptance', failures)
        self.assertIn('class_submit', failures)
        self.assertIn('aria_disabled_earlier_duplicate', failures)
        self.assertIn('foreign_form_decoy', failures)
        self.assertIn('ambiguous_owned_submit_reject', failures)
        self.assertIn('form_changed_before_arm', failures)
        self.assertIn('editor_changed_before_arm', failures)
        self.assertEqual(proof['nativeFormSubmits'], 1)
        self.assertEqual(proof['exactAcceptedRequests'], 1)

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_485_owned_native_submit_and_exact_acceptance(self):
        result, proof = self.run_fixture()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(proof['ok'])
        self.assertFalse(proof['baselineRegression'])
        self.assertEqual(proof['passed'], proof['scenarios'])
        self.assertGreaterEqual(proof['checks'], 80)
        self.assertEqual(proof['nativeGestures'], 2)
        self.assertEqual(proof['nativeFormSubmits'], 2)
        self.assertEqual(proof['exactAcceptedRequests'], 2)
