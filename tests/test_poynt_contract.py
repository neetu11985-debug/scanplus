import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from storage import Store
from poynt_contract import PoyntContractHarness,SyntheticPoyntTransport,PaymentBlocked

def txn(status='CAPTURED',**extra):
    return dict({'id':'fixture-txn','context':{'businessId':'fixture-business','storeId':'fixture-store'},'amounts':{'transactionAmount':100,'orderAmount':100,'currency':'USD'},'status':status,'action':'SALE'},**extra)

class PoyntTests(unittest.TestCase):
    def harness(self,*responses):
        t=SyntheticPoyntTransport(*responses); h=PoyntContractHarness(t,Store());self.addCleanup(h.store.close)
        o=h.create_order(verified=True,service_available=True)
        return h,o,t
    def test_server_owned_request_and_repeat_charge(self):
        h,o,t=self.harness((200,{'id':'fixture-txn'}),(200,txn()),(200,txn()))
        self.assertEqual(h.charge_fixture(o.id,'fixture-nonce-a'),'pending')
        self.assertEqual(h.charge_fixture(o.id,'fixture-nonce-a'),'pending'); self.assertEqual(len(t.calls),1)
        body=t.calls[0]['body']; self.assertEqual(body['amounts']['transactionAmount'],100)
        self.assertEqual(t.calls[0]['headers']['Poynt-Request-Id'],o.request_id)
        self.assertEqual(h.reconcile_fixture(o.id),'paid'); receipt=o.receipt.copy()
        self.assertEqual(h.reconcile_fixture(o.id),'paid'); self.assertEqual(o.receipt,receipt)
    def test_mismatched_amount_currency_business_or_id(self):
        bad=[txn(amounts={'transactionAmount':1,'orderAmount':100,'currency':'USD'}),txn(amounts={'transactionAmount':100,'orderAmount':100,'currency':'EUR'}),txn(context={'businessId':'other','storeId':'fixture-store'}),txn(id='other'),txn(voided=True)]
        for payload in bad:
            h,o,t=self.harness((200,{'id':'fixture-txn'}),(200,payload));h.charge_fixture(o.id,'fixture-nonce-a')
            self.assertEqual(h.reconcile_fixture(o.id),'rejected');self.assertIsNone(o.receipt)
    def test_authorized_declined_refunded_unknown_fail_closed(self):
        for status,expected in [('AUTHORIZED','pending'),('DECLINED','not_paid'),('REFUNDED','not_paid'),('UNKNOWN','pending')]:
            h,o,t=self.harness((200,{'id':'fixture-txn'}),(200,txn(status)));h.charge_fixture(o.id,'fixture-nonce-a')
            self.assertEqual(h.reconcile_fixture(o.id),expected);self.assertIsNone(o.receipt)
    def test_timeout_never_recharges(self):
        h,o,t=self.harness(TimeoutError())
        self.assertEqual(h.charge_fixture(o.id,'fixture-nonce-a'),'uncertain')
        self.assertEqual(h.charge_fixture(o.id,'fixture-nonce-a'),'uncertain');self.assertEqual(len(t.calls),1)
        with self.assertRaises(PaymentBlocked):h.reconcile_fixture(o.id)
    def test_nonce_and_transaction_replay_across_orders(self):
        h,o,t=self.harness((200,{'id':'fixture-txn'}),(200,{'id':'fixture-txn'}))
        h.charge_fixture(o.id,'fixture-nonce-a')
        other=h.create_order(verified=True,service_available=True)
        with self.assertRaises(PaymentBlocked):h.charge_fixture(other.id,'fixture-nonce-a')
        self.assertEqual(h.charge_fixture(other.id,'fixture-nonce-b'),'rejected')
    def test_service_and_verification_gates(self):
        h=PoyntContractHarness(SyntheticPoyntTransport(),Store());self.addCleanup(h.store.close)
        for verified,available in [(False,True),(True,False)]:
            with self.assertRaises(PaymentBlocked):h.create_order(verified=verified,service_available=available)
        o=h.create_order(verified=True,service_available=True)
        with self.assertRaises(PaymentBlocked):h.charge_fixture(o.id,'real-nonce-disallowed')
    def test_http_failure_and_reconcile_failure(self):
        h,o,t=self.harness((500,{}));self.assertEqual(h.charge_fixture(o.id,'fixture-nonce-a'),'uncertain')
        h,o,t=self.harness((200,{'id':'fixture-txn'}),TimeoutError(),(503,{}))
        h.charge_fixture(o.id,'fixture-nonce-a');self.assertEqual(h.reconcile_fixture(o.id),'pending');self.assertEqual(h.reconcile_fixture(o.id),'pending')
