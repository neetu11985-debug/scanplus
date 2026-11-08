"""Offline, synthetic-only PDF structure/privacy/security regression tests."""
from copy import deepcopy
import io
import re
import unittest
from unittest.mock import patch

from scan_report_pdf import report_pdf, demo_report_pdf, safe_url, wrap, width
from providers import FixtureDiscovery
from test_scan_report import ready_session


class PDFTests(unittest.TestCase):
    def setUp(self):
        self.report = ready_session()[0].report

    def test_valid_xref_and_tagged_reading_navigation(self):
        raw = report_pdf(self.report)
        self.assertTrue(raw.startswith(b'%PDF-1.7\n'))
        self.assertTrue(raw.endswith(b'%%EOF\n'))
        pointer = int(re.search(rb'startxref\n(\d+)\n',raw).group(1))
        self.assertEqual(raw[pointer:pointer+4],b'xref')
        rows = raw[pointer:].split(b'\n')
        total = int(rows[1].split()[1])
        for index,row in enumerate(rows[3:total+2],1):
            offset = int(row[:10])
            self.assertTrue(raw[offset:].startswith(str(index).encode()+b' 0 obj\n'))
        for value in (b'/StructTreeRoot',b'/MarkInfo << /Marked true',b'/Lang (en-US)',b'/ToUnicode',b'/Outlines',b'/Tabs /S',b'/StructParent',b'/OBJR'):
            self.assertIn(value,raw)
        for forbidden in (b'/JavaScript',b'/JS ',b'/Launch',b'/OpenAction',b'/EmbeddedFile',b'/SubmitForm'):
            self.assertNotIn(forbidden,raw)

    def test_generation_is_memory_only_deterministic_and_does_not_mutate(self):
        before = deepcopy(self.report)
        with patch('builtins.open',side_effect=AssertionError('No file I/O')), patch('socket.socket',side_effect=AssertionError('No network')):
            one = report_pdf(self.report)
            two = report_pdf(self.report)
        self.assertEqual(one,two)
        self.assertEqual(before,self.report)
        self.assertNotIn(b'+12025550147',one)
        self.assertNotIn(b'SYNTHETIC-SERPER-KEY',one)

    def test_reports_preserve_ownership_unavailable_and_removal_limits(self):
        self.report.update(test_scope='private_owner',ownership_verified=False)
        self.report['sources'][1].update(status='source_unavailable',candidates=[],reason='timeout',query_attempted=False)
        self.report['sources'][2].update(status='not_found_in_checked_sources',candidates=[])
        raw = report_pdf(self.report)
        for text in (b'PRIVATE NO-SMS SELF-TEST',b'self-attested, not verified',b'Query not attempted',b'Unavailable - no conclusion',b'No exact match in checked results',b'not independently verified',b'not encrypted'):
            self.assertIn(text,raw)

    def test_untrusted_guide_and_snippets_cannot_add_destinations_or_metadata(self):
        self.report['sources'][0]['guide']={'url':'https://evil.example','steps':['SECRET-CONTENT']}
        self.report['sources'][0]['candidates'][0]['evidence']='SECRET-CONTENT /JavaScript'
        self.report['phone']='+12025550147'
        raw=report_pdf(self.report)
        self.assertNotIn(b'evil.example',raw)
        self.assertNotIn(b'SECRET-CONTENT',raw)
        self.assertIn(b'https://www.spokeo.com/optout',raw)

    def test_url_scheme_host_userinfo_control_and_length_fail_closed(self):
        for url in ('javascript:alert(1)','https://evil.example/a','https://spokeo.com.evil.example/a','https://user:password@spokeo.com/a','https://@spokeo.com/a','https://spokeo.com:444/a','https://spokeo.com/a\nq','https://spokeo.com/'+('a'*2050)):
            with self.subTest(url=url[:60]), self.assertRaises(ValueError):
                safe_url(url,'spokeo.com')
        self.assertEqual(safe_url('https://spokeo.com/caf\u00e9','spokeo.com'),'https://spokeo.com/caf%C3%A9')

    def test_long_urls_and_pdf_metacharacters_remain_wrapped_text(self):
        url='https://spokeo.com/'+('W'*1700)+'?value=(synthetic)\\path'
        self.report['sources'][0]['candidates'][0]['source_url']=url
        raw=report_pdf(self.report)
        self.assertIn(b'%5Cpath',raw)
        for line in wrap(safe_url(url,'spokeo.com'),8,516):
            self.assertLessEqual(width(line,8),516)
        for source in self.report['sources']:
            source['candidates']=[dict(source['candidates'][0]) for _ in range(10)]
        raw=report_pdf(self.report)
        count=len(re.findall(rb'/Type /Page /',raw))
        self.assertGreater(count,5)
        self.assertLess(count,81)
        self.assertLess(len(raw),2_000_000)

    def test_illustrated_roadmap_is_ordered_selectable_and_honest(self):
        raw=report_pdf(self.report)
        steps=(b'1. Confirm the exact record', b'2. Open the official removal page',
               b'3. Submit and complete verification', b'4. Save confirmation and recheck')
        offsets=[raw.index(step) for step in steps]
        self.assertEqual(offsets,sorted(offsets))
        displayed=b' '.join(re.findall(rb'\((.*?)\) Tj',raw))
        for text in (b'Illustrations, not screenshots', b'not been live-verified',
                     b'No automatic removal or completed deletion',
                     b'No authorized public deletion API verified', b'8 November 2026'):
            self.assertIn(text,displayed)
        # Vector line art is decorative; instruction text remains tagged/readable.
        self.assertGreaterEqual(raw.count(b'1.8 w 1 J 1 j'),4)
        self.assertNotIn(b'/Subtype /Image',raw)
        for url in (b'https://www.spokeo.com/optout',
                    b'https://www.whitepages.com/privacy/consumer-rights',
                    b'https://www.truepeoplesearch.com/privacy'):
            self.assertIn(url,raw)

    def test_inconsistent_or_oversized_inputs_fail_closed(self):
        for mutate in (lambda r:r.update(last_four='+12025550147'),
                       lambda r:r['sources'].append(deepcopy(r['sources'][0])),
                       lambda r:r['sources'][0].update(status='source_unavailable'),
                       lambda r:r['sources'][0].update(candidates=[r['sources'][0]['candidates'][0]]*11)):
            r=deepcopy(self.report);mutate(r)
            with self.assertRaises(ValueError): report_pdf(r)

    def test_demo_never_becomes_a_real_finding(self):
        report={'demo':True,'test_mode':True,'phone':'+12025550147','report_id':'fixture','providers':FixtureDiscovery().discover()}
        raw=demo_report_pdf(report)
        self.assertIn(b'STRIPE SANDBOX DEMO',raw)
        self.assertIn(b'Example listing - synthetic only',raw)
        self.assertIn(b'No live source was checked',raw)
        self.assertNotIn(b'/URI (https://spokeo.com/profile',raw)
        with self.assertRaises(ValueError):demo_report_pdf(dict(report,demo=False))
