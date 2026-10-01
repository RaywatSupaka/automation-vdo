"""Exercise the actual Product queue dialog in a network-isolated native DOM."""
import os
from pathlib import Path
import subprocess
import unittest

from core.cancellable_process import hidden_process_kwargs


class CreationProductEditorNativeUiTests(unittest.TestCase):
    def test_actual_product_editor_entry_points(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        env.setdefault('NODE_PATH', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result = subprocess.run(
            ['node', 'tests/creation_product_editor_ui_449.cjs'], cwd=root,
            capture_output=True, text=True, encoding='utf-8', env=env, timeout=45,
            **hidden_process_kwargs(),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS native Product editor', result.stdout)


if __name__ == '__main__':
    unittest.main()
