"""Offline adapter contracts. SQLite emulates driver calls, NOT live Postgres proof."""
import base64
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import test_secure_admin as admin_contract
from encrypted_storage import SecureStorageError
from neon_storage import (NeonSettings, PostgresEncryptedStore, _PostgresStatements,
                          read_environment, settings_from_environment, validate_database_url)
from secure_admin import Principal, PaidStorageGrant, create_preview

URL = 'postgresql://fixture:NOT_A_SECRET@ep-fixture-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
KEY = b'K' * 32


class FakeConnection:
    def __init__(self, path):
        self.raw = sqlite3.connect(path, check_same_thread=False)
        self.statements = []
        self.raw.execute('CREATE TABLE IF NOT EXISTS encrypted_records (purpose TEXT NOT NULL,id TEXT PRIMARY KEY,version INTEGER NOT NULL,lookup BLOB NOT NULL,nonce BLOB NOT NULL,ciphertext BLOB NOT NULL,UNIQUE(purpose,lookup))')
        self.raw.commit()

    @contextmanager
    def transaction(self):
        self.raw.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.raw.commit()
        except BaseException:
            self.raw.rollback()
            raise

    def execute(self, statement, parameters=()):
        self.statements.append((statement, parameters))
        if statement.startswith(('SET LOCAL ', 'SELECT pg_advisory_xact_lock')):
            return None
        return self.raw.execute(statement.replace('scanplus.encrypted_records', 'encrypted_records').replace('%s', '?'), parameters)

    @contextmanager
    def cursor(self):
        yield self

    def executemany(self, statement, parameters):
        return self.raw.executemany(statement.replace('scanplus.encrypted_records', 'encrypted_records').replace('%s', '?'), parameters)


class FakePool:
    def __init__(self, path):
        self.conn = FakeConnection(path)

    @contextmanager
    def connection(self):
        yield self.conn

    def close(self):
        self.conn.raw.close()


