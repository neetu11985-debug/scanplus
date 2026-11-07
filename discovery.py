"""Brave schema adapter, offline transport only. Never registered in demo HTTP routes."""
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Protocol
from urllib.parse import urlencode, urlsplit, urlunsplit

FIXTURE_PHONE = '+12025550147'
ENDPOINT = 'https://api.search.brave.com/res/v1/web/search'
SITES = frozenset({'spokeo.com', 'whitepages.com', 'truepeoplesearch.com'})

@dataclass(frozen=True)
class Response:
    status: int
    payload: object

class Transport(Protocol):
    def request(self, method: str, url: str, *, headers: dict, timeout: float) -> Response: ...

class DisabledTransport:
    def request(self, *args, **kwargs):
        raise RuntimeError('Outbound discovery is disabled.')

class SyntheticTransport:
    """No network implementation. A synthetic response or exception is injected."""
    def __init__(self, response): self.response=response; self.calls=[]
    def request(self, method, url, *, headers, timeout):
        self.calls.append((method,url,headers,timeout))
        if isinstance(self.response, Exception): raise self.response
        return self.response

def source_link(raw, site):
    if not isinstance(raw,str) or len(raw)>2048: return None
    try:
        p=urlsplit(raw)
        if p.scheme!='https' or p.username or p.password or p.port not in (None,443): return None
        host=(p.hostname or '').lower()
        if host != site and not host.endswith('.'+site): return None
        # No provider query/fragment, tracking parameters, snippets, names or household fields.
        return urlunsplit(('https',host,p.path or '/', '', ''))
    except ValueError: return None

def phone_present(text, phone):
    # Exact US digit sequence with normal formatting; no partial/longer-number matches.
    pattern=r'(?<!\d)(?:\+?1[\s.()-]*)?' + r'[\s.()-]*'.join(phone[-10:]) + r'(?!\d)'
    return re.search(pattern,text) is not None

class BraveDiscovery:
    def __init__(self, transport=None): self.transport=transport or DisabledTransport()
    def discover(self, phone, site, *, verified=False, consent=False):
        if phone != FIXTURE_PHONE: raise ValueError('Only the synthetic reserved number is enabled.')
        if site not in SITES: raise ValueError('Unsupported source.')
        if verified is not True or consent is not True:
            raise ValueError('Ownership verification and explicit search-provider disclosure/consent required.')
        checked=datetime.now(timezone.utc).isoformat()
        base={'provider':'brave','site':site,'demo':True,'checked_at':checked,'candidates':[],
              'coverage':'One bounded web-index query; not a site-wide or internet-wide search.'}
        # Hard lock prevents a caller from injecting a live network transport through configuration.
        if not isinstance(self.transport,SyntheticTransport):
            return dict(base,status='source_unavailable',reason='outbound_disabled')
        query=f'"{phone}" site:{site}'
        url=ENDPOINT+'?'+urlencode({'q':query,'count':10,'result_filter':'web','text_decorations':'false','extra_snippets':'false'})
        try:
            response=self.transport.request('GET',url,headers={'Accept':'application/json','X-Subscription-Token':'SYNTHETIC-NOT-A-KEY'},timeout=5.0)
        except TimeoutError: return dict(base,status='source_unavailable',reason='timeout')
        except Exception: return dict(base,status='source_unavailable',reason='transport_error')
        if response.status==429: return dict(base,status='source_unavailable',reason='throttled')
        if response.status!=200: return dict(base,status='source_unavailable',reason='provider_error')
        payload=response.payload
        if not isinstance(payload,dict): return dict(base,status='source_unavailable',reason='invalid_response')
        web=payload.get('web')
        if not isinstance(web,dict) or not isinstance(web.get('results'),list):
            return dict(base,status='source_unavailable',reason='missing_web_results')
        candidates=[]; seen=set()
        for result in web['results'][:10]:
            if not isinstance(result,dict): continue
            link=source_link(result.get('url'),site)
            text=' '.join(v for v in (result.get('title'),result.get('description')) if isinstance(v,str))
            if not link or link in seen or not phone_present(text,phone): continue
            seen.add(link)
            # Do not export raw snippets, page titles, addresses, household data or search response.
            candidates.append({'source_url':link,'status':'match_needs_confirmation',
                'evidence':'Exact phone text appeared in an indexed result; ownership is unconfirmed.',
                'removal_eligible':False})
        return dict(base,status='match_needs_confirmation' if candidates else 'not_found_in_checked_sources',candidates=candidates)
