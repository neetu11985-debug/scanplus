"""Synthetic transports only. Never invokes real HTTPS/SMS/search."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_scan import Settings, Providers, ScanSession, ScanError, HTTPSJSONTransport, normalize_phone, exact_phone_present

from scan_report import build_report

PHONE = '+12025550147'
SID = 'VE' + '1' * 32
SETTINGS = Settings('AC' + '0' * 32, 'SYNTHETIC-TOKEN', 'VA' + '0' * 32, 'SYNTHETIC-KEY')

def verification(status='pending', **extra):
    return dict({'sid': SID, 'service_sid': SETTINGS.verify_service_sid, 'to': PHONE, 'status': status}, **extra)

class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

class LiveScanTests(unittest.TestCase):
    def session(self, *responses):
        transport = FakeTransport(*responses)
        return ScanSession(Providers(SETTINGS, transport)), transport
    def ready(self, *responses):
        session, transport = self.session((201, verification()), (200, verification('approved')), *responses)
        session.start(PHONE, own_number=True, twilio_consent=True)
        session.verify('123456')
        return session, transport
    def test_configuration_disabled_and_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ScanError, 'disabled'): Settings.from_environment()
        with patch.dict(os.environ, {'SCANPLUS_LOCAL_LIVE_TEST': '1'}, clear=True):
            with self.assertRaisesRegex(ScanError, 'TWILIO_ACCOUNT_SID'): Settings.from_environment()
        self.assertNotIn('SYNTHETIC-TOKEN', repr(SETTINGS))
    def test_no_calls_without_explicit_consent(self):
        session, transport = self.session()
        for args in ({}, {'own_number': True}, {'twilio_consent': True}):
            with self.assertRaises(ScanError): session.start(PHONE, **args)
        with self.assertRaises(ScanError): session.scan(brave_consent=True)
        self.assertEqual(transport.calls, [])
    def test_normalization_and_international_matching(self):
        self.assertEqual(normalize_phone('+1 (202) 555-0147'), PHONE)
        self.assertTrue(exact_phone_present('(202) 555-0147', PHONE))
        self.assertTrue(exact_phone_present('+44 7700 900123', '+447700900123'))
        self.assertFalse(exact_phone_present('920255501470', PHONE))
        self.assertFalse(exact_phone_present('+44 202 555 0147', PHONE))
        self.assertFalse(exact_phone_present('9 202 555 0147 0', PHONE))
        for value in ('2025550147', '+12025550147 ext 2', '+012345678', [], None):
            with self.assertRaises(ScanError): normalize_phone(value)
    def test_verification_binding_and_attempt_limit(self):
        session, transport = self.session((201, verification()), *[(200, verification('approved', to='+12025550148'))] * 5)
        session.start(PHONE, own_number=True, twilio_consent=True)
        for _ in range(5):
            with self.assertRaises(ScanError): session.verify('123456')
        with self.assertRaises(ScanError): session.verify('123456')
        with self.assertRaises(ScanError): session.scan(brave_consent=True)
        self.assertEqual(len(transport.calls), 6)
    def test_unknown_sms_no_retry_or_stored_number(self):
        session, transport = self.session(TimeoutError('secret details'))
        with self.assertRaisesRegex(ScanError, 'uncertain'): session.start(PHONE, own_number=True, twilio_consent=True)
        self.assertEqual(session.phase, 'start_uncertain')
        self.assertIsNone(session.phone)
        with self.assertRaises(ScanError): session.start(PHONE, own_number=True, twilio_consent=True)
        self.assertEqual(len(transport.calls), 1)
    def test_expiry_and_clear_drop_state(self):
        session, transport = self.ready()
        session.expires = -1
        with self.assertRaises(ScanError): session.scan(brave_consent=True)
        self.assertIsNone(session.phone)
        self.assertEqual(len(transport.calls), 2)
        session.report = {'sources': []}
        session.clear()
        self.assertIsNone(session.report)
    def test_full_scan_real_shape_and_repeated_click(self):
        responses = [(200, {'web': {'results': [{'url': 'https://'+site+'/profile?utm_source=secret', 'title': 'Private Name', 'description': 'Phone '+PHONE+' lives at private street'}]}}) for site in sorted(('spokeo.com','truepeoplesearch.com','whitepages.com'))]
        session, transport = self.ready(*responses)
        with self.assertRaises(ScanError): session.scan()
        self.assertEqual(len(transport.calls), 2)
        state = session.scan(brave_consent=True)
        self.assertEqual(state['report']['sources_checked'], 3)
        self.assertEqual(len(transport.calls), 5)
        self.assertIsNone(session.phone)
        self.assertIsNone(session.sid)
        self.assertEqual(session.scan(brave_consent=True), state)
        self.assertEqual(len(transport.calls), 5)
        text = json.dumps(state)
        for value in ('Private Name', 'private street', 'utm_source', PHONE, 'SYNTHETIC-KEY', 'SYNTHETIC-TOKEN'):
            self.assertNotIn(value, text)
        for source in state['report']['sources']:
            self.assertEqual(source['status'], 'match_needs_confirmation')
            self.assertFalse(source['candidates'][0]['removal_eligible'])
    def test_errors_never_claim_absence(self):
        session, transport = self.ready((429, None), TimeoutError(), (200, {}))
        report = session.scan(brave_consent=True)['report']
        self.assertEqual(report['sources_checked'], 0)
        self.assertTrue(all(s['status']=='source_unavailable' for s in report['sources']))
    def test_links_and_false_matches_rejected(self):
        transport = FakeTransport((200, {'web': {'results': [
            {'url': 'https://spokeo.com.evil.example/a', 'description': PHONE},
            {'url': 'https://spokeo.com/a', 'description': '920255501470'},
            {'url': 'http://spokeo.com/a', 'description': PHONE}]}}))
        report = Providers(SETTINGS, transport).discover(PHONE, 'spokeo.com')
        self.assertEqual(report['status'], 'not_found_in_checked_sources')
    def test_query_listing_identifier_is_preserved(self):
        transport = FakeTransport((200, {'web': {'results': [{'url': 'https://spokeo.com/search?id=42&utm_source=campaign', 'description': PHONE}]}}))
        report = Providers(SETTINGS, transport).discover(PHONE, 'spokeo.com')
        self.assertEqual(report['candidates'][0]['source_url'], 'https://spokeo.com/search?id=42')
    def test_https_transport_response_boundaries(self):
        from unittest.mock import MagicMock
        connection = MagicMock()
        response = connection.getresponse.return_value
        transport = HTTPSJSONTransport()
        with patch('live_scan.http.client.HTTPSConnection', return_value=connection):
            response.status = 302
            response.read.return_value = b'private provider body'
            self.assertEqual(transport.request('GET', 'https://api.search.brave.com/res/v1/web/search', headers={}), (302, None))
            connection.request.assert_called_once()
            connection.close.assert_called()
            response.status = 200
            response.read.return_value = b'not-json'
            with self.assertRaises(ValueError): transport.request('GET', 'https://api.search.brave.com/res/v1/web/search', headers={})
            response.read.return_value = b'x' * (1024 * 1024 + 1)
            with self.assertRaises(ScanError): transport.request('GET', 'https://api.search.brave.com/res/v1/web/search', headers={})
            response.read.return_value = b'{"web":{"results":[]}}'
            self.assertEqual(transport.request('GET', 'https://api.search.brave.com/res/v1/web/search', headers={})[0], 200)
            connection.request.side_effect = TimeoutError('private connection detail')
            with self.assertRaises(TimeoutError): transport.request('GET', 'https://api.search.brave.com/res/v1/web/search', headers={})
            self.assertEqual(connection.close.call_count, 5)
    def test_expiry_during_provider_calls(self):
        now = [1]
        session, transport = self.session((201, verification()), (200, verification('approved')))
        session.clock = lambda: now[0]
        session.start(PHONE, own_number=True, twilio_consent=True)
        original = transport.request
        def slow_verification(*args, **kwargs):
            result = original(*args, **kwargs)
            now[0] = 400
            return result
        transport.request = slow_verification
        self.assertEqual(session.verify('123456')['phase'], 'entry')
        with self.assertRaises(ScanError): session.scan(brave_consent=True)
        session, transport = self.ready((200, {'web': {'results': []}}))
        session.clock = lambda: now[0]
        session.expires = 401
        original = transport.request
        def slow_search(*args, **kwargs):
            result = original(*args, **kwargs)
            now[0] = 402
            return result
        transport.request = slow_search
        with patch('live_scan.build_report', wraps=build_report) as builder:
            self.assertEqual(session.scan(brave_consent=True)['phase'], 'entry')
            skipped = builder.call_args.args[0][1:]
            self.assertTrue(all(source['query_attempted'] is False for source in skipped))
        self.assertEqual(len(transport.calls), 3, 'No further queries may start after expiry')
        self.assertIsNone(session.phone)
    def test_transport_rejects_unapproved_destinations_without_network(self):
        for url in ('http://verify.twilio.com/a','https://example.com/a','https://x@verify.twilio.com/a','https://api.search.brave.com:444/a'):
            with self.assertRaises(ScanError): HTTPSJSONTransport().request('GET', url, headers={})

if __name__ == '__main__': unittest.main()
