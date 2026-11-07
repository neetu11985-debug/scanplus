"""Synthetic WSGI contract tests; no real identity provider or service calls."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from encrypted_storage import EncryptedStore
from secure_admin import application, create_preview, Principal, PaidStorageGrant, CREDENTIALS, REPORT


class SecureAdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.now = 1000.0
        self.path = Path(self.temp.name) / 'encrypted.sqlite3'
        self.store = EncryptedStore(self.path, {1: b'1' * 32}, 1, clock=lambda: self.now)
        self.principal = Principal('fixture_owner_a', 'admin', 1500, 'c' * 48)
        self.payment = PaidStorageGrant('fixture_owner_a', 'fixture_paid_order_1', 149, 'USD', 1500)
        self.app = create_preview(self.store, lambda env: self.principal,
                                  origin='https://security.example.invalid', verify_payment=lambda principal: self.payment,
                                  clock=lambda: self.now)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def call(self, path='/admin', method='GET', body=None, app=None, **overrides):
        raw = json.dumps(body).encode() if body is not None else b''
        env = {'REQUEST_METHOD': method, 'PATH_INFO': path, 'QUERY_STRING': '',
               'wsgi.url_scheme': 'https', 'HTTP_HOST': 'security.example.invalid',
               'HTTP_ORIGIN': 'https://security.example.invalid',
               'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(raw)),
               'HTTP_X_CSRF_TOKEN': 'c' * 48, 'wsgi.input': io.BytesIO(raw)}
        env.update(overrides)
        result = {}
        def capture(status, headers): result.update(status=status, headers=dict(headers))
        result['body'] = b''.join((app or self.app)(env, capture))
        return result

    def save_report(self):
        result = self.call('/api/security/demo-record', 'POST', {'confirm_synthetic': True})
        self.assertEqual(result['status'], '201 Created')
        return json.loads(result['body'])

    def test_default_entry_denies_and_no_anonymous_access(self):
        self.assertEqual(self.call(app=application)['status'], '503 Service Unavailable')
        self.principal = None
        for path in ('/admin', '/security.js', '/api/admin/status', '/api/reports/x/download'):
            self.assertEqual(self.call(path)['status'], '401 Unauthorized')

    def test_admin_gate_and_no_role_in_body_override(self):
        self.principal = Principal('fixture_owner_a', 'customer', 1500, 'c' * 48)
        for path in ('/admin', '/api/admin/status'):
            self.assertEqual(self.call(path)['status'], '403 Forbidden')
        result = self.call('/api/admin/credential', 'POST', {'name': 'serper_api_key', 'confirm_synthetic': True, 'role': 'admin'})
        self.assertEqual(result['status'], '403 Forbidden')
        self.assertEqual(self.store.list_credential_names(), [])

    def test_save_credential_never_returns_value_and_rejects_real_input(self):
        result = self.call('/api/admin/credential', 'POST', {'name': 'serper_api_key', 'confirm_synthetic': True})
        self.assertEqual(result['status'], '200 OK')
        status = self.call('/api/admin/status')
        self.assertNotIn(CREDENTIALS['serper_api_key'][1].encode(), status['body'])
        self.assertTrue(json.loads(status['body'])['credentials'][0]['configured'])
        self.assertNotIn(CREDENTIALS['serper_api_key'][1].encode(), self.path.read_bytes())
        self.assertEqual(self.call('/api/admin/credential', 'POST', {'name': 'serper_api_key', 'confirm_synthetic': True, 'value': 'not-a-real-secret'})['status'], '400 Bad Request')
        self.assertEqual(self.call('/api/admin/credential')['status'], '404 Not Found')

    def test_same_origin_tls_csrf_and_host_checks(self):
        body = {'name': 'serper_api_key', 'confirm_synthetic': True}
        for overrides in ({'HTTP_HOST': 'attacker.invalid'}, {'wsgi.url_scheme': 'http'},
                          {'HTTP_ORIGIN': 'https://attacker.invalid'}, {'HTTP_ORIGIN': None},
                          {'HTTP_X_CSRF_TOKEN': 'invalid'}, {'HTTP_SEC_FETCH_SITE': 'cross-site'},
                          {'QUERY_STRING': 'phone=synthetic'}):
            self.assertEqual(self.call('/api/admin/credential', 'POST', body, **overrides)['status'], '403 Forbidden')
        self.assertEqual(self.store.list_credential_names(), [])

    def test_phone_and_report_encrypted_then_owner_download(self):
        data = self.save_report()
        self.assertIsNotNone(self.store.find_phone('fixture_owner_a', '+12025550147'))
        raw = self.path.read_bytes()
        for text in ('+12025550147', REPORT, 'fixture_owner_a'):
            self.assertNotIn(text.encode(), raw)
        result = self.call(data['download_url'])
        self.assertEqual(result['body'].decode(), REPORT)
        self.assertEqual(result['headers']['Content-Type'], 'text/plain; charset=utf-8')
        self.assertEqual(result['headers']['Content-Disposition'], 'attachment; filename="scanmydigits-report.txt"')
        self.assertIn('no-store', result['headers']['Cache-Control'])
        self.assertEqual(result['headers']['X-Content-Type-Options'], 'nosniff')

    def test_unpaid_invalid_expired_and_other_owner_payment_never_persist(self):
        for payment in (None, {'paid': True},
                        PaidStorageGrant('fixture_owner_b', 'fixture_paid_order_1', 149, 'USD', 1500),
                        PaidStorageGrant('fixture_owner_a', 'fixture_paid_order_1', 0, 'USD', 1500),
                        PaidStorageGrant('fixture_owner_a', 'fixture_paid_order_1', 149, 'USD', 999)):
            self.payment = payment
            result = self.call('/api/security/demo-record', 'POST', {'confirm_synthetic': True})
            self.assertEqual(result['status'], '402 Payment Required')
            self.assertIsNone(self.store.find_phone('fixture_owner_a', '+12025550147'))

    def test_paid_replay_returns_same_report(self):
        first = self.save_report()
        second = self.save_report()
        self.assertEqual(first['report_id'], second['report_id'])

    def test_other_customer_and_admin_cannot_download_another_owner_report(self):
        data = self.save_report()
        for role in ('customer', 'admin'):
            self.principal = Principal('fixture_owner_b', role, 1500, 'c' * 48)
            result = self.call(data['download_url'])
            self.assertEqual(result['status'], '404 Not Found')
            self.assertNotIn(REPORT.encode(), result['body'])

    def test_expired_session_expired_report_and_missing_report(self):
        data = self.save_report()
        self.now = 1500
        self.assertEqual(self.call(data['download_url'])['status'], '401 Unauthorized')
        self.principal = Principal('fixture_owner_a', 'customer', 2500, 'c' * 48)
        self.now = 1901
        self.assertEqual(self.call(data['download_url'])['status'], '404 Not Found')
        self.assertEqual(self.call('/api/reports/unknown/download')['status'], '404 Not Found')

    def test_injected_customer_can_save_only_fixed_fixture_not_supplied_pii(self):
        self.principal = Principal('fixture_owner_a', 'customer', 1500, 'c' * 48)
        for body in ({'confirm_synthetic': True, 'phone': '+12025550148'},
                     {'confirm_synthetic': True, 'report': 'not accepted'},
                     {'confirm_synthetic': True, 'owner_id': 'fixture_owner_b'}):
            self.assertEqual(self.call('/api/security/demo-record', 'POST', body)['status'], '400 Bad Request')

    def test_invalid_json_type_size_transfer_method_and_path(self):
        for overrides, expected in (({'CONTENT_TYPE': 'text/plain'}, '400'),
                                   ({'CONTENT_LENGTH': '2000'}, '413'),
                                   ({'HTTP_TRANSFER_ENCODING': 'chunked'}, '400'),
                                   ({'wsgi.input': io.BytesIO(b'invalid')}, '400')):
            self.assertTrue(self.call('/api/admin/credential', 'POST', {'confirm_synthetic': True}, **overrides)['status'].startswith(expected))
        self.assertEqual(self.call(method='DELETE')['status'], '405 Method Not Allowed')
        self.assertEqual(self.call('/../encrypted.sqlite3')['status'], '404 Not Found')

    def test_ui_and_assets_no_secret_form_or_external_scripts(self):
        html = self.call()['body'].decode()
        self.assertIn('Synthetic values only', html)
        self.assertNotIn('<input', html)
        self.assertNotIn('https://', html)
        for path in ('/security.css', '/security.js'):
            self.assertEqual(self.call(path)['status'], '200 OK')

    def test_unexpected_backend_error_does_not_leak(self):
        class Broken:
            def list_credential_names(self): raise RuntimeError('SECRET-DO-NOT-EXPOSE')
        app = create_preview(Broken(), lambda env: self.principal,
                             origin='https://security.example.invalid', clock=lambda: self.now)
        result = self.call('/api/admin/status', app=app)
        self.assertEqual(result['status'], '503 Service Unavailable')
        self.assertNotIn(b'SECRET', result['body'])


if __name__ == '__main__': unittest.main()
