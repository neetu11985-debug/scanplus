"""Synthetic browser runner boundaries. No network, database or credentials."""
import io
import json
import unittest
from unittest.mock import patch

from tool.hosted_fixture_server import FixtureApplication, FixtureTransport, deny_outbound


class HostedFixtureTests(unittest.TestCase):
    def setUp(self):
        self.app = FixtureApplication(4177)
        self.addCleanup(self.app.close)
        self.cookie = ''
        self.csrf = ''

    def call(self, path, data=None, **changes):
        raw = json.dumps(data).encode() if data is not None else b''
        env = {'PATH_INFO': path, 'REQUEST_METHOD': 'GET' if data is None else 'POST',
               'HTTP_HOST': '127.0.0.1:4177', 'HTTP_ORIGIN': 'http://127.0.0.1:4177',
               'HTTP_COOKIE': self.cookie, 'HTTP_X_CSRF_TOKEN': self.csrf,
               'CONTENT_TYPE': 'application/json', 'CONTENT_LENGTH': str(len(raw)),
               'wsgi.input': io.BytesIO(raw), 'wsgi.url_scheme': 'http'}
        env.update(changes)
        result = {}
        def start(status, headers):
            result.update(status=int(status.split()[0]), headers=dict(headers))
        result['raw'] = b''.join(self.app(env, start))
        if result['headers'].get('Set-Cookie'):
            self.cookie = result['headers']['Set-Cookie'].split(';', 1)[0]
        try:
            result['body'] = json.loads(result['raw'])
            self.csrf = result['body'].get('csrf_token', self.csrf)
        except ValueError:
            result['body'] = None
        return result

    def test_banner_and_exact_loopback_origin(self):
        response = self.call('/')
        self.assertEqual(response['status'], 200)
        self.assertIn(b'SYNTHETIC BROWSER QA ONLY', response['raw'])
        self.assertIn(b'PRIVATE LIVE SELF-TEST', response['raw'])
        self.assertEqual(int(response['headers']['Content-Length']), len(response['raw']))
        for changes in ({'HTTP_HOST': 'evil.example'}, {'HTTP_ORIGIN': 'https://evil.example'},
                        {'HTTP_SEC_FETCH_SITE': 'cross-site'}):
            self.assertEqual(self.call('/', **changes)['status'], 403)
        self.assertEqual(self.call('/api/clear', {}, HTTP_ORIGIN='')['status'], 403)

    def test_only_fixture_number_and_no_external_operations(self):
        with patch('live_scan.HTTPSJSONTransport.request', side_effect=AssertionError('Real transport forbidden')):
            self.call('/api/session')
            self.assertEqual(self.call('/api/start', {'phone': '+12025550148'})['status'], 400)
            self.assertEqual(self.app.application.state.providers.transport.counts['sms'], 0)
            started = self.call('/api/start', {'phone': '+12025550147', 'own_number': True, 'twilio_consent': True})
            self.assertEqual(started['body']['phase'], 'code')
            self.assertEqual(self.call('/api/verify', {'code': '000000'})['status'], 409)
            self.assertEqual(self.call('/api/verify', {'code': '123456'})['body']['phase'], 'verified')
            result = self.call('/api/scan', {'serper_consent': True})
            self.assertEqual(result['body']['report']['sources_checked'], 3)
            self.assertEqual(sum(len(source['candidates']) for source in result['body']['report']['sources']), 3)
            self.assertEqual(self.call('/api/scan', {'serper_consent': True})['status'], 200)
            self.assertEqual(self.app.application.state.providers.transport.counts, {'sms': 1, 'checks': 2, 'searches': 3})
            self.call('/api/clear', {})
            self.assertEqual(self.call('/api/session')['body']['sms_allowance_remaining'], 0)

    def test_mock_transport_rejects_unexpected_targets(self):
        transport = FixtureTransport()
        with self.assertRaises(AssertionError):
            transport.request('POST', 'https://unapproved.example', body='')
        with self.assertRaises(AssertionError):
            deny_outbound()
        for port in (80, 65536, '4177'):
            with self.assertRaises(ValueError):
                FixtureApplication(port)

    def test_empty_and_unavailable_scenarios_are_honest_and_bounded(self):
        for scenario in ('empty', 'unavailable'):
            with self.subTest(scenario=scenario):
                self.app.close()
                self.app = FixtureApplication(4177, scenario)
                self.addCleanup(self.app.close)
                self.cookie = ''; self.csrf = ''
                self.assertIn(('Fixture scenario: '+scenario).encode(), self.call('/')['raw'])
                with patch('live_scan.HTTPSJSONTransport.request', side_effect=AssertionError('Real transport forbidden')):
                    self.call('/api/session')
                    self.call('/api/start', {'phone': '+12025550147', 'own_number': True, 'twilio_consent': True})
                    self.call('/api/verify', {'code': '123456'})
                    report = self.call('/api/scan', {'serper_consent': True})['body']['report']
                    self.assertTrue(all(not source['candidates'] for source in report['sources']))
                    if scenario == 'empty':
                        self.assertEqual(report['sources_checked'], 3)
                        self.assertTrue(all(source['status'] == 'not_found_in_checked_sources' for source in report['sources']))
                        self.assertEqual(self.app.transport.searches, 3)
                    else:
                        self.assertEqual(report['sources_checked'], 0)
                        self.assertTrue(all(source['status'] == 'source_unavailable' for source in report['sources']))
                        self.assertEqual(self.app.transport.searches, 1)
                        self.assertTrue(all(source['query_attempted'] is False for source in report['sources'][1:]))
                    self.call('/api/scan', {'serper_consent': True})
                    self.assertEqual(self.app.transport.searches, 3 if scenario == 'empty' else 1)

    def test_scenario_cannot_select_an_unknown_or_live_transport(self):
        for scenario in ('live', 'https://example.invalid', '<script>', None, []):
            with self.assertRaises(ValueError):
                FixtureTransport(scenario)

    def test_no_fixture_paths_or_imports_in_deployment(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        for name in ('owner_live_wsgi.py', 'render_wsgi.py', 'deployment/owner-live-start.sh', 'deployment/render-start.sh'):
            self.assertNotIn('hosted_fixture', (root / name).read_text())
