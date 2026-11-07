import sys,time,tempfile,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_server as journey
import server
from storage import Store,digest
from history import DemoHistory,eligible,WEEK
from refunds import RefundHarness,SyntheticRefundTransport

class HistoryReturn(unittest.TestCase):
    setUpClass=classmethod(journey.Journey.setUpClass.__func__);tearDownClass=classmethod(journey.Journey.tearDownClass.__func__)
    setUp=journey.Journey.setUp;req=journey.Journey.req;start=journey.Journey.start;ready=journey.Journey.ready
    def test_expiry_fresh_reauth_and_wrong_user(self):
        self.ready();receipt=self.req('checkout',{'accept':True})[1];old=(self.cookie,self.csrf)
        key=digest(self.cookie.split('=',1)[1])
        with server.STORE.transaction():server.STORE.conn.execute("UPDATE records SET expires=0 WHERE kind='session' AND id=?",(key,))
        self.assertEqual(self.req('history')[0],403)
        self.cookie='';self.csrf='';self.req('start',{'phone':server.FIXTURE_PHONES[1],'consent':True});self.req('verify',{'code':'246810'})
        self.assertEqual(self.req('history')[1]['payments'],[])
        self.assertEqual(self.req('refund',{'payment_id':receipt['payment_id'],'confirm':True})[0],404)
        self.cookie='';self.csrf='';self.start();self.assertEqual(self.req('history')[0],403)
        verified=self.req('verify',{'code':'246810'})[1];self.assertTrue(verified['has_history'])
        self.assertEqual(self.req('history')[1]['payments'][0]['payment_id'],receipt['payment_id'])
        first=self.req('refund',{'payment_id':receipt['payment_id'],'confirm':True})
        self.assertEqual(first[0],200);self.assertEqual(first,self.req('refund',{'payment_id':receipt['payment_id'],'confirm':True}))
        self.cookie,self.csrf=old;self.assertEqual(self.req('history')[0],403)
    def test_exact_boundary_outside_and_exception(self):
        now=time.time();self.assertTrue(eligible(now-WEEK,now));self.assertFalse(eligible(now-WEEK-.001,now))
        owner='fixture-owner';h=DemoHistory(server.STORE)
        for key,created in [('exact',now-WEEK),('outside',now-WEEK-.001)]:
            with server.STORE.transaction():h.save(owner,{'payment_id':key,'created_at':created,'charged_cents':0,'currency':'USD','mode':'test'})
        with server.STORE.transaction():self.assertEqual(h.request(owner,'exact',True,now=now)['refund_cents'],0)
        with server.STORE.transaction():
            with self.assertRaises(ValueError):h.request(owner,'outside',True,now=now)
            self.assertEqual(h.request(owner,'outside',True,category='non_delivery',now=now)['status'],'manual_review')
    def test_history_delete_and_retention(self):
        self.ready();self.assertEqual(self.req('history/delete',{'confirm':False})[0],400)
        self.assertEqual(self.req('history/delete',{'confirm':True})[0],200);self.assertEqual(self.req('history')[1]['payments'],[])
        self.assertEqual(self.req('report')[0],403)
        with server.STORE.transaction():
            h=DemoHistory(server.STORE);h.save('fixture-owner',{'payment_id':'expire','created_at':time.time()-9*86400,'charged_cents':0,'currency':'USD','mode':'test'})
            server.STORE.prune()
            self.assertEqual(h.items('fixture-owner'),[])
    def test_history_requires_fresh_verification_and_type_safe_request(self):
        self.start();self.assertEqual(self.req('verify',{'code':'246810','phone':[]})[0],400)
        self.req('verify',{'code':'246810'});self.req('checkout',{'accept':True})
        key=digest(self.cookie.split('=',1)[1])
        with server.STORE.transaction():
            s=server.STORE.get('session',key,key);s['verified_at']=0;server.STORE.put('session',key,key,s['expires'],s)
        self.assertEqual(self.req('history')[0],403);self.assertEqual(self.req('refund',{'confirm':True})[0],403)
    def test_concurrent_history_request_one_record(self):
        owner='fixture-owner';h=DemoHistory(server.STORE)
        with server.STORE.transaction():h.save(owner,{'payment_id':'concurrent','created_at':time.time(),'charged_cents':0,'currency':'USD','mode':'test'})
        def ask(_):
            with server.STORE.transaction():return h.request(owner,'concurrent',True)
        with ThreadPoolExecutor(8) as pool:results=list(pool.map(ask,range(16)))
        self.assertTrue(all(r==results[0] for r in results))
        self.assertEqual(server.STORE.conn.execute("SELECT COUNT(*) FROM records WHERE kind='demo_refund'").fetchone()[0],1)

