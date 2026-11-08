"""Restart-safe private-test attempt reservation. No automatic schema or grants.

Only an opaque run ID, operation kind and counters reach the allowance database.
No phone, OTP, result, provider key or user-entered data is accepted by this API.
"""
from uuid import UUID
from neon_storage import validate_database_url
from live_scan import ProviderNotDispatched

LIMITS = {'sms': 1, 'checks': 5, 'searches': 3}


class AllowanceUnavailable(ProviderNotDispatched):
    pass


def validate_run_id(value):
    try:
        parsed = UUID(value)
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError()
    except (TypeError, ValueError, AttributeError):
        raise AllowanceUnavailable('A separately approved private-test run ID is required.') from None
    return value


class PostgresAllowance:
    """Commit an atomic server-defined reservation before any provider dispatch.

    Initialization validates configuration only. No database connection occurs
    until an explicit provider operation reaches consume(). Any failure,
    including uncertain commit, is fail-closed with no automatic retry.
    """
    statement = 'SELECT scanplus.consume_owner_test_allowance(%s::uuid, %s)'

    def __init__(self, database_url, run_id, *, connect=None):
        self._url = validate_database_url(database_url)
        self._run_id = validate_run_id(run_id)
        self._connect = connect

    def consume(self, kind):
        if kind not in LIMITS:
            raise AllowanceUnavailable('Unsupported private-test allowance operation.')
        try:
            connect = self._connect
            if connect is None:
                import psycopg
                connect = psycopg.connect
            with connect(self._url, sslmode='verify-full', sslrootcert='system', channel_binding='require',
                         connect_timeout=5,
                         options='-c statement_timeout=5000 -c lock_timeout=2000') as connection:
                with connection.cursor() as cursor:
                    cursor.execute(self.statement, (self._run_id, kind))
                    row = cursor.fetchone()
                    used = row[0] if row else None
                    if type(used) is not int or not 1 <= used <= LIMITS[kind]:
                        raise AllowanceUnavailable()
            # Exiting the connection context has confirmed commit before return.
            return used
        except Exception:
            raise AllowanceUnavailable('The durable test allowance is unavailable, expired or used. No provider request was sent; ask the operator to review the run.') from None
