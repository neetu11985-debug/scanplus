import http.client
import json
import sys
import threading
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from storage import Store

class Journey(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=server.LocalHTTPServer(('127.0.0.1',0),server.Handler)
        cls.port=cls.http.server_address[1]
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.http.shutdown(); cls.http.server_close()
    def setUp(self):
        server.STORE.close(); server.STORE=Store(); self.addCleanup(lambda:server.STORE.close()); self.cookie=''; self.csrf=''
    def req(self,path,data=None,origin=True):
        c=http.client.HTTPConnection('127.0.0.1',self.port)
        headers={'Cookie':self.cookie,'X-CSRF-Token':self.csrf}
        if origin: headers['Origin']=f'http://127.0.0.1:{self.port}'
        body=json.dumps(data) if data is not None else None
        c.request('POST' if data is not None else 'GET','/api/'+path,body,headers)
        r=c.getresponse(); raw=r.read(); cookie=r.getheader('Set-Cookie')
        if cookie: self.cookie=cookie.split(';')[0]
        status=r.status; c.close(); result=json.loads(raw)
        if 'csrf_token' in result:self.csrf=result['csrf_token']
        return status,result
    def start(self): return self.req('start',{'phone':server.PHONE,'consent':True})
    def ready(self):
        self.start(); self.req('verify',{'code':'246810'}); self.req('checkout',{'accept':True})
    def test_complete_journey_and_synthetic_removal(self):
        self.assertEqual(self.start()[0],200)
        self.assertEqual(self.req('verify',{'code':'246810'})[0],200)
        status,payment=self.req('checkout',{'accept':True,'amount_cents':0})
        self.assertEqual(status,200); self.assertEqual(payment['amount_cents'],99); self.assertEqual(payment['charged_cents'],0)
        status,report=self.req('report'); self.assertEqual(status,200)
        self.assertTrue(report['demo']); self.assertEqual(len(report['providers']),3)
        self.assertTrue(all(p['source_url'] is None for p in report['providers']))
        self.assertEqual(self.req('removal',{'provider':'fixture','authorize':True})[1]['status'],'request_submitted')
        self.assertEqual(self.req('removal/status',{})[1]['status'],'pending')
        self.assertEqual(self.req('removal/status',{})[1]['status'],'removal_confirmed')
    def test_real_numbers_and_cross_origin_rejected(self):
        self.assertEqual(self.req('start',{'phone':'+12025550149','consent':True})[0],400)
        self.assertEqual(self.req('start',{'phone':server.PHONE,'consent':True},False)[0],403)
        self.assertEqual(server.STORE.conn.execute("SELECT COUNT(*) FROM records WHERE kind='session'").fetchone()[0],0)
    def test_server_gates_and_rate_limit(self):
        self.assertEqual(self.req('report')[0],403)
        self.start(); self.assertEqual(self.req('checkout',{'accept':True})[0],403)
        for _ in range(5): self.assertEqual(self.req('verify',{'code':'wrong'})[0],400)
        self.assertEqual(self.req('verify',{'code':'246810'})[0],429)
    def test_authorization_and_live_removal(self):
        self.ready()
        self.assertEqual(self.req('removal',{'provider':'fixture','authorize':False})[0],400)
        self.assertEqual(self.req('removal',{'provider':'spokeo','authorize':True})[0],409)
        self.assertEqual(self.req('report')[1]['removal'],'not_requested')
    def test_expiry_and_clear(self):
        self.ready(); self.req('clear',{})
        self.assertEqual(self.req('report')[0],403)
        self.start()
        with server.STORE.transaction():server.STORE.conn.execute("UPDATE records SET expires=0 WHERE kind='session'")
        self.assertEqual(self.req('verify',{'code':'246810'})[0],401)
        self.assertEqual(server.STORE.conn.execute("SELECT COUNT(*) FROM records WHERE kind='session'").fetchone()[0],0)
    def test_duplicate_checkout_is_idempotent(self):
        self.ready()
        first=self.req('checkout',{'accept':True})[1]
        second=self.req('checkout',{'accept':True})[1]
        self.assertEqual(first,second)
        self.assertEqual(second['charged_cents'],0)

    def test_unknown_endpoint(self):
        self.ready(); self.assertEqual(self.req('missing',{})[0],404)

if __name__=='__main__': unittest.main(verbosity=2)
