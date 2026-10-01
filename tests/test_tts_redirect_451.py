import io
import json
import tempfile
import unittest
import urllib.request
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from core.external_tts import ExternalTtsClient, ExternalTtsError, _TtsRedirectHandler


class FakeHttp(urllib.request.HTTPSHandler):
    def __init__(self, target, code=302):
        super().__init__()
        self.target, self.code, self.requests = target, code, []

    def https_open(self, request):
        self.requests.append(request)
        headers = Message()
        first = len(self.requests) == 1
        if first:
            headers['Location'] = self.target
        headers['Content-Type'] = 'application/json'
        result = urllib.response.addinfourl(io.BytesIO(json.dumps({'ok': True}).encode()), headers, request.full_url, self.code if first else 200)
        result.msg = 'fixture'
        return result


class TtsRedirectTests(unittest.TestCase):
    def test_downgrade_and_url_credentials_are_rejected_before_request(self):
        redirect = _TtsRedirectHandler(('https', 'www.catfufu.com', 443))
        request = urllib.request.Request('https://www.catfufu.com/api/test', headers={'X-API-Key':'synthetic'})
        for target in ['http://www.catfufu.com/next', 'https://user@www.catfufu.com/next']:
            with self.subTest(target=target), self.assertRaises(ExternalTtsError):
                redirect.redirect_request(request, None, 302, 'fixture', {}, target)

    def run_request(self, target, *, method='GET', download=False, code=302):
        fake = FakeHttp(target, code)
        original = urllib.request.build_opener
        def built(*handlers):
            return original(fake, *handlers)
        # Intercepts both old urlopen and new client-owned opener without network.
        with patch('urllib.request.build_opener', side_effect=built), patch('urllib.request._opener', None):
            client = ExternalTtsClient('synthetic-test-key')
            if download:
                with tempfile.TemporaryDirectory() as temp:
                    target_file = Path(temp) / 'old.mp3'
                    target_file.write_bytes(b'original')
                    with self.assertRaises(ExternalTtsError):
                        client.download('out-1', target_file)
                    self.assertEqual(target_file.read_bytes(), b'original')
                    self.assertEqual(list(Path(temp).iterdir()), [target_file])
            else:
                try:
                    client._json_request(method, '/api/test', b'text=test' if method == 'POST' else None)
                except ExternalTtsError:
                    pass
        return fake.requests

    def test_cross_host_blocked_before_key_leaves_origin(self):
        self.assertEqual(len(self.run_request('https://audit.invalid/destination')), 1)

    def test_cross_port_blocked(self):
        self.assertEqual(len(self.run_request('https://www.catfufu.com:444/next')), 1)
        self.assertEqual(len(self.run_request('https://www.catfufu.com:0/next')), 1)

    def test_download_cross_origin_blocked_preserves_old_file(self):
        self.assertEqual(len(self.run_request('https://audit.invalid/destination', download=True)), 1)

    def test_same_origin_get_redirect_supported(self):
        requests = self.run_request('https://www.catfufu.com:443/next')
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[-1].get_header('X-api-key'), 'synthetic-test-key')

    def test_post_not_replayed_or_changed_to_get(self):
        for code in [301, 302, 303, 307, 308]:
            with self.subTest(code=code):
                self.assertEqual(len(self.run_request('https://www.catfufu.com/next', method='POST', code=code)), 1)

    def test_base_origin_rejects_port_credentials_and_http(self):
        for url in ['https://www.catfufu.com:444', 'https://www.catfufu.com:0', 'https://user@www.catfufu.com', 'http://www.catfufu.com']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                ExternalTtsClient('synthetic-test-key', url)


if __name__ == '__main__':
    unittest.main()
