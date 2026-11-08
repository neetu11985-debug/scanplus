"""Offline fixtures only: never contact Stripe, read keys or use the real app store."""
import copy
import hashlib
import hmac
import io
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults
from storage import Store
from stripe_checkout import StripeCheckout, StripeError, verify_event, request, NoRedirect, new_checkout_contract

ENV = {'SCANPLUS_MODE': 'demo', 'SCANPLUS_STRIPE_TEST': '1',
       'STRIPE_SECRET_KEY': 'sk_test_fixture_not_a_credential',
       'STRIPE_WEBHOOK_SECRET': 'whsec_fixture_not_a_credential',
       'SCANPLUS_STRIPE_ORIGIN': 'https://scanplus.test',
       'SCANPLUS_ALLOWED_ORIGINS': 'https://scanplus.test'}

class FakeStripe:
    def __init__(self): self.calls = []; self.result = None; self.fail = False
    def __call__(self, method, path, key, fields=None, idem=None):
        self.calls.append((method, path, fields, idem))
        if self.fail: raise StripeError('Fixture timeout; outcome uncertain.')
        if method == 'POST':
            self.result = {'id': 'cs_test_fixture', 'object': 'checkout.session', 'livemode': False,
                'mode': 'payment', 'amount_total': int(fields['line_items[0][price_data][unit_amount]']), 'currency': 'usd',
                'client_reference_id': fields['client_reference_id'],
                'metadata': {'scanplus_order': fields['metadata[scanplus_order]']},
                'status': 'open', 'payment_status': 'unpaid', 'payment_intent': None,
                'url': 'https://checkout.stripe.com/c/pay/cs_test_fixture'}
        return copy.deepcopy(self.result)
    def paid(self): self.result.update(status='complete', payment_status='paid', payment_intent='pi_fixture')

