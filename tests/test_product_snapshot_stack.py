"""Product capture options must survive every actual UI wrapper and persistence."""
import os
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from core.cancellable_process import hidden_process_kwargs
from core.product_prepare_options import freeze_product_options


class ProductSnapshotStackTests(unittest.TestCase):
    def test_actual_option_wrapper_stack(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        env.setdefault('NODE_PATH', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result = subprocess.run(['node', 'tests/product_snapshot_stack.cjs'], cwd=root,
            capture_output=True, text=True, encoding='utf-8', env=env, timeout=60,
            **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS Product snapshot actual wrapper stack', result.stdout)
        # Feed the actual UI payload into the real series validator/persistence;
        # this catches a browser-only acceptance that the backend would reject.
        from core.drama_series import DramaSeriesManager
        rows = json.loads(next(line.removeprefix('BACKEND_DRAMA=') for line in result.stdout.splitlines()
                               if line.startswith('BACKEND_DRAMA=')))
        self.assertEqual(len(rows), 8)
        with tempfile.TemporaryDirectory() as temp:
            manager = DramaSeriesManager(temp)
            for row in rows:
                with self.subTest(mode=row['storytelling_options']['mode'], enqueue=row['enqueue_only']):
                    saved = manager.create('Synthetic UI contract', characters=row['characters'],
                                           render_options=row['render_options'])
                    self.assertEqual(saved['auto_cast_pending'], row['storytelling_options']['mode'] == 'narrator')
                    self.assertEqual(saved['render_options']['storytelling_options'], row['storytelling_options'])

    def test_snapshot_persistence_is_detached_and_strips_runtime_secrets(self):
        options = dict(product_option_snapshot={'version': 1, 'form': 'product-batch'},
            audio_choices={'mode': 'none', 'subtitle': False}, flow_settings={},
            ai_cover_options={'enabled': True}, intro_options={'enabled': False},
            green_options={'enabled': False}, presenter={'enabled': False}, subtitle=False,
            product_runtime_snapshot={'voice_reference_id': 'saved-voice', 'render': {'fps': 24},
                'voice_api_key': 'synthetic-private', 'finish_config': {'secret': 'synthetic-private', 'subtitle_font': 'Saved'}})
        saved = freeze_product_options(options)
        options['audio_choices']['mode'] = 'api'
        options['product_runtime_snapshot']['render']['fps'] = 60
        self.assertEqual(saved['audio_choices']['mode'], 'none')
        self.assertEqual(saved['product_runtime_snapshot']['render']['fps'], 24)
        self.assertNotIn('voice_api_key', saved['product_runtime_snapshot'])
        self.assertNotIn('secret', saved['product_runtime_snapshot']['finish_config'])
        self.assertEqual(saved['product_option_snapshot'], {'version': 1, 'form': 'product-batch'})
        self.assertFalse(saved['subtitle'])

    def test_invalid_or_incomplete_marked_snapshots_fail_before_capture(self):
        for marker in ({'version': True, 'form': 'product'}, {'version': 2, 'form': 'product'},
                       {'version': 1, 'form': 'story'}, {'version': 1, 'form': 'product', 'extra': True},
                       {'version': 1, 'form': 'product'}):
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                freeze_product_options({'product_option_snapshot': marker})

    def test_legacy_preparation_is_not_given_live_form_defaults(self):
        saved = freeze_product_options({'provider': 'gemini', 'scene_count': 6})
        self.assertNotIn('product_option_snapshot', saved)
        self.assertNotIn('audio_choices', saved)
        self.assertNotIn('flow_settings', saved)


if __name__ == '__main__':
    unittest.main()
