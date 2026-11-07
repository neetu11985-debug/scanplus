import sys,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ownership import TwilioVerifyOffline,SyntheticVerifyTransport,PHONE,SERVICE

def payload(status='pending',**extra):return dict({'sid':'VE'+'0'*32,'service_sid':SERVICE,'to':PHONE,'status':status},**extra)
class OwnershipTests(unittest.TestCase):
    def test_schema_bindings_and_replay(self):
        t=SyntheticVerifyTransport((201,payload()),(200,payload('approved')));a=TwilioVerifyOffline(t)
        challenge=a.start('session-a',PHONE,True)
        self.assertEqual(t.calls[0]['form'],{'To':PHONE,'Channel':'sms'})
        with self.assertRaises(ValueError):a.check(challenge,'session-b',PHONE,'246810')
        self.assertTrue(a.check(challenge,'session-a',PHONE,'246810'))
        with self.assertRaises(ValueError):a.check(challenge,'session-a',PHONE,'246810')
    def test_expired_attempt_limit_and_provider_mismatch(self):
        a=TwilioVerifyOffline(SyntheticVerifyTransport((201,payload()),*( [(200,payload('pending'))]*5 )))
        c=a.start('session-a',PHONE,True)
        for _ in range(5):self.assertFalse(a.check(c,'session-a',PHONE,'000000'))
        with self.assertRaises(ValueError):a.check(c,'session-a',PHONE,'246810')
        c.attempts=0;c.expires=0
        with self.assertRaises(ValueError):a.check(c,'session-a',PHONE,'246810')
        a=TwilioVerifyOffline(SyntheticVerifyTransport((201,payload()),(200,payload('approved',to='+12025550148'))));c=a.start('s',PHONE,True)
        self.assertFalse(a.check(c,'s',PHONE,'246810'))
    def test_no_real_phone_or_live_transport_and_timeout(self):
        with self.assertRaises(ValueError):TwilioVerifyOffline(object())
        t=SyntheticVerifyTransport();a=TwilioVerifyOffline(t)
        with self.assertRaises(ValueError):a.start('s','+12025550148',True)
        self.assertEqual(t.calls,[])
        a=TwilioVerifyOffline(SyntheticVerifyTransport((201,payload()),TimeoutError()));c=a.start('s',PHONE,True)
        self.assertFalse(a.check(c,'s',PHONE,'246810'))
