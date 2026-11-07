"""Offline Poynt contract harness, NOT a live gateway or callback verifier."""
from dataclasses import asdict,dataclass
from uuid import uuid4
import time,re
from config import PAYMENT_TTL

class PaymentBlocked(ValueError):pass

@dataclass
class Order:
    id:str
    request_id:str
    business_id:str
    store_id:str
    owner:str='fixture-owner'
    expires:float=0
    amount:int=100
    currency:str='USD'
    state:str='created'
    transaction_id:str|None=None
    receipt:dict|None=None

class SyntheticPoyntTransport:
    def __init__(self,*responses):self.responses=list(responses);self.calls=[]
    def request(self,method,path,*,headers,body=None,timeout=5):
        self.calls.append({'method':method,'path':path,'headers':headers,'body':body})
        if not self.responses:raise PaymentBlocked('No synthetic response configured.')
        result=self.responses.pop(0)
        if isinstance(result,Exception):raise result
        return result

class PoyntContractHarness:
    def __init__(self,transport,store):
        if not isinstance(transport,SyntheticPoyntTransport):raise PaymentBlocked('Only offline synthetic transport is enabled.')
        self.transport=transport;self.store=store;self.orders={}
    def _load(self,key,owner):
        data=self.store.get('payment',key,owner)
        if not data:raise PaymentBlocked('Order unavailable for this session.')
        if key in self.orders:self.orders[key].__dict__.update(data)
        else:self.orders[key]=Order(**data)
        return self.orders[key]
    def _save(self,order,state=None):
        if state is not None:order.state=state
        self.store.put('payment',order.id,order.owner,order.expires,asdict(order));return order.state
    def create_order(self,*,verified,service_available,owner='fixture-owner'):
        if verified is not True or service_available is not True or not owner:
            raise PaymentBlocked('Verified control, session and available service required.')
        with self.store.transaction():
            self.store.prune()
            order=Order(str(uuid4()),str(uuid4()),'fixture-business','fixture-store',owner,time.time()+PAYMENT_TTL)
            self.orders[order.id]=order;self._save(order);return order
    def charge_fixture(self,order_id,nonce,owner='fixture-owner'):
        # Reserve the charge durably BEFORE the synthetic transport. A crash remains uncertain.
        with self.store.transaction():
            self.store.prune();order=self._load(order_id,owner)
            if order.state!='created':return order.state
            if not isinstance(nonce,str) or not nonce.startswith('fixture-nonce-'):raise PaymentBlocked('Synthetic nonces only.')
            if not self.store.claim('nonce',nonce,order.id,order.expires):raise PaymentBlocked('Nonce already consumed.')
            self._save(order,'uncertain')
        headers={'Api-Version':'1.2','Authorization':'Bearer SYNTHETIC-NOT-A-TOKEN','Content-Type':'application/json','Poynt-Request-Id':order.request_id}
        body={'action':'SALE','context':{'businessId':order.business_id,'storeId':order.store_id},'amounts':{'transactionAmount':100,'orderAmount':100,'currency':'USD'},'fundingSource':{'nonce':nonce},'emailReceipt':False}
        try:status,payload=self.transport.request('POST',f'/businesses/{order.business_id}/cards/tokenize/charge',headers=headers,body=body)
        except Exception:return 'uncertain'
        with self.store.transaction():
            order=self._load(order_id,owner)
            if status!=200 or not isinstance(payload,dict):return order.state
            txn=payload.get('id')
            if not isinstance(txn,str) or not re.fullmatch('[A-Za-z0-9-]{1,128}',txn):return order.state
            if not self.store.claim('transaction',txn,order.id,order.expires):return self._save(order,'rejected')
            order.transaction_id=txn;return self._save(order,'pending')
    def reconcile_fixture(self,order_id,owner='fixture-owner'):
        with self.store.transaction():
            self.store.prune();order=self._load(order_id,owner)
            if not order.transaction_id:raise PaymentBlocked('No bound transaction; manual reconciliation required.')
            # Offline only. A future network implementation must avoid holding a DB lock over I/O.
            try:status,payload=self.transport.request('GET',f'/businesses/{order.business_id}/transactions/{order.transaction_id}',headers={'Api-Version':'1.2','Authorization':'Bearer SYNTHETIC-NOT-A-TOKEN'})
            except Exception:return order.state
            if status!=200 or not isinstance(payload,dict):return order.state
            context=payload.get('context',{});amounts=payload.get('amounts',{})
            if not isinstance(context,dict) or not isinstance(amounts,dict):return order.state
            valid=(payload.get('id')==order.transaction_id and context.get('businessId')==order.business_id and context.get('storeId')==order.store_id and type(amounts.get('transactionAmount')) is int and amounts.get('transactionAmount')==order.amount and amounts.get('orderAmount')==order.amount and amounts.get('currency')==order.currency and payload.get('action') in ('SALE','CAPTURE') and payload.get('voided') is not True)
            if not valid:order.receipt=None;return self._save(order,'rejected')
            state=payload.get('status')
            if state=='CAPTURED':
                if not order.receipt:order.receipt={'order_id':order.id,'amount_cents':100,'currency':'USD','demo':True}
                return self._save(order,'paid')
            order.receipt=None
            return self._save(order,'not_paid' if state in ('DECLINED','VOIDED','REFUNDED','PARTIALLY_REFUNDED','PARTIALLY_CAPTURED_AND_PARTIALLY_REFUNDED') else 'pending')
