"""Native creative picker bounds, accessible catalog and modal focus regression."""
import json
import os
from pathlib import Path
import subprocess
import unittest

from core.cancellable_process import hidden_process_kwargs
from core.creative_brief import public_catalog


class CreativePickerLayoutTests(unittest.TestCase):
    def test_full_css_cascade_product_queue_story_and_small_windows(self):
        root = Path(__file__).resolve().parents[1]
        env = {**os.environ, 'SMARTFLOW_CREATIVE_CATALOG': json.dumps(public_catalog(), ensure_ascii=False)}
        env.setdefault('NODE_PATH', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result = subprocess.run(['node', 'tests/creative_picker_layout_20260927.cjs'], cwd=root,
                                env=env, capture_output=True, text=True, encoding='utf-8',
                                timeout=120, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(evidence['ok'])
        self.assertEqual(evidence['productChoices'], 15)
        self.assertEqual(evidence['storyChoices'], 12)
        self.assertEqual(evidence['networkRequests'], 0)
        self.assertEqual(evidence['providerRequests'], 0)


if __name__ == '__main__':
    unittest.main()
