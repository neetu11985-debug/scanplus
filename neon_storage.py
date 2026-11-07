"""Postgres persistence for the existing encrypted, owner-scoped storage API.

This is a backend adapter, not an identity or payment verifier. Existing demo
storage remains unchanged; Render has a separate read-only connection probe.
Schema creation is a separate reviewed step.
No customer data or provider credentials are written on import.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
import base64
import json
import os
from pathlib import Path
from threading import RLock
import time
from urllib.parse import parse_qs, urlsplit

from dotenv import dotenv_values
from psycopg_pool import ConnectionPool

from encrypted_storage import EncryptedStore, SecureStorageError, _key


@dataclass(frozen=True)
class NeonSettings:
    database_url: str = field(repr=False)
    keys: dict = field(repr=False)
    active_version: int


def validate_database_url(value, *, direct=False):
    """Reject local/insecure/multihost DSNs; never echo a malformed credential."""
    try:
        url = urlsplit(value)
        query = parse_qs(url.query, strict_parsing=True)
        if (url.scheme not in ('postgres', 'postgresql') or not url.username
                or not url.password or not url.hostname
                or not url.hostname.endswith('.neon.tech')
                or url.port not in (None, 5432) or not url.path.strip('/')
                or url.fragment or ',' in url.netloc
                or any(key not in ('sslmode', 'channel_binding') for key in query)
                or query.get('sslmode', ['require']) not in (['require'], ['verify-full'])
                or query.get('channel_binding', ['require']) != ['require']
                or (direct and '-pooler.' in url.hostname)):
            raise ValueError()
    except (TypeError, ValueError):
        raise SecureStorageError('Valid Neon database configuration required') from None
    return value


def read_environment(root=None, environ=None):
    """Mirror Neon's env file choice; deployment environment always takes priority.

    No expansion: file values cannot interpolate other secrets. The process's
    environment is never modified. This function never prints values.
    """
    root = Path(root or Path(__file__).parent)
    source = root / '.env'
    if not source.exists():
        source = root / '.env.local'
    values = dict(dotenv_values(source, interpolate=False)) if source.exists() else {}
    values.update(dict(os.environ if environ is None else environ))
    return values


def settings_from_environment(root=None, environ=None):
    values = read_environment(root, environ)
    try:
        database_url = validate_database_url(values.get('DATABASE_URL'))
        raw = json.loads(values.get('SCANPLUS_STORAGE_KEYS_JSON', ''))
        if not isinstance(raw, dict) or not raw:
            raise ValueError()
        keys = {}
        for version, value in raw.items():
            if not isinstance(version, str) or not version.isdecimal() or str(int(version)) != version:
                raise ValueError()
            decoded = base64.b64decode(value, validate=True)
            _key(int(version), decoded)
            keys[int(version)] = decoded
        active = int(values.get('SCANPLUS_STORAGE_ACTIVE_VERSION', ''))
        if active not in keys:
            raise ValueError()
        return NeonSettings(database_url, keys, active)
    except Exception:
        raise SecureStorageError('Neon storage configuration unavailable') from None


class _PostgresStatements:
    """Translate only the trusted reference store's fixed SQL, not request input.

    Its SQL is standard INSERT/SELECT/DELETE with SQLite '?' parameters. The
    PostgreSQL driver receives the same bound values as '%s' parameters. Schema
    qualification prevents search_path from redirecting encrypted writes.
    """
    def __init__(self, connection, table='scanplus.encrypted_records'):
        self.connection = connection
        if table not in ('scanplus.encrypted_records', 'pg_temp.encrypted_records'):
            raise SecureStorageError('Unsupported storage table')
        self.table = table

    def sql(self, statement):
        if 'encrypted_records' not in statement or ';' in statement:
            raise SecureStorageError('Unsupported storage operation')
        return statement.replace('encrypted_records', self.table).replace('?', '%s')

    def execute(self, statement, parameters=()):
        return self.connection.execute(self.sql(statement), parameters)

    def executemany(self, statement, parameters):
        with self.connection.cursor() as cursor:
            cursor.executemany(self.sql(statement), parameters)


class PostgresEncryptedStore(EncryptedStore):
    """Reuse audited AES-GCM, HMAC, paid-bundle and owner-check behavior.

    Each operation borrows a pooled connection for one explicit transaction.
    A transaction advisory lock serializes operations across app processes,
    preserving the reference store's replay/rotation semantics at modest scale.
    This deliberately favors correctness over high write throughput. Keys are
    external; this adapter neither generates nor saves them in the database.
    """
    _table = 'scanplus.encrypted_records'
    _lock_id = 1

    def __init__(self, settings, *, pool=None, clock=time.time):
        self._lock = RLock()
        self._clock = clock
        self._keys = {}
        self._active = settings.active_version
        self._ready = False
        self._conn = None
        self._owns_pool = pool is None
        try:
            if not settings.keys:
                raise ValueError()
            for version, key in settings.keys.items():
                self._keys[version] = self._derive(_key(version, key))
            if type(self._active) is not int or self._active not in self._keys:
                raise ValueError()
            if pool is None:
                validate_database_url(settings.database_url)
                pool = ConnectionPool(
                    settings.database_url, min_size=0, max_size=4, timeout=10,
                    max_idle=60, open=False,
                    kwargs={'autocommit': True, 'prepare_threshold': None,
                            'connect_timeout': 10, 'sslmode': 'verify-full',
                            'sslrootcert': 'system', 'channel_binding': 'require'},
                )
                pool.open()
            self._pool = pool
            with self._transaction():
                row = self._marker()
                if row is None:
                    any_row = self._conn.execute('SELECT id FROM encrypted_records LIMIT 1').fetchone()
                    if any_row:
                        raise ValueError()
                    self._save('key_check', 'key-check', {'marker': 'scanplus-v1', 'expires': None})
                else:
                    self._verify_marker(row)
            self._ready = True
        except Exception:
            if self._owns_pool and pool is not None:
                pool.close()
            raise SecureStorageError('Secure storage unavailable') from None

    def _marker(self):
        return self._conn.execute(
            "SELECT purpose,id,version,lookup,nonce,ciphertext FROM encrypted_records "
            "WHERE purpose='key_check' AND id='key-check'").fetchone()

    def _verify_marker(self, row):
        # The marker is the database's active-key protocol, not just a password
        # check. All writes use that version; only atomic rotate() may change it.
        # Otherwise two overlapping keyrings could create invisible blind indexes
        # and bypass paid-bundle replay protection.
        if (row is None or row[2] != self._active
                or self._open(row) != {'marker': 'scanplus-v1', 'expires': None}):
            raise SecureStorageError('Secure storage unavailable')
        versions = self._conn.execute('SELECT DISTINCT version FROM encrypted_records').fetchall()
        if {version[0] for version in versions} != {self._active}:
            raise SecureStorageError('Secure storage unavailable')

    @contextmanager
    def _transaction(self):
        with self._lock:
            try:
                with self._pool.connection() as connection:
                    with connection.transaction():
                        connection.execute("SET LOCAL statement_timeout = '10s'")
                        connection.execute("SET LOCAL lock_timeout = '5s'")
                        connection.execute('SELECT pg_advisory_xact_lock(1852141422, %s)', (self._lock_id,))
                        self._conn = _PostgresStatements(connection, self._table)
                        if self._ready:
                            self._verify_marker(self._marker())
                        yield
            except BaseException as error:
                if isinstance(error, (KeyboardInterrupt, SystemExit)):
                    raise
                raise SecureStorageError('Secure storage unavailable') from None
            finally:
                self._conn = None

    def close(self):
        with self._lock:
            if self._owns_pool:
                self._pool.close()


def create_neon_preview(resolve_identity, *, origin, verify_payment=None,
                        root=None, environ=None):
    """Wire env-backed Postgres into existing synthetic, authenticated WSGI flow.

    Trusted server adapters must supply identity and verified-payment evidence.
    This does not install demo identity in a public entry point or enable live
    customer records. The default secure_admin.application still fails closed.
    Return the store as well so the hosting process can close it on shutdown.
    """
    from secure_admin import create_preview
    store = PostgresEncryptedStore(settings_from_environment(root, environ))
    try:
        app = create_preview(store, resolve_identity, origin=origin, verify_payment=verify_payment)
        return app, store
    except BaseException:
        store.close()
        raise
