"""Offline refund policy harness. No gateway/signature/legal-policy implementation."""
import time
from uuid import uuid4
from storage import digest

WEEK=7*86400
class SyntheticRefundTransport:
    def __init__(self,status='pending'):self.status=status;self.calls=[]
    def submit(self,request):self.calls.append(request);return self.status

class RefundHarness:
    def __init__(self,store,transport):
        if not isinstance(transport,SyntheticRefundTransport):raise ValueError('Live refunds disabled.')
        self.store=store;self.transport=transport
    def record_fixture_payment(self,payment_id,owner,amount,currency,fee=None,fee_currency=None,created=None,refunded=0):
        if not payment_id.startswith('fixture-'):raise ValueError('Fixture payment only.')
        created=time.time() if created is None else created
        with self.store.transaction():self.store.put('settled_payment',payment_id,owner,created+WEEK+86400,dict(amount=amount,currency=currency,fee=fee,fee_currency=fee_currency,created=created,refunded=refunded))
    def request(self,payment_id,owner,category='voluntary',now=None):
        now=time.time() if now is None else now
        key=digest(owner+':'+payment_id)
        with self.store.transaction():
            payment=self.store.get('settled_payment',payment_id,owner)
            if not payment:raise ValueError('Original payment not available for this user.')
            existing=self.store.get('refund',key,owner)
            if existing:return existing
            age=now-payment['created']
            if age<0 or age>WEEK:raise ValueError('Outside voluntary seven-day eligibility; review any applicable mandatory remedy separately.')
            fee=payment['fee'];amount=payment['amount']
            review=(not isinstance(payment['currency'],str) or len(payment['currency'])!=3 or not payment['currency'].isascii() or not payment['currency'].isalpha() or payment['currency']!=payment['currency'].upper() or category!='voluntary' or type(amount)is not int or amount<0 or type(fee)is not int or fee<0 or fee>amount or payment['fee_currency']!=payment['currency'] or payment['refunded']!=0)
            result=dict(id=str(uuid4()),original_payment_id=payment_id,status='manual_review' if review else 'pending',amount_cents=None if review else amount-fee,currency=payment['currency'],destination='original_payment_method',demo=True)
            self.store.put('refund',key,owner,payment['created']+WEEK+86400,result)
        if review:return result
        # Persist intent first: duplicate/restart never resubmits even if outcome is uncertain.
        try:status=self.transport.submit(result.copy())
        except Exception:status='pending'
        if status not in ('pending','succeeded','failed'):status='pending'
        result['status']=status
        with self.store.transaction():self.store.put('refund',key,owner,payment['created']+WEEK+86400,result)
        return result

    def approve_full_fixture(self,payment_id,owner,approval):
        """Explicit fixture reviewer decision; never exposed as a customer/admin HTTP API."""
        if approval!='fixture-review-approved':raise ValueError('Explicit synthetic reviewer approval required.')
        key=digest(owner+':'+payment_id)
        with self.store.transaction():
            payment=self.store.get('settled_payment',payment_id,owner);prior=self.store.get('refund',key,owner)
            if not payment or not prior:raise ValueError('Owned original payment and review request required.')
            if prior['status']!='manual_review':return prior
            if type(payment['amount'])is not int or payment['amount']<0 or payment['refunded']!=0:raise ValueError('Full refund needs reconciliation.')
            prior.update(status='pending',amount_cents=payment['amount'],fixture_review='full_refund_approved')
            self.store.put('refund',key,owner,payment['created']+WEEK+86400,prior)
        try:status=self.transport.submit(prior.copy())
        except Exception:status='pending'
        prior['status']=status if status in ('pending','succeeded','failed') else 'pending'
        with self.store.transaction():self.store.put('refund',key,owner,payment['created']+WEEK+86400,prior)
        return prior
