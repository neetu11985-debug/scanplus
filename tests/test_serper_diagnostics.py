"""Synthetic Serper diagnostics. Real sockets, credentials and provider calls forbidden."""
import http.client
import json
import socket
import ssl
import unittest
from unittest.mock import MagicMock, patch

from live_scan import HTTPSJSONTransport, MAX_RESPONSE, ScanError, SerperSearch, Settings
from no_sms_scan import NoSMSSession, SerperOnlySearch
from hosted_self_test import OneTestTransport
from search_diagnostics import (SearchTransportFailure, diagnose_search_exception,
                                search_diagnostic, search_diagnostic_text)

PHONE = '+12025550147'
PRIVATE = 'PRIVATE-KEY-AND-BODY ' + PHONE


class SyntheticTransport:
    def __init__(self, response):
        self.response = response
        self.calls = 0
    def request(self, *args, **kwargs):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class SearchDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('External requests forbidden'))
        guard.start(); self.addCleanup(guard.stop)

    def test_native_error_classes_are_allowlisted_without_message_access(self):
        cases = [(TimeoutError(PRIVATE), 'timeout'), (socket.gaierror(-2, PRIVATE), 'dns_error'),
                 (ssl.SSLCertVerificationError(1, PRIVATE), 'tls_certificate_error'),
                 (ssl.SSLError(1, PRIVATE), 'tls_error'),
                 (PermissionError(13, PRIVATE), 'network_permission_denied'),
                 (ConnectionRefusedError(PRIVATE), 'connection_refused'),
                 (ConnectionResetError(PRIVATE), 'connection_closed'),
                 (http.client.IncompleteRead(PRIVATE.encode(), 100), 'response_incomplete'),
                 (http.client.BadStatusLine(PRIVATE), 'http_protocol_error'),
                 (json.JSONDecodeError('bad', PRIVATE, 0), 'invalid_json'),
                 (OSError(PRIVATE), 'network_error'), (ValueError(PRIVATE), 'transport_error')]
        class Unprintable(Exception):
            def __str__(self):
                raise AssertionError('Exception text must never be inspected')
        cases.append((Unprintable(), 'transport_error'))
        for error, category in cases:
            with self.subTest(category=category):
                transport = SyntheticTransport(error)
                result = SerperSearch('SYNTHETIC-KEY', transport).discover(PHONE, 'spokeo.com')
                self.assertEqual(result['reason'], category)
                self.assertEqual(result['search_diagnostic'], {'category': category, 'http_status': None})
                self.assertEqual(result['status'], 'source_unavailable')
                self.assertEqual(result['candidates'], [])
                self.assertEqual(transport.calls, 1)
                for forbidden in (PRIVATE, PHONE, 'SYNTHETIC-KEY'):
                    self.assertNotIn(forbidden, json.dumps(result))

    def test_status_and_category_inputs_are_revalidated(self):
        for category in (PRIVATE, [], {}, None, '__proto__'):
            for status in (True, '200', 99, 600, 200.1, {}, None):
                safe = search_diagnostic(category, status)
                self.assertEqual(safe, {'category': 'transport_error', 'http_status': None})
                self.assertNotIn(PRIVATE, search_diagnostic_text({'category': category, 'http_status': status, 'body': PRIVATE}))
        failure = SearchTransportFailure(PRIVATE, 'PRIVATE')
        failure.category = PRIVATE; failure.http_status = PRIVATE
        self.assertEqual(diagnose_search_exception(failure), search_diagnostic('transport_error'))
        self.assertNotIn(PRIVATE, str(failure))
        self.assertEqual(search_diagnostic_text(None), '')

    def test_http_and_schema_failures_retain_only_numeric_status(self):
        for status, payload, category in ((401, {'key': PRIVATE}, 'http_error'),
                                           (429, PRIVATE, 'http_error'),
                                           (500, PRIVATE, 'http_error'),
                                           (200, {'organic': PRIVATE}, 'invalid_response'),
                                           (200, {'organic': [{'link': PRIVATE}]}, 'invalid_response')):
            result = SerperSearch('SYNTHETIC-KEY', SyntheticTransport((status, payload))).discover(PHONE, 'spokeo.com')
            self.assertEqual(result['search_diagnostic'], {'category': category, 'http_status': status})
            self.assertNotIn(PRIVATE, json.dumps(result))
            self.assertEqual(result['status'], 'source_unavailable')
        success = SerperSearch('SYNTHETIC', SyntheticTransport((200, {'organic': []}))).discover(PHONE, 'spokeo.com')
        self.assertNotIn('search_diagnostic', success)
        self.assertEqual(success['status'], 'not_found_in_checked_sources')

    def test_response_read_errors_keep_known_http_status_and_no_body(self):
        for body, error, category in ((PRIVATE.encode(), None, 'invalid_json'),
                                      (b'x' * (MAX_RESPONSE + 1), None, 'response_too_large'),
                                      (None, TimeoutError(PRIVATE), 'timeout'),
                                      (None, http.client.IncompleteRead(PRIVATE.encode(), 100), 'response_incomplete')):
            connection = MagicMock()
            response = connection.getresponse.return_value
            response.status = 200; response.read.return_value = body; response.read.side_effect = error
            with patch('live_scan.http.client.HTTPSConnection', return_value=connection):
                result = SerperSearch('SYNTHETIC', HTTPSJSONTransport()).discover(PHONE, 'spokeo.com')
            self.assertEqual(result['search_diagnostic'], {'category': category, 'http_status': 200})
            self.assertNotIn(PRIVATE, json.dumps(result))
            connection.request.assert_called_once(); connection.close.assert_called_once()

    def test_no_sms_one_failed_attempt_skips_two_and_never_refills(self):
        transport = SyntheticTransport(TimeoutError(PRIVATE))
        search = SerperOnlySearch('SYNTHETIC', transport)
        scan = NoSMSSession(search)
        scan.start(PHONE, own_number=True, no_sms_acknowledged=True)
        report = scan.scan(serper_consent=True, free_allowance_confirmed=True)['report']
        self.assertEqual(report['queries_attempted'], 1)
        self.assertEqual(report['sources_checked'], 0)
        self.assertEqual(report['sources'][0]['search_diagnostic']['category'], 'timeout')
        for source in report['sources'][1:]:
            self.assertFalse(source['query_attempted'])
            self.assertEqual(source['reason'], 'not_attempted_after_provider_error')
        scan.scan(serper_consent=True, free_allowance_confirmed=True)
        scan.clear()
        for session in (scan, NoSMSSession(search)):
            with self.assertRaises(ScanError):
                session.start(PHONE, own_number=True, no_sms_acknowledged=True)
        self.assertTrue(search.used); self.assertEqual(search.attempts, 1); self.assertEqual(transport.calls, 1)

    def test_hosted_stopped_queries_are_explicitly_not_dispatched(self):
        class Allowance:
            calls = 0
            def consume(self, kind):
                self.calls += 1
                return self.calls
        allowance = Allowance(); transport = SyntheticTransport(TimeoutError(PRIVATE))
        settings = Settings('AC' + '0' * 32, 'SYNTHETIC', 'VA' + '0' * 32, search_provider='serper', serper_key='SYNTHETIC')
        wrapper = OneTestTransport(settings, transport, allowance)
        first = SerperSearch('SYNTHETIC', wrapper).discover(PHONE, 'spokeo.com')
        self.assertTrue(first['query_attempted'])
        for site in ('truepeoplesearch.com', 'whitepages.com'):
            result = SerperSearch('SYNTHETIC', wrapper).discover(PHONE, site)
            self.assertFalse(result['query_attempted'])
            self.assertEqual(result['reason'], 'not_attempted_after_provider_error')
        self.assertEqual(wrapper.counts['searches'], 1)
        self.assertEqual(allowance.calls, 1); self.assertEqual(transport.calls, 1)
