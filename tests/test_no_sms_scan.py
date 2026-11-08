"""No live credentials or provider calls. Reserved numbers and injected transport."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from no_sms_scan import (NoSMSSession, SerperOnlySearch, SerperOnlyTransport,
                         ScanError, load_approved_search, no_sms_report_text)
import test_local_no_sms as http_support
PHONE = http_support.PHONE


class FakeTransport:
    def __init__(self, responses=None):
        self.responses = list(responses or [(200, {'organic': []})] * 3)
        self.calls = []

    def request(self, method, url, *, headers, body=None):
        self.calls.append((method, url, headers, body))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class NoSMSSearchTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.search = SerperOnlySearch('SYNTHETIC-SERPER-KEY', self.transport)
        self.clock = [0]
        self.scan = NoSMSSession(self.search, clock=lambda: self.clock[0])

    def start(self):
        return self.scan.start(PHONE, own_number=True, no_sms_acknowledged=True)

    def run_scan(self):
        return self.scan.scan(serper_consent=True, free_allowance_confirmed=True)

    def test_full_scan_honest_ownership_and_one_process_allowance(self):
        state = self.start()
        self.assertIs(state['ownership_verified'], False)
        self.assertEqual(self.transport.calls, [])
        state = self.run_scan()
        self.assertEqual(state['phase'], 'report')
        report = state['report']
        self.assertEqual(report['sources_checked'], 3)
        self.assertEqual(report['queries_attempted'], 3)
        self.assertIs(report['ownership_verified'], False)
        self.assertIs(report['sms_sent'], False)
        self.assertEqual(report['ownership_method'], 'self_attestation_only')
        self.assertEqual({json.loads(call[3])['q'].split('site:')[1] for call in self.transport.calls},
                         {'spokeo.com', 'truepeoplesearch.com', 'whitepages.com'})
        self.assertTrue(all(call[0] == 'POST' and call[1] == 'https://google.serper.dev/search' for call in self.transport.calls))
        self.assertIsNone(self.scan.phone)
        self.assertNotIn(PHONE, json.dumps(report))
        self.assertIn('not verified', no_sms_report_text(report))
        self.assertEqual(self.run_scan(), state)
        self.assertEqual(len(self.transport.calls), 3)
        self.scan.clear()
        with self.assertRaises(ScanError): self.start()
        another = NoSMSSession(self.search)
        with self.assertRaises(ScanError): another.start(PHONE, own_number=True, no_sms_acknowledged=True)
        self.assertEqual(len(self.transport.calls), 3)

    def test_missing_wrong_and_cross_provider_consent_do_not_query(self):
        self.start()
        for data in ({}, {'serper_consent': True}, {'free_allowance_confirmed': True},
                     {'serper_consent': 'true', 'free_allowance_confirmed': True},
                     {'serper_consent': True, 'free_allowance_confirmed': 1}):
            with self.assertRaises(ScanError): self.scan.scan(**data)
        self.assertEqual(self.transport.calls, [])
        self.assertFalse(self.search.used)

    def test_transport_refuses_sms_other_providers_redirects_and_unarmed_requests(self):
        transport = SerperOnlyTransport(self.transport)
        with self.assertRaises(ScanError): transport.request('POST', 'https://google.serper.dev/search', headers={})
        transport.authorize_once()
        for method, url in [('POST','https://verify.twilio.com/v2/Services/test/Verifications'),
                            ('GET','https://api.search.brave.com/res/v1/web/search'),
                            ('POST','https://google.serper.dev/search?redirect=1'),
                            ('POST','http://google.serper.dev/search'),
                            ('GET','https://google.serper.dev/search')]:
            with self.assertRaises(ScanError): transport.request(method, url, headers={})
        for _ in range(3): transport.request('POST','https://google.serper.dev/search',headers={})
        with self.assertRaises(ScanError): transport.request('POST','https://google.serper.dev/search',headers={})
        with self.assertRaises(ScanError): transport.authorize_once()
        self.assertEqual(len(self.transport.calls), 3)

    def test_quota_timeout_malformed_stop_later_queries_without_no_match_claim(self):
        for response in [(402, None), (429, None), (200, {'unexpected': []}), TimeoutError('synthetic timeout')]:
            transport = FakeTransport([response])
            scan = NoSMSSession(SerperOnlySearch('SYNTHETIC-KEY', transport))
            scan.start(PHONE, own_number=True, no_sms_acknowledged=True)
            report = scan.scan(serper_consent=True, free_allowance_confirmed=True)['report']
            self.assertEqual(len(transport.calls), 1)
            self.assertEqual(report['queries_attempted'], 1)
            self.assertEqual(report['sources_checked'], 0)
            self.assertTrue(all(source['status'] == 'source_unavailable' for source in report['sources']))
            self.assertFalse(report['sources'][1]['query_attempted'])
            self.assertNotIn('synthetic timeout', json.dumps(report))

    def test_clear_and_expiry_remove_number_report_and_never_refill_allowance(self):
        self.start(); self.clock[0] = 301
        with self.assertRaises(ScanError): self.run_scan()
        self.assertIsNone(self.scan.phone)
        self.assertEqual(self.transport.calls, [])
        self.start(); self.run_scan(); self.clock[0] = 602
        with self.assertRaises(ScanError): self.scan.current_report()
        self.assertIsNone(self.scan.report)
        self.assertTrue(self.search.used)

    def test_expiry_during_first_response_stops_remaining_queries(self):
        original = self.transport.request
        def expire(*args, **kwargs):
            self.clock[0] = 301
            return original(*args, **kwargs)
        self.transport.request = expire
        self.start()
        state = self.run_scan()
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(state['phase'], 'entry')
        self.assertIsNone(state['report'])
        self.assertIsNone(self.scan.phone)
        self.assertTrue(self.search.used)

    def test_report_candidates_keep_exact_links_but_drop_personal_snippets(self):
        self.transport.responses = [(200, {'organic':[{'link':'https://spokeo.com/synthetic-record',
                                                     'title':PHONE+' Reserved test',
                                                     'snippet':'Do not retain personal snippet'}]})] + [(200, {'organic':[]})]*2
        self.start()
        report = self.run_scan()['report']
        self.assertEqual(report['sources'][0]['candidates'][0]['source_url'], 'https://spokeo.com/synthetic-record')
        text = json.dumps(report)
        self.assertNotIn('Do not retain personal snippet', text)
        self.assertNotIn('SYNTHETIC-SERPER-KEY', text)
        self.assertFalse(report['sources'][0]['candidates'][0]['removal_verified'])

    def test_startup_confirmation_precedes_any_key_read_and_never_calls_provider(self):
        with patch('tool.local_keys.read_properties') as reader:
            for count, topup in [(None,False),(3,False),(True,True),(2,True),(4,True)]:
                with self.assertRaises(ScanError):
                    load_approved_search(Path('SYNTHETIC-NOT-REAL'), confirmed_free_queries=count, no_paid_topup_confirmed=topup)
            reader.assert_not_called()
            reader.return_value = {'SERPER_API_KEY':'SYNTHETIC-ONLY', 'TWILIO_AUTH_TOKEN':'SYNTHETIC-IGNORED'}
            with patch('no_sms_scan.HTTPSJSONTransport') as transport:
                search = load_approved_search(Path('SYNTHETIC-NOT-REAL'), confirmed_free_queries=3, no_paid_topup_confirmed=True)
                self.assertEqual(search.adapter.key, 'SYNTHETIC-ONLY')
                self.assertFalse(search.used)
                transport.return_value.request.assert_not_called()
                self.assertEqual(reader.return_value, {})


class NoSMSLiveHTTPTests(unittest.TestCase):
    tearDown = http_support.NoSMSHTTPTests.tearDown
    request = http_support.NoSMSHTTPTests.request
    start = http_support.NoSMSHTTPTests.start
    bootstrap = http_support.NoSMSHTTPTests.bootstrap

    def setUp(self):
        http_support.NoSMSHTTPTests.setUp(self)
        self.transport = FakeTransport()
        self.server.search = SerperOnlySearch('SYNTHETIC-SERPER-KEY', self.transport)

    def test_live_report_exports_reload_repeat_and_clear(self):
        state = self.bootstrap()
        self.assertTrue(state['search_enabled'])
        self.assertEqual(self.start()[0], 200)
        self.assertEqual(self.request('/api/scan', {})[0], 409)
        status, state = self.request('/api/scan', {'serper_consent': True, 'free_allowance_confirmed': True})
        self.assertEqual(status, 200)
        self.assertIs(state['ownership_verified'], False)
        self.assertEqual(state['queries_attempted'], 3)
        self.assertEqual(self.bootstrap()['report']['report_id'], state['report']['report_id'])
        self.assertEqual(self.request('/api/report')[0], 200)
        status, text = self.request('/api/export.txt')
        self.assertEqual(status, 200)
        self.assertIn('self-attested, not verified', text)
        status, data = self.request('/api/export.pdf')
        self.assertEqual(status, 200)
        self.assertTrue(data.startswith(b'%PDF-1.7'))
        self.assertIn(b'self-attested, not verified', data)
        self.assertEqual(self.request('/api/export.json')[0],404)
        self.assertEqual(self.request('/api/scan', {'serper_consent': True, 'free_allowance_confirmed': True})[0], 200)
        self.assertEqual(len(self.transport.calls), 3)
        self.request('/api/clear', {})
        self.assertEqual(self.request('/api/report')[0], 409)
        self.assertEqual(self.request('/api/export.txt')[0], 409)
        self.assertEqual(self.start()[0], 409)

    def test_report_other_session_expired_session_and_secret_routes(self):
        self.bootstrap(); self.start()
        self.request('/api/scan', {'serper_consent': True, 'free_allowance_confirmed': True})
        cookie, csrf = self.cookie, self.csrf
        self.cookie=''; self.csrf=''
        self.assertEqual(self.request('/api/export.pdf')[0], 401)
        self.assertEqual(self.request('/api/session')[0], 409)
        self.cookie, self.csrf = cookie, csrf
        self.server.session['scan'].expires = -1
        self.assertEqual(self.request('/api/export.txt')[0], 409)
        for path in ('/api/verify','/api/checkout','/api/removal'):
            self.assertEqual(self.request(path, {})[0], 404)
        self.assertEqual(self.request('/scanplus.local.properties')[0], 404)
        self.server.session['expires'] = -1
        self.assertEqual(self.bootstrap()['phase'], 'entry')
        self.assertEqual(self.start()[0], 409)
        self.assertEqual(len(self.transport.calls), 3)


if __name__ == '__main__': unittest.main()
