import json
import logging
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from core.local_bridge import LocalBridge
from core.product_manager import ProductManager
from core.extension_identity import ExtensionIdentity


class UpgradeDiagnosticTests(unittest.TestCase):
    def test_customer_update_preserves_id_but_requires_matching_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'app/browser_extension'
            loaded = root / 'data/browser_extension'
            profile = root / 'chrome/Default'
            for folder in (source, loaded, profile):
                folder.mkdir(parents=True)
            def install(folder, version):
                (folder / 'manifest.json').write_text(json.dumps({'name':'SmartFlow AI','version':version}), encoding='utf-8')
                (folder / 'background.js').write_text('worker-version-' + version, encoding='utf-8')
            install(source, 'A'); install(loaded, 'A')
            ident = 'a' * 32
            (profile / 'Preferences').write_text(json.dumps({'extensions':{'settings':{ident:{'path':str(loaded)}}}}), encoding='utf-8')
            identity = ExtensionIdentity(root, source, root / 'chrome')
            self.assertEqual(identity.discover(), {ident})
            install(source, 'B')
            self.assertEqual(identity.discover(), set())
            install(loaded, 'B')
            self.assertEqual(identity.discover(), {ident})
            # Version/name alone cannot make a tampered copy trusted.
            (loaded / 'background.js').write_text('untrusted', encoding='utf-8')
            self.assertEqual(identity.discover(), set())

    def test_unpaired_old_worker_gets_public_upgrade_hint_but_no_capability(self):
        with tempfile.TemporaryDirectory() as temp:
            bridge = LocalBridge('127.0.0.1', 0, ProductManager(Path(temp)), logging.getLogger('diagnostic451')).start()
            try:
                url = f'http://127.0.0.1:{bridge.server.server_address[1]}/api/extension/heartbeat'
                headers = {'Content-Type': 'application/json', 'Origin': 'chrome-extension://' + 'b' * 32}
                for version in ['0.0.1', bridge.REQUIRED_EXTENSION_VERSION]:
                    with patch.object(bridge._extension_identity, 'allowed', return_value=False):
                        req = urllib.request.Request(url, data=json.dumps({'client_id': 'b' * 32, 'version': version}).encode(), headers=headers)
                        with self.assertRaises(urllib.error.HTTPError) as result:
                            urllib.request.urlopen(req, timeout=2)
                    self.assertEqual(result.exception.code, 403)
                    payload = json.load(result.exception)
                    self.assertEqual(payload.get('extension_version_required'), bridge.REQUIRED_EXTENSION_VERSION)
                    self.assertFalse(payload.get('paired'))
                    self.assertNotIn('extension_token', payload)
                    self.assertEqual(payload.get('reload_required'), version != bridge.REQUIRED_EXTENSION_VERSION)
                    self.assertFalse(bridge._extension_sessions)
                    self.assertFalse(bridge._extension_clients)
            finally:
                bridge.stop()


if __name__ == '__main__':
    unittest.main()
