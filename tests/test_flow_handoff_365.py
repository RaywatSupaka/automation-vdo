import subprocess
import ast
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs


class FlowHandoff365Tests(unittest.TestCase):
    def test_desktop_does_not_race_extension_owned_handoff(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root/'ui/main_window.py').read_text(encoding='utf-8-sig'))
        checks = [n.test for n in ast.walk(tree) if isinstance(n, ast.If)
                  and 'flow_repair_handoff' in ast.unparse(n.test)]
        self.assertEqual(len(checks), 1)
        expression = compile(ast.Expression(checks[0]), '<handoff guard>', 'eval')
        from types import SimpleNamespace
        for handoff, expected in [(True, False), (False, True)]:
            self.assertEqual(eval(expression, {'step':'opening_project',
                'client':{'flow_repair_handoff':handoff},'last_change':0,
                'time':SimpleNamespace(monotonic=lambda:200)}),expected)

    def test_actual_handoff_guards(self):
        result = subprocess.run(['node', 'tests/flow_handoff_365.js'],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, encoding='utf-8',
                                timeout=30, **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
