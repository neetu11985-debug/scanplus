"""Bounded repeated own-number testing, using synthetic transports only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
import io
from pathlib import Path
import json
import socket
import threading
import unittest
from unittest.mock import patch, MagicMock

from no_sms_scan import NoSMSSession, ScanError, SerperOnlySearch, SerperOnlyTransport, load_approved_search
from local_no_sms_server import main
import test_no_sms_scan as no_sms_support

PHONE = '+12025550147'
OTHER = '+12025550148'


class RepeatScanTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('No external requests'))
        guard.start(); self.addCleanup(guard.stop)
        self.transport = no_sms_support.FakeTransport([(200, {'organic': []})] * 15)
        self.search = SerperOnlySearch('SYNTHETIC', self.transport, max_scans=2)
        self.session = NoSMSSession(self.search)

    def start(self, session=None, phone=PHONE):
        return (session or self.session).start(phone, own_number=True, no_sms_acknowledged=True)

    def scan(self, session=None):
        return (session or self.session).scan(serper_consent=True, free_allowance_confirmed=True)

    def test_two_explicit_scans_same_number_and_per_scan_report_counts(self):
        for number in (1, 2):
            self.start()
            state = self.scan()
            self.assertEqual(state['test_usage'], {'scan_limit': 2, 'scans_started': number,
                'scans_remaining': 2-number, 'query_limit': 6, 'queries_attempted': 3*number, 'same_number_locked': True})
            self.assertEqual(state['report']['queries_attempted'], 3)
            self.assertEqual(state['report']['scan_number'], number)
            self.assertIn('Queries attempted: 3.', state['report']['coverage'])
            self.assertEqual(self.scan()['report']['report_id'], state['report']['report_id'])
            self.assertEqual(len(self.transport.calls), 3*number)
            self.session.clear()
        with self.assertRaises(ScanError): self.start()
        self.assertTrue(self.search.used)
        self.assertEqual(len(self.transport.calls), 6)

    def test_each_scan_requires_fresh_ownership_and_provider_consent(self):
        self.start(); self.scan(); self.session.clear()
        with self.assertRaises(ScanError): self.session.start(PHONE)
        self.start()
        for kwargs in ({}, {'serper_consent': True}, {'free_allowance_confirmed': True},
                       {'serper_consent': 1, 'free_allowance_confirmed': True}):
            with self.assertRaises(ScanError): self.session.scan(**kwargs)
        self.assertEqual(self.search.usage()['scans_started'], 1)
        self.assertEqual(len(self.transport.calls), 3)
        self.scan()
        self.assertEqual(len(self.transport.calls), 6)

    def test_binding_survives_clear_expiry_new_session_without_plaintext_number(self):
        self.start(); self.scan(); self.session.clear()
        for session in (self.session, NoSMSSession(self.search)):
            with self.assertRaises(ScanError): self.start(session, OTHER)
            self.assertEqual(session.phase, 'entry')
        self.assertNotIn(PHONE, json.dumps(self.search.__dict__, default=repr))
        self.assertNotIn(PHONE, json.dumps(self.session.state()))
        other = NoSMSSession(self.search, clock=lambda: 1000)
        self.start(other); other.expires = 1
        other.expire()
        with self.assertRaises(ScanError): self.start(other, OTHER)
        self.start(other); self.scan(other)
        self.assertEqual(self.search.usage()['scans_remaining'], 0)

    def test_first_provider_failure_spends_scan_and_unused_slots_are_not_carried(self):
        self.transport.responses = [TimeoutError('do not expose')] + [(200, {'organic': []})] * 3
        self.start(); report = self.scan()['report']
        self.assertEqual(report['queries_attempted'], 1)
        self.assertTrue(all(not source['query_attempted'] for source in report['sources'][1:]))
        self.assertEqual(self.search.usage()['scans_started'], 1)
        self.session.clear(); self.start(); report = self.scan()['report']
        self.assertEqual(report['queries_attempted'], 3)
        self.assertEqual(self.search.attempts, 4)
        self.session.clear()
        with self.assertRaises(ScanError): self.start()
        self.assertEqual(len(self.transport.calls), 4)

    def test_concurrent_transport_attempts_and_authorizations_are_bounded(self):
        transport = SerperOnlyTransport(self.transport, max_scans=2)
        barrier = threading.Barrier(8)
        def authorize(_):
            barrier.wait()
            try: transport.authorize_once(); return True
            except ScanError: return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(authorize, range(8))), 1)
        def request(_):
            try: transport.request('POST', 'https://google.serper.dev/search', headers={}); return True
            except ScanError: return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(request, range(20))), 3)
        transport.finish_scan(); transport.authorize_once()
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(request, range(20))), 3)
        transport.finish_scan()
        with self.assertRaises(ScanError): transport.authorize_once()
        self.assertEqual(transport.attempts, 6)

    def test_repeat_budget_validated_before_keys_and_no_startup_network(self):
        with patch('tool.local_keys.read_properties') as reader:
            for count, free in ((0,0), (6,18), (True,3), ('2',6), (2,3), (2,True), (2,7)):
                with self.assertRaises(ScanError):
                    load_approved_search(Path('SYNTHETIC'), max_scans=count,
                                         confirmed_free_queries=free, no_paid_topup_confirmed=True)
            reader.assert_not_called()
            reader.return_value = {'SERPER_API_KEY': 'SYNTHETIC'}
            with patch('no_sms_scan.HTTPSJSONTransport') as transport:
                search = load_approved_search(Path('SYNTHETIC'), max_scans=5,
                                              confirmed_free_queries=15, no_paid_topup_confirmed=True)
                self.assertEqual(search.usage()['scan_limit'], 5)
                self.assertEqual(search.usage()['query_limit'], 15)
                transport.return_value.request.assert_not_called()
                self.assertEqual(reader.return_value, {})
        with patch('local_no_sms_server.load_approved_search') as loader:
            for argv in (['--local-no-sms', '--test-max-scans', '2'],
                         ['--local-no-sms', '--serper-live', '--test-max-scans', '6'],
                         ['--local-no-sms', '--properties-file', '/SYNTHETIC/private.properties'],
                         ['--local-no-sms', '--diagnostic-log']):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit): main(argv)
            loader.assert_not_called()

    def test_explicit_properties_path_is_forwarded_without_copy_or_provider_calls(self):
        fake_server = MagicMock()
        fake_server.server_port = 4178
        fake_server.session = None
        fake_server.serve_forever.side_effect = KeyboardInterrupt
        with patch('local_no_sms_server.load_approved_search', return_value=self.search) as loader, \
             patch('local_no_sms_server.NoSMSServer') as server, patch('builtins.print'):
            server.return_value.__enter__.return_value = fake_server
            main(['--local-no-sms', '--serper-live', '--test-max-scans', '5',
                  '--confirmed-free-queries', '15', '--no-paid-topup-confirmed',
                  '--properties-file', '/SYNTHETIC/private.properties', '--port', '4178'])
            loader.assert_called_once_with(Path('/SYNTHETIC/private.properties'),
                confirmed_free_queries=15, no_paid_topup_confirmed=True, max_scans=5)
            server.assert_called_once_with(('127.0.0.1', 4178), self.search)
        self.assertEqual(self.transport.calls, [])

    def test_different_number_cannot_authorize_or_discover_after_binding(self):
        self.start(); self.scan(); self.session.clear()
        with self.assertRaises(ScanError): self.search.authorize_once(OTHER)
        with self.assertRaises(ScanError): self.search.discover(OTHER, 'spokeo.com')
        self.assertEqual(self.search.usage()['scans_started'], 1)
        self.assertEqual(len(self.transport.calls), 3)


class RepeatScanHTTPTests(no_sms_support.NoSMSLiveHTTPTests):
    def setUp(self):
        super().setUp()
        self.transport.responses = [(200, {'organic': []})] * 6
        self.server.search = SerperOnlySearch('SYNTHETIC', self.transport, max_scans=2)

    # Existing one-scan expectations remain covered in their original class.
    test_live_report_exports_reload_repeat_and_clear = None
    test_report_other_session_expired_session_and_secret_routes = None

    def test_clear_reload_and_session_rotation_keep_number_and_usage_lock(self):
        self.bootstrap(); self.start()
        consent = {'serper_consent': True, 'free_allowance_confirmed': True}
        self.assertEqual(self.request('/api/scan', consent)[0], 200)
        self.request('/api/clear', {})
        self.assertEqual(self.request('/api/export.pdf')[0], 409)
        self.assertEqual(self.bootstrap()['test_usage']['scans_started'], 1)
        self.assertEqual(self.start(phone=OTHER)[0], 409)
        self.server.session['expires'] = -1
        self.assertEqual(self.bootstrap()['test_usage']['scans_started'], 1)
        self.assertEqual(self.start(phone=OTHER)[0], 409)
        self.assertEqual(self.start()[0], 200)
        self.assertEqual(self.request('/api/scan', {})[0], 409)
        state = self.request('/api/scan', consent)[1]
        self.assertEqual(state['test_usage']['queries_attempted'], 6)
        self.assertEqual(state['report']['queries_attempted'], 3)
        self.request('/api/clear', {})
        self.assertEqual(self.start()[0], 409)
        self.assertEqual(len(self.transport.calls), 6)


if __name__ == '__main__': unittest.main()
