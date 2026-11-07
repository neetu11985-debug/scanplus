"""Synthetic-only staging checks. Test strings are NOT deployable owner credentials."""
import base64
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOST = 'synthetic-fixture.onrender.com'
USER = 'fixture'
PASSWORD = 'Synthetic-Only-Not-A-Secret-74829!'
AUTH = 'Basic ' + base64.b64encode((USER + ':' + PASSWORD).encode()).decode()


def environment():
    return dict(PATH=os.environ.get('PATH', ''), PYTHONDONTWRITEBYTECODE='1',
                RENDER='true', RENDER_EXTERNAL_HOSTNAME=HOST, SCANPLUS_STAGING_HOST=HOST,
                SCANPLUS_STAGING_USER=USER, SCANPLUS_STAGING_PASSWORD=PASSWORD,
                RENDER_GIT_COMMIT='a' * 40, SCANPLUS_MODE='live', SCANPLUS_STRIPE_TEST='1',
                SCANPLUS_SEARCH_PROVIDER='live', SCANPLUS_DB_PATH='/must-not-open.sqlite3')


class Configuration(unittest.TestCase):
    def run_code(self, code, changes=None):
        env = environment()
        env.update(changes or {})
        return subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT, env=env,
                              capture_output=True, text=True)

    def test_missing_or_weak_settings_fail_before_wsgi_import(self):
        code = "import sys;\ntry: import render_wsgi\nexcept RuntimeError: assert 'wsgi' not in sys.modules; sys.exit(0)\nraise AssertionError('accepted unsafe config')"
        for changes in ({'SCANPLUS_STAGING_USER': ''}, {'SCANPLUS_STAGING_PASSWORD': ''},
                        {'SCANPLUS_STAGING_PASSWORD': 'a' * 40},
                        {'SCANPLUS_STAGING_PASSWORD': 'short'},
                        {'SCANPLUS_STAGING_HOST': 'evil.example'},
                        {'RENDER_EXTERNAL_HOSTNAME': 'other.onrender.com'}, {'RENDER': ''}):
            with self.subTest(changes=list(changes)):
                result = self.run_code(code, changes)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_auth_parser_and_forced_fixture_configuration(self):
        code = r'''import base64, os
import render_wsgi as r
assert os.environ['SCANPLUS_MODE'] == 'demo'
assert os.environ['SCANPLUS_DB_PATH'] == ':memory:'
assert os.environ['SCANPLUS_STRIPE_TEST'] == '0'
assert os.environ['SCANPLUS_SEARCH_PROVIDER'] == 'disabled'
assert r.authenticated('Basic ' + base64.b64encode(b'fixture:Synthetic-Only-Not-A-Secret-74829!').decode())
for value in ('', 'Basic', 'Bearer aaa', 'Basic !!!', 'Basic \u2603', 'Basic ' + 'x'*10000, 'Basic Zm9vOmJhcg==', None):
    assert not r.authenticated(value)
'''
        result = self.run_code(code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_native_hostname_needs_no_duplicate_setting(self):
        result = self.run_code("import render_wsgi as r; assert r.HOST == 'synthetic-fixture.onrender.com'", {'SCANPLUS_STAGING_HOST': ''})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_revision_is_not_echoed(self):
        result = self.run_code("import render_wsgi as r; assert r.REVISION == ''", {'RENDER_GIT_COMMIT': 'bad\r\nheader'})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_start_script_overrides_render_defaults(self):
        text = (ROOT / 'deployment/render-start.sh').read_text()
        self.assertIn("export GUNICORN_CMD_ARGS=''", text)
        self.assertIn('--config gunicorn.conf.py render_wsgi:application', text)


@unittest.skipUnless(importlib.util.find_spec('gunicorn'), 'Install requirements-render.txt for Gunicorn integration')
class GunicornIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); cls.port = sock.getsockname()[1]
        env = environment()
        env.update(PORT=str(cls.port), GUNICORN_CMD_ARGS='--preload --access-logfile - --workers 3',
                   PATH=str(Path(sys.executable).parent) + os.pathsep + env['PATH'])
        cls.process = subprocess.Popen(['sh', 'deployment/render-start.sh', '--bind', '127.0.0.1:' + str(cls.port)], cwd=ROOT, env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for _ in range(100):
            if cls.process.poll() is not None:
                raise RuntimeError('Gunicorn startup failed: ' + cls.process.communicate()[1].decode())
            try:
                with socket.create_connection(('127.0.0.1', cls.port), timeout=.1): return
            except OSError: time.sleep(.05)
        cls.process.terminate(); cls.process.wait(timeout=5)
        raise RuntimeError('Gunicorn startup timeout')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        out, err = cls.process.communicate(timeout=10)
        if out or err:
            raise AssertionError('Staging server emitted unexpected logs')

    def call(self, path, payload=None, extra=None):
        headers = {'Host': HOST, 'X-Forwarded-Proto': 'https', 'Authorization': AUTH}
        headers.update(extra or {})
        headers = {k: v for k, v in headers.items() if v is not None}
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request('POST' if payload is not None else 'GET', path,
                     json.dumps(payload) if payload is not None else None, headers)
        response = conn.getresponse(); body = response.read(); result = (response.status, dict(response.getheaders()), body)
        conn.close()
        return result

    def test_auth_all_paths_and_boundaries(self):
        for path in ('/', '/app.js', '/style.css', '/api/session/status', '/api/report', '/api/staging/database', '/.env', '/server.py'):
            for auth in (None, 'Basic !!!', 'Basic Zm9vOmJhcg=='):
                status, headers, body = self.call(path, extra={'Authorization': auth})
                self.assertEqual(status, 401, path)
                self.assertIn('WWW-Authenticate', headers)
                self.assertEqual(headers['Cache-Control'], 'no-store')
                self.assertIn('noindex', headers['X-Robots-Tag'])
        for changes in ({'Host': 'evil.example'}, {'Host': HOST + ':443'},
                        {'Origin': 'https://evil.example'}, {'Origin': 'null'},
                        {'X-Forwarded-Proto': None}, {'X-Forwarded-Proto': 'http'},
                        {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.call('/', extra=changes)[0], 403)

    def test_authenticated_assets_and_private_files(self):
        for path in ('/app.js', '/style.css'):
            self.assertEqual(self.call(path)[0], 200)
        for path in ('/.env', '/server.py', '/render_wsgi.py', '/.data/scanplus-demo.sqlite3', '/%2e%2e/server.py'):
            self.assertEqual(self.call(path)[0], 404)
        for path in ('/api/stripe/status', '/api/stripe/webhook', '/stripe-test', '/stripe-test.js'):
            self.assertEqual(self.call(path)[0], 503)
        status, headers, body = self.call('/')
        self.assertEqual(status, 200)
        self.assertIn(b'PRIVATE SYNTHETIC STAGING', body)
        self.assertEqual(int(headers['Content-Length']), len(body))
        self.assertEqual(headers['X-ScanPlus-Release'], 'a' * 40)

    def test_full_synthetic_journey(self):
        headers = {'Origin': 'https://' + HOST}
        def api(path, data=None):
            status, response_headers, body = self.call('/api/' + path, data, headers)
            if 'Set-Cookie' in response_headers:
                headers['Cookie'] = response_headers['Set-Cookie'].split(';')[0]
                self.assertIn('Secure', response_headers['Set-Cookie'])
                self.assertIn('HttpOnly', response_headers['Set-Cookie'])
                self.assertIn('SameSite=Strict', response_headers['Set-Cookie'])
            result = json.loads(body)
            if 'csrf_token' in result: headers['X-CSRF-Token'] = result['csrf_token']
            return status, result
        self.assertEqual(api('start', {'phone': '+12025550147', 'consent': True})[0], 200)
        self.assertEqual(api('verify', {'code': '246810'})[0], 200)
        status, quote = api('quote', {})
        self.assertEqual((status, quote['amount_cents']), (200, 149))
        status, receipt = api('checkout', {'accept': True})
        self.assertEqual((status, receipt['charged_cents']), (200, 0))
        self.assertEqual(api('report')[1]['demo'], True)
        self.assertEqual(api('clear', {})[0], 200)
        self.assertEqual(api('report')[0], 403)

    def test_database_probe_is_private_read_only_and_missing_env_is_not_success(self):
        status, headers, body = self.call('/api/staging/database')
        self.assertEqual(status, 503)
        result = json.loads(body)
        self.assertEqual(result['database'], 'not_configured')
        self.assertFalse(result['customer_storage_enabled'])
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(self.call('/api/staging/database?sql=SELECT1')[0], 400)
        self.assertEqual(self.call('/api/staging/database', payload={})[0], 405)


if __name__ == '__main__': unittest.main()
