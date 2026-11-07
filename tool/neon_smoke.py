"""Opt-in real Neon/psycopg/HTTP smoke; synthetic data, TEMP table, outer rollback.

Run only after authenticating and verifying the intended project/branch. It uses
DATABASE_URL_UNPOOLED, never logs it, and never creates a persistent table or key.
Identity, payment and the HTTPS ingress flag are synthetic test adapters. This
does not qualify real authentication, payments, public TLS or production rollout.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
from wsgiref.simple_server import WSGIRequestHandler, make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg
from neon_storage import NeonSettings, PostgresEncryptedStore, read_environment, validate_database_url
from secure_admin import Principal, PaidStorageGrant, create_preview, PHONE, REPORT


class TempStore(PostgresEncryptedStore):
    _table = 'pg_temp.encrypted_records'
    _lock_id = 2  # Separate from application writes.


class SingleConnectionPool:
    def __init__(self, connection):
        self.conn = connection

    @contextmanager
    def connection(self):
        yield self.conn


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


def run_http(store):
    state = {'paid': False}
    expiry = time.time() + 120
    csrf = 'PUBLIC_SYNTHETIC_CSRF_FIXTURE_0123456789'
    def identity(env):
        # Only this loopback test runner recognizes these public fixture cookies.
        owner = {'fixture=a': 'fixture_owner_a', 'fixture=b': 'fixture_owner_b'}.get(env.get('HTTP_COOKIE'))
        return Principal(owner, 'customer', expiry, csrf) if owner else None
    def payment(principal):
        return PaidStorageGrant(principal.owner_id, 'fixture_paid_order_1', 149, 'USD', expiry) if state['paid'] else None
    app = create_preview(store, identity, origin='https://security.example.invalid', verify_payment=payment)
    def ingress(env, start_response):
        env['wsgi.url_scheme'] = 'https'  # Synthetic TLS-terminating ingress, NOT a real TLS test.
        return app(env, start_response)
    server = make_server('127.0.0.1', 0, ingress, handler_class=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    opener = build_opener(ProxyHandler({}))
    def call(path, body=None, cookie='fixture=a'):
        data = None if body is None else json.dumps(body).encode()
        req = Request(f'http://127.0.0.1:{server.server_port}' + path, data=data,
            headers={'Host': 'security.example.invalid', 'Origin': 'https://security.example.invalid',
                     'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'Cookie': cookie})
        try:
            response = opener.open(req, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read(), response.headers
    try:
        status, _, _ = call('/api/security/demo-record', {'confirm_synthetic': True})
        assert status == 402, 'Unpaid write was not rejected'
        assert store.find_phone('fixture_owner_a', PHONE) is None
        print('PASS: running WSGI app rejects unpaid persistence (HTTP 402).')
        state['paid'] = True
        status, raw, _ = call('/api/security/demo-record', {'confirm_synthetic': True})
        assert status == 201, 'Paid synthetic write failed'
        saved = json.loads(raw)
        status, raw, _ = call('/api/security/demo-record', {'confirm_synthetic': True})
        assert status == 201 and json.loads(raw)['report_id'] == saved['report_id']
        status, raw, headers = call(saved['download_url'])
        assert status == 200 and raw.decode() == REPORT
        assert 'attachment;' in headers.get('Content-Disposition', '')
        assert call(saved['download_url'], cookie='fixture=b')[0] == 404
        assert call(saved['download_url'], cookie='')[0] == 401
        print('PASS: paid save, idempotent retry and owner text download over HTTP; other user 404, anonymous 401.')
        return saved['report_id']
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main():
    values = read_environment()
    if values.get('SCANPLUS_NEON_SMOKE') != '1':
        print('NOT RUN: set SCANPLUS_NEON_SMOKE=1 after verifying the target and secure credentials.')
        return 2
    try:
        url = validate_database_url(values.get('DATABASE_URL_UNPOOLED'), direct=True)
        with psycopg.connect(url, autocommit=True, connect_timeout=10, prepare_threshold=None,
                            sslmode='verify-full', sslrootcert='system', channel_binding='require') as connection:
            with connection.transaction(force_rollback=True):
                connection.execute('CREATE TEMP TABLE encrypted_records (purpose TEXT NOT NULL, id TEXT PRIMARY KEY, version INTEGER NOT NULL, lookup BYTEA NOT NULL, nonce BYTEA NOT NULL, ciphertext BYTEA NOT NULL, UNIQUE(purpose,lookup)) ON COMMIT DROP')
                pool = SingleConnectionPool(connection)
                # Public, disposable fixture key; never deploy this key or save it.
                settings = NeonSettings(url, {1: bytes(range(32))}, 1)
                store = TempStore(settings, pool=pool)
                report_id = run_http(store)
                rows = connection.execute('SELECT purpose,id,version,lookup,nonce,ciphertext FROM pg_temp.encrypted_records').fetchall()
                for row in rows:
                    for column in row:
                        raw = column if isinstance(column, bytes) else str(column).encode()
                        assert PHONE.encode() not in raw and REPORT.encode() not in raw
                        assert b'fixture_owner_a' not in raw
                reopened = TempStore(settings, pool=pool)
                assert reopened.get_report(report_id, 'fixture_owner_a') == REPORT
                print('PASS: real Postgres contains ciphertext, not fixture PII; new adapter instance decrypts authorized report.')
        print('PASS: Neon smoke complete; TEMP table and synthetic writes rolled back. No live auth/payment/TLS proof.')
        return 0
    except Exception:
        # No exception repr/traceback: database errors can include credentials or SQL data.
        print('FAILED: Neon integration smoke did not complete. No production success is claimed; inspect credentials/network and rerun safely.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
