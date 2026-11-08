"""Synthetic report/export/removal checklist regressions. No real provider calls."""
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_scan import Providers, ScanSession, ScanError, HTTPSJSONTransport, live_source_link
from local_live_server import LocalLiveServer
from scan_report import build_report, report_text, removal_guide
from test_live_scan import FakeTransport, SETTINGS, PHONE, verification
from test_serper_scan import SERPER

SITES = ('spokeo.com', 'truepeoplesearch.com', 'whitepages.com')

def payload(site, provider='serper', title='Synthetic listing', snippet=PHONE):
    item={'title':title}
    if provider=='serper':
        item.update(link='https://'+site+'/profile?id=123',snippet=snippet)
        return {'organic':[item]}
    item.update(url='https://'+site+'/profile?id=123',description=snippet)
    return {'web':{'results':[item]}}

def ready_session():
    transport=FakeTransport((201,verification()),(200,verification('approved')),
                            *[(200,payload(site)) for site in SITES])
    session=ScanSession(Providers(SERPER,transport))
    session.start(PHONE,own_number=True,twilio_consent=True)
    session.verify('123456')
    session.scan(serper_consent=True)
    return session,transport

class ReportTests(unittest.TestCase):
    def test_report_has_guides_dates_coverage_and_no_personal_snippets(self):
        session,transport=ready_session()
        report=session.current_report()
        self.assertEqual(report['sources_checked'],3)
        self.assertEqual(report['last_four'],'0147')
        self.assertEqual(report['schema_version'],1)
        self.assertIn('No removal was submitted',report['removal_notice'])
        for source in report['sources']:
            guide=source['guide']
            self.assertEqual(guide['destination_verification'],'primary_registry_confirmed')
            self.assertEqual(guide['workflow_verification'],'not_verified')
            self.assertEqual(guide['reviewed_at'],'2026-11-06')
            self.assertFalse(guide['automation_supported'])
            self.assertTrue(guide['steps'])
            self.assertEqual(source['candidates'][0]['match_review'],'needs_confirmation')
        for value in (PHONE,'Synthetic listing','SYNTHETIC-TOKEN','SYNTHETIC-SERPER-KEY'):
            self.assertNotIn(value,json.dumps(report))
        self.assertEqual(len(transport.calls),5)

    def test_manual_progress_is_explicit_local_idempotent_and_never_verified(self):
        session,transport=ready_session()
        candidate=session.report['sources'][0]['candidates'][0]
        cid=candidate['id']
        for args in ((cid,'confirm_mine',False),(cid,'confirm_mine','true'),(cid,'record_manual_request',True),('missing','confirm_mine',True),(cid,'mark_removed',True)):
            with self.assertRaises(ScanError):session.review_listing(*args)
        session.review_listing(cid,'confirm_mine',True)
        self.assertEqual(candidate['match_review'],'confirmed_by_user')
        for _ in range(2):session.review_listing(cid,'record_manual_request',True)
        self.assertEqual(candidate['manual_action'],'user_recorded_request')
        session.review_listing(cid,'confirm_mine',True)
        self.assertEqual(candidate['manual_action'],'user_recorded_request','Repeated confirmation cannot reset a recorded request')
        self.assertFalse(candidate['removal_eligible'])
        self.assertFalse(candidate['removal_verified'])
        self.assertEqual(len(transport.calls),5,'Local checklist must never contact a provider')
        session.review_listing(cid,'not_mine',True)
        self.assertEqual(candidate['match_review'],'not_mine')
        self.assertEqual(candidate['manual_action'],'not_started')
        with self.assertRaises(ScanError):session.review_listing(cid,'record_manual_request',True)
        session.review_listing(cid,'reset',True)
        self.assertEqual(candidate['match_review'],'needs_confirmation')

    def test_report_clear_and_expiry_invalidate_exports_and_updates(self):
        for action in ('clear','expire'):
            session,transport=ready_session()
            cid=session.report['sources'][0]['candidates'][0]['id']
            if action=='clear':session.clear()
            else:session.expires=-1
            with self.assertRaises(ScanError):session.current_report()
            with self.assertRaises(ScanError):session.review_listing(cid,'confirm_mine',True)
            self.assertIsNone(session.report)
            self.assertEqual(len(transport.calls),5)

    def test_readable_report_all_outcomes_and_download_disclosure(self):
        session,_=ready_session()
        report=session.report
        report['sources'][1].update(status='source_unavailable',reason='throttled',candidates=[])
        report['sources'][2].update(status='not_found_in_checked_sources',candidates=[])
        text=report_text(report)
        for word in ('SCANPLUS LOCAL SEARCH REPORT','Potential match','Source unavailable: no absence conclusion','No exact phone match',
                     'spokeo.com/optout','whitepages.com/privacy/consumer-rights','truepeoplesearch.com/privacy',
                     'Removal verified by ScanPlus: no','California Data Broker Registry','remain on your device'):
            self.assertIn(word,text)
        self.assertNotIn(PHONE,text)

    def test_skipped_sources_are_not_labeled_checked_in_text_export(self):
        session,_=ready_session()
        session.report['sources'][1].update(status='source_unavailable', candidates=[],
            query_attempted=False, checked_at='UNATTEMPTED_TIMESTAMP', reason='not_attempted_after_provider_error')
        text=report_text(session.report)
        self.assertIn('Query not attempted', text)
        self.assertNotIn('UNATTEMPTED_TIMESTAMP', text)
        self.assertIn('Source unavailable: no absence conclusion', text)

    def test_stale_listing_action_cannot_mutate_a_replacement_report(self):
        session,transport=ready_session()
        report_a=session.report
        cid_a=report_a['sources'][0]['candidates'][0]['id']
        # Same site/listing URL, different report and verified phone context.
        report_b=build_report(report_a['sources'],'serper','0148')
        session.clear()
        session.phase='report';session.report=report_b
        cid_b=report_b['sources'][0]['candidates'][0]['id']
        self.assertNotEqual(report_a['report_id'],report_b['report_id'])
        self.assertNotEqual(cid_a,cid_b)
        with self.assertRaisesRegex(ScanError,'not in this session'):
            session.review_listing(cid_a,'confirm_mine',True)
        self.assertEqual(report_b['sources'][0]['candidates'][0]['match_review'],'needs_confirmation')
        self.assertEqual(len(transport.calls),5)

    def test_unknown_source_has_no_invented_guide(self):
        with self.assertRaises(ValueError):removal_guide('unknown.example')

    def test_brave_malformed_nonempty_results_unavailable(self):
        valid={'url':'https://spokeo.com/a','description':PHONE}
        for results in ([None],[{}],[{'url':'https://spokeo.com/a','description':42}],[valid,None]):
            transport=FakeTransport((200,{'web':{'results':results}}))
            result=Providers(SETTINGS,transport).discover(PHONE,'spokeo.com')
            self.assertEqual(result['status'],'source_unavailable')
            self.assertEqual(result['reason'],'invalid_response')
            self.assertEqual(len(transport.calls),1)
        result=Providers(SETTINGS,FakeTransport((200,{'web':{'results':[]}}))).discover(PHONE,'spokeo.com')
        self.assertEqual(result['status'],'not_found_in_checked_sources')

    def test_fields_never_fabricate_or_hide_an_exact_phone(self):
        for settings in (SERPER,SETTINGS):
            for title,snippet,expected in [('202','555-0147',False),('202-555-0147','1 public record found',True),
                                          ('Phone directory 2026','(202) 555-0147',True)]:
                result=Providers(settings,FakeTransport((200,payload('spokeo.com',settings.search_provider,title,snippet)))).discover(PHONE,'spokeo.com')
                self.assertEqual(bool(result['candidates']),expected,(settings.search_provider,title,snippet))

    def test_source_links_reject_controls_and_untrusted_destinations(self):
        for raw in (' https://spokeo.com/a','https://spokeo.com/a\x00b','https://spokeo.com/a\x0bb',
                    'https://spokeo.com/a\x7fb','https://spokeo.com/a b','javascript:alert(1)',
                    'https://spokeo.com.evil.test/a','https://user:secret@spokeo.com/a'):
            self.assertIsNone(live_source_link(raw,'spokeo.com'),repr(raw))
        self.assertEqual(live_source_link('https://www.spokeo.com/a?id=42&utm_source=x','spokeo.com'),'https://www.spokeo.com/a?id=42')

    def test_all_transports_restrict_operation_before_connecting(self):
        for method,url in [('GET','https://verify.twilio.com/v2/Services/'+SETTINGS.verify_service_sid+'/Verifications'),
                           ('POST','https://verify.twilio.com/other'),('POST','https://api.search.brave.com/res/v1/web/search'),
                           ('GET','https://api.search.brave.com/other'),('GET','https://api.search.brave.com/res/v1/web/search#x')]:
            with patch('live_scan.http.client.HTTPSConnection') as connection:
                with self.assertRaises(ScanError):HTTPSJSONTransport().request(method,url,headers={})
                connection.assert_not_called()

