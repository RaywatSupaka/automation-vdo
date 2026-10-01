"""Execute the real legacy Product tool routes with inert managers/dispatch."""
import ast
import copy
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from core.ai_web_models import normalize_ai_web_model

ROOT = Path(__file__).resolve().parents[1]


def actual_route():
    tree = ast.parse((ROOT / 'ui/main_window.py').read_text(encoding='utf-8-sig'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MainWindow')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_desktop_execute_action')
    branch = next(n for n in method.body if isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
                  and ast.unparse(n.test) == "action in {'product_add_images', 'product_add_video', 'product_tool'}")
    method.body = [branch]
    method.decorator_list = []  # Separate file-claim tests exercise the decorator.
    namespace = {'normalize_ai_web_model': normalize_ai_web_model,
                 'VIDEO_AI_PROVIDERS': {'Google Flow': 'flow', 'Meta AI': 'meta_ai'}}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), '<actual-product-tool>', 'exec'), namespace)
    return namespace[method.name]


def actual_prepare():
    tree = ast.parse((ROOT / 'ui/main_window.py').read_text(encoding='utf-8-sig'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MainWindow')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_prepare_chatgpt_for_job')
    method.decorator_list = []  # File-claim behavior has its own tests; this fixture never opens job files.
    namespace = {'messagebox': SimpleNamespace(showinfo=Mock(), showwarning=Mock(), showerror=Mock())}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), '<actual-product-prepare>', 'exec'), namespace)
    return namespace[method.name], namespace['messagebox']


class ProductToolScopeTests(unittest.TestCase):
    def test_actual_product_tool_ui_scope(self):
        env = dict(os.environ)
        env.setdefault('NODE_PATH', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules'))
        result = subprocess.run(['node', str(ROOT / 'tests/product_tool_scope_ui.cjs')], cwd=ROOT,
                                env=env, capture_output=True, text=True, encoding='utf-8', timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def app(self, job):
        self.job = copy.deepcopy(job)
        products = SimpleNamespace(get_job=lambda _: self.job,
            set_image_ai_provider=Mock(side_effect=lambda _, val: self.job.update(image_ai_provider=val)),
            set_ai_web_model=Mock(side_effect=lambda _, provider, val: self.job.update(ai_web_model=val)),
            set_video_ai_provider=Mock(side_effect=lambda _, val: self.job.update(video_ai_provider=val)),
            plugin_request=Mock(side_effect=lambda _: {'job': self.job}))
        return SimpleNamespace(products=products, _desktop_select_product=lambda _: True,
            _image_provider_key=lambda: 'gemini', _ai_web_model_key=lambda _: 'flash',
            image_ai_provider=SimpleNamespace(set=Mock()), video_ai_provider=SimpleNamespace(set=Mock()),
            _set_ai_web_model=Mock(), _prepare_chatgpt_plugin=Mock(),
            _start_multi_flow=Mock(), _send_to_google_flow=Mock(),
            _video_provider_label=lambda value: value,
            bridge=SimpleNamespace(extension_status=lambda: {'connected': True},
                queue_extension_command=Mock(return_value={'id': 'test-only'})),
            _activate_or_launch_chrome=Mock(), status=SimpleNamespace(set=Mock()), _write_console=Mock())

    def test_ai_repair_does_not_copy_new_form_or_persist_global_model(self):
        job = {'id': 'JOB-SAVED', 'image_ai_provider': 'chatgpt', 'ai_web_model': 'thinking'}
        app = self.app(job)
        actual_route()(app, 'product_tool', {'job_id': job['id'], 'tool': 'ai_web',
            'provider': 'gemini', 'ai_web_model': 'flash'})
        self.assertEqual(self.job, job)
        app._set_ai_web_model.assert_not_called()
        app._prepare_chatgpt_plugin.assert_called_once()

    def test_flow_specific_tools_reject_meta_without_changing_job(self):
        for tool in ('auto_flow', 'multi_flow'):
            with self.subTest(tool=tool):
                job = {'id': 'JOB-SAVED', 'video_ai_provider': 'meta_ai'}
                app = self.app(job)
                with self.assertRaisesRegex(ValueError, 'Flow'):
                    actual_route()(app, 'product_tool', {'job_id': job['id'], 'tool': tool})
                self.assertEqual(self.job, job)
                app._start_multi_flow.assert_not_called()
                app._send_to_google_flow.assert_not_called()

    def test_saved_flow_and_missing_legacy_provider_still_dispatch_flow(self):
        for extra in ({'video_ai_provider': 'flow'}, {}):
            app = self.app({'id': 'JOB-SAVED', **extra})
            actual_route()(app, 'product_tool', {'job_id': 'JOB-SAVED', 'tool': 'multi_flow', 'video_provider': 'meta_ai'})
            app._start_multi_flow.assert_called_once()
            app.products.set_video_ai_provider.assert_not_called()

    def test_prepare_uses_saved_provider_and_keeps_manifest(self):
        for provider in ('chatgpt', 'gemini', None):
            with self.subTest(provider=provider):
                job = {'id': 'JOB-SAVED', 'product_name': 'fixture', 'source_images': ['saved.png']}
                if provider:
                    job.update(image_ai_provider=provider, ai_web_model='auto')
                app = self.app(job)
                prepare, messages = actual_prepare()
                prepare(app, job['id'])
                self.assertEqual(self.job, job)
                expected = 'https://gemini.google.com/app' if provider == 'gemini' else 'https://chatgpt.com/'
                app._activate_or_launch_chrome.assert_called_once_with(expected)
                app.bridge.queue_extension_command.assert_called_once_with('open_chatgpt', job['id'])
                messages.showerror.assert_not_called()

    def test_invalid_saved_provider_is_not_silently_replaced(self):
        app = self.app({'id': 'JOB-SAVED', 'image_ai_provider': 'unknown', 'source_images': ['saved.png']})
        prepare, messages = actual_prepare()
        prepare(app, 'JOB-SAVED')
        app.bridge.queue_extension_command.assert_not_called()
        messages.showerror.assert_called_once()


if __name__ == '__main__':
    unittest.main()