def signed(event, stamp=None):
    raw = json.dumps(event, separators=(',', ':')).encode(); stamp = str(int(time.time()) if stamp is None else stamp)
    signature = hmac.new(ENV['STRIPE_WEBHOOK_SECRET'].encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
    return raw, f't={stamp},v1={signature}'

class StripeTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, ENV); env.start(); self.addCleanup(env.stop)
        self.store = Store(); self.addCleanup(self.store.close)
        self.fake = FakeStripe(); self.gateway = StripeCheckout(self.store, self.fake)
        self.session = {'verified': True, 'verified_until': time.time()+900, 'expires': time.time()+900, 'report_id': 'fixture-report',
                        'stripe_checkout_contract': new_checkout_contract()}
    def create(self):
        with self.store.transaction(): return self.gateway.create('owner', self.session)
    def event(self): return {'id': 'evt_fixture', 'livemode': False, 'type': 'checkout.session.completed', 'data': {'object': copy.deepcopy(self.fake.result)}}
    def test_default_disabled_live_keys_and_live_mode_rejected(self):
        for change in ({'SCANPLUS_STRIPE_TEST': ''}, {'STRIPE_SECRET_KEY': 'sk_live_fixture'}, {'STRIPE_SECRET_KEY': 'rk_live_fixture'}, {'SCANPLUS_MODE': 'live'}, {'STRIPE_WEBHOOK_SECRET': ''}, {'SCANPLUS_STRIPE_ORIGIN': 'https://evil.test/path'}, {'SCANPLUS_STRIPE_ORIGIN': 'http://remote.test'}):
            with self.subTest(change=change), patch.dict(os.environ, change), self.assertRaises(StripeError): StripeCheckout(self.store, self.fake)
    def test_create_is_fixed_price_test_only_and_idempotent(self):
        result = self.create(); self.assertEqual(result, self.create()); self.assertEqual(len(self.fake.calls), 1)
        fields = self.fake.calls[0][2]; self.assertEqual(fields['line_items[0][price_data][unit_amount]'], '149')
        self.assertFalse(any(name.startswith('payment_method_types') for name in fields))
        self.assertFalse(any(name.startswith('allowed_payment_method_types') for name in fields))
        self.assertRegex(fields['integration_identifier'], r'^scanplus-sandbox-[a-z]{8}$')
        self.assertEqual(self.gateway.status('owner')['state'], 'pending')
        self.assertNotIn('phone', str(fields)); self.assertNotIn('customer_email', fields)
    def test_price_is_pinned_across_configuration_changes(self):
        self.create()
        with patch('stripe_checkout.LOOKUP_PRICE_CENTS', 199):
            self.fake.paid()
            with self.store.transaction(): self.gateway.reconcile('owner')
            self.assertEqual(self.gateway.status('owner')['amount_cents'], 149)
            self.assertEqual(self.gateway.status('owner')['state'], 'paid')

    def test_legacy_order_retry_and_fulfillment_keep_99_cent_price(self):
        self.create()
        order = self.gateway.order('owner')
        for name in ('amount_cents', 'request_version', 'integration_identifier'):
            del order[name]
        self.fake.result['amount_total'] = 99
        with self.store.transaction(): self.gateway.save(order)
        self.create()  # Existing URL is safe; do not send changed create parameters.
        self.assertEqual(len(self.fake.calls), 1)
        self.fake.paid()
        with self.store.transaction(): self.gateway.webhook(*signed(self.event()))
        self.assertEqual(self.gateway.status('owner')['amount_cents'], 99)
        self.assertEqual(self.gateway.status('owner')['state'], 'paid')
        self.assertNotIn('amount_cents', self.gateway.order('owner'))

    def test_legacy_uncertain_creation_blocks_new_parameters_but_webhook_recovers(self):
        self.fake.fail = True
        with self.store.transaction():
            with self.assertRaises(StripeError): self.gateway.create('owner', self.session)
        order = self.gateway.order('owner')
        for name in ('request_version', 'integration_identifier'):
            del order[name]
        with self.store.transaction(): self.gateway.save(order)
        self.fake.fail = False
        with self.assertRaisesRegex(StripeError, 'operator reconciliation'): self.create()
        self.assertEqual(len(self.fake.calls), 1)
        self.fake('POST', '/v1/checkout/sessions', 'fixture', self.fake.calls[0][2], 'fixture')
        self.fake.paid()
        with self.store.transaction(): self.gateway.webhook(*signed(self.event()))
        self.assertEqual(self.gateway.status('owner')['state'], 'paid')

    def test_integration_identifier_is_snapshotted_for_uncertain_retries(self):
        self.fake.fail = True
        with self.store.transaction():
            with self.assertRaises(StripeError): self.gateway.create('owner', self.session)
        first = copy.deepcopy(self.fake.calls[0])
        self.fake.fail = False
        with patch('stripe_checkout.INTEGRATION_IDENTIFIER', 'scanplus-sandbox-abcdefgh'):
            with self.store.transaction(): StripeCheckout(self.store, self.fake).create('owner', self.session)
        self.assertEqual(first, self.fake.calls[1])

    def test_restricted_test_key_works_and_malformed_or_live_keys_never_send(self):
        restricted = 'rk_test_fixture_not_a_credential'
        with patch.dict(os.environ, {'STRIPE_SECRET_KEY': restricted}):
            gateway = StripeCheckout(self.store, self.fake)
            with self.store.transaction(): gateway.create('owner', self.session)
            self.assertEqual(gateway.key, restricted)
        with patch('stripe_checkout.build_opener') as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b'{}'
            self.assertEqual(request('GET', '/v1/checkout/sessions/cs_test_fixture', restricted), {})
            sent = opener.return_value.open.call_args.args[0]
            self.assertEqual(sent.get_header('Authorization'), 'Bearer ' + restricted)
        for key in ('sk_live_fixture_not_real', 'rk_live_fixture_not_real',
                    restricted + '\n', restricted + ' ', 'pk_test_fixture_not_real', '', None, True):
            with self.subTest(kind=type(key).__name__), patch('stripe_checkout.build_opener') as opener:
                with self.assertRaises(StripeError): request('POST', '/v1/checkout/sessions', key)
                opener.assert_not_called()

    def test_delayed_failure_is_idempotent_and_never_unlocks_or_recreates_checkout(self):
        self.create()
        self.fake.result.update(status='complete', payment_status='unpaid', payment_intent='pi_fixture')
        completed = self.event()
        with self.store.transaction(): self.gateway.webhook(*signed(completed))
        self.assertEqual(self.gateway.status('owner')['state'], 'pending')
        failed = self.event(); failed.update(id='evt_async_failed', type='checkout.session.async_payment_failed')
        with self.store.transaction():
            self.gateway.webhook(*signed(failed)); self.gateway.webhook(*signed(failed))
        self.assertEqual(self.gateway.status('owner')['state'], 'failed')
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM records WHERE kind='stripe_event'").fetchone()[0], 2)
        with self.assertRaises(StripeError): self.create()
        self.assertEqual(len(self.fake.calls), 1)
        with self.store.transaction(): self.gateway.reconcile('owner')
        self.assertEqual(self.gateway.status('owner')['state'], 'failed')
        self.fake.paid()
        success = self.event(); success.update(id='evt_async_success', type='checkout.session.async_payment_succeeded')
        with self.store.transaction():
            self.gateway.webhook(*signed(success)); self.gateway.webhook(*signed(failed))
        self.assertEqual(self.gateway.status('owner')['state'], 'paid')
        later = copy.deepcopy(failed); later['id'] = 'evt_reordered_failure'
        with self.store.transaction(): self.gateway.webhook(*signed(later))
        self.assertEqual(self.gateway.status('owner')['state'], 'paid')

    def test_malformed_async_failure_does_not_change_payment_state(self):
        self.create()
        failed = self.event(); failed.update(id='evt_invalid_failure', type='checkout.session.async_payment_failed')
        for change in ({'status': 'open'}, {'status': 'complete', 'payment_status': 'paid'},
                       {'status': 'complete', 'payment_status': 'unpaid', 'amount_total': 1}):
            event = copy.deepcopy(failed); event['data']['object'].update(change)
            with self.subTest(change=change), self.assertRaises(StripeError):
                with self.store.transaction(): self.gateway.webhook(*signed(event))
        self.assertEqual(self.gateway.status('owner')['state'], 'pending')

    def test_unverified_rejected_without_call(self):
        self.session['verified'] = False
        with self.assertRaises(StripeError): self.create()
        self.assertFalse(self.fake.calls)
    def test_timeout_retry_and_restart_use_same_key(self):
        self.fake.fail = True
        with self.store.transaction():
            with self.assertRaises(StripeError): self.gateway.create('owner', self.session)
        idem = self.fake.calls[0][3]; self.fake.fail = False
        with self.store.transaction(): StripeCheckout(self.store, self.fake).create('owner', self.session)
        self.assertEqual(idem, self.fake.calls[1][3])
    def test_reconciliation_is_required_and_idempotent(self):
        self.create(); self.assertEqual(self.gateway.status('owner')['state'], 'pending')
        self.fake.paid()
        with self.store.transaction(): self.gateway.reconcile('owner'); self.gateway.reconcile('owner')
        self.assertEqual(self.gateway.status('owner')['state'], 'paid'); self.assertEqual(len(self.fake.calls), 2)
    def test_signature_raw_body_tolerance_rotation_and_malformed(self):
        self.create(); raw, signature = signed(self.event())
        self.assertEqual(verify_event(raw, signature+',v1=bad', ENV['STRIPE_WEBHOOK_SECRET'])['id'], 'evt_fixture')
        for body, sig in ((raw+b' ',signature),(raw,'v1=bad'),signed(self.event(),int(time.time())-301),signed(self.event(),int(time.time())+301),(raw, signature+',t=1'),(raw,b'bad'.decode()),(b'x'*65537,signature)):
            with self.subTest(sig=sig), self.assertRaises(StripeError): verify_event(body,sig,ENV['STRIPE_WEBHOOK_SECRET'])
    def test_signed_webhook_duplicate_and_out_of_order(self):
        self.create(); self.fake.paid(); raw, signature = signed(self.event())
        with self.store.transaction(): self.gateway.webhook(raw,signature); self.gateway.webhook(raw,signature)
        self.assertEqual(self.gateway.status('owner')['state'], 'paid')
        event=self.event();event['id']='evt_expired';event['type']='checkout.session.expired';event['data']['object'].update(status='expired',payment_status='unpaid')
        with self.store.transaction(): self.gateway.webhook(*signed(event))
        self.assertEqual(self.gateway.status('owner')['state'], 'paid')
    def test_mismatched_fields_never_fulfill(self):
        self.create(); self.fake.paid(); original=copy.deepcopy(self.fake.result)
        for change in ({'amount_total':99},{'amount_total':1},{'amount_total':True},{'currency':'eur'},{'livemode':True},{'mode':'subscription'},{'client_reference_id':'other'},{'metadata':{}},{'id':'cs_test_other'},{'id':None},{'payment_intent':None}):
            self.fake.result=dict(original,**change)
            with self.subTest(change=change), self.assertRaises(StripeError):
                with self.store.transaction(): self.gateway.reconcile('owner')
            self.assertEqual(self.gateway.status('owner')['state'],'pending')
    def test_unpaid_expired_and_cleared_orders(self):
        self.create()
        with self.store.transaction(): self.gateway.reconcile('owner')
        self.assertEqual(self.gateway.status('owner')['state'],'pending')
        self.fake.result['status']='expired'
        with self.store.transaction(): self.gateway.reconcile('owner')
        self.assertEqual(self.gateway.status('owner')['state'],'expired')
        self.fake.paid();event=self.event()
        with self.store.transaction(): self.store.clear_owner('owner');self.gateway.webhook(*signed(event))
        self.assertEqual(self.gateway.status('owner')['state'],'not_started')
    def test_payment_cannot_be_reused_by_other_order(self):
        self.create();self.fake.paid()
        with self.store.transaction(): self.gateway.reconcile('owner')
        with self.store.transaction(): self.gateway.create('other',dict(self.session,report_id='other'))
        self.fake.paid()
        with self.assertRaises(StripeError):
            with self.store.transaction(): self.gateway.reconcile('other')
    def test_malformed_checkout_url_is_safe_error(self):
        for url in (None, [], 'https://[broken', 'https://checkout.stripe.com.evil.test/pay', 'http://checkout.stripe.com/pay'):
            with self.subTest(url=url):
                fake=FakeStripe()
                def transport(*args):
                    result=fake(*args);result['url']=url;return result
                gateway=StripeCheckout(self.store,transport)
                with self.store.transaction():
                    with self.assertRaises(StripeError):gateway.create('owner',self.session)
                self.assertEqual(gateway.status('owner')['state'],'pending')
    def test_file_backed_restart_preserves_fulfillment_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path=directory+'/stripe-test.sqlite3'
            store=Store(path);gateway=StripeCheckout(store,self.fake)
            with store.transaction():gateway.create('owner',self.session)
            self.fake.paid();event=self.event();raw,sig=signed(event)
            with store.transaction():gateway.webhook(raw,sig)
            store.close()
            store=Store(path)
            try:
                gateway=StripeCheckout(store,self.fake)
                with store.transaction():gateway.webhook(raw,sig)
                self.assertEqual(gateway.status('owner')['state'],'paid')
                self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM records WHERE kind='stripe_event'").fetchone()[0],1)
            finally:store.close()
    def test_timeout_then_signed_webhook_binds_session(self):
        self.fake.fail=True
        with self.store.transaction():
            with self.assertRaises(StripeError):self.gateway.create('owner',self.session)
        fields=self.fake.calls[-1][2];self.fake.fail=False
        self.fake('POST','/v1/checkout/sessions','fixture',fields,'fixture')
        self.fake.paid()
        with self.store.transaction():self.gateway.webhook(*signed(self.event()))
        self.assertEqual(self.gateway.status('owner')['state'],'paid')
        self.assertEqual(self.gateway.order('owner')['checkout_id'],'cs_test_fixture')
    def test_transaction_rollback_preserves_retry_key(self):
        with self.assertRaises(RuntimeError):
            with self.store.transaction():
                self.gateway.create('owner',self.session)
                raise RuntimeError('Fixture local commit failure')
        first=copy.deepcopy(self.fake.calls[-1])
        self.create()
        self.assertEqual(first,self.fake.calls[-1])
    def test_rollback_retry_keeps_session_contract_across_price_and_label_change(self):
        with self.assertRaises(RuntimeError):
            with self.store.transaction():
                self.gateway.create('owner', self.session)
                raise RuntimeError('Fixture commit failure')
        first = copy.deepcopy(self.fake.calls[-1])
        self.assertIsNone(self.gateway.order('owner'))
        with patch('stripe_checkout.INTEGRATION_IDENTIFIER', 'scanplus-sandbox-abcdefgh'), \
             patch('stripe_checkout.LOOKUP_PRICE_CENTS', 199):
            with self.store.transaction(): StripeCheckout(self.store, self.fake).create('owner', self.session)
        self.assertEqual(first, self.fake.calls[-1])
        self.assertEqual(self.gateway.status('owner')['amount_cents'], 149)

    def test_rollback_after_request_version_change_blocks_instead_of_mutating_retry(self):
        with self.assertRaises(RuntimeError):
            with self.store.transaction():
                self.gateway.create('owner', self.session)
                raise RuntimeError('Fixture commit failure')
        with patch('stripe_checkout.CHECKOUT_REQUEST_VERSION', 3), self.assertRaisesRegex(StripeError, 'saved Stripe request contract'):
            self.create()
        self.assertIsNone(self.gateway.order('owner'))
        self.assertEqual(len(self.fake.calls), 1)

    def test_missing_legacy_session_contract_never_recreates_unknown_checkout(self):
        del self.session['stripe_checkout_contract']
        with self.assertRaisesRegex(StripeError, 'saved Stripe request contract'): self.create()
        self.assertFalse(self.fake.calls)

    def test_transport_rejects_live_and_arbitrary_paths_without_network(self):
        for key,path in [('sk_live_fixture','/v1/checkout/sessions'),('sk_test_fixture','https://evil.test'),('sk_test_fixture','/v1/checkout/sessions/cs_live_x')]:
            with self.assertRaises(StripeError): request('POST',path,key)
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://evil.test'))

