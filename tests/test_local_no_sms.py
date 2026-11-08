"""Synthetic loopback checks. Fail any attempted non-loopback connection."""
import http.client
import json
from pathlib import Path
import socket
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_no_sms_server import NoSMSServer, BLOCKER

PHONE = '+12025550147'


class NoSMSHTTPTests(unittest.TestCase):
    def setUp(self):
        original = socket.socket.connect
        self.connections = []
        def guarded(sock, address):
            self.assertEqual(address[0], '127.0.0.1', 'External network is forbidden in this test.')
            self.connections.append(address)
            return original(sock, address)
        self.guard = patch.object(socket.socket, 'connect', guarded)
        self.guard.start()
        self.server = NoSMSServer(('127.0.0.1', 0))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.cookie = ''
        self.csrf = ''

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.guard.stop()

    def request(self, path, data=None, **overrides):
        headers = {'Origin': 'http://127.0.0.1:' + str(self.port), 'Cookie': self.cookie,
                   'X-CSRF-Token': self.csrf, 'Content-Type': 'application/json'}
        headers.update(overrides)
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=2)
        conn.request('POST' if data is not None else 'GET', path,
                     json.dumps(data) if data is not None else None, headers)
        reply = conn.getresponse()
        raw = reply.read()
        cookie = reply.getheader('Set-Cookie')
        if cookie:
            self.assertIn('HttpOnly; SameSite=Strict', cookie)
            self.cookie = cookie.split(';')[0]
        self.assertEqual(reply.getheader('Cache-Control'), 'no-store')
        self.assertIn("frame-ancestors 'none'", reply.getheader('Content-Security-Policy'))
        payload = json.loads(raw) if reply.getheader('Content-Type') == 'application/json' else raw if reply.getheader('Content-Type') == 'application/pdf' else raw.decode()
        if isinstance(payload, dict) and 'csrf_token' in payload:
            self.csrf = payload['csrf_token']
        status = reply.status
        conn.close()
        return status, payload

    def start(self, **changes):
        data = {'phone': PHONE, 'own_number': True, 'no_sms_acknowledged': True}
        data.update(changes)
        return self.request('/api/start', data)

    def bootstrap(self):
        status, state = self.request('/api/session')
        self.assertEqual(status, 200)
        return state

    def assert_unverified(self, state):
        self.assertIs(state['sms_enabled'], False)
        self.assertIs(state['ownership_verified'], False)
        self.assertIs(state['search_enabled'], False)
        self.assertEqual(state['sources_checked'], 0)
        self.assertIsNone(state['report'])

    def test_full_no_sms_flow_repeated_scan_and_clear(self):
        self.assert_unverified(self.bootstrap())
        status, state = self.start()
        self.assertEqual(status, 200)
        self.assertEqual(state['phase'], 'ready')
        self.assertEqual(state['last_four'], '0147')
        self.assert_unverified(state)
        self.assertNotIn(PHONE, json.dumps(self.server.session['scan'].__dict__, default=str))
        self.assertEqual(self.bootstrap()['phase'], 'ready')
        first = self.request('/api/scan', {})
        self.assertEqual(first[0], 409)
        self.assertEqual(first[1]['error'], BLOCKER)
        self.assert_unverified(first[1]['state'])
        again = self.request('/api/scan', {})
        self.assertEqual(first[0], again[0])
        self.assertEqual(first[1]['error'], again[1]['error'])
        self.assertEqual(first[1]['state']['phase'], again[1]['state']['phase'])
        self.assertEqual(self.request('/api/clear', {})[1]['phase'], 'entry')
        self.assertIsNone(self.bootstrap()['last_four'])
        self.assertEqual(self.request('/api/scan', {})[0], 409)

    def test_consent_and_number_validation(self):
        self.bootstrap()
        for change in ({'own_number': False}, {'own_number': 'true'}, {'no_sms_acknowledged': False},
                       {'phone': '2025550147'}, {'phone': '+0123456789'}, {'phone': '<script>'},
                       {'phone': '+12025550147 ext 3'}, {'phone': '+1234567890123456'}):
            self.assertEqual(self.start(**change)[0], 409)
        self.assertEqual(self.start(phone='+1 (202) 555-0147')[0], 200)
        self.assertEqual(self.start()[0], 409)

    def test_host_origin_proxy_csrf_and_size(self):
        self.bootstrap()
        for headers in ({'Host': 'evil.test'}, {'Host': 'localhost:' + str(self.port)},
                        {'Origin': 'https://evil.test'}, {'Sec-Fetch-Site': 'cross-site'},
                        {'Forwarded': 'for=127.0.0.1'}, {'X-Forwarded-Host': 'public.example'},
                        {'X-CSRF-Token': ''}):
            self.assertEqual(self.request('/api/start', {}, **headers)[0], 403)
        self.assertEqual(self.request('/api/start', {}, **{'Content-Type': 'text/plain'})[0], 400)
        self.assertEqual(self.request('/api/start', {'phone': 'x' * 3000})[0], 413)
        self.assertEqual(self.request('/api/start', ['not an object'])[0], 400)

    def test_second_browser_and_expired_session(self):
        self.bootstrap()
        cookie, csrf = self.cookie, self.csrf
        self.cookie = ''; self.csrf = ''
        self.assertEqual(self.request('/api/session')[0], 409)
        self.assertEqual(self.start()[0], 401)
        self.cookie, self.csrf = cookie, csrf
        self.start()
        self.server.session['expires'] = -1
        self.assertEqual(self.request('/api/scan', {})[0], 401)
        self.assertIsNone(self.server.session)
        self.assertEqual(self.bootstrap()['phase'], 'entry')
        self.assertNotEqual(cookie, self.cookie)

    def test_no_live_routes_no_secrets_no_public_binding(self):
        self.bootstrap()
        for path in ('/api/verify', '/api/checkout', '/api/removal', '/api/export.json'):
            self.assertEqual(self.request(path, {})[0], 404)
        self.assertEqual(self.request('/api/report')[0], 409)
        for path in ('/scanplus.local.properties', '/local_no_sms_server.py', '/../live_scan.py'):
            self.assertEqual(self.request(path)[0], 404)
        for path in ('/', '/no_sms.js', '/no_sms.css'):
            self.assertEqual(self.request(path)[0], 200)
        for bind in ('0.0.0.0', 'localhost', '::1', '192.0.2.1'):
            with self.assertRaises(ValueError):
                NoSMSServer((bind, 0))
        root = Path(__file__).resolve().parents[1]
        source = (root / 'local_no_sms_server.py').read_text()
        for forbidden in ('import live_scan', 'import local_keys', 'HTTPSConnection(', 'os.environ', 'read_properties('):
            self.assertNotIn(forbidden, source)
        for path in ('server.py', 'wsgi.py', 'local_live_server.py', 'tool/local_keys.py'):
            self.assertNotIn('import local_no_sms_server', (root / path).read_text())


if __name__ == '__main__':
    unittest.main()
