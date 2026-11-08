"""Offline durable-ledger contracts. SQLite emulates the SQL function, not Postgres proof."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from owner_test_allowance import PostgresAllowance, AllowanceUnavailable, LIMITS
from hosted_self_test import OneTestTransport
from test_hosted_self_test import ALLOWANCE_URL, RUN_ID, environment, configuration
from test_live_scan import FakeTransport


class FakeConnection:
    def __init__(self, factory):
        self.factory = factory
        self.db = sqlite3.connect(factory.path, timeout=5)
        self.result = None
    def __enter__(self):
        self.db.execute('BEGIN IMMEDIATE')
        return self
    def __exit__(self, kind, value, traceback):
        try:
            if kind:
                self.db.rollback()
            else:
                self.db.commit()
                if self.factory.uncertain_commit:
                    raise OSError('PRIVATE fixture DSN must not escape')
        finally:
            self.db.close()
    @contextmanager
    def cursor(self):
        yield self
    def execute(self, statement, parameters):
        self.factory.statements.append((statement, parameters))
        if statement != PostgresAllowance.statement:
            raise AssertionError('Only the fixed consume function may be called')
        run_id, kind = parameters
        row = self.db.execute('SELECT enabled,expires,sms,checks,searches FROM grants WHERE id=?', (run_id,)).fetchone()
        index = {'sms': 2, 'checks': 3, 'searches': 4}[kind]
        if not row or not row[0] or row[1] <= time.time() or row[index] >= LIMITS[kind]:
            self.result = (None,)
            return
        self.db.execute('UPDATE grants SET '+kind+'='+kind+'+1 WHERE id=?', (run_id,))
        self.result = (row[index] + 1,)
    def fetchone(self):
        return self.result


class FakeConnect:
    def __init__(self, path):
        self.path = path
        self.calls = 0
        self.statements = []
        self.uncertain_commit = False
        self.unavailable = False
    def __call__(self, url, **kwargs):
        self.calls += 1
        if url != ALLOWANCE_URL or kwargs != {'sslmode': 'verify-full', 'sslrootcert': 'system', 'channel_binding': 'require',
                                               'connect_timeout': 5,
                                               'options': '-c statement_timeout=5000 -c lock_timeout=2000'}:
            raise AssertionError('Trusted TLS and bounded database operations required')
        if self.unavailable:
            raise OSError('PRIVATE fixture connection detail')
        return FakeConnection(self)


class DurableAllowanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'fixture.sqlite'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE grants (id TEXT PRIMARY KEY, enabled INTEGER, expires REAL,sms INTEGER,checks INTEGER,searches INTEGER)')
            db.execute('INSERT INTO grants VALUES (?,?,?,0,0,0)', (RUN_ID, 1, time.time() + 300))
        self.connect = FakeConnect(self.path)
    def ledger(self):
        return PostgresAllowance(ALLOWANCE_URL, RUN_ID, connect=self.connect)
    def update(self, statement, params=()):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(statement, params)
    def test_construction_no_connection_and_fixed_bound_inputs(self):
        ledger = self.ledger()
        self.assertEqual(self.connect.calls, 0)
        self.assertEqual(ledger.consume('sms'), 1)
        self.assertEqual(self.connect.statements, [(PostgresAllowance.statement, (RUN_ID, 'sms'))])
        with self.assertRaises(AllowanceUnavailable):
            ledger.consume('DROP TABLE')
        self.assertEqual(self.connect.calls, 1)
    def test_reopen_and_parallel_adapters_cannot_replenish_limits(self):
        self.assertEqual(self.ledger().consume('sms'), 1)
        with self.assertRaises(AllowanceUnavailable):
            self.ledger().consume('sms')
        def attempt(_):
            try:
                return self.ledger().consume('searches')
            except AllowanceUnavailable:
                return None
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(attempt, range(12)))
        self.assertEqual(sorted(x for x in results if x), [1, 2, 3])
        with self.assertRaises(AllowanceUnavailable):
            self.ledger().consume('searches')
    def test_missing_disabled_expired_and_database_failure_are_closed(self):
        for statement in ("UPDATE grants SET enabled=0", "UPDATE grants SET enabled=1,expires=0", 'DELETE FROM grants'):
            self.update(statement)
            with self.assertRaises(AllowanceUnavailable):
                self.ledger().consume('sms')
        self.connect.unavailable = True
        with self.assertRaises(AllowanceUnavailable) as result:
            self.ledger().consume('sms')
        self.assertNotIn('PRIVATE', str(result.exception))
    def test_uncertain_commit_consumes_but_never_dispatches(self):
        self.connect.uncertain_commit = True
        transport = FakeTransport((201, {}))
        wrapper = OneTestTransport(configuration(environment()).providers, transport, self.ledger())
        with self.assertRaises(AllowanceUnavailable):
            wrapper.request('POST', wrapper.sms_url, headers={})
        self.assertEqual(transport.calls, [])
        self.connect.uncertain_commit = False
        reopened = OneTestTransport(configuration(environment()).providers, transport, self.ledger())
        with self.assertRaises(AllowanceUnavailable):
            reopened.request('POST', reopened.sms_url, headers={})
        self.assertEqual(transport.calls, [])
    def test_restart_uses_same_grant_before_dispatch(self):
        transport = FakeTransport((201, {}))
        first = OneTestTransport(configuration(environment()).providers, transport, self.ledger())
        first.request('POST', first.sms_url, headers={})
        second = OneTestTransport(configuration(environment()).providers, transport, self.ledger())
        with self.assertRaises(AllowanceUnavailable):
            second.request('POST', second.sms_url, headers={})
        self.assertEqual(len(transport.calls), 1)
    def test_migration_is_additive_and_grant_is_not_automatic(self):
        sql = (Path(__file__).resolve().parents[1] / 'migrations/002_owner_test_allowance.sql').read_text()
        self.assertIn('BEGIN;', sql)
        self.assertIn('COMMIT;', sql)
        self.assertIn('FOR UPDATE', sql)
        self.assertIn('SECURITY DEFINER', sql)
        self.assertIn('SET search_path = pg_catalog', sql)
        self.assertIn('REVOKE ALL ON FUNCTION', sql)
        for forbidden in ('DROP ', 'TRUNCATE ', 'INSERT INTO', 'encrypted_records', 'CREATE ROLE'):
            self.assertNotIn(forbidden, sql)
