"""Local HTTP tests with reserved number and fake provider transport only."""
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_live_server import LocalLiveServer
from live_scan import Providers, ScanError
from test_live_scan import FakeTransport, SETTINGS, PHONE, verification

class LocalLiveHTTPTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.server = LocalLiveServer(('127.0.0.1', 0), Providers(SETTINGS, self.transport))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.cookie = ''
        self.csrf = ''
        self.port = self.server.server_port
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
    def request(self, path, data=None, **overrides):
        headers = {'Cookie': self.cookie, 'X-CSRF-Token': self.csrf, 'Origin': 'http://127.0.0.1:' + str(self.port), 'Content-Type': 'application/json'}
        headers.update(overrides)
        connection = http.client.HTTPConnection('127.0.0.1', self.port)
        connection.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        response = connection.getresponse()
        raw = response.read()
        cookie = response.getheader('Set-Cookie')
        if cookie: self.cookie = cookie.split(';')[0]
        result = json.loads(raw) if 'json' in response.getheader('Content-Type', '') else raw.decode()
        if isinstance(result, dict) and 'csrf_token' in result: self.csrf = result['csrf_token']
        status = response.status
        connection.close()
        return status, result
    def bootstrap(self):
        self.assertEqual(self.request('/api/session')[0], 200)
    def start(self):
        return self.request('/api/start', {'phone': PHONE, 'own_number': True, 'twilio_consent': True})
    def test_full_journey_resumes_no_duplicate_search_and_clear(self):
        self.transport.responses = [(201, verification()), (200, verification('approved'))] + [(200, {'web': {'results': []}})] * 3
        self.bootstrap()
        self.assertEqual(self.start()[0], 200)
        self.assertEqual(self.request('/api/session')[1]['phase'], 'code')
        self.assertEqual(self.request('/api/scan', {'brave_consent': True})[0], 409)
        self.assertEqual(self.request('/api/verify', {'code': '123456'})[0], 200)
        self.assertEqual(self.request('/api/scan', {'brave_consent': False})[0], 409)
        result = self.request('/api/scan', {'brave_consent': True})
        self.assertEqual(result[0], 200)
        self.assertEqual(result[1]['report']['sources_checked'], 3)
        self.assertEqual(result, self.request('/api/scan', {'brave_consent': True}))
        self.assertEqual(len(self.transport.calls), 5)
        self.assertNotIn(PHONE, json.dumps(result))
        self.assertEqual(self.request('/api/clear', {})[1]['phase'], 'entry')
        self.assertEqual(self.request('/api/session')[1]['report'], None)
    def test_origin_host_csrf_body_routes_and_no_calls(self):
        self.bootstrap()
        for headers in ({'Origin': 'https://evil.example'}, {'Host': 'evil.example'}, {'X-CSRF-Token': ''}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.request('/api/start', {}, **headers)[0], 403)
        self.assertEqual(self.request('/api/start', {}, **{'Content-Type': 'text/plain'})[0], 400)
        self.assertEqual(self.request('/api/start', {'phone': 'x' * 3000})[0], 413)
        for path in ('/api/checkout', '/api/removal', '/api/export'):
            self.assertEqual(self.request(path, {})[0], 404)
        self.assertEqual(self.transport.calls, [])
    def test_static_no_secrets_and_loopback_only(self):
        for path in ('/', '/live.js', '/live.css'):
            status, result = self.request(path)
            self.assertEqual(status, 200)
            self.assertNotIn('SYNTHETIC-TOKEN', result)
        self.assertEqual(self.request('/../live_scan.py')[0], 404)
        self.assertEqual(self.request('/live_scan.py')[0], 404)
        with self.assertRaises(ScanError): LocalLiveServer(('0.0.0.0', 0), Providers(SETTINGS, self.transport))
    def test_cross_session_isolation_and_expiry(self):
        self.transport.responses = [(201, verification())]
        self.bootstrap()
        first_cookie = self.cookie
        self.start()
        self.cookie = ''; self.csrf = ''
        self.bootstrap()
        self.assertEqual(self.request('/api/session')[1]['phase'], 'entry')
        self.assertEqual(self.request('/api/verify', {'code': '123456'})[0], 409)
        self.cookie = first_cookie
        self.bootstrap()
        session = self.server.sessions[first_cookie.split('=', 1)[1]]
        session['scan'].expires = -1
        self.assertEqual(self.request('/api/session')[1]['phase'], 'entry')
        self.assertIsNone(session['scan'].phone)
        session['expires'] = -1
        self.assertEqual(self.request('/api/clear', {})[0], 401)
    def test_invalid_starts_do_not_consume_sms_budget(self):
        self.bootstrap()
        for _ in range(4):
            self.assertEqual(self.request('/api/start', {'phone': 'not a number', 'own_number': True, 'twilio_consent': True})[0], 409)
        self.assertEqual(self.server.starts, [])
        self.assertEqual(self.transport.calls, [])
    def test_sms_rate_limit_survives_clear(self):
        self.bootstrap()
        self.transport.responses = [(201, verification())] * 3
        for _ in range(3):
            self.assertEqual(self.start()[0], 200)
            self.assertEqual(self.request('/api/clear', {})[0], 200)
        self.assertEqual(self.start()[0], 429)
        self.assertEqual(len(self.transport.calls), 3)

if __name__ == '__main__': unittest.main()
