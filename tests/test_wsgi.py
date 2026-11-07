import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import io,json,os,unittest
from wsgiref.util import setup_testing_defaults
from wsgiref.validate import validator
from unittest.mock import patch
import server
from wsgi import application
from storage import Store

class WSGITests(unittest.TestCase):
    def setUp(self):
        server.STORE.close();server.STORE=Store();self.addCleanup(lambda:server.STORE.close());self.cookie='';self.csrf=''
        self.allowed=patch.dict(os.environ,{'SCANPLUS_ALLOWED_ORIGINS':'https://scanplus.test,http://scanplus.test'});self.allowed.start();self.addCleanup(self.allowed.stop)
    def call(self,path,body=None,scheme='https',method=None):
        env={};setup_testing_defaults(env)
        raw=json.dumps(body).encode() if body is not None else b''
        env.update(QUERY_STRING='',PATH_INFO=path,REQUEST_METHOD=method or ('POST' if body is not None else 'GET'),CONTENT_LENGTH=str(len(raw)),HTTP_HOST='scanplus.test',HTTP_ORIGIN=scheme+'://scanplus.test',HTTP_COOKIE=self.cookie,HTTP_X_CSRF_TOKEN=self.csrf)
        env['wsgi.url_scheme']=scheme;env['wsgi.input']=io.BytesIO(raw)
        response={}
        def start(status,headers,exc_info=None):response.update(status=status,headers=dict(headers))
        iterator=validator(application)(env,start)
        try:response['body']=b''.join(iterator)
        finally:iterator.close()
        if 'Set-Cookie' in response['headers']: self.cookie=response['headers']['Set-Cookie'].split(';')[0]
        try:self.csrf=json.loads(response['body']).get('csrf_token',self.csrf)
        except (ValueError,AttributeError):pass
        return response
    def test_wsgi_full_demo_and_secure_cookie(self):
        r=self.call('/api/start',{'phone':server.PHONE,'consent':True});self.assertTrue(r['status'].startswith('200'));self.assertIn('Secure',r['headers']['Set-Cookie'])
        self.assertTrue(self.call('/api/verify',{'code':'246810'})['status'].startswith('200'))
        self.assertTrue(self.call('/api/checkout',{'accept':True})['status'].startswith('200'))
        report=self.call('/api/report');self.assertTrue(json.loads(report['body'])['demo'])
        self.call('/api/clear',{});self.assertTrue(self.call('/api/report')['status'].startswith('403'))
    def test_wsgi_static_and_method(self):
        self.assertIn(b'phone privacy',self.call('/')['body'])
        self.assertTrue(self.call('/',method='DELETE')['status'].startswith('405'))
    def test_live_wsgi_mode_rejected(self):
        with patch.dict(os.environ,{'SCANPLUS_MODE':'live'}):self.assertTrue(self.call('/')['status'].startswith('503'))
