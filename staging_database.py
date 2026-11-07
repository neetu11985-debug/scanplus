"""On-demand read-only connectivity probe. No schema, customer data or key writes.

Only the authenticated Render wrapper exposes this probe. Import/startup never
reads DATABASE_URL or opens a connection. Results are cached briefly to avoid
waking a Neon compute repeatedly; exceptions and connection details stay private.
"""
import os
from threading import Lock
import time

import psycopg
from neon_storage import validate_database_url


class DatabaseProbe:
    def __init__(self, *, connect=None, environ=None, clock=time.monotonic):
        self._connect = connect or psycopg.connect
        self._environ = os.environ if environ is None else environ
        self._clock = clock
        self._lock = Lock()
        self._cached = None
        self._checked_at = 0.0

    def check(self):
        with self._lock:
            now = self._clock()
            if self._cached is not None and 0 <= now - self._checked_at < 30:
                status, result = self._cached
                return status, {**result, 'cached': True,
                                'checked_seconds_ago': int(now - self._checked_at)}
            result = {'database': 'unavailable', 'customer_storage_enabled': False,
                      'error': 'Database connection could not be verified.'}
            status = 503
            try:
                value = self._environ.get('DATABASE_URL', '')
                if not value:
                    result = {'database': 'not_configured', 'customer_storage_enabled': False,
                              'error': 'DATABASE_URL has not been configured for this service.'}
                else:
                    if not isinstance(value, str) or len(value) > 8192:
                        raise ValueError()
                    validate_database_url(value)
                    with self._connect(value, connect_timeout=5, autocommit=True,
                                       prepare_threshold=None, sslmode='verify-full',
                                       sslrootcert='system', channel_binding='require') as connection:
                        with connection.transaction():
                            connection.execute('SET TRANSACTION READ ONLY')
                            connection.execute("SET LOCAL statement_timeout = '5s'")
                            if connection.execute('SELECT 1').fetchone() != (1,):
                                raise ValueError()
                    status = 200
                    result = {'database': 'reachable', 'check': 'SELECT 1',
                              'customer_storage_enabled': False}
            except Exception:
                # Database/provider exceptions can contain credentials, hostnames,
                # SQL or other private values. Never log or serialize them.
                pass
            self._checked_at = self._clock()
            self._cached = status, result
            return status, {**result, 'cached': False, 'checked_seconds_ago': 0}


DATABASE_PROBE = DatabaseProbe()
