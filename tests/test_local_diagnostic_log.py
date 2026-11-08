"""Synthetic local diagnostics only; no real provider calls or credentials."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from local_diagnostic_log import DiagnosticLogError, LocalDiagnosticLog, MAX_LOG_BYTES
from no_sms_scan import NoSMSSession, SerperOnlySearch
from local_no_sms_server import main
import test_no_sms_scan as support

PRIVATE = 'SECRET +12025550147 https://example.invalid/private'


class LocalDiagnosticLogTests(unittest.TestCase):
    def setUp(self):
        guard = patch.object(socket.socket, 'connect', side_effect=AssertionError('No external network'))
        guard.start(); self.addCleanup(guard.stop)
        self.directory = tempfile.TemporaryDirectory(prefix='scanplus-log-test-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'synthetic.log'

    def test_only_allowlisted_fields_and_exact_numeric_types_are_written(self):
        log = LocalDiagnosticLog(self.path)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(log.record({'category':'dns_error','http_status':None,'body':PRIVATE},scan_number=1,query_attempt=1))
        for diagnostic in ({'category':PRIVATE, 'http_status':PRIVATE}, {'category':[], 'http_status':True}, None):
            log.record(diagnostic,scan_number=PRIVATE,query_attempt=True)
        raw = self.path.read_text()
        self.assertNotIn(PRIVATE, raw)
        lines = [json.loads(line) for line in raw.splitlines()]
        self.assertEqual(lines[0]['category'], 'dns_error')
        for line in lines:
            self.assertEqual(set(line), {'event','time_utc','category','http_status','scan_number','query_attempt'})
            self.assertEqual(line['event'], 'serper_request_failed')
        for line in lines[1:]:
            self.assertEqual(line['category'], 'transport_error')
            for field in ('http_status','scan_number','query_attempt'): self.assertIsNone(line[field])

    def test_symlinks_hardlinks_nonprivate_permissions_and_nonfiles_rejected(self):
        original = Path(self.directory.name) / 'original.log'
        original.write_text('SYNTHETIC UNCHANGED'); original.chmod(0o600)
        self.path.symlink_to(original)
        with self.assertRaises(DiagnosticLogError): LocalDiagnosticLog(self.path)
        self.path.unlink(); os.link(original, self.path)
        with self.assertRaises(DiagnosticLogError): LocalDiagnosticLog(self.path)
        self.path.unlink(); original.chmod(0o644)
        with self.assertRaises(DiagnosticLogError): LocalDiagnosticLog(original)
        with self.assertRaises(DiagnosticLogError): LocalDiagnosticLog(Path(self.directory.name))
        self.assertEqual(original.read_text(), 'SYNTHETIC UNCHANGED')
        self.assertEqual(original.stat().st_mode & 0o777, 0o644)

    def test_size_cap_no_truncation_and_concurrent_append(self):
        log = LocalDiagnosticLog(self.path)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: log.record({'category':'timeout','http_status':None},scan_number=1,query_attempt=1), range(500)))
        raw = self.path.read_bytes()
        self.assertLessEqual(len(raw), MAX_LOG_BYTES)
        self.assertEqual(log.status, 'full')
        self.assertTrue(all(json.loads(line)['category'] == 'timeout' for line in raw.splitlines()))
        self.assertFalse(log.record({'category':'http_error','http_status':500},scan_number=2,query_attempt=4))
        self.assertEqual(self.path.read_bytes(), raw)

    def test_write_failure_has_no_raw_error_and_disables_further_logging(self):
        log = LocalDiagnosticLog(self.path)
        with patch('local_diagnostic_log.os.write', side_effect=OSError(PRIVATE)) as writer:
            self.assertFalse(log.record({'category':'timeout'},scan_number=1,query_attempt=1))
            self.assertFalse(log.record({'category':'timeout'},scan_number=1,query_attempt=1))
            writer.assert_called_once()
        self.assertEqual(log.status, 'unavailable')
        self.assertEqual(self.path.read_text(), '')

    def test_request_failure_logged_once_no_retry_or_skipped_query_log(self):
        transport = support.FakeTransport([socket.gaierror(-2, PRIVATE)])
        search = SerperOnlySearch('SYNTHETIC-KEY', transport, max_scans=5)
        search.diagnostic_log = LocalDiagnosticLog(self.path)
        session = NoSMSSession(search)
        session.start('+12025550147',own_number=True,no_sms_acknowledged=True)
        state = session.scan(serper_consent=True,free_allowance_confirmed=True)
        self.assertEqual(state['diagnostic_log_status'], 'ready')
        self.assertEqual(state['report']['queries_attempted'], 1)
        self.assertEqual(len(transport.calls), 1)
        line = json.loads(self.path.read_text())
        self.assertEqual(line['category'], 'dns_error')
        self.assertEqual(line['scan_number'], 1)
        self.assertEqual(line['query_attempt'], 1)
        self.assertIsNone(line['http_status'])
        session.scan(serper_consent=True,free_allowance_confirmed=True)
        session.clear(); session.state()
        self.assertEqual(len(self.path.read_text().splitlines()), 1)
        self.assertEqual(search.usage()['scans_started'], 1)
        self.assertNotIn(PRIVATE, self.path.read_text())

    def test_success_is_not_logged_and_log_failure_does_not_erase_report(self):
        for failed in (False, True):
            transport = support.FakeTransport([(500, None)] if failed else [(200, {'organic': []})]*3)
            search = SerperOnlySearch('SYNTHETIC', transport)
            search.diagnostic_log = LocalDiagnosticLog(self.path)
            session = NoSMSSession(search)
            session.start('+12025550147',own_number=True,no_sms_acknowledged=True)
            with patch('local_diagnostic_log.os.write', side_effect=PermissionError(PRIVATE)):
                state = session.scan(serper_consent=True,free_allowance_confirmed=True)
            self.assertEqual(state['phase'], 'report')
            self.assertEqual(state['diagnostic_log_status'], 'unavailable' if failed else 'ready')
            self.assertEqual(self.path.read_text(), '')

    def test_logging_flag_cannot_bypass_credit_gate(self):
        with patch('tool.local_keys.read_properties') as reader, patch('local_no_sms_server.LocalDiagnosticLog') as logger:
            with self.assertRaises(SystemExit):
                main(['--local-no-sms','--serper-live','--test-max-scans','5','--diagnostic-log'])
            reader.assert_not_called(); logger.assert_not_called()


if __name__ == '__main__': unittest.main()
