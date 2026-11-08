"""Private owner-test WSGI checks. All provider responses are synthetic fixtures."""
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from hosted_self_test import configuration, OwnerTestApplication, OneTestTransport
from test_live_scan import FakeTransport, PHONE, SETTINGS, verification
from test_serper_scan import organic

ROOT = Path(__file__).resolve().parents[1]
USER = 'fixture'
PASSWORD = 'Synthetic-Owner-Test-Only-92817!'
HOST = 'synthetic-fixture.onrender.com'
ALLOWANCE_URL = 'postgresql://fixture:NOT_A_SECRET@ep-fixture-pooler.us-east-2.aws.neon.tech/fixture?sslmode=require&channel_binding=require'
RUN_ID = '713cedf6-1ce7-4447-a72a-176c6bd1a92f'
AUTH = 'Basic ' + base64.b64encode((USER + ':' + PASSWORD).encode()).decode()


def environment():
    return {'SCANPLUS_HOSTED_SELF_TEST': '1', 'SCANPLUS_HOSTED_FREE_ALLOWANCE_CONFIRMED': '1',
            'RENDER': 'true', 'RENDER_EXTERNAL_HOSTNAME': HOST,
            'SCANPLUS_OWNER_TEST_USER': USER, 'SCANPLUS_OWNER_TEST_PASSWORD': PASSWORD,
            'SCANPLUS_SEARCH_PROVIDER': 'serper', 'TWILIO_ACCOUNT_SID': SETTINGS.account_sid,
            'TWILIO_VERIFY_SERVICE_SID': SETTINGS.verify_service_sid,
            'TWILIO_AUTH_TOKEN': 'SYNTHETIC-NOT-A-SECRET', 'SERPER_API_KEY': 'SYNTHETIC-KEY',
            'SCANPLUS_OWNER_TEST_DATABASE_URL': ALLOWANCE_URL, 'SCANPLUS_OWNER_TEST_RUN_ID': RUN_ID}


class MemoryAllowance:
    # Explicit synthetic stand-in. Persistence/commit tests live in the ledger suite.
    def __init__(self):
        self.counts = {'sms': 0, 'checks': 0, 'searches': 0}
    def consume(self, kind):
        limits = {'sms': 1, 'checks': 5, 'searches': 3}
        if self.counts[kind] >= limits[kind]:
            from owner_test_allowance import AllowanceUnavailable
            raise AllowanceUnavailable('Fixture allowance used')
        self.counts[kind] += 1
        return self.counts[kind]


class HostedConfigurationTests(unittest.TestCase):
    def test_disabled_default_and_strict_configuration(self):
        with self.assertRaises(RuntimeError):
            configuration({})
        for changes in ({'SCANPLUS_HOSTED_SELF_TEST': '0'}, {'SCANPLUS_HOSTED_FREE_ALLOWANCE_CONFIRMED': '0'},
                        {'RENDER': ''}, {'RENDER_EXTERNAL_HOSTNAME': 'evil.example'},
                        {'SCANPLUS_OWNER_TEST_PASSWORD': 'short'}, {'SCANPLUS_OWNER_TEST_PASSWORD': 'x' * 40},
                        {'SCANPLUS_OWNER_TEST_USER': ''}, {'SCANPLUS_SEARCH_PROVIDER': 'brave'},
                        {'TWILIO_ACCOUNT_SID': ''}, {'TWILIO_VERIFY_SERVICE_SID': ''},
                        {'TWILIO_AUTH_TOKEN': ''}, {'SERPER_API_KEY': ''}, {'SERPER_API_KEY': 'bad\nkey'},
                        {'SCANPLUS_STRIPE_TEST': '1'}, {'SCANPLUS_ENCRYPTED_REPORTS': '1'},
                        {'SCANPLUS_OWNER_TEST_DATABASE_URL': ''}, {'SCANPLUS_OWNER_TEST_RUN_ID': 'bad'}):
            with self.subTest(change=list(changes)):
                with self.assertRaises(RuntimeError):
                    configuration(dict(environment(), **changes))
        self.assertNotIn('SYNTHETIC', repr(configuration(environment())))

    def test_default_entrypoint_refuses_without_provider_calls_or_database(self):
        code = "import sys\ntry: import owner_live_wsgi\nexcept RuntimeError: assert 'server' not in sys.modules; sys.exit(0)\nraise AssertionError('enabled without approval')"
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                                env={'PATH': os.environ.get('PATH', ''), 'PYTHONDONTWRITEBYTECODE': '1'},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')

    def test_existing_deployment_unchanged_and_new_start_is_single_process(self):
        current = (ROOT / 'deployment/render-start.sh').read_text()
        self.assertIn('render_wsgi:application', current)
        self.assertNotIn('owner_live_wsgi', current)
        new = (ROOT / 'deployment/owner-live-start.sh').read_text()
        self.assertIn("GUNICORN_CMD_ARGS=''", new)
        self.assertIn('--workers 1 --threads 1 --worker-class sync owner_live_wsgi:application', new)
        self.assertNotIn('"$@"', new)


class HostedJourneyTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.app = OwnerTestApplication(configuration(environment()), self.transport, allowance=MemoryAllowance(), start_cleanup=False)
        self.addCleanup(self.app.close)
        self.cookie = ''
        self.csrf = ''

    def call(self, path, data=None, *, overrides=None, raw=None):
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else b''
        env = {'PATH_INFO': path, 'REQUEST_METHOD': 'POST' if data is not None or raw is not None else 'GET',
               'HTTP_HOST': HOST, 'HTTP_AUTHORIZATION': AUTH, 'HTTP_ORIGIN': 'https://' + HOST,
               'HTTP_COOKIE': self.cookie, 'HTTP_X_CSRF_TOKEN': self.csrf,
               'CONTENT_LENGTH': str(len(body)), 'CONTENT_TYPE': 'application/json',
               'wsgi.url_scheme': 'https', 'wsgi.input': io.BytesIO(body)}
        env.update(overrides or {})
        response = {}
        def start(status, headers):
            response.update(status=int(status.split()[0]), headers=dict(headers))
        response['raw'] = b''.join(self.app(env, start))
        if 'Set-Cookie' in response['headers']:
            self.cookie = response['headers']['Set-Cookie'].split(';', 1)[0]
        try:
            response['body'] = json.loads(response['raw'])
            self.csrf = response['body'].get('csrf_token', self.csrf)
        except (ValueError, AttributeError):
            response['body'] = None
        return response

    def start(self):
        self.assertEqual(self.call('/api/session')['status'], 200)
        return self.call('/api/start', {'phone': PHONE, 'own_number': True, 'twilio_consent': True})

    def verified(self, *search_responses):
        self.transport.responses = [(201, verification()), (200, verification('approved')), *search_responses]
        self.assertEqual(self.start()['status'], 200)
        self.assertEqual(self.call('/api/verify', {'code': '123456'})['status'], 200)

    def test_auth_origin_host_scheme_query_and_private_paths(self):
        for path in ('/', '/live.js', '/live.css', '/api/session', '/api/export.pdf', '/.env'):
            for auth in ('', 'Basic !!!', 'Basic \u2603', 'Basic Zm9vOmJhcg=='):
                self.assertEqual(self.call(path, overrides={'HTTP_AUTHORIZATION': auth})['status'], 401)
        for change in ({'HTTP_HOST': 'evil.example'}, {'wsgi.url_scheme': 'http'},
                       {'HTTP_ORIGIN': 'https://evil.example'}, {'HTTP_SEC_FETCH_SITE': 'cross-site'}):
            self.assertEqual(self.call('/', overrides=change)['status'], 403)
        for change in ({'QUERY_STRING': 'phone=fixture'}, {'SCRIPT_NAME': '/test'}):
            self.assertEqual(self.call('/', overrides=change)['status'], 400)
        self.assertEqual(self.call('/', overrides={'REQUEST_METHOD': 'PUT'})['status'], 405)
        for path in ('/.env', '/hosted_self_test.py', '/api/checkout', '/api/removal', '/api/refund', '/stripe-test'):
            self.assertEqual(self.call(path)['status'], 404)
        self.assertEqual(self.transport.calls, [])

    def test_assets_and_session_are_not_provider_actions(self):
        for path in ('/', '/live.js', '/live.css'):
            response = self.call(path)
            self.assertEqual(response['status'], 200)
            self.assertEqual(response['headers']['Cache-Control'], 'no-store')
            self.assertIn('noindex', response['headers']['X-Robots-Tag'])
            self.assertNotIn(b'SYNTHETIC-KEY', response['raw'])
        self.assertIn(b'PRIVATE LIVE SELF-TEST', self.call('/')['raw'])
        response = self.call('/api/session')
        self.assertTrue(response['headers']['Set-Cookie'].startswith('scanplus_owner_sid='))
        for flag in ('HttpOnly', 'SameSite=Strict', 'Secure'):
            self.assertIn(flag, response['headers']['Set-Cookie'])
        self.assertEqual(response['body']['test_scope'], 'private_owner')
        self.assertEqual(response['body']['expires_in_ms'], 0)
        self.assertEqual(self.transport.calls, [])

    def test_consent_csrf_bodies_and_ownership_gate(self):
        self.call('/api/session')
        for change in ({'HTTP_X_CSRF_TOKEN': ''}, {'HTTP_X_CSRF_TOKEN': '\u2603'}, {'HTTP_ORIGIN': ''}):
            self.assertEqual(self.call('/api/start', {}, overrides=change)['status'], 403)
        for raw in (b'[]', b'not json'):
            self.assertEqual(self.call('/api/start', raw=raw)['status'], 400)
        self.assertEqual(self.call('/api/start', raw=b'x' * 2049)['status'], 413)
        self.assertEqual(self.call('/api/start', {}, overrides={'CONTENT_TYPE': 'text/plain'})['status'], 400)
        for data in ({'phone': PHONE}, {'phone': PHONE, 'own_number': True},
                     {'phone': PHONE, 'twilio_consent': True},
                     {'phone': PHONE, 'own_number': 'true', 'twilio_consent': True}):
            self.assertEqual(self.call('/api/start', data)['status'], 409)
        self.assertEqual(self.call('/api/scan', {'serper_consent': True})['status'], 409)
        self.assertEqual(self.transport.calls, [])

    def test_full_live_shape_and_report_privacy_without_real_transport(self):
        self.verified(*[(200, organic(site)) for site in sorted(('spokeo.com', 'truepeoplesearch.com', 'whitepages.com'))])
        for data in ({}, {'brave_consent': True}, {'serper_consent': 'true'}):
            self.assertEqual(self.call('/api/scan', data)['status'], 409)
        self.assertEqual(len(self.transport.calls), 2)
        response = self.call('/api/scan', {'serper_consent': True})
        self.assertEqual(response['status'], 200)
        self.assertEqual(response['body']['report']['sources_checked'], 3)
        self.assertGreater(response['body']['expires_in_ms'], 0)
        self.assertEqual(len(self.transport.calls), 5)
        self.assertEqual(self.call('/api/scan', {'serper_consent': True})['status'], 200)
        self.assertEqual(len(self.transport.calls), 5)
        for value in (PHONE.encode(), b'Fictional Name', b'private street', b'SYNTHETIC-KEY', b'SYNTHETIC-NOT-A-SECRET'):
            self.assertNotIn(value, response['raw'])
        saved = self.call('/api/export.pdf')
        self.assertEqual(saved['status'], 200)
        self.assertTrue(saved['raw'].startswith(b'%PDF-1.7'))
        self.assertIn(b'PRIVATE OWNER SELF-TEST', saved['raw'])
        self.assertEqual(saved['headers']['Content-Type'], 'application/pdf')
        self.assertEqual(int(saved['headers']['Content-Length']), len(saved['raw']))
        self.assertEqual(saved['headers']['Cache-Control'], 'no-store')
        self.assertEqual(self.call('/api/export.json')['status'], 404)
        self.assertIn('attachment', saved['headers']['Content-Disposition'])
        self.assertEqual(self.call('/api/clear', {})['status'], 200)
        self.assertEqual(self.call('/api/export.pdf')['status'], 409)
        self.assertEqual(self.call('/api/removal', {})['status'], 404)
        self.assertEqual(len(self.transport.calls), 5)

    def test_other_session_and_expired_report_cannot_download(self):
        self.verified(*[(200, {'organic': []})] * 3)
        self.call('/api/scan', {'serper_consent': True})
        original = self.cookie
        self.cookie = ''; self.csrf = ''
        self.assertEqual(self.call('/api/export.pdf')['status'], 401)
        self.call('/api/session')
        self.assertEqual(self.call('/api/export.pdf')['status'], 409)
        self.cookie = original
        token = original.split('=', 1)[1]
        scan = self.app.state.sessions[token]['scan']
        scan.expires = time.monotonic() - 1
        self.app.state.service_actions()
        self.assertIsNone(scan.report)
        self.assertIsNone(scan.phone)
        self.assertEqual(self.call('/api/export.pdf')['status'], 409)

    def test_sms_allowance_survives_clear_new_sessions_and_uncertain_response(self):
        self.transport.responses = [TimeoutError('private token in provider failure')]
        response = self.start()
        self.assertEqual(response['status'], 409)
        self.assertNotIn(b'private token', response['raw'])
        self.assertEqual(len(self.transport.calls), 1)
        self.call('/api/clear', {})
        self.assertEqual(self.start()['status'], 409)
        self.cookie = ''; self.csrf = ''
        self.assertEqual(self.start()['status'], 409)
        self.assertEqual(len(self.transport.calls), 1)

    def test_exhausted_durable_allowance_after_process_restart_blocks_sms(self):
        allowance = MemoryAllowance()
        allowance.consume('sms')
        self.app.close()
        self.app = OwnerTestApplication(configuration(environment()), self.transport, allowance=allowance, start_cleanup=False)
        self.addCleanup(self.app.close)
        response = self.start()
        self.assertEqual(response['status'], 409)
        self.assertEqual(response['body']['state']['phase'], 'entry')
        self.assertTrue(response['body']['state']['allowance_blocked'])
        self.assertEqual(self.transport.calls, [])

    def test_wrong_phone_verification_cannot_unlock_search(self):
        self.transport.responses = [(201, verification()), *[(200, verification('approved', to='+12025550148'))] * 5]
        self.start()
        for _ in range(6):
            self.assertEqual(self.call('/api/verify', {'code': '123456'})['status'], 409)
        self.assertEqual(self.call('/api/scan', {'serper_consent': True})['status'], 409)
        self.assertEqual(len(self.transport.calls), 6)
        self.assertEqual(self.app.state.providers.transport.counts, {'sms': 1, 'checks': 5, 'searches': 0})

    def test_first_search_error_stops_later_provider_requests(self):
        self.verified((429, None))
        response = self.call('/api/scan', {'serper_consent': True})
        self.assertEqual(response['status'], 200)
        self.assertEqual(response['body']['report']['sources_checked'], 0)
        self.assertTrue(all(s['status'] == 'source_unavailable' for s in response['body']['report']['sources']))
        self.assertEqual(len(self.transport.calls), 3)
        self.assertEqual(self.app.state.providers.transport.counts['searches'], 1)

    def test_request_body_is_bounded_and_read_without_blocking_cleanup(self):
        self.call('/api/session')
        app = self.app
        class Input:
            def read(inner, length):
                self.assertFalse(app.state.lock._is_owned())
                self.assertEqual(length, 2)
                return b'{}'
        self.assertEqual(self.call('/api/clear', {}, overrides={'wsgi.input': Input()})['status'], 200)
        self.assertEqual(self.call('/api/clear', {}, overrides={'CONTENT_LENGTH': '3'})['status'], 400)
        self.assertEqual(self.call('/api/clear', {}, overrides={'CONTENT_LENGTH': 'invalid'})['status'], 400)
        self.assertEqual(self.call('/api/clear', {}, overrides={'HTTP_TRANSFER_ENCODING': 'chunked'})['status'], 400)
        self.assertEqual(self.transport.calls, [])

    def test_malformed_success_stops_search_spending(self):
        self.verified((200, {'organic': 'invalid'}))
        response = self.call('/api/scan', {'serper_consent': True})
        self.assertEqual(response['status'], 200)
        self.assertEqual(response['body']['report']['sources_checked'], 0)
        self.assertTrue(all(s['status'] == 'source_unavailable' for s in response['body']['report']['sources']))
        self.assertEqual(len(self.transport.calls), 3)

    def test_unsupported_calling_codes_are_rejected_on_server(self):
        self.call('/api/session')
        for phone in ('+447700900123', '+120255501470'):
            self.assertEqual(self.call('/api/start', {'phone': phone, 'own_number': True, 'twilio_consent': True})['status'], 409)
        self.assertEqual(self.transport.calls, [])

    def test_budget_rejects_unapproved_destinations_before_network(self):
        budget = self.app.state.providers.transport
        for method, url in (('GET', 'https://google.serper.dev/search'),
                            ('POST', 'https://google.serper.dev/search?x=1'),
                            ('POST', 'https://evil.example/search')):
            with self.assertRaises(Exception):
                budget.request(method, url, headers={})
        self.assertEqual(self.transport.calls, [])

    def test_idle_cleanup_and_shutdown_remove_memory_state(self):
        app = OwnerTestApplication(configuration(environment()), FakeTransport(), allowance=MemoryAllowance())
        self.addCleanup(app.close)
        expired = type('ExpiredScan', (), {'expire': lambda self: None, 'clear': lambda self: setattr(self, 'cleared', True)})()
        app.state.sessions['fixture'] = {'expires': time.monotonic() - 1, 'scan': expired}
        deadline = time.monotonic() + 3
        while app.state.sessions and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertEqual(app.state.sessions, {})
        self.assertTrue(expired.cleared)
        app.close()
        self.assertFalse(app._cleanup.is_alive())