class PartialRefundBoundaries(unittest.TestCase):
    def test_exact_outside_fee_unknown_full_override_and_restart(self):
        now=time.time()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'refund.db';store=Store(path);transport=SyntheticRefundTransport('succeeded');h=RefundHarness(store,transport)
            h.record_fixture_payment('fixture-boundary','a',100,'USD',17,'USD',created=now-WEEK)
            self.assertEqual(h.request('fixture-boundary','a',now=now)['amount_cents'],83)
            h.record_fixture_payment('fixture-out','a',100,'USD',17,'USD',created=now-WEEK-.001)
            with self.assertRaises(ValueError):h.request('fixture-out','a',now=now)
            h.record_fixture_payment('fixture-full','a',100,'USD',None,None)
            self.assertEqual(h.request('fixture-full','a',category='non_delivery')['status'],'manual_review')
            with self.assertRaises(ValueError):h.approve_full_fixture('fixture-full','a','unapproved')
            self.assertEqual(h.approve_full_fixture('fixture-full','a','fixture-review-approved')['amount_cents'],100)
            store.close();store=Store(path);again=SyntheticRefundTransport();h=RefundHarness(store,again)
            self.assertEqual(h.request('fixture-full','a')['amount_cents'],100);self.assertEqual(again.calls,[]);store.close()

class DownloadArtifact(unittest.TestCase):
    setUpClass=classmethod(journey.Journey.setUpClass.__func__);tearDownClass=classmethod(journey.Journey.tearDownClass.__func__)
    setUp=journey.Journey.setUp;req=journey.Journey.req;start=journey.Journey.start;ready=journey.Journey.ready
    def test_http_export_downloaded_bytes(self):
        import http.client,json
        self.ready();connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
        connection.request('GET','/api/export',headers={'Cookie':self.cookie,'Origin':f'http://127.0.0.1:{self.port}'})
        response=connection.getresponse();raw=response.read();self.assertEqual(response.status,200)
        self.assertIn('attachment',response.getheader('Content-Disposition'));connection.close()
        folder=Path(__file__).resolve().parents[1]/'evidence'/'return-journey-2026-11-03';folder.mkdir(exist_ok=True)
        path=folder/f'http-export-{time.time_ns()}.json';path.write_bytes(raw)
        parsed=json.loads(path.read_text());self.assertTrue(parsed['demo']);self.assertEqual(parsed['phone'],server.PHONE)
        self.assertEqual(len(parsed['providers']),3);self.assertTrue(all(p['source_url']is None for p in parsed['providers']))
        for field in ('csrf_token','csrf_hash','phone_ref','sid','receipt'):self.assertNotIn(field,parsed)
        self.assertNotIn(self.cookie.split('=',1)[1],raw.decode());self.assertNotIn(self.csrf,raw.decode())

class ConcurrentPartialRefund(unittest.TestCase):
    def test_two_connections_one_offline_refund_submission(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'concurrent.db';one=Store(path);two=Store(path)
            first=SyntheticRefundTransport('succeeded');second=SyntheticRefundTransport('succeeded')
            a=RefundHarness(one,first);b=RefundHarness(two,second)
            a.record_fixture_payment('fixture-concurrent','a',100,'USD',23,'USD')
            with ThreadPoolExecutor(2) as pool:
                futures=[pool.submit(h.request,'fixture-concurrent','a') for h in (a,b)]
                results=[f.result() for f in futures]
            self.assertEqual(len(first.calls)+len(second.calls),1)
            self.assertTrue(all(r['amount_cents']==77 and r['status']in ('pending','succeeded') for r in results))
            one.close();two.close()