class StripeHTTPTests(unittest.TestCase):
    def setUp(self):
        import server
        self.server=server; self.store=Store(); self.fake=FakeStripe();self.cookie='';self.csrf=''
        self.patches=[patch.dict(os.environ, ENV),patch.object(server,'STORE',self.store),patch('stripe_checkout.request',self.fake)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.addCleanup(self.store.close)
    def call(self,path,data=None,raw=None,signature=None,origin=True):
        from wsgi import application
        env={};setup_testing_defaults(env)
        body=raw if raw is not None else (json.dumps(data).encode() if data is not None else b'')
        env.update(PATH_INFO=path,REQUEST_METHOD='POST' if data is not None or raw is not None else 'GET',CONTENT_LENGTH=str(len(body)),HTTP_HOST='scanplus.test',HTTP_COOKIE=self.cookie,HTTP_X_CSRF_TOKEN=self.csrf)
        env['wsgi.url_scheme']='https';env['wsgi.input']=io.BytesIO(body)
        if origin:env['HTTP_ORIGIN']='https://scanplus.test'
        if signature:env['HTTP_STRIPE_SIGNATURE']=signature
        response={}
        def start(status,headers):response.update(status=int(status.split()[0]),headers=dict(headers))
        response['raw']=b''.join(application(env,start))
        if 'Set-Cookie' in response['headers']:self.cookie=response['headers']['Set-Cookie'].split(';')[0]
        try:
            response['body']=json.loads(response['raw']);self.csrf=response['body'].get('csrf_token',self.csrf)
        except ValueError:pass
        return response
    def start(self):
        self.assertEqual(self.call('/api/start',{'phone':self.server.PHONE,'consent':True})['status'],200)
        self.assertEqual(self.call('/api/verify',{'code':'246810'})['status'],200)
    def test_full_wsgi_signed_webhook_and_report_gate(self):
        self.start();self.assertEqual(self.call('/api/stripe/report')['status'],403)
        self.call('/api/checkout',{'accept':True}) # Legacy demo receipt cannot unlock Stripe report.
        self.assertEqual(self.call('/api/stripe/report')['status'],403)
        self.assertEqual(self.call('/api/stripe/checkout',{'accept_test':True})['status'],200)
        self.fake.paid();event={'id':'evt_http','livemode':False,'type':'checkout.session.completed','data':{'object':self.fake.result}}
        raw,sig=signed(event)
        self.assertEqual(self.call('/api/stripe/webhook',raw=raw,signature=sig,origin=False)['status'],200)
        self.assertEqual(self.call('/api/stripe/report')['status'],200)
        self.call('/api/clear',{});self.assertEqual(self.call('/api/stripe/report')['status'],403)
    def test_csrf_origin_price_tampering_and_unsigned_webhook(self):
        self.start()
        self.assertEqual(self.call('/api/stripe/checkout',{'accept_test':True},origin=False)['status'],403)
        csrf=self.csrf;self.csrf='bad';self.assertEqual(self.call('/api/stripe/checkout',{'accept_test':True})['status'],403);self.csrf=csrf
        self.assertEqual(self.call('/api/stripe/checkout',{'accept_test':True,'amount':1})['status'],400)
        self.assertEqual(self.call('/api/stripe/webhook',raw=b'{}',origin=False)['status'],400)
        self.assertFalse(self.fake.calls)
    def test_return_page_never_fulfills_and_reconcile_recovers(self):
        self.start();self.call('/api/stripe/checkout',{'accept_test':True});self.fake.paid()
        self.assertEqual(self.call('/stripe-test')['status'],200)
        self.assertEqual(self.call('/api/stripe/report')['status'],403)
        self.assertEqual(self.call('/api/stripe/reconcile',{})['body']['state'],'paid')
        self.assertEqual(self.call('/api/stripe/report')['status'],200)
    def test_declined_payment_stays_locked_after_reconcile_and_reload(self):
        self.start();self.call('/api/stripe/checkout',{'accept_test':True})
        # Stripe-hosted card rejection leaves this Checkout unpaid/open. No card
        # data is posted to ScanPlus, and no payment-failed event grants access.
        self.fake.result.update(status='open',payment_status='unpaid',payment_intent='pi_declined_fixture')
        event={'id':'evt_declined','livemode':False,'type':'payment_intent.payment_failed',
               'data':{'object':{'id':'pi_declined_fixture','object':'payment_intent',
                                 'status':'requires_payment_method',
                                 'last_payment_error':{'code':'card_declined','decline_code':'generic_decline'}}}}
        raw,sig=signed(event)
        self.assertEqual(self.call('/api/stripe/webhook',raw=raw,signature=sig,origin=False)['status'],200)
        self.assertEqual(self.call('/api/stripe/reconcile',{})['body']['state'],'pending')
        self.assertEqual(self.call('/stripe-test')['status'],200)
        self.assertEqual(self.call('/api/stripe/status')['body']['state'],'pending')
        self.assertEqual(self.call('/api/stripe/report')['status'],403)
    def test_session_commits_nonsecret_request_contract_before_any_checkout(self):
        self.start()
        from storage import digest
        sid = digest(self.cookie.split('=', 1)[1])
        persisted = self.store.get('session', sid, sid)
        contract = persisted['stripe_checkout_contract']
        self.assertEqual(contract['amount_cents'], 149)
        self.assertEqual(contract['origin'], ENV['SCANPLUS_STRIPE_ORIGIN'])
        self.assertEqual(set(contract), {'request_version', 'integration_identifier', 'amount_cents', 'origin'})
        self.assertFalse(self.fake.calls)
        with patch('stripe_checkout.INTEGRATION_IDENTIFIER', 'scanplus-sandbox-abcdefgh'), \
             patch('stripe_checkout.LOOKUP_PRICE_CENTS', 199):
            self.assertEqual(self.call('/api/stripe/status')['body']['amount_cents'], 149)
            result = self.call('/api/stripe/checkout', {'accept_test': True})
        self.assertEqual(result['status'], 200)
        fields = self.fake.calls[-1][2]
        self.assertEqual(fields['integration_identifier'], contract['integration_identifier'])
        self.assertEqual(fields['line_items[0][price_data][unit_amount]'], '149')

    def test_signed_async_failure_denies_report_and_duplicate_create(self):
        self.start(); self.call('/api/stripe/checkout', {'accept_test': True})
        self.fake.result.update(status='complete', payment_status='unpaid', payment_intent='pi_delayed_fixture')
        event = {'id': 'evt_http_failure', 'livemode': False, 'type': 'checkout.session.async_payment_failed',
                 'data': {'object': self.fake.result}}
        raw, sig = signed(event)
        self.assertEqual(self.call('/api/stripe/webhook', raw=raw, signature=sig, origin=False)['status'], 200)
        self.assertEqual(self.call('/api/stripe/status')['body']['state'], 'failed')
        self.assertEqual(self.call('/api/stripe/report')['status'], 403)
        self.assertEqual(self.call('/api/stripe/checkout', {'accept_test': True})['status'], 400)
        self.assertEqual(len(self.fake.calls), 1)

    def test_disabled_and_live_wsgi_fail_closed(self):
        self.start()
        with patch.dict(os.environ,{'SCANPLUS_STRIPE_TEST':''}): self.assertEqual(self.call('/api/stripe/status')['status'],503)
        with patch.dict(os.environ,{'SCANPLUS_MODE':'live'}): self.assertEqual(self.call('/stripe-test')['status'],503)

if __name__=='__main__':unittest.main()
