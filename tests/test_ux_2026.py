import ast
import subprocess
from types import SimpleNamespace
import unittest
from pathlib import Path


class Ux2026Tests(unittest.TestCase):
    def test_desktop_reports_connection_not_extension_membership(self):
        source = (Path(__file__).resolve().parents[1] / 'ui/main_window.py').read_text(encoding='utf-8')
        expressions = [value for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Dict)
                       for key, value in zip(node.keys, node.values)
                       if isinstance(key, ast.Constant) and key.value == 'extension_authorized']
        self.assertEqual(len(expressions), 2)  # full and compact snapshots
        for expression in expressions:
            code = compile(ast.Expression(expression), '<authorization-display>', 'eval')
            owner = SimpleNamespace(bridge=SimpleNamespace(REQUIRED_EXTENSION_VERSION='paired'))
            for connected, version, expected in [(False,'paired',False),(True,'old',False),(True,'paired',True)]:
                self.assertIs(eval(code, {'self':owner,'extension':{'connected':connected},'extension_version':version}), expected)

    def test_actual_source_dialogs_motion_and_connection(self):
        result = subprocess.run(['node', 'tests/ux_2026_ui.cjs'],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('"providerSubmissions":0', result.stdout)


if __name__ == '__main__':
    unittest.main()
