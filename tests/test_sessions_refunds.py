import sys,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_server as journeys
from storage import Store
from refunds import RefundHarness,SyntheticRefundTransport,WEEK
import server

class SwitchTests(unittest.TestCase):
    setUpClass=classmethod(journeys.Journey.setUpClass.__func__)
    tearDownClass=classmethod(journeys.Journey.tearDownClass.__func__)
    setUp=journeys.Journey.setUp;req=journeys.Journey.req;start=journeys.Journey.start;ready=journeys.Journey.ready
    def test_new_verified_session_revokes_previous_apis(self):
        self.ready();a=(self.cookie,self.csrf)
        self.cookie='';self.csrf='';self.start();b=(self.cookie,self.csrf)
        self.req('verify',{'code':'bad'});self.cookie,self.csrf=a
        self.assertEqual(self.req('report')[0],200) # An unverified/failed challenger cannot log A out.
        self.cookie,self.csrf=b;self.assertEqual(self.req('verify',{'code':'246810'})[0],200)
        self.req('checkout',{'accept':True});self.assertEqual(self.req('report')[0],200)
        self.cookie,self.csrf=a
        self.assertEqual(self.req('report')[0],403);self.assertEqual(self.req('export')[0],403)
        self.assertEqual(self.req('refund',{'confirm':True})[0],401)
        self.assertEqual(self.req('checkout',{'accept':True})[0],401)
        self.assertEqual(self.req('removal',{'provider':'fixture','authorize':True})[0],401)
        self.assertEqual(self.req('removal/status',{})[0],401)
        self.assertFalse(self.req('session/status')[1]['active'])
    def test_refund_request_repeat_and_export(self):
        self.ready();first=self.req('refund',{'confirm':True});self.assertEqual(first[0],200)
        self.assertEqual(first,self.req('refund',{'confirm':True}));self.assertEqual(first[1]['refund_cents'],0)
        self.assertEqual(self.req('export')[1]['refund'],first[1])

class RefundTests(unittest.TestCase):
    def setUp(self):self.store=Store();self.addCleanup(self.store.close)
    def test_actual_fee_and_idempotency(self):
        t=SyntheticRefundTransport('succeeded');h=RefundHarness(self.store,t)
        h.record_fixture_payment('fixture-pay','a',100,'USD',17,'USD')
        first=h.request('fixture-pay','a');self.assertEqual(first['amount_cents'],83)
        self.assertEqual(first,h.request('fixture-pay','a'));self.assertEqual(len(t.calls),1)
        self.assertEqual(first['destination'],'original_payment_method')
        with self.assertRaises(ValueError):h.request('fixture-pay','b')
    def test_pending_fee_currency_partial_and_exception_review(self):
        for i,(fee,currency,refunded,category) in enumerate([(None,'USD',0,'voluntary'),(33,'EUR',0,'voluntary'),(101,'USD',0,'voluntary'),(33,'USD',1,'voluntary'),(33,'USD',0,'duplicate_charge'),(33,'USD',0,'non_delivery')]):
            t=SyntheticRefundTransport();h=RefundHarness(self.store,t);key='fixture-'+str(i)
            h.record_fixture_payment(key,'a',100,'USD',fee,currency,refunded=refunded)
            result=h.request(key,'a',category);self.assertEqual(result['status'],'manual_review');self.assertIsNone(result['amount_cents']);self.assertEqual(t.calls,[])
    def test_deadline_and_failed_state(self):
        now=time.time();h=RefundHarness(self.store,SyntheticRefundTransport('failed'))
        h.record_fixture_payment('fixture-old','a',100,'USD',20,'USD',created=now-WEEK-1)
        with self.assertRaises(ValueError):h.request('fixture-old','a',now=now)
        h.record_fixture_payment('fixture-new','a',100,'USD',20,'USD')
        self.assertEqual(h.request('fixture-new','a')['status'],'failed')
