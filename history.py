"""Durable SYNTHETIC receipts only. Called inside the server's transaction."""
import time
from config import DEMO_HISTORY_TTL
WEEK=7*86400
EXCEPTIONS=frozenset({'duplicate_charge','incorrect_charge','non_delivery','misrepresentation','mandatory_remedy'})
def eligible(created,now):return 0<=now-created<=WEEK
class DemoHistory:
    def __init__(self,store):self.store=store
    def save(self,owner,receipt):
        if receipt.get('mode')!='test' or receipt.get('charged_cents')!=0:raise ValueError('Only zero-dollar synthetic receipts can be retained.')
        if not isinstance(receipt.get('payment_id'),str) or not isinstance(receipt.get('created_at'),(int,float)):raise ValueError('Unsupported synthetic receipt.')
        existing=self.store.get('demo_payment',receipt['payment_id'],owner)
        if existing:return
        if len(self.items(owner))>=100:raise ValueError('Demo history limit reached; delete synthetic history before another test.')
        self.store.put('demo_payment',receipt['payment_id'],owner,receipt['created_at']+DEMO_HISTORY_TTL,receipt)
    def items(self,owner,now=None):
        now=time.time() if now is None else now
        rows=self.store.conn.execute("SELECT id,expires,data FROM records WHERE kind='demo_payment' AND owner=? AND expires>? ORDER BY expires DESC LIMIT 100",(owner,now)).fetchall()
        import json
        return [dict(payment_id=key,created_at=(r:=json.loads(raw))['created_at'],charged_cents=0,currency=r['currency'],eligible=eligible(r['created_at'],now),refund=self.store.get('demo_refund',key,owner)) for key,expires,raw in rows]
    def request(self,owner,payment_id,confirm,category='voluntary',now=None):
        now=time.time() if now is None else now
        if confirm is not True:raise ValueError('Confirm the test-only refund request.')
        if not isinstance(payment_id,str):raise ValueError('Choose an original synthetic payment.')
        payment=self.store.get('demo_payment',payment_id,owner)
        if not payment:raise LookupError('Original payment not available for this verified demo user.')
        prior=self.store.get('demo_refund',payment_id,owner)
        if prior:return prior
        if category!='voluntary' and category not in EXCEPTIONS:raise ValueError('Unknown review category.')
        if category=='voluntary' and not eligible(payment['created_at'],now):raise ValueError('Outside the voluntary seven-day window; applicable exceptions require review.')
        result=dict(status='test_request_received' if category=='voluntary' else 'manual_review',original_payment_id=payment_id,charged_cents=0,refund_cents=0 if category=='voluntary' else None,category=category,destination='original_payment_method',demo=True)
        self.store.put('demo_refund',payment_id,owner,payment['created_at']+DEMO_HISTORY_TTL,result)
        return result
    def delete(self,owner):
        self.store.conn.execute("DELETE FROM records WHERE owner=? AND kind IN ('demo_payment','demo_refund')",(owner,))
