"""Exact Render wrapper with only mocked Stripe and local synthetic encryption."""
import base64
import json
import subprocess
import sys
import unittest
import test_render_staging as staging


class RenderSandboxTests(unittest.TestCase):
    def run_code(self, code, changes=None):
        env = staging.environment()
        env.update(SCANPLUS_RELEASE_PROFILE='sandbox',
                   STRIPE_SECRET_KEY='sk_test_fixture_not_a_credential',
                   STRIPE_WEBHOOK_SECRET='whsec_fixture_not_a_credential',
                   DATABASE_URL='postgresql://fixture:synthetic@ep-fixture-pooler.us-east-2.aws.neon.tech/fixture?sslmode=require',
                   SCANPLUS_STORAGE_KEYS_JSON=json.dumps({'1': base64.b64encode(b'R' * 32).decode()}),
                   SCANPLUS_STORAGE_ACTIVE_VERSION='1')
        env.update(changes or {})
        return subprocess.run([sys.executable, '-B', '-c', code], cwd=staging.ROOT,
                              env=env, capture_output=True, text=True)

    def test_invalid_sandbox_configuration_fails_before_app_import(self):
        code = "import sys\ntry: import render_wsgi\nexcept Exception: assert 'wsgi' not in sys.modules; sys.exit(0)\nraise AssertionError('unsafe sandbox config')"
        for changes in ({'STRIPE_SECRET_KEY': ''}, {'STRIPE_SECRET_KEY': 'sk_live_fixture'},
                        {'STRIPE_WEBHOOK_SECRET': ''}, {'DATABASE_URL': ''},
                        {'SCANPLUS_STORAGE_KEYS_JSON': '{}'}, {'SCANPLUS_RELEASE_PROFILE': 'live'}):
            with self.subTest(change=list(changes)):
                result = self.run_code(code, changes)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_startup_validation_never_connects_database(self):
        code = """from unittest.mock import patch
with patch('psycopg_pool.ConnectionPool', side_effect=AssertionError('unexpected connection')):
 import render_wsgi as r
 import os
 assert r.SANDBOX
 assert os.environ['SCANPLUS_DB_PATH'] == ':memory:'
 assert os.environ['SCANPLUS_SESSION_TTL'] == '900'
 assert os.environ['SCANPLUS_STRIPE_ORIGIN'] == 'https://' + r.HOST
 assert os.environ['SCANPLUS_ENCRYPTED_REPORTS'] == '1'
"""
        result = self.run_code(code)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_protected_wrapper_payment_encryption_download_and_signed_webhook(self):
        code = r'''import sys, io, json, base64, os
sys.path.insert(0, 'tests')
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults
from test_stripe_checkout import FakeStripe, signed
from encrypted_storage import EncryptedStore
from secure_reports import SandboxReports
import render_wsgi as r
fake = FakeStripe()
encrypted = EncryptedStore(':memory:', {1: b'Z' * 32}, 1)
cookie = ''; csrf = ''
auth = 'Basic ' + base64.b64encode((os.environ['SCANPLUS_STAGING_USER'] + ':' + os.environ['SCANPLUS_STAGING_PASSWORD']).encode()).decode()
def call(path, data=None, *, logged_in=True, raw=None, signature=None, query=''):
 global cookie, csrf
 env = {}; setup_testing_defaults(env)
 body = raw if raw is not None else (json.dumps(data).encode() if data is not None else b'')
 env.update(PATH_INFO=path, REQUEST_METHOD='POST' if data is not None or raw is not None else 'GET',
            HTTP_HOST=r.HOST, HTTP_COOKIE=cookie, HTTP_X_CSRF_TOKEN=csrf,
            CONTENT_LENGTH=str(len(body)), QUERY_STRING=query)
 env['wsgi.url_scheme']='https'; env['wsgi.input']=io.BytesIO(body)
 if logged_in: env['HTTP_AUTHORIZATION']=auth; env['HTTP_ORIGIN']='https://' + r.HOST
 if signature: env['HTTP_STRIPE_SIGNATURE']=signature
 result={}
 def start(status, headers, exc_info=None): result.update(status=int(status.split()[0]), headers=dict(headers))
 result['raw']=b''.join(r.application(env,start))
 if 'Set-Cookie' in result['headers']: cookie=result['headers']['Set-Cookie'].split(';')[0]
 try:
  result['body']=json.loads(result['raw']); csrf=result['body'].get('csrf_token',csrf)
 except ValueError: pass
 return result
with patch('stripe_checkout.request',fake), patch('secure_reports.REPORTS', SandboxReports(lambda: encrypted)):
 for path in ('/', '/stripe-test', '/stripe-test.js', '/api/stripe/status', '/api/stripe/report/download'):
  assert call(path,logged_in=False)['status']==401, path
 assert call('/api/stripe/webhook',logged_in=False)['status']==405
 assert call('/api/stripe/webhook',raw=b'{}',logged_in=False)['status']==400
 assert call('/api/stripe/webhook',raw=b'{}',logged_in=False,query='x=1')['status']==405
 assert call('/api/stripe/status',query='owner=x')['status']==400
 assert b'PRIVATE STRIPE SANDBOX' in call('/')['raw']
 assert call('/api/start',{'phone':'+12025550147','consent':True})['status']==200
 assert call('/api/verify',{'code':'246810'})['status']==200
 assert call('/api/stripe/report/save',{'confirm_synthetic':True})['status']==402
 assert call('/api/stripe/checkout',{'accept_test':True})['status']==200
 fake.paid()
 event={'id':'evt_render_fixture','livemode':False,'type':'checkout.session.completed','data':{'object':fake.result}}
 body, signature=signed(event)
 assert call('/api/stripe/webhook',raw=body,signature=signature,logged_in=False)['status']==200
 assert call('/api/stripe/report/save',{'confirm_synthetic':True})['status']==200
 download=call('/api/stripe/report/download')
 assert download['status']==200
 assert b'SYNTHETIC STRIPE SANDBOX' in download['raw']
 assert download['headers']['Cache-Control']=='no-store'
 assert call('/api/clear',{})['status']==200
 assert call('/api/stripe/report/download')['status']==403
encrypted.close()
'''
        result = self.run_code(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
