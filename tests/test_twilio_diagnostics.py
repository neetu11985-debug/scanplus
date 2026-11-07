"""Reserved fixtures and mocked HTTPS only; no live provider calls."""
import json
import unittest
from unittest.mock import MagicMock, patch
from live_scan import HTTPSJSONTransport, Providers, ScanSession, ScanError, verification_diagnostic, MAX_RESPONSE
from test_live_scan import FakeTransport, SETTINGS, PHONE, verification
import test_local_live_server as http_support

URL = 'https://verify.twilio.com/v2/Services/' + SETTINGS.verify_service_sid + '/Verifications'
PRIVATE = 'synthetic private provider detail'

class TwilioDiagnosticTests(unittest.TestCase):
    def transport_response(self, status, raw, failure=None):
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = status
        response.read.return_value = raw
        response.read.side_effect = failure
        with patch('live_scan.http.client.HTTPSConnection', return_value=connection):
            result = HTTPSJSONTransport().request('POST', URL, headers={}, body='synthetic')
        connection.request.assert_called_once()
        response.read.assert_called_once_with(MAX_RESPONSE + 1)
        connection.close.assert_called_once()
        return result

    def test_transport_returns_only_numeric_code(self):
        raw = json.dumps({'code': 20003, 'message': PRIVATE, 'to': PHONE,
                          'auth_token': SETTINGS.auth_token, 'otp': '123456',
                          'more_info': 'https://example.invalid/private'}).encode()
        result = self.transport_response(401, raw)
        self.assertEqual(result, (401, {'code': 20003}))
        for private in (PRIVATE, PHONE, SETTINGS.auth_token, '123456', 'example.invalid'):
            self.assertNotIn(private, repr(result))

    def test_error_code_types_and_bounds_are_allowlisted(self):
        for code in (True, False, '20003', '123456 secret', None, 20003.0,
                     0, -1, 1000000, [], {}, [20003]):
            with self.subTest(code=code):
                self.assertEqual(self.transport_response(400, json.dumps({'code': code}).encode()), (400, None))
        for code in (20003, 60200, 60203):
            self.assertEqual(self.transport_response(400, json.dumps({'code': code}).encode()), (400, {'code': code}))

    def test_unreadable_bodies_keep_only_http(self):
        for raw in (b'', b'not JSON private', b'[]', b'null', b'{}', bytes([255]), b'{' + b'x' * MAX_RESPONSE):
            with self.subTest(length=len(raw)):
                self.assertEqual(self.transport_response(401, raw), (401, None))
        self.assertEqual(self.transport_response(201, b'not JSON'), (201, None))
        self.assertEqual(self.transport_response(201, b'', TimeoutError(PRIVATE)), (201, None))

    def test_success_schema_and_status_bounds(self):
        payload = verification()
        self.assertEqual(self.transport_response(201, json.dumps(payload).encode()), (201, payload))
        self.assertEqual(verification_diagnostic(201, {'code': 123456}),
                         {'http_status': 201, 'twilio_error_code': None})
        for status in (True, '401', 99, 600, 401.0, {}, None):
            self.assertEqual(verification_diagnostic(status, {'code': 20003}),
                             {'http_status': None, 'twilio_error_code': None})

    def test_other_providers_still_discard_error_payloads_and_no_redirects(self):
        for method, url in (('POST', 'https://google.serper.dev/search'),
                            ('GET', 'https://api.search.brave.com/res/v1/web/search')):
            connection = MagicMock()
            connection.getresponse.return_value.status = 401
            connection.getresponse.return_value.read.return_value = b'{"code":20003,"message":"private"}'
            with patch('live_scan.http.client.HTTPSConnection', return_value=connection):
                self.assertEqual(HTTPSJSONTransport().request(method, url, headers={}), (401, None))
            connection.request.assert_called_once()
        self.assertEqual(self.transport_response(302, b'private redirect body'), (302, None))

    def test_failed_start_diagnostic_blocks_retry_and_search_then_expires(self):
        for response, expected in (((401, {'code': 20003, 'message': PRIVATE, 'to': PHONE}), (401, 20003)),
                                   ((201, {}), (201, None)),
                                   (TimeoutError(PRIVATE), (None, None))):
            transport = FakeTransport(response)
            session = ScanSession(Providers(SETTINGS, transport))
            with self.assertRaises(ScanError) as raised:
                session.start(PHONE, own_number=True, twilio_consent=True)
            diagnostic = session.state()['verification_diagnostic']
            self.assertEqual(diagnostic, dict(zip(('http_status', 'twilio_error_code'), expected)))
            output = str(raised.exception) + json.dumps(session.state())
            for value in (PRIVATE, PHONE, SETTINGS.auth_token):
                self.assertNotIn(value, output)
            self.assertIn('Diagnostic: HTTP ', str(raised.exception))
            self.assertEqual(session.phase, 'start_uncertain')
            self.assertIsNone(session.phone)
            self.assertIsNone(session.sid)
            with self.assertRaises(ScanError): session.start(PHONE, own_number=True, twilio_consent=True)
            with self.assertRaises(ScanError): session.scan(brave_consent=True)
            self.assertEqual(len(transport.calls), 1)
            diagnostic['http_status'] = 500
            self.assertEqual(session.state()['verification_diagnostic']['http_status'], expected[0])
            session.expires = -1
            self.assertEqual(session.state()['phase'], 'entry')
            self.assertNotIn('verification_diagnostic', session.state())

    def test_code_check_diagnostic_clears_on_success_and_clear(self):
        transport = FakeTransport((201, verification()), (429, {'code': 60203}),
                                  (200, verification('approved')))
        session = ScanSession(Providers(SETTINGS, transport))
        session.start(PHONE, own_number=True, twilio_consent=True)
        with self.assertRaisesRegex(ScanError, 'HTTP 429; Twilio error code 60203'): session.verify('123456')
        self.assertEqual(session.phase, 'code')
        self.assertEqual(session.attempts, 1)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(session.state()['verification_diagnostic']['twilio_error_code'], 60203)
        self.assertNotIn('verification_diagnostic', session.verify('123456'))
        self.assertEqual(len(transport.calls), 3)
        session.verification_diagnostic = verification_diagnostic(401, {'code': 20003})
        session.clear()
        self.assertNotIn('verification_diagnostic', session.state())