class NeonAdminContractTests(admin_contract.SecureAdminTests):
    """Run all WSGI auth/payment/download contracts against the new adapter."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = 1000.0
        self.path = Path(self.temp.name) / 'mock-driver.sqlite3'
        self.pool = FakePool(self.path)
        self.store = PostgresEncryptedStore(NeonSettings(URL, {1: KEY}, 1),
            pool=self.pool, clock=lambda: self.now)
        self.principal = Principal('fixture_owner_a', 'admin', 1500, 'c' * 48)
        self.payment = PaidStorageGrant('fixture_owner_a', 'fixture_paid_order_1', 149, 'USD', 1500)
        self.app = create_preview(self.store, lambda env: self.principal,
            origin='https://security.example.invalid', verify_payment=lambda principal: self.payment,
            clock=lambda: self.now)

    def tearDown(self):
        self.store.close()
        self.pool.close()
        self.temp.cleanup()

    def test_reopen_and_wrong_key_fail_closed(self):
        result = self.save_report()
        reopened = PostgresEncryptedStore(NeonSettings(URL, {1: KEY}, 1), pool=self.pool, clock=lambda: self.now)
        self.assertIsNotNone(reopened.get_report(result['report_id'], 'fixture_owner_a'))
        with self.assertRaisesRegex(SecureStorageError, '^Secure storage unavailable$'):
            PostgresEncryptedStore(NeonSettings(URL, {1: b'X' * 32}, 1), pool=self.pool)

    def test_transaction_settings_and_bound_parameters(self):
        self.save_report()
        statements = self.pool.conn.statements
        self.assertTrue(any(sql == "SET LOCAL statement_timeout = '10s'" for sql, _ in statements))
        self.assertTrue(any(sql.startswith('SELECT pg_advisory_xact_lock') for sql, _ in statements))
        for sql, _ in statements:
            if 'encrypted_records' in sql:
                self.assertIn('scanplus.encrypted_records', sql)
            self.assertNotIn('fixture_owner_a', sql)
            self.assertNotIn('+12025550147', sql)

    def test_paid_bundle_rolls_back_on_failure(self):
        before = self.pool.conn.raw.execute('SELECT COUNT(*) FROM encrypted_records').fetchone()[0]
        original = self.store._save
        def fail(purpose, record_id, data):
            if purpose == 'payment_claim':
                raise RuntimeError('PRIVATE FIXTURE MUST NOT ESCAPE')
            return original(purpose, record_id, data)
        with patch.object(self.store, '_save', fail):
            result = self.call('/api/security/demo-record', 'POST', {'confirm_synthetic': True})
        self.assertEqual(result['status'], '503 Service Unavailable')
        self.assertNotIn(b'PRIVATE FIXTURE', result['body'])
        self.assertEqual(before, self.pool.conn.raw.execute('SELECT COUNT(*) FROM encrypted_records').fetchone()[0])

    def test_rotation_fails_closed_for_stale_worker(self):
        other = PostgresEncryptedStore(NeonSettings(URL, {1: KEY}, 1), pool=self.pool)
        self.store.rotate(2, b'N' * 32)
        with self.assertRaises(SecureStorageError):
            other.list_credential_names()
        self.assertEqual([], self.store.list_credential_names())

    def test_active_version_cannot_change_without_atomic_rotation(self):
        self.save_report()
        with self.assertRaises(SecureStorageError):
            PostgresEncryptedStore(NeonSettings(URL, {1: KEY, 2: b'N' * 32}, 2), pool=self.pool)
        # Even a worker with both keys must use the database's active generation.
        overlapping = PostgresEncryptedStore(NeonSettings(URL, {1: KEY, 2: b'N' * 32}, 1), pool=self.pool)
        self.store.rotate(2, b'N' * 32)
        with self.assertRaises(SecureStorageError):
            overlapping.put_paid_bundle('fixture_owner_a', 'fixture_paid_order_1', '+12025550147',
                'SYNTHETIC', 9999999999)

    def test_mixed_key_versions_fail_closed_on_reopen_and_running_worker(self):
        self.save_report()
        self.pool.conn.raw.execute("UPDATE encrypted_records SET version=2 WHERE purpose='payment_claim'")
        self.pool.conn.raw.commit()
        with self.assertRaises(SecureStorageError):
            PostgresEncryptedStore(NeonSettings(URL, {1: KEY}, 1), pool=self.pool)
        with self.assertRaises(SecureStorageError):
            self.store.put_paid_bundle('fixture_owner_a', 'fixture_paid_order_1', '+12025550147',
                'SYNTHETIC', 9999999999)

    def test_started_http_app_with_mocked_database_driver(self):
        from tool.neon_smoke import run_http
        import time
        self.store._clock = time.time
        report_id = run_http(self.store)
        self.assertIsNotNone(self.store.get_report(report_id, 'fixture_owner_a'))


class NeonConfigurationTests(unittest.TestCase):
    def environment(self):
        return {'DATABASE_URL': URL,
                'SCANPLUS_STORAGE_KEYS_JSON': json.dumps({'1': base64.b64encode(KEY).decode()}),
                'SCANPLUS_STORAGE_ACTIVE_VERSION': '1'}

    def test_environment_is_private_and_file_values_do_not_override_host(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            root.joinpath('.env.local').write_text('SOURCE=local\nOTHER=${PRIVATE}\n')
            self.assertEqual(read_environment(root, {'SOURCE': 'host'})['SOURCE'], 'host')
            self.assertEqual(read_environment(root, {})['OTHER'], '${PRIVATE}')
            root.joinpath('.env').write_text('SOURCE=env\n')
            self.assertEqual(read_environment(root, {})['SOURCE'], 'env')
            settings = settings_from_environment(root, self.environment())
            self.assertNotIn('NOT_A_SECRET', repr(settings))
            self.assertNotIn(str(KEY), repr(settings))

    def test_missing_or_wrong_keys_refused(self):
        for replacement in ('', '{}', '[]', '{"01":"a"}', '{"1":"short"}'):
            env = self.environment()
            env['SCANPLUS_STORAGE_KEYS_JSON'] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(SecureStorageError):
                settings_from_environment('/does-not-exist', env)

    def test_dsn_restrictions_and_sanitized_error(self):
        self.assertEqual(URL, validate_database_url(URL))
        invalid = (None, 'PRIVATE', URL.replace('sslmode=require', 'sslmode=disable'),
                   URL.replace('neon.tech', 'attacker.invalid'), URL + '&host=attacker.invalid',
                   URL.replace('/neondb?', '/?'), URL + '&sslmode=require')
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(SecureStorageError) as error:
                validate_database_url(url)
            self.assertNotIn('PRIVATE', str(error.exception))
            self.assertNotIn('NOT_A_SECRET', str(error.exception))
        with self.assertRaises(SecureStorageError):
            validate_database_url(URL, direct=True)
        self.assertEqual(URL.replace('-pooler.', '.'), validate_database_url(URL.replace('-pooler.', '.'), direct=True))

    def test_runtime_pool_options_and_sanitized_connection_failure(self):
        with patch('neon_storage.ConnectionPool') as factory:
            factory.return_value.connection.side_effect = RuntimeError('NOT_A_SECRET')
            with self.assertRaisesRegex(SecureStorageError, '^Secure storage unavailable$'):
                PostgresEncryptedStore(NeonSettings(URL, {1: KEY}, 1))
            kwargs = factory.call_args.kwargs
            self.assertEqual(kwargs['kwargs']['sslmode'], 'verify-full')
            self.assertEqual(kwargs['kwargs']['sslrootcert'], 'system')
            self.assertEqual(kwargs['kwargs']['channel_binding'], 'require')
            self.assertIsNone(kwargs['kwargs']['prepare_threshold'])
            self.assertEqual(kwargs['max_size'], 4)
            factory.return_value.close.assert_called_once()

    def test_fixed_sql_adapter_rejects_other_tables_and_multiple_statements(self):
        adapter = _PostgresStatements(None)
        for statement in ('DROP TABLE users', 'SELECT * FROM encrypted_records; DROP TABLE users'):
            with self.assertRaises(SecureStorageError):
                adapter.sql(statement)