class ReportHTTPTests(unittest.TestCase):
    def setUp(self):
        self.transport=FakeTransport((201,verification()),(200,verification('approved')),*[(200,payload(site)) for site in SITES])
        self.server=LocalLiveServer(('127.0.0.1',0),Providers(SERPER,self.transport))
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.cookie='';self.csrf=''
    def tearDown(self):
        self.server.shutdown();self.server.server_close()
    def request(self,path,data=None,**overrides):
        headers={'Cookie':self.cookie,'X-CSRF-Token':self.csrf,'Origin':'http://127.0.0.1:'+str(self.server.server_port),'Content-Type':'application/json'}
        headers.update(overrides)
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        conn.request('GET' if data is None else 'POST',path,None if data is None else json.dumps(data),headers)
        response=conn.getresponse();raw=response.read();self.headers=dict(response.getheaders());status=response.status
        if response.getheader('Set-Cookie'):self.cookie=response.getheader('Set-Cookie').split(';')[0]
        result=json.loads(raw) if 'json' in response.getheader('Content-Type','') else raw if response.getheader('Content-Type') == 'application/pdf' else raw.decode()
        if isinstance(result,dict) and 'csrf_token' in result:self.csrf=result['csrf_token']
        conn.close();return status,result
    def ready(self):
        self.assertEqual(self.request('/api/session')[0],200)
        self.assertEqual(self.request('/api/start',{'phone':PHONE,'own_number':True,'twilio_consent':True})[0],200)
        self.assertEqual(self.request('/api/verify',{'code':'123456'})[0],200)
        status,state=self.request('/api/scan',{'serper_consent':True});self.assertEqual(status,200)
        return state['report']
    def test_exports_need_current_completed_session_and_are_attachments(self):
        for path in ('/api/report','/api/export.txt','/api/export.pdf'):
            self.assertEqual(self.request(path)[0],401)
        self.request('/api/session')
        self.assertEqual(self.request('/api/export.txt')[0],409)
        report=self.ready()
        status,text=self.request('/api/export.txt')
        self.assertEqual(status,200);self.assertIn(report['report_id'],text)
        self.assertEqual(self.headers['Content-Disposition'],'attachment; filename=scanplus-local-report.txt')
        self.assertEqual(self.headers['Cache-Control'],'no-store')
        self.assertEqual(self.headers['X-Content-Type-Options'],'nosniff')
        status,download=self.request('/api/export.pdf')
        self.assertEqual(status,200);self.assertTrue(download.startswith(b'%PDF-1.7'));self.assertIn(report['report_id'].encode(),download)
        self.assertEqual(self.headers['Content-Type'],'application/pdf')
        self.assertEqual(int(self.headers['Content-Length']),len(download))
        self.assertEqual(self.headers['Content-Disposition'],'attachment; filename=scanplus-local-report.pdf')
        self.assertEqual(len(self.transport.calls),5)
        self.assertEqual(self.request('/api/export.json')[0],404)
        self.request('/api/clear',{})
        self.assertEqual(self.request('/api/export.pdf')[0],409)
    def test_export_isolated_same_origin_and_expiring(self):
        self.ready();first_cookie=self.cookie
        for headers in ({'Origin':'https://evil.example'},{'Host':'evil.example'},{'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.request('/api/export.pdf',**headers)[0],403)
        self.cookie='';self.csrf='';self.request('/api/session')
        self.assertEqual(self.request('/api/export.pdf')[0],409)
        self.cookie=first_cookie
        self.server.sessions[first_cookie.split('=',1)[1]]['scan'].expires=-1
        self.assertEqual(self.request('/api/export.txt')[0],409)
    def test_pdf_expiry_during_generation_fails_before_download(self):
        self.ready()
        scan=self.server.sessions[self.cookie.split('=',1)[1]]['scan']
        def slow_pdf(report):
            scan.expires=-1
            return b'%PDF-1.7 synthetic result must not be returned'
        with patch('local_live_server.report_pdf',side_effect=slow_pdf):
            status,body=self.request('/api/export.pdf')
        self.assertEqual(status,409)
        self.assertNotIn('Content-Disposition',self.headers)
        self.assertEqual(len(self.transport.calls),5)

    def test_checklist_csrf_confirmation_scope_and_no_removal_endpoint(self):
        report=self.ready();cid=report['sources'][0]['candidates'][0]['id']
        data={'candidate_id':cid,'action':'confirm_mine','confirmed':True}
        self.assertEqual(self.request('/api/listing/review',data,**{'X-CSRF-Token':''})[0],403)
        self.assertEqual(self.request('/api/listing/review',dict(data,confirmed=False))[0],409)
        self.assertEqual(self.request('/api/listing/review',dict(data,candidate_id='other-report-id'))[0],409)
        self.assertEqual(self.request('/api/listing/review',data)[0],200)
        self.assertEqual(self.request('/api/listing/review',dict(data,action='record_manual_request'))[0],200)
        report=self.request('/api/report')[1]
        self.assertEqual(report['sources'][0]['candidates'][0]['manual_action'],'user_recorded_request')
        self.assertFalse(report['sources'][0]['candidates'][0]['removal_verified'])
        for path in ('/api/removal','/api/removal/status','/api/checkout'):
            self.assertEqual(self.request(path,{})[0],404)
        self.assertEqual(len(self.transport.calls),5)

if __name__=='__main__':unittest.main()
