"""Offline Twilio Verify schema contract; no SMS/network/authentication implementation."""
from dataclasses import dataclass
import re,time
from typing import Protocol
from storage import digest

PHONE='+12025550147'
SERVICE='VA'+'0'*32

class OwnershipAdapter(Protocol):
    def start(self,session_id: str,phone: str,consent: bool): ...
    def check(self,challenge,session_id: str,phone: str,code: str): ...

class SyntheticVerifyTransport:
    def __init__(self,*responses):self.responses=list(responses);self.calls=[]
    def post(self,url,form,timeout=5):
        self.calls.append({'url':url,'form':form,'timeout':timeout})
        if not self.responses:raise TimeoutError()
        result=self.responses.pop(0)
        if isinstance(result,Exception):raise result
        return result

@dataclass
class Challenge:
    session_ref:str
    phone_ref:str
    provider_sid:str
    expires:float
    attempts:int=0
    consumed:bool=False

class TwilioVerifyOffline:
    def __init__(self,transport):
        if not isinstance(transport,SyntheticVerifyTransport):raise ValueError('Live verification is disabled.')
        self.transport=transport
    def start(self,session_id,phone,consent):
        if phone!=PHONE or not session_id or consent is not True:raise ValueError('Synthetic number, session and consent required.')
        code,payload=self.transport.post(f'https://verify.twilio.com/v2/Services/{SERVICE}/Verifications',{'To':phone,'Channel':'sms'})
        if code!=201 or not isinstance(payload,dict) or payload.get('to')!=phone or payload.get('service_sid')!=SERVICE or payload.get('status')!='pending' or not re.fullmatch(r'VE[0-9a-fA-F]{32}',payload.get('sid','')):
            raise ValueError('Verification unavailable.')
        return Challenge(digest(session_id),digest(phone),payload['sid'],time.time()+300)
    def check(self,challenge,session_id,phone,code):
        if phone!=PHONE or digest(session_id)!=challenge.session_ref or digest(phone)!=challenge.phone_ref:
            raise ValueError('Challenge binding mismatch.')
        if challenge.consumed or challenge.expires<=time.time() or challenge.attempts>=5:raise ValueError('Challenge expired, consumed or locked.')
        if not isinstance(code,str) or not re.fullmatch(r'[0-9]{6}',code):raise ValueError('Six-digit code required.')
        challenge.attempts+=1
        try:
            status,payload=self.transport.post(f'https://verify.twilio.com/v2/Services/{SERVICE}/VerificationCheck',{'VerificationSid':challenge.provider_sid,'Code':code})
        except Exception:return False
        approved=(status==200 and isinstance(payload,dict) and payload.get('status')=='approved'
                  and payload.get('sid')==challenge.provider_sid and payload.get('service_sid')==SERVICE and payload.get('to')==phone)
        if approved:challenge.consumed=True
        return approved