class DiagnosticHTTPTests(unittest.TestCase):
    setUp = http_support.LocalLiveHTTPTests.setUp
    tearDown = http_support.LocalLiveHTTPTests.tearDown
    request = http_support.LocalLiveHTTPTests.request
    bootstrap = http_support.LocalLiveHTTPTests.bootstrap
    start = http_support.LocalLiveHTTPTests.start

    def test_http_error_resume_clear_and_isolation(self):
        self.transport.responses = [(401, {'code': 20003, 'message': PRIVATE, 'to': PHONE})]
        self.bootstrap()
        original_cookie, original_csrf = self.cookie, self.csrf
        status, result = self.start()
        self.assertEqual(status, 409)
        self.assertIn('HTTP 401; Twilio error code 20003', result['error'])
        self.assertEqual(result['state']['verification_diagnostic'], {'http_status': 401, 'twilio_error_code': 20003})
        self.assertEqual(self.request('/api/session')[1]['verification_diagnostic'], result['state']['verification_diagnostic'])
        for value in (PRIVATE, PHONE, SETTINGS.auth_token): self.assertNotIn(value, json.dumps(result))
        self.assertEqual(self.start()[0], 409)
        self.assertEqual(len(self.transport.calls), 1)
        self.cookie = ''; self.csrf = ''
        self.bootstrap()
        self.assertNotIn('verification_diagnostic', self.request('/api/session')[1])
        self.cookie, self.csrf = original_cookie, original_csrf
        self.assertNotIn('verification_diagnostic', self.request('/api/clear', {})[1])
        self.assertEqual(len(self.server.starts), 1, 'Clear must not reset SMS budget')
        self.assertEqual(len(self.transport.calls), 1)

if __name__ == '__main__': unittest.main()
