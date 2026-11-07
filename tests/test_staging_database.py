"""Offline staging DB probe checks. No real credential, database or Neon call."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import Mock

from staging_database import DatabaseProbe
from test_render_staging import environment, ROOT

URL = 'postgresql://fixture:NOT_A_SECRET@ep-fixture-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require'


class FakeConnection:
    def __init__(self, result=(1,), failure=None):
        self.result = result
        self.failure = failure
        self.statements = []
        self.transactions = 0
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    @contextmanager
    def transaction(self):
        self.transactions += 1
        yield

    def execute(self, statement):
        self.statements.append(statement)
        if self.failure:
            raise self.failure
        return self

    def fetchone(self):
        return self.result


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.connection = FakeConnection()
        self.connect = Mock(return_value=self.connection)
        self.env = {'DATABASE_URL': URL}
        self.probe = DatabaseProbe(connect=self.connect, environ=self.env, clock=lambda: self.now)

    def test_no_secret_access_or_connection_on_initialization(self):
        class UnreadableEnvironment:
            def get(self, *args):
                raise AssertionError('Secret read on construction')
        DatabaseProbe(connect=self.connect, environ=UnreadableEnvironment())
        self.connect.assert_not_called()

    def test_read_only_fixed_query_tls_timeouts_and_no_sensitive_response(self):
        status, body = self.probe.check()
        self.assertEqual(status, 200)
        self.assertEqual(body['database'], 'reachable')
        self.assertFalse(body['customer_storage_enabled'])
        self.assertFalse(body['cached'])
        self.assertEqual(self.connection.transactions, 1)
        self.assertTrue(self.connection.closed)
        self.assertEqual(self.connection.statements, [
            'SET TRANSACTION READ ONLY', "SET LOCAL statement_timeout = '5s'", 'SELECT 1'])
        kwargs = self.connect.call_args.kwargs
        self.assertEqual(kwargs['sslmode'], 'verify-full')
        self.assertEqual(kwargs['sslrootcert'], 'system')
        self.assertEqual(kwargs['channel_binding'], 'require')
        self.assertEqual(kwargs['connect_timeout'], 5)
        self.assertIsNone(kwargs['prepare_threshold'])
        for value in ('NOT_A_SECRET', 'ep-fixture', URL, 'neondb'):
            self.assertNotIn(value, json.dumps(body))

    def test_missing_url_does_not_connect(self):
        self.env.clear()
        status, body = self.probe.check()
        self.assertEqual(status, 503)
        self.assertEqual(body['database'], 'not_configured')
        self.connect.assert_not_called()

    def test_bad_url_fails_closed_without_connecting(self):
        for value in ('PRIVATE', URL.replace('neon.tech', 'attacker.invalid'),
                      URL.replace('sslmode=require', 'sslmode=disable'), 'x' * 8193):
            with self.subTest(kind=len(value)):
                probe = DatabaseProbe(connect=self.connect, environ={'DATABASE_URL': value})
                status, body = probe.check()
                self.assertEqual(status, 503)
                self.assertEqual(body['database'], 'unavailable')
                self.assertNotIn(value, json.dumps(body))
        self.connect.assert_not_called()

    def test_errors_never_echo_connection_details_or_log(self):
        for failure in (RuntimeError(URL), TimeoutError('NOT_A_SECRET'), OSError('ep-fixture')):
            with self.subTest(error=type(failure).__name__):
                probe = DatabaseProbe(connect=Mock(side_effect=failure), environ=self.env)
                output = io.StringIO()
                with redirect_stderr(output), redirect_stdout(output):
                    status, body = probe.check()
                self.assertEqual(status, 503)
                self.assertEqual(output.getvalue(), '')
                self.assertNotIn('NOT_A_SECRET', json.dumps(body))
                self.assertNotIn('ep-fixture', json.dumps(body))

    def test_unexpected_result_or_query_error_cannot_pass(self):
        for connection in (FakeConnection(result=(2,)), FakeConnection(failure=RuntimeError(URL))):
            probe = DatabaseProbe(connect=Mock(return_value=connection), environ=self.env)
            status, body = probe.check()
            self.assertEqual(status, 503)
            self.assertEqual(body['database'], 'unavailable')
            self.assertTrue(connection.closed)

    def test_success_and_error_cache_expiry_bounds(self):
        first = self.probe.check()
        self.now += 29
        status, body = self.probe.check()
        self.assertTrue(body['cached'])
        self.assertEqual(body['checked_seconds_ago'], 29)
        self.connect.assert_called_once()
        self.now += 1
        self.connect.side_effect = TimeoutError(URL)
        status, body = self.probe.check()
        self.assertEqual(status, 503)
        self.assertFalse(body['cached'])
        self.assertEqual(self.connect.call_count, 2)
        self.assertTrue(self.probe.check()[1]['cached'])
        self.assertEqual(self.connect.call_count, 2)


class RenderProbeBoundaryTests(unittest.TestCase):
    def test_auth_origin_method_and_parameter_gates_before_probe(self):
        code = r'''
import base64, io, json
from unittest.mock import Mock
import render_wsgi as r
r.DATABASE_PROBE.check = Mock(return_value=(200, {'database':'reachable','customer_storage_enabled':False}))
auth = 'Basic ' + base64.b64encode(b'fixture:Synthetic-Only-Not-A-Secret-74829!').decode()
def call(**overrides):
    env = {'REQUEST_METHOD':'GET','PATH_INFO':'/api/staging/database','QUERY_STRING':'',
           'wsgi.url_scheme':'https','HTTP_HOST':'synthetic-fixture.onrender.com',
           'HTTP_AUTHORIZATION':auth,'wsgi.input':io.BytesIO(b'')}
    env.update(overrides)
    result = {}
    def start(status,headers,exc_info=None): result.update(status=status,headers=dict(headers))
    result['body'] = b''.join(r.application(env,start))
    return result
for changes, expected in (({'HTTP_AUTHORIZATION':''},'401'),
        ({'HTTP_HOST':'attacker.invalid'},'403'),({'wsgi.url_scheme':'http'},'403'),
        ({'HTTP_ORIGIN':'https://attacker.invalid'},'403'),
        ({'HTTP_SEC_FETCH_SITE':'cross-site'},'403'),
        ({'REQUEST_METHOD':'POST'},'405'),({'QUERY_STRING':'sql=DROP'},'400')):
    assert call(**changes)['status'].startswith(expected)
    assert r.DATABASE_PROBE.check.call_count == 0
result = call()
assert result['status'] == '200 OK'
assert json.loads(result['body'])['customer_storage_enabled'] is False
assert result['headers']['Cache-Control'] == 'no-store'
assert result['headers']['X-Content-Type-Options'] == 'nosniff'
assert result['headers']['X-ScanPlus-Release'] == 'a'*40
assert r.DATABASE_PROBE.check.call_count == 1
'''
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                                env=environment(), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
