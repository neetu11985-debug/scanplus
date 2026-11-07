"""Serper tests use synthetic data and injected transport. No real provider calls."""
import http.client
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_scan import Settings, Providers, ScanSession, ScanError, HTTPSJSONTransport
from local_live_server import LocalLiveServer
from test_live_scan import FakeTransport, PHONE, verification, SETTINGS

SERPER = Settings(SETTINGS.account_sid, SETTINGS.auth_token, SETTINGS.verify_service_sid,
                  search_provider='serper', serper_key='SYNTHETIC-SERPER-KEY')

def organic(site='spokeo.com'):
    return {'organic': [{'link': 'https://' + site + '/listing?id=123&utm_source=private',
                         'title': 'Fictional Name', 'snippet': PHONE + ' synthetic private street'}],
            'knowledgeGraph': {'description': 'unrelated private household data'}}

class SerperTests(unittest.TestCase):
    def session(self, *responses):
        transport = FakeTransport(*responses)
        return ScanSession(Providers(SERPER, transport)), transport

    def ready(self, *responses):
        session, transport = self.session((201, verification()), (200, verification('approved')), *responses)
        session.start(PHONE, own_number=True, twilio_consent=True)
        session.verify('123456')
        return session, transport

    def test_environment_default_is_serper_no_brave_fallback(self):
        env = {'SCANPLUS_LOCAL_LIVE_TEST': '1', 'TWILIO_ACCOUNT_SID': SETTINGS.account_sid,
               'TWILIO_AUTH_TOKEN': SETTINGS.auth_token, 'TWILIO_VERIFY_SERVICE_SID': SETTINGS.verify_service_sid,
               'SERPER_API_KEY': 'SYNTHETIC-SERPER-KEY'}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_environment()
            self.assertEqual(settings.search_provider, 'serper')
            self.assertEqual(settings.brave_key, '')
            self.assertNotIn('SYNTHETIC-SERPER-KEY', repr(settings))
        with patch.dict(os.environ, dict(env, SERPER_API_KEY='', BRAVE_SEARCH_API_KEY='SYNTHETIC-BRAVE'), clear=True):
            with self.assertRaisesRegex(ScanError, 'SERPER_API_KEY'): Settings.from_environment()
        with patch.dict(os.environ, dict(env, SCANPLUS_SEARCH_PROVIDER='brave', BRAVE_SEARCH_API_KEY='SYNTHETIC-BRAVE'), clear=True):
            settings = Settings.from_environment()
            self.assertEqual(settings.search_provider, 'brave')
            self.assertEqual(settings.serper_key, '')
        for changed in ({'SCANPLUS_SEARCH_PROVIDER': 'unknown'}, {'SERPER_API_KEY': 'bad\nkey'}):
            with patch.dict(os.environ, dict(env, **changed), clear=True):
                with self.assertRaises(ScanError): Settings.from_environment()

    def test_provider_specific_consent_and_no_unverified_calls(self):
        session, transport = self.session()
        with self.assertRaises(ScanError): session.scan(serper_consent=True)
        self.assertEqual(transport.calls, [])
        session, transport = self.ready(*[(200, {'organic': []})] * 3)
        self.assertEqual(session.state()['search_provider'], 'serper')
        for consent in ({}, {'brave_consent': True}, {'serper_consent': 'true'}):
            with self.assertRaisesRegex(ScanError, 'Serper'): session.scan(**consent)
        self.assertEqual(len(transport.calls), 2)
        report = session.scan(serper_consent=True)
        self.assertEqual(report['report']['sources_checked'], 3)
        self.assertEqual(session.scan(serper_consent=True), report)
        self.assertEqual(len(transport.calls), 5)
        self.assertIsNone(session.phone)
        self.assertIsNone(session.sid)

    def test_bounded_request_and_minimal_candidates(self):
        transport = FakeTransport((200, organic()))
        result = Providers(SERPER, transport).discover(PHONE, 'spokeo.com')
        method, url, kwargs = transport.calls[0]
        self.assertEqual(method, 'POST')
        self.assertEqual(url, 'https://google.serper.dev/search')
        self.assertNotIn(PHONE, url)
        self.assertEqual(json.loads(kwargs['body']), {'q': '"' + PHONE + '" site:spokeo.com', 'num': 10})
        self.assertEqual(kwargs['headers']['X-API-KEY'], 'SYNTHETIC-SERPER-KEY')
        self.assertEqual(result['provider'], 'serper')
        self.assertEqual(result['candidates'][0]['source_url'], 'https://spokeo.com/listing?id=123')
        self.assertFalse(result['candidates'][0]['removal_eligible'])
        for value in (PHONE, 'Fictional Name', 'private street', 'household', 'SYNTHETIC-SERPER-KEY'):
            self.assertNotIn(value, json.dumps(result))

    def test_invalid_outcomes_no_absence_or_fallback(self):
        for response in ((401, None), (402, None), (403, None), (429, None), (500, None),
                         TimeoutError('private detail'), (200, {}), (200, {'organic': None}), (200, []), (200, {'organic':[None, {}]}),
                         (200, {'organic':[{'link':'https://spokeo.com/a','snippet':42}]})):
            transport = FakeTransport(response)
            result = Providers(SERPER, transport).discover(PHONE, 'spokeo.com')
            self.assertEqual(result['status'], 'source_unavailable')
            self.assertEqual(result['candidates'], [])
            self.assertEqual(len(transport.calls), 1)
            self.assertEqual(transport.calls[0][1], 'https://google.serper.dev/search')
            self.assertNotIn('private detail', json.dumps(result))

    def test_false_matches_urls_duplicates_and_result_bound(self):
        items = [{'link':'https://spokeo.com.evil.example/a','snippet':PHONE},
                 {'link':'http://spokeo.com/a','snippet':PHONE},
                 {'link':'https://user:password@spokeo.com/a','snippet':PHONE},
                 {'link':'https://spokeo.com/a','snippet':'+44 202 555 0147'},
                 {'link':'https://spokeo.com/b','snippet':'920255501470'},
                 {'link':'https://spokeo.com/c','snippet':PHONE},
                 {'link':'https://spokeo.com/c','snippet':PHONE}]
        items += [{'link':'https://spokeo.com/no-match','snippet':'No exact phone'}] * 3
        items += [{'link':'https://spokeo.com/beyond-bound','snippet':PHONE}]
        self.assertEqual(len(items), 11)
        transport = FakeTransport((200, {'organic':items}))
        result = Providers(SERPER, transport).discover(PHONE, 'spokeo.com')
        self.assertEqual([c['source_url'] for c in result['candidates']], ['https://spokeo.com/c'])
        with self.assertRaises(ScanError): Providers(SERPER, transport).discover(PHONE, 'evil.example')
        self.assertEqual(len(transport.calls), 1)

    def test_expired_session_does_not_start_queries(self):
        session, transport = self.ready()
        session.expires = -1
        with self.assertRaises(ScanError): session.scan(serper_consent=True)
        self.assertEqual(len(transport.calls), 2)

    def test_transport_destination_method_and_path_are_fixed(self):
        for method, url in [('GET','https://google.serper.dev/search'), ('POST','https://google.serper.dev/maps'),
                            ('POST','https://google.serper.dev/search?q=private'), ('POST','https://google.serper.dev/search#x'),
                            ('POST','https://evil.example/search'), ('POST','https://google.serper.dev.evil.example/search')]:
            with patch('live_scan.http.client.HTTPSConnection') as connection:
                with self.assertRaises(ScanError): HTTPSJSONTransport().request(method,url,headers={})
                connection.assert_not_called()
        connection = MagicMock()
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read.return_value = b'{"organic":[]}'
        with patch('live_scan.http.client.HTTPSConnection', return_value=connection) as ctor:
            self.assertEqual(HTTPSJSONTransport().request('POST','https://google.serper.dev/search',headers={},body='{}'),(200,{'organic':[]}))
            ctor.assert_called_once_with('google.serper.dev',timeout=5)
            connection.request.assert_called_once_with('POST','/search',body='{}',headers={})
            connection.close.assert_called_once()

class SerperHTTPTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport((201, verification()), (200, verification('approved')),
                                      *[(200, {'organic':[]})] * 3)
        self.server = LocalLiveServer(('127.0.0.1',0),Providers(SERPER,self.transport))
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.cookie=''; self.csrf=''
    def tearDown(self):
        self.server.shutdown();self.server.server_close()
    def request(self,path,data=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        c.request('GET' if data is None else 'POST', '/api/'+path,
                  None if data is None else json.dumps(data),
                  {'Origin':'http://127.0.0.1:'+str(self.server.server_port),'Content-Type':'application/json',
                   'Cookie':self.cookie,'X-CSRF-Token':self.csrf})
        r=c.getresponse();body=json.loads(r.read());cookie=r.getheader('Set-Cookie')
        if cookie:self.cookie=cookie.split(';')[0]
        if 'csrf_token' in body:self.csrf=body['csrf_token']
        status=r.status;c.close();return status,body
    def test_provider_bound_full_http_journey(self):
        self.assertEqual(self.request('session')[1]['search_provider'],'serper')
        self.assertEqual(self.request('start',{'phone':PHONE,'own_number':True,'twilio_consent':True})[0],200)
        self.assertEqual(self.request('verify',{'code':'123456'})[0],200)
        self.assertEqual(self.request('scan',{'brave_consent':True})[0],409)
        self.assertEqual(len(self.transport.calls),2)
        status,result=self.request('scan',{'serper_consent':True})
        self.assertEqual(status,200);self.assertEqual(result['report']['sources_checked'],3)
        self.assertTrue(all(s['provider']=='serper' for s in result['report']['sources']))
        self.assertEqual((status,result),self.request('scan',{'serper_consent':True}))
        self.assertEqual(len(self.transport.calls),5)
        self.assertEqual(self.request('clear',{})[1]['phase'],'entry')
        self.assertIsNone(self.request('session')[1]['report'])

if __name__ == '__main__':unittest.main()
