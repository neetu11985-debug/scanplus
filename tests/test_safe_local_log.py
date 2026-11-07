"""Local log checks use temporary files and fake providers only."""
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from safe_local_log import SafeLocalLog, safe_record, format_safe_line
import test_local_live_server as support
from test_live_scan import PHONE, SETTINGS, verification

class SafeLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'activity.log'
        self.log = SafeLocalLog(self.path)
    def tearDown(self): self.temp.cleanup()
    def test_fixed_schema_and_private_file(self):
        self.assertTrue(self.log.write('sms_start', local_status=409, provider_status=403, twilio_error_code=21608, phase='start_uncertain'))
        result = json.loads(self.path.read_text())
        self.assertEqual(set(result), {'time_utc','event','local_http_status','provider_http_status','twilio_error_code','phase'})
        self.assertEqual(result['twilio_error_code'], 21608)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertFalse(self.log.write('secret phone ' + PHONE))
        self.assertFalse(self.log.write('sms_start', body=PHONE))
        self.assertNotIn(PHONE, self.path.read_text())
    def test_viewer_never_prints_raw_or_unknown_fields(self):
        row=safe_record('sms_start',local_status=409,provider_status=403,twilio_error_code=21608)
        row['message']='PRIVATE'
        row['phone']=PHONE
        text=format_safe_line(json.dumps(row))
        self.assertIn('twilio_error_code=21608',text)
        for private in ('PRIVATE', PHONE): self.assertNotIn(private,text)
        for raw in ('PRIVATE', '[]', '{"event":"PRIVATE"}', json.dumps(dict(row,time_utc='PRIVATE'))):
            self.assertIsNone(format_safe_line(raw))
        self.assertNotIn('123456',format_safe_line(json.dumps(dict(row,twilio_error_code='123456'))))

    def test_values_not_coerced_or_echoed(self):
        for value in (True, False, '403', 'private', 403.5, None, [], {}):
            row = safe_record('sms_start', local_status=value, provider_status=value, twilio_error_code=value, phase=value)
            self.assertEqual(set(row), {'time_utc','event'})
        self.assertEqual(set(safe_record('sms_start',local_status=600,provider_status=201,twilio_error_code=123456)), {'time_utc','event','provider_http_status'})
        for event in (PHONE, [], None): self.assertIsNone(safe_record(event))
    def test_refuses_links_and_insecure_or_nonregular_files(self):
        target = Path(self.temp.name) / 'target'
        target.write_text('do not modify')
        self.path.symlink_to(target)
        self.assertFalse(self.log.write('server_started'))
        self.path.unlink()
        os.link(target, self.path)
        self.assertFalse(self.log.write('server_started'))
        self.path.unlink()
        os.mkfifo(self.path, 0o600)
        self.assertFalse(self.log.write('server_started'))
        self.path.unlink()
        self.path.write_text('existing')
        self.path.chmod(0o644)
        self.assertFalse(self.log.write('server_started'))
        self.assertEqual(target.read_text(), 'do not modify')
        self.assertEqual(self.path.read_text(), 'existing')
    def test_cap_never_truncates_and_failure_is_nonfatal(self):
        self.assertTrue(self.log.write('server_started'))
        original = self.path.read_bytes()
        with patch('safe_local_log.MAX_LOG_BYTES', len(original)):
            self.assertFalse(self.log.write('server_stopped'))
        self.assertEqual(self.path.read_bytes(), original)
        with patch('safe_local_log.os.open', side_effect=OSError('PRIVATE')):
            self.assertFalse(self.log.write('server_started'))

class SafeLogHTTPTests(unittest.TestCase):
    request = support.LocalLiveHTTPTests.request
    bootstrap = support.LocalLiveHTTPTests.bootstrap
    start = support.LocalLiveHTTPTests.start
    def setUp(self):
        support.LocalLiveHTTPTests.setUp(self)
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'activity.log'
        self.server.activity_log = SafeLocalLog(self.path)
    def tearDown(self):
        support.LocalLiveHTTPTests.tearDown(self)
        self.temp.cleanup()
    def test_numeric_diagnostic_no_request_or_response_content(self):
        self.transport.responses = [(403, {'code':21608, 'message':'PRIVATE', 'to':PHONE})]
        self.bootstrap()
        self.assertEqual(self.start()[0],409)
        self.assertEqual(self.request('/unknown?phone=' + PHONE)[0],404)
        self.assertEqual(self.request('/.data/scanmydigits-local.log')[0],404)
        text=self.path.read_text()
        for private in (PHONE, 'PRIVATE', SETTINGS.auth_token, 'unknown?phone', 'scanmydigits-local.log', self.csrf, self.cookie):
            self.assertNotIn(private, text)
        rows=[json.loads(line) for line in text.splitlines()]
        sms=next(row for row in rows if row['event']=='sms_start')
        self.assertEqual((sms['local_http_status'],sms['provider_http_status'],sms['twilio_error_code']), (409,403,21608))
        self.assertEqual(len(self.transport.calls),1)
        self.assertEqual(rows[-1]['event'],'unknown_route')
    def test_logging_failure_does_not_break_app_or_trigger_provider(self):
        with patch.object(self.server.activity_log,'write',side_effect=OSError('PRIVATE')):
            self.assertEqual(self.request('/')[0],200)
            self.bootstrap()
        self.assertEqual(self.transport.calls,[])
    def test_successful_code_not_recorded(self):
        self.transport.responses=[(201,verification()),(200,verification('approved'))]
        self.bootstrap(); self.assertEqual(self.start()[0],200)
        self.assertEqual(self.request('/api/verify',{'code':'123456'})[0],200)
        text=self.path.read_text()
        for private in (PHONE,'123456',SETTINGS.auth_token): self.assertNotIn(private,text)
        row=json.loads(text.splitlines()[-1])
        self.assertEqual(row['event'],'code_check')
        self.assertEqual(row['phase'],'verified')
        self.assertNotIn('twilio_error_code',row)

if __name__=='__main__': unittest.main()
