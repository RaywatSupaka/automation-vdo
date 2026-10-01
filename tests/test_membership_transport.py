"""Transport regressions; synthetic responses only, never real account secrets."""
import io
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler

from core.membership import API, USER_AGENT, MembershipError, NoRedirect, request_server


class MembershipTransportTests(unittest.TestCase):
    def setUp(self):
        self.opener = MagicMock()
        self.opener.open.return_value.__enter__.return_value.read.return_value = b'{"ok":true}'
        self.factory = patch('core.membership.build_opener', return_value=self.opener)
        self.build = self.factory.start()
        self.addCleanup(self.factory.stop)

    def assert_request(self, route, body, bearer=''):
        self.assertEqual(request_server(route, body, bearer), {'ok': True})
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, API + '/' + route)
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.get_header('User-agent'), USER_AGENT)
        self.assertTrue(USER_AGENT.startswith('SmartFlowAI-Membership/'))
        self.assertNotIn('Mozilla', USER_AGENT)
        self.assertNotIn('Python-urllib', USER_AGENT)
        self.assertEqual(request.get_header('Accept'), 'application/json')
        self.assertEqual(request.get_header('Content-type'), 'application/json')
        self.assertEqual(request.get_header('Authorization'), 'Bearer ' + bearer if bearer else None)
        self.assertEqual(json.loads(request.data), body)
        self.assertEqual(self.opener.open.call_args.kwargs['timeout'], 8)
        return request

    def test_desktop_and_extension_activation_have_product_identity(self):
        for scope in ('desktop', 'extension'):
            with self.subTest(scope=scope):
                body = {'scope': scope, 'activation_token': 'synthetic-not-a-real-token',
                        'device_id': 'synthetic-device', 'version': 'test'}
                request = self.assert_request('activate', body)
                for value in (body['activation_token'], body['device_id']):
                    self.assertNotIn(value, request.get_header('User-agent'))

    def test_renewal_keeps_bearer_separate_from_identity(self):
        self.assert_request('renew', {'device_proof': 'synthetic-proof', 'version': 'test'}, 'synthetic-renewal')
        self.assertNotIn('synthetic-renewal', USER_AGENT)

    def test_both_heartbeat_scopes_have_product_identity(self):
        for scope in ('desktop', 'extension'):
            with self.subTest(scope=scope):
                self.assert_request('heartbeat', {'scope': scope, 'version': 'test'}, 'synthetic-session')

    def test_no_redirect_or_environment_proxy_fallback(self):
        self.assert_request('heartbeat', {'scope': 'desktop'})
        proxy, redirect = self.build.call_args.args
        self.assertIsInstance(proxy, ProxyHandler)
        self.assertEqual(proxy.proxies, {})
        self.assertIsInstance(redirect, NoRedirect)
        self.assertIsNone(redirect.redirect_request(None, None, 307, '', {}, 'https://other.invalid'))
        self.assertEqual(self.opener.open.call_count, 1)

    def test_edge_denial_stays_closed_without_browser_retry(self):
        self.opener.open.side_effect = HTTPError(API, 403, 'Forbidden', {}, io.BytesIO(b'error code: 1010\n'))
        with self.assertRaises(MembershipError) as error:
            request_server('activate', {})
        self.assertEqual(error.exception.code, 'SERVER_UNAVAILABLE')
        self.assertEqual(self.opener.open.call_count, 1)

    def test_invalid_token_and_kick_still_require_login(self):
        for route in ('activate', 'renew', 'heartbeat'):
            with self.subTest(route=route):
                self.opener.open.side_effect = HTTPError(API, 401, 'Unauthorized', {}, io.BytesIO(b'{"detail":"LOGIN_REQUIRED"}'))
                with self.assertRaises(MembershipError) as error:
                    request_server(route, {})
                self.assertEqual(error.exception.code, 'LOGIN_REQUIRED')

    def test_oversized_and_non_json_responses_do_not_unlock(self):
        for raw in (b'x' * 16385, b'not json', b'[]'):
            with self.subTest(size=len(raw)):
                self.opener.open.return_value.__enter__.return_value.read.return_value = raw
                with self.assertRaises(MembershipError) as error:
                    request_server('activate', {})
                self.assertEqual(error.exception.code, 'SERVER_UNAVAILABLE')

    def test_network_failure_does_not_leak_exception_or_retry(self):
        self.opener.open.side_effect = OSError('synthetic-sensitive-body')
        with self.assertRaises(MembershipError) as error:
            request_server('activate', {})
        self.assertNotIn('synthetic-sensitive-body', str(error.exception))
        self.assertEqual(self.opener.open.call_count, 1)


if __name__ == '__main__':
    unittest.main()
