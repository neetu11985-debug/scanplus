"""Offline synthetic consent/service/HTTP checks. No personal data or network APIs."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import copy
import json
import time
import unittest
from unittest.mock import patch

import removal_requests as removal
import server
import test_server as journeys
from storage import digest


class RemovalContracts(unittest.TestCase):
    def setUp(self):
        self.s={'report_id':'report-a','phone_ref':digest(server.PHONE),'expires':time.time()+900,
                'removal':'not_requested'}
        self.listing={k:removal.fixture_listing(self.s)[k] for k in ('provider','report_id','listing_id')}

    def grant(self):
        preview=removal.prepare(self.s,self.listing)
        return {**self.listing,'consent_id':preview['consent_id'],
                'consent_version':preview['disclosure']['consent_version'],
                'confirm_listing':True,'authorize':True}

    def test_disclosure_is_exact_and_only_fixture_data(self):
        preview=removal.prepare(self.s,self.listing)
        d=preview['disclosure']
        self.assertEqual(d['data'][0]['value'],server.PHONE)
        self.assertEqual(d['listing_id'],self.listing['listing_id'])
        self.assertIn('no external recipient',d['recipient'])
        for field in ('scope','purpose','consequences','cost','retention','cancellation'):
            self.assertTrue(d[field])
        self.assertLessEqual(preview['expires_at'],self.s['expires'])
        self.assertIsNone(removal.public_request(self.s))

    def test_each_explicit_confirmation_required(self):
        for field in ('authorize','confirm_listing'):
            for value in (False,None,'true',1):
                data=self.grant();data[field]=value
                with self.assertRaises(removal.RemovalError):removal.submit(self.s,data)
        self.assertIsNone(removal.public_request(self.s))

    def test_live_provider_external_fields_and_nonfixture_identity_fail_closed(self):
        with patch.object(removal.FixtureRemoval,'submit') as adapter:
            for provider in ('spokeo','whitepages','optery','https://example.com',None):
                with self.assertRaises(removal.RemovalError):removal.prepare(self.s,{**self.listing,'provider':provider})
            for key in ('phone','recipient','destination','url','data','provider_token'):
                with self.assertRaises(removal.RemovalError):removal.prepare(self.s,{**self.listing,key:'blocked'})
            self.s['phone_ref']=digest('+12025550149')
            with self.assertRaises(removal.RemovalError):removal.prepare(self.s,self.listing)
            adapter.assert_not_called()

    def test_report_listing_cross_session_and_stale_tabs(self):
        first=self.grant();second=self.grant()
        with self.assertRaises(removal.RemovalError):removal.submit(self.s,first)
        for field in ('report_id','listing_id','consent_id','consent_version'):
            bad={**second,field:'stale-value-000000000000000000'}
            with self.assertRaises(removal.RemovalError):removal.submit(self.s,bad)
        other=copy.deepcopy(self.s);other['report_id']='another-report'
        with self.assertRaises(removal.RemovalError):removal.submit(other,second)
        self.assertEqual(removal.submit(self.s,second)['status'],'request_submitted')

    def test_cancel_and_expiry_invalidate_permission(self):
        data=self.grant();removal.cancel(self.s,{'consent_id':data['consent_id']})
        with self.assertRaises(removal.RemovalError):removal.submit(self.s,data)
        data=self.grant()
        with self.assertRaises(removal.RemovalError):
            removal.submit(self.s,data,now=self.s['removal_preview']['expires_at'])

    def test_disclosure_change_requires_new_permission(self):
        data=self.grant();self.s['phone_ref']=digest(server.FIXTURE_PHONES[1])
        with self.assertRaises(removal.RemovalError):removal.submit(self.s,data)

    def test_duplicate_idempotent_receipt_and_readonly_status(self):
        data=self.grant()
        with patch.object(removal.FixtureRemoval,'submit',autospec=True,
                          side_effect=lambda self,provider,authorized,**kw:
                          {'demo':True,'status':'request_submitted','receipt':kw['request_id']}) as adapter:
            first=removal.submit(self.s,data)
            for _ in range(4):self.assertEqual(removal.submit(self.s,data),first)
            self.assertEqual(adapter.call_count,1)
            self.assertEqual(adapter.call_args.kwargs['payload'],
                             {'phone':server.PHONE,'listing_id':self.listing['listing_id']})
        snapshot=copy.deepcopy(self.s)
        for _ in range(20):
            self.assertEqual(removal.status(self.s,{'request_id':first['request_id']}),first)
        self.assertEqual(snapshot,self.s)
        self.assertFalse(first['removal_verified'])
        self.assertNotIn('consent_hash',first)
        self.assertNotIn('consent_id',json.dumps(first))
        self.assertEqual(removal.prepare(self.s,self.listing)['request'],first)
        with self.assertRaises(removal.RemovalError):
            removal.cancel(self.s,{'consent_id':data['consent_id']})

    def test_timeout_and_invalid_receipt_do_not_retry_or_leak(self):
        for result in (TimeoutError('secret-data'),{'demo':True,'status':'removal_confirmed','receipt':'made-up'}):
            self.s.pop('removal_request',None);data=self.grant()
            kwargs={'side_effect':result} if isinstance(result,Exception) else {'return_value':result}
            with patch.object(removal.FixtureRemoval,'submit',**kwargs) as adapter:
                receipt=removal.submit(self.s,data)
                self.assertEqual(receipt['status'],'outcome_unknown')
                self.assertEqual(removal.submit(self.s,data),receipt)
                self.assertEqual(adapter.call_count,1)
                self.assertNotIn('secret-data',json.dumps(receipt))
                self.assertFalse(receipt['removal_verified'])

    def test_status_cannot_assert_completion_or_invent_request(self):
        data=self.grant();receipt=removal.submit(self.s,data)
        for body in ({'request_id':'other'}, {'request_id':receipt['request_id'],'status':'removal_confirmed'}):
            with self.assertRaises(removal.RemovalError):removal.status(self.s,body)

    def test_malformed_unicode_tokens_fail_without_adapter_or_exception_leak(self):
        body=self.grant()
        with patch.object(removal.FixtureRemoval,'submit') as adapter:
            for token in ('é'*32, '\ud800'*32, ' '*43, [], {}, 100):
                with self.assertRaises(removal.RemovalError):
                    removal.submit(self.s,{**body,'consent_id':token})
            adapter.assert_not_called()
        self.assertIsNone(removal.public_request(self.s))


class RemovalHTTP(unittest.TestCase):
    setUpClass=classmethod(journeys.Journey.setUpClass.__func__)
    tearDownClass=classmethod(journeys.Journey.tearDownClass.__func__)
    setUp=journeys.Journey.setUp;req=journeys.Journey.req;start=journeys.Journey.start;ready=journeys.Journey.ready

    def listing(self):
        report=self.req('report')[1]
        return {k:report['removal_listing'][k] for k in ('provider','report_id','listing_id')}

    def consent(self,listing):
        preview=self.req('removal/prepare',listing)[1]
        return {**listing,'consent_id':preview['consent_id'],'consent_version':removal.CONSENT_VERSION,
                'authorize':True,'confirm_listing':True}

    def test_auth_checkout_csrf_origin_and_nonexistent_routes(self):
        self.assertEqual(self.req('removal/prepare',{})[0],401)
        self.start();self.assertEqual(self.req('removal/prepare',{})[0],403)
        self.req('verify',{'code':'246810'});self.assertEqual(self.req('removal/prepare',{})[0],403)
        self.req('checkout',{'accept':True});listing=self.listing()
        token=self.csrf;self.csrf='wrong'
        self.assertEqual(self.req('removal/prepare',listing)[0],403)
        self.csrf=token;self.assertEqual(self.req('removal/prepare',listing,False)[0],403)
        self.assertEqual(self.req('removal/confirm',{'status':'removal_confirmed'})[0],404)
        self.assertEqual(self.req('removal/status',{})[0],404)

    def test_cancel_duplicate_reload_and_clear(self):
        self.ready();listing=self.listing();first=self.consent(listing)
        self.assertEqual(self.req('removal/cancel',{'consent_id':first['consent_id']})[0],200)
        self.assertEqual(self.req('removal',first)[0],409)
        body=self.consent(listing);status,receipt=self.req('removal',body)
        self.assertEqual(status,200);self.assertEqual(self.req('removal',body)[1],receipt)
        self.assertEqual(self.req('report')[1]['removal_request'],receipt)
        self.assertTrue(self.req('export')[1].startswith(b'%PDF-'))
        for _ in range(3):self.assertEqual(self.req('removal/status',{'request_id':receipt['request_id']})[1],receipt)
        self.req('clear',{});self.assertEqual(self.req('removal',body)[0],401)
        self.assertEqual(server.STORE.conn.execute("SELECT COUNT(*) FROM records WHERE kind='session'").fetchone()[0],0)

    def test_independent_identity_cannot_reuse_consent_or_receipt(self):
        self.ready();listing=self.listing();body=self.consent(listing)
        self.cookie='';self.csrf=''
        self.req('start',{'phone':server.FIXTURE_PHONES[1],'consent':True})
        self.req('verify',{'code':'246810'});self.req('checkout',{'accept':True})
        self.assertEqual(self.req('removal',body)[0],409)

    def test_http_unicode_token_is_structured_409(self):
        self.ready();body=self.consent(self.listing())
        for token in ('é'*32, '\ud800'*32):
            status,result=self.req('removal',{**body,'consent_id':token})
            self.assertEqual(status,409);self.assertIn('error',result)
        self.assertIsNone(self.req('report')[1]['removal_request'])

    def test_old_polling_claim_is_not_exported_as_removal_evidence(self):
        self.ready()
        with server.STORE.transaction():
            row=server.STORE.conn.execute("SELECT id,owner,expires,data FROM records WHERE kind='session'").fetchone()
            s=json.loads(row[3]);s['removal']='removal_confirmed'
            server.STORE.put('session',row[0],row[1],row[2],s)
        report=self.req('report')[1]
        self.assertEqual(report['removal'],'not_requested')
        self.assertIsNone(report['removal_request'])
        self.assertTrue(self.req('export')[1].startswith(b'%PDF-'))

    def test_same_identity_new_login_revokes_all_removal_routes(self):
        self.ready();listing=self.listing();body=self.consent(listing)
        original=(self.cookie,self.csrf);self.cookie='';self.csrf='';self.ready()
        self.cookie,self.csrf=original
        for path,data in (('removal/prepare',listing),('removal',body),
                          ('removal/cancel',{'consent_id':body['consent_id']}),('removal/status',{})):
            self.assertEqual(self.req(path,data)[0],401)


if __name__=='__main__':unittest.main(verbosity=2)
