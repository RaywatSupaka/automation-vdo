import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FunctionControlTests(unittest.TestCase):
    def test_display_layer_has_no_job_or_persistence_ownership(self):
        source = (ROOT / 'web_ui/function_controls.js').read_text(encoding='utf-8')
        for forbidden in ('postAction(', 'fetch(', 'localStorage', 'setInterval(',
                          'dispatchEvent(', '.checked =', '.checked=', 'innerHTML'):
            self.assertNotIn(forbidden, source)
        html = (ROOT / 'web_ui/index.html').read_text(encoding='utf-8')
        self.assertIn('/desktop/function_controls.css?v=2', html)
        self.assertIn('/desktop/function_controls.js?v=2', html)
        self.assertGreater(html.index('/desktop/function_controls.js'), html.index('/desktop/shopee_posting.js'))

    def test_actual_source_browser_contract(self):
        env = os.environ.copy()
        result = subprocess.run(['node', 'tests/function_controls_ui.cjs'], cwd=ROOT,
                                env=env, capture_output=True, text=True,
                                encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
