import json
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools import customer_updater as updater


class CustomerUpdaterUnicodeTests(unittest.TestCase):
    def test_patch_and_rollback_with_thai_paths_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root, backup = Path(temp) / 'โปรแกรม', Path(temp) / 'สำรอง'
            root.mkdir()
            old = {'app_id':'smartflow','version':'0.3.0-beta.1','extension_version':'0.15.450','note':'พร้อม'}
            new = {**old,'version':'0.3.0-beta.2','extension_version':'0.15.451'}
            (root / 'customer-release.json').write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
            (root / 'SmartFlow AI.exe').write_bytes(b'original')
            archive = Path(temp) / 'แพตช์.zip'
            with zipfile.ZipFile(archive, 'w') as zipped:
                zipped.writestr('SmartFlow AI.exe', b'updated')
                zipped.writestr('customer-release.json', json.dumps(new, ensure_ascii=False).encode('utf-8'))
            release = {**new,'supported_from':[old['version']], 'patch':{'size':archive.stat().st_size, 'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}}
            original_read = Path.read_text
            def locale_read(path, encoding=None, *args, **kwargs):
                return original_read(path, encoding=encoding or 'cp1252', *args, **kwargs)
            with patch.object(Path, 'read_text', locale_read):
                updater.apply_patch(root, archive, release, backup)
                self.assertEqual((root / 'SmartFlow AI.exe').read_bytes(), b'updated')
                updater.rollback(root, backup)
                self.assertEqual(json.loads((root / 'customer-release.json').read_text(encoding='utf-8')), old)
                self.assertEqual((root / 'SmartFlow AI.exe').read_bytes(), b'original')

    def test_launch_reads_owned_json_explicitly_as_utf8(self):
        with tempfile.TemporaryDirectory(prefix='sf-451-') as temp:
            root = Path(temp)
            data = root / 'SmartFlowAI/data'
            data.mkdir(parents=True)
            (data / 'config.json').write_text(json.dumps({'font': 'ก.ttf', 'bridge_port': 9911}, ensure_ascii=False), encoding='utf-8')
            marker = data / 'logs/desktop-ready.json'
            marker.parent.mkdir()
            original_read = Path.read_text
            reads = []

            def locale_read(path, encoding=None, *args, **kwargs):
                reads.append((path.name, encoding))
                return original_read(path, encoding=encoding or 'cp1252', *args, **kwargs)

            def started(*args, **kwargs):
                marker.write_text(json.dumps({'pid': 12, 'engine_pid': 34, 'note': 'พร้อม'}, ensure_ascii=False), encoding='utf-8')
                process = MagicMock(pid=12)
                process.poll.return_value = None
                return process

            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({'release_version': '0.15.451', 'desktop_ui': 'hybrid', 'engine_pid': 34}).encode()
            with patch.dict('os.environ', {'LOCALAPPDATA': temp}), patch.object(Path, 'read_text', locale_read), patch.object(updater.subprocess, 'Popen', side_effect=started) as launch, patch.object(updater, 'urlopen', return_value=response):
                updater.launch_verified(root, '0.15.451')
            self.assertEqual(launch.call_count, 1)
            self.assertTrue(all(encoding == 'utf-8' for _, encoding in reads), reads)

    def test_invalid_config_is_named_before_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / 'SmartFlowAI/data'
            data.mkdir(parents=True)
            (data / 'config.json').write_text('{broken', encoding='utf-8')
            with patch.dict('os.environ', {'LOCALAPPDATA': temp}), patch.object(updater.subprocess, 'Popen') as launch:
                with self.assertRaisesRegex(ValueError, 'config.json'):
                    updater.launch_verified(Path(temp), '0.15.451')
                launch.assert_not_called()

    def test_real_launch_failure_terminates_only_started_process(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / 'SmartFlowAI/data'
            data.mkdir(parents=True)
            (data / 'config.json').write_text('{}', encoding='utf-8')
            process = MagicMock()
            process.poll.return_value = None
            with patch.dict('os.environ', {'LOCALAPPDATA': temp}), patch.object(updater.subprocess, 'Popen', return_value=process), patch.object(updater.time, 'monotonic', side_effect=[0, 60]):
                with self.assertRaises(RuntimeError):
                    updater.launch_verified(Path(temp), '0.15.451')
            process.terminate.assert_called_once()


if __name__ == '__main__':
    unittest.main()
