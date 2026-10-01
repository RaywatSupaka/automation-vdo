"""Compact storytelling controls preserve authored text and the saved-job boundary."""
import json
import os
from pathlib import Path
import subprocess
import unittest

from core.cancellable_process import hidden_process_kwargs
from core.creative_brief import public_catalog


class StorytellingCompactUiTests(unittest.TestCase):
    def test_actual_compact_forms_text_audio_batch_resume_and_layout(self):
        root = Path(__file__).resolve().parents[1]
        env = {**os.environ, 'SMARTFLOW_CREATIVE_CATALOG': json.dumps(public_catalog(), ensure_ascii=False)}
        env.setdefault('NODE_PATH', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result = subprocess.run(['node', 'tests/storytelling_compact_ui.cjs'], cwd=root,
                                env=env, capture_output=True, text=True, encoding='utf-8',
                                timeout=90, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        evidence = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertTrue(evidence['ok'])
        self.assertEqual(evidence['forms'], 3)
        self.assertEqual(evidence['modes'], ['narrator', 'solo', 'dialogue', 'visual'])
        self.assertEqual(evidence['networkRequests'], 0)
        self.assertEqual(evidence['providerRequests'], 0)


if __name__ == '__main__':
    unittest.main()
