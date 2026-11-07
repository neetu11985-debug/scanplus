import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import unittest
from urllib.parse import parse_qs, urlsplit
from discovery import BraveDiscovery, Response, SyntheticTransport, FIXTURE_PHONE

class DiscoveryTests(unittest.TestCase):
    def lookup(self,payload,status=200):
        transport=SyntheticTransport(Response(status,payload))
        return BraveDiscovery(transport).discover(FIXTURE_PHONE,'spokeo.com',verified=True,consent=True),transport
    def test_exact_match_minimizes_data_and_request(self):
        result,transport=self.lookup({'web':{'results':[{'url':'https://www.spokeo.com/example?tracking=x#person','title':'A fictional person','description':'Phone (202) 555-0147; address: synthetic private street; family: synthetic household'}]}})
        self.assertEqual(result['status'],'match_needs_confirmation')
        c=result['candidates'][0]
        self.assertEqual(c['source_url'],'https://www.spokeo.com/example')
        self.assertFalse(c['removal_eligible'])
        self.assertNotIn('private street',json.dumps(result)); self.assertNotIn('fictional person',json.dumps(result))
        query=parse_qs(urlsplit(transport.calls[0][1]).query)
        self.assertEqual(query['result_filter'],['web']); self.assertEqual(query['extra_snippets'],['false'])
    def test_no_matches(self):
        result,_=self.lookup({'web':{'results':[]}})
        self.assertEqual(result['status'],'not_found_in_checked_sources')
    def test_unrelated_and_longer_numbers_ignored(self):
        result,_=self.lookup({'web':{'results':[{'url':'https://spokeo.com/a','description':'202-555-0148'},{'url':'https://spokeo.com/b','description':'920255501470'}]}})
        self.assertEqual(result['candidates'],[])
    def test_recycled_number_still_needs_confirmation(self):
        result,_=self.lookup({'web':{'results':[{'url':'https://spokeo.com/old','description':'Former subscriber +1 202 555 0147'}]}})
        self.assertEqual(result['candidates'][0]['status'],'match_needs_confirmation')
        self.assertFalse(result['candidates'][0]['removal_eligible'])
    def test_untrusted_links_and_dedup(self):
        urls=['javascript:alert(1)','https://spokeo.com.evil.test/a','https://user@spokeo.com/a','http://spokeo.com/a','https://spokeo.com/a?x=1','https://spokeo.com/a?x=2']
        result,_=self.lookup({'web':{'results':[{'url':u,'description':FIXTURE_PHONE} for u in urls]}})
        self.assertEqual(len(result['candidates']),1)
    def test_throttle_errors_and_timeout(self):
        for code,reason in ((429,'throttled'),(401,'provider_error'),(500,'provider_error')):
            with self.subTest(code=code): self.assertEqual(self.lookup({},code)[0]['reason'],reason)
        result=BraveDiscovery(SyntheticTransport(TimeoutError())).discover(FIXTURE_PHONE,'spokeo.com',verified=True,consent=True)
        self.assertEqual(result['reason'],'timeout')
    def test_missing_and_malformed_schema_are_unavailable(self):
        for payload in (None,[],{}, {'web':None},{'web':{'results':'oops'}}):
            with self.subTest(payload=payload): self.assertEqual(self.lookup(payload)[0]['status'],'source_unavailable')
    def test_no_real_phone_or_unconsented_calls(self):
        transport=SyntheticTransport(Response(200,{})); adapter=BraveDiscovery(transport)
        with self.assertRaises(ValueError): adapter.discover('+12025550148','spokeo.com',verified=True,consent=True)
        with self.assertRaises(ValueError): adapter.discover(FIXTURE_PHONE,'spokeo.com',verified=True)
        with self.assertRaises(ValueError): adapter.discover(FIXTURE_PHONE,'evil.test',verified=True,consent=True)
        self.assertEqual(transport.calls,[])
    def test_default_transport_fails_closed(self):
        result=BraveDiscovery().discover(FIXTURE_PHONE,'spokeo.com',verified=True,consent=True)
        self.assertEqual(result['reason'],'outbound_disabled')
