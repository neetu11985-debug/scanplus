"""Opt-in local self-test adapters. No network occurs at import or construction.

The existing synthetic app never imports this module. Only explicitly enabled
local or private-hosted self-test entrypoints may use its real transport after
provider configuration and the required consent gates.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import http.client
import json
import os
import re
import time
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from discovery import SITES
from scan_report import build_report, update_manual_action
from search_diagnostics import (SearchTransportFailure, diagnose_search_exception,
                                search_diagnostic, NOT_DISPATCHED)

MAX_RESPONSE = 1024 * 1024
TTL = 300

class ScanError(ValueError):
    pass

class ProviderNotDispatched(ScanError):
    """A preflight reservation failed before any external provider call."""
    pass

@dataclass(frozen=True, repr=False)
class Settings:
    account_sid: str
    auth_token: str
    verify_service_sid: str
    brave_key: str = ""
    search_provider: str = "brave"  # Legacy injected fixtures; environment defaults to Serper.
    serper_key: str = ""

    def __post_init__(self):
        if self.search_provider not in ("brave", "serper"):
            raise ScanError("Unsupported search provider; choose serper or brave explicitly.")

    @classmethod
    def from_environment(cls):
        # Opt-in is intentionally separate from SCANPLUS_MODE; the demo stays demo.
        if os.environ.get('SCANPLUS_LOCAL_LIVE_TEST') != '1':
            raise ScanError('Local live test is disabled. Provider setup and permission are required first.')
        provider = os.environ.get('SCANPLUS_SEARCH_PROVIDER', 'serper')
        if provider not in ('serper', 'brave'):
            raise ScanError('Unsupported search provider; choose serper or brave explicitly.')
        key_name = 'SERPER_API_KEY' if provider == 'serper' else 'BRAVE_SEARCH_API_KEY'
        names = ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_VERIFY_SERVICE_SID', key_name)
        missing = [name for name in names if not os.environ.get(name)]
        if missing:
            raise ScanError('Missing approved server-side configuration: ' + ', '.join(missing))
        result = cls(*(os.environ[name] for name in names[:3]),
                     brave_key=os.environ[key_name] if provider == 'brave' else '',
                     search_provider=provider,
                     serper_key=os.environ[key_name] if provider == 'serper' else '')
        if not re.fullmatch(r'AC[0-9a-fA-F]{32}', result.account_sid) or not re.fullmatch(r'VA[0-9a-fA-F]{32}', result.verify_service_sid):
            raise ScanError('Invalid Twilio account or Verify service identifier format.')
        if any('\n' in value or '\r' in value for value in (result.auth_token, result.brave_key, result.serper_key)):
            raise ScanError('Invalid credential format.')
        return result

def verification_diagnostic(status=None, payload=None):
    """Allow only HTTP status and Twilio's numeric error code, never body text."""
    http_status = status if type(status) is int and 100 <= status <= 599 else None
    code = payload.get('code') if isinstance(payload, dict) else None
    # A successful verification payload is not an error-code source. Reject
    # strings, booleans, floats, nested values and numbers beyond six digits.
    error_code = code if (http_status is not None and http_status >= 300
                         and type(code) is int and 1 <= code <= 999999) else None
    return {'http_status': http_status, 'twilio_error_code': error_code}


def verification_diagnostic_text(diagnostic):
    status = diagnostic['http_status']
    code = diagnostic['twilio_error_code']
    return (' Diagnostic: HTTP ' + (str(status) if status is not None else 'status unavailable')
            + '; Twilio error code ' + (str(code) if code is not None else 'unavailable') + '.')


class HTTPSJSONTransport:
    """Fixed HTTPS destinations, default certificate checks, no redirects/retries."""
    def request(self, method, url, *, headers, body=None):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in ('verify.twilio.com', 'api.search.brave.com', 'google.serper.dev') or parsed.port not in (None, 443) or parsed.username or parsed.password:
            raise ScanError('Unsupported provider destination.')
        if parsed.hostname == 'google.serper.dev' and (method != 'POST' or parsed.path != '/search' or parsed.query or parsed.fragment):
            raise ScanError('Unsupported Serper operation.')
        if parsed.hostname == 'verify.twilio.com' and (method != 'POST' or not re.fullmatch(r'/v2/Services/VA[0-9a-fA-F]{32}/(?:Verifications|VerificationCheck)', parsed.path) or parsed.query or parsed.fragment):
            raise ScanError('Unsupported Twilio operation.')
        if parsed.hostname == 'api.search.brave.com' and (method != 'GET' or parsed.path != '/res/v1/web/search' or parsed.fragment):
            raise ScanError('Unsupported Brave operation.')
        path = parsed.path + ('?' + parsed.query if parsed.query else '')
        connection = http.client.HTTPSConnection(parsed.hostname, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            is_twilio = parsed.hostname == 'verify.twilio.com'
            try:
                raw = response.read(MAX_RESPONSE + 1)
                if len(raw) > MAX_RESPONSE:
                    if parsed.hostname == 'google.serper.dev':
                        raise SearchTransportFailure('response_too_large', response.status)
                    raise ScanError('Provider response exceeded the limit.')
                if response.status not in (200, 201):
                    if is_twilio:
                        # Parse only this bounded response in memory, then discard
                        # everything except a strictly numeric Twilio error code.
                        code = verification_diagnostic(response.status, json.loads(raw))['twilio_error_code']
                        return response.status, {'code': code} if code is not None else None
                    return response.status, None
                return response.status, json.loads(raw)
            except Exception as error:
                if is_twilio:
                    # Headers arrived but the body was unreadable, malformed or
                    # too large. Preserve only the known HTTP status. Never retry.
                    return response.status, None
                if parsed.hostname == 'google.serper.dev':
                    raise SearchTransportFailure(**diagnose_search_exception(error, response.status)) from None
                raise
        finally:
            connection.close()

def normalize_phone(value):
    if not isinstance(value, str) or len(value) > 32 or not re.fullmatch(r'\+[0-9\s().-]+', value.strip()):
        raise ScanError('Enter an international number beginning with + and its country code.')
    phone = re.sub(r'[\s().-]', '', value.strip())
    if not re.fullmatch(r'\+[1-9][0-9]{7,14}', phone):
        raise ScanError('Use 8–15 digits including the country code; extensions are unsupported.')
    return phone

def exact_phone_present(text, phone):
    digits = phone[1:]
    variants = {digits}
    if len(digits) == 11 and digits.startswith('1'):
        variants.add(digits[1:])
    # Consume complete formatted phone-like tokens, not a suffix inside another
    # country's number or an overlong digit sequence with separators.
    for token in re.finditer(r'(?<![\w+])\+?\d(?:[\d \t().-]*\d)?(?!\w)', text):
        if re.sub(r'\D', '', token.group()) in variants:
            return True
    return False

def live_source_link(raw, site):
    if not isinstance(raw, str) or len(raw) > 2048 or any(c == '\\' or ord(c) <= 32 or ord(c) == 127 for c in raw):
        return None
    try:
        parsed = urlsplit(raw)
        host = (parsed.hostname or '').lower()
        if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
            return None
        if host != site and not host.endswith('.' + site):
            return None
        # Preserve query-dependent listing identity. Only discard parameters whose
        # sole documented role is conventional tracking; never invent a new URL.
        parts = []
        for part in parsed.query.split('&'):
            key = parse_qsl(part, keep_blank_values=True)[0][0].lower() if part and parse_qsl(part, keep_blank_values=True) else ''
            if not key.startswith('utm_') and key not in ('gclid', 'fbclid', 'msclkid'):
                parts.append(part)
        return urlunsplit(('https', host, parsed.path or '/', '&'.join(parts), parsed.fragment))
    except ValueError:
        return None

class SerperSearch:
    """Bounded Google search-index adapter. No account setup, retries or fallback.

    The owner must qualify their free-credit account and approve phone transmission
    before live use. Synthetic tests cannot establish API availability or billing.
    """
    def __init__(self, key, transport):
        self.key = key
        self.transport = transport

    def discover(self, phone, site):
        if site not in SITES:
            raise ScanError('Unsupported source.')
        result = {'site': site, 'provider': 'serper', 'live': True,
                  'checked_at': datetime.now(timezone.utc).isoformat(),
                  'status': 'source_unavailable', 'candidates': [], 'reason': 'provider_error'}
        query = '"' + phone + '" site:' + site
        try:
            status, payload = self.transport.request('POST', 'https://google.serper.dev/search',
                headers={'Accept': 'application/json', 'Content-Type': 'application/json', 'X-API-KEY': self.key},
                body=json.dumps({'q': query, 'num': 10}))
        except ProviderNotDispatched:
            return dict(result, reason='not_dispatched', query_attempted=False,
                        search_diagnostic=search_diagnostic('not_dispatched'))
        except Exception as error:
            diagnostic = diagnose_search_exception(error)
            return dict(result, reason=diagnostic['category'], search_diagnostic=diagnostic,
                        query_attempted=diagnostic['category'] not in NOT_DISPATCHED)
        if status != 200:
            reason = 'throttled' if status == 429 else ('quota_or_access_unavailable' if status in (401, 402, 403) else 'provider_error')
            return dict(result, reason=reason, search_diagnostic=search_diagnostic('http_error', status))
        if not isinstance(payload, dict) or not isinstance(payload.get('organic'), list):
            return dict(result, reason='invalid_response', search_diagnostic=search_diagnostic('invalid_response', status))
        results = payload['organic'][:10]
        # A malformed nonempty response is unavailable, never evidence of absence.
        if any(not isinstance(item, dict) or not isinstance(item.get('link'), str) or not item['link']
               or not any(isinstance(item.get(key), str) for key in ('title', 'snippet')) for item in results):
            return dict(result, reason='invalid_response', search_diagnostic=search_diagnostic('invalid_response', status))
        seen = set()
        for item in results:
            link = live_source_link(item.get('link'), site)
            matched = any(exact_phone_present(item[key], phone) for key in ('title', 'snippet') if isinstance(item.get(key), str))
            if link and link not in seen and matched:
                seen.add(link)
                result['candidates'].append({'source_url': link, 'status': 'match_needs_confirmation', 'removal_eligible': False,
                    'evidence': 'This exact phone text appeared in the search index. Confirm that the listing is yours.'})
        result.pop('reason')
        result['status'] = 'match_needs_confirmation' if result['candidates'] else 'not_found_in_checked_sources'
        return result


class Providers:
    def __init__(self, settings, transport):
        self.settings = settings
        self.transport = transport

    def verify_request(self, action, data):
        credentials = self.settings.account_sid + ':' + self.settings.auth_token
        auth = base64.b64encode(credentials.encode()).decode()
        return self.transport.request('POST', 'https://verify.twilio.com/v2/Services/' + self.settings.verify_service_sid + '/' + action,
            headers={'Authorization': 'Basic ' + auth, 'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'}, body=urlencode(data))

    def valid_verification(self, payload, phone, sid=None, status='pending'):
        return (isinstance(payload, dict) and payload.get('service_sid') == self.settings.verify_service_sid
                and payload.get('to') == phone and payload.get('status') == status
                and isinstance(payload.get('sid'), str) and re.fullmatch(r'VE[0-9a-fA-F]{32}', payload['sid'])
                and (sid is None or payload['sid'] == sid))

    def discover(self, phone, site):
        if self.settings.search_provider == 'serper':
            return SerperSearch(self.settings.serper_key, self.transport).discover(phone, site)
        if site not in SITES:
            raise ScanError('Unsupported source.')
        result = {'site': site, 'provider': 'brave', 'live': True, 'checked_at': datetime.now(timezone.utc).isoformat(),
                  'status': 'source_unavailable', 'candidates': [], 'reason': 'provider_error'}
        query = '"' + phone + '" site:' + site
        url = 'https://api.search.brave.com/res/v1/web/search?' + urlencode({'q': query, 'count': 10, 'result_filter': 'web', 'text_decorations': 'false', 'extra_snippets': 'false'})
        try:
            status, payload = self.transport.request('GET', url, headers={'Accept': 'application/json', 'X-Subscription-Token': self.settings.brave_key})
        except Exception:
            return dict(result, reason='request_failed')
        if status != 200:
            return dict(result, reason='throttled' if status == 429 else 'provider_error')
        if not isinstance(payload, dict) or not isinstance(payload.get('web'), dict) or not isinstance(payload['web'].get('results'), list):
            return dict(result, reason='invalid_response')
        results = payload['web']['results'][:10]
        if any(not isinstance(item, dict) or not isinstance(item.get('url'), str) or not item['url']
               or not any(isinstance(item.get(key), str) for key in ('title', 'description')) for item in results):
            return dict(result, reason='invalid_response')
        seen = set()
        for item in results:
            link = live_source_link(item.get('url'), site)
            matched = any(exact_phone_present(item[key], phone) for key in ('title', 'description') if isinstance(item.get(key), str))
            if link and link not in seen and matched:
                seen.add(link)
                result['candidates'].append({'source_url': link, 'status': 'match_needs_confirmation', 'removal_eligible': False,
                    'evidence': 'This exact phone text appeared in the search index. Confirm that the listing is yours.'})
        result.pop('reason')
        result['status'] = 'match_needs_confirmation' if result['candidates'] else 'not_found_in_checked_sources'
        return result

class ScanSession:
    """One browser's short-lived state, held only in process memory."""
    def __init__(self, providers, clock=time.monotonic):
        self.providers = providers
        self.clock = clock
        self.clear()

    def clear(self):
        self.phase = 'entry'
        self.phone = None
        self.last_four = None
        self.sid = None
        self.expires = 0
        self.attempts = 0
        self.report = None
        self.verification_diagnostic = None

    def expire(self):
        if self.expires and self.expires <= self.clock():
            self.clear()
            return True
        return False

    def state(self):
        self.expire()
        result = {'phase': self.phase, 'last_four': self.last_four, 'report': self.report,
                  'search_provider': self.providers.settings.search_provider}
        if self.verification_diagnostic is not None:
            result['verification_diagnostic'] = dict(self.verification_diagnostic)
        return result

    def validate_start(self, phone, *, own_number=False, twilio_consent=False):
        self.expire()
        if self.phase != 'entry':
            raise ScanError('A test is already active. Clear it before starting a different test.')
        if own_number is not True or twilio_consent is not True:
            raise ScanError('Confirm this is your own number and explicitly approve Twilio SMS verification.')
        return normalize_phone(phone)

    def start(self, phone, *, own_number=False, twilio_consent=False):
        phone = self.validate_start(phone, own_number=own_number, twilio_consent=twilio_consent)
        self.expires = self.clock() + TTL
        # An uncertain SMS response must never automatically resend.
        self.phase = 'start_uncertain'
        try:
            status, payload = self.providers.verify_request('Verifications', {'To': phone, 'Channel': 'sms'})
        except ProviderNotDispatched:
            self.clear()
            raise
        except Exception:
            self.verification_diagnostic = verification_diagnostic()
            raise ScanError('SMS status is uncertain. A message may have been sent. No automatic retry occurred.'
                            + verification_diagnostic_text(self.verification_diagnostic)) from None
        if status != 201 or not self.providers.valid_verification(payload, phone):
            self.verification_diagnostic = verification_diagnostic(status, payload)
            raise ScanError('SMS verification was not confirmed. Check the provider account before trying again.'
                            + verification_diagnostic_text(self.verification_diagnostic))
        self.phone = phone
        self.last_four = phone[-4:]
        self.sid = payload['sid']
        self.phase = 'code'
        return self.state()

    def verify(self, code):
        self.expire()
        if self.phase != 'code' or not self.phone:
            raise ScanError('A current SMS challenge is required.')
        if self.attempts >= 5:
            raise ScanError('Verification attempt limit reached. Review the provider account and authorized allowance before any new test.')
        if not isinstance(code, str) or not re.fullmatch(r'[0-9]{4,10}', code):
            raise ScanError('Enter the verification code from the SMS.')
        self.attempts += 1
        self.verification_diagnostic = None
        try:
            status, payload = self.providers.verify_request('VerificationCheck', {'VerificationSid': self.sid, 'Code': code})
        except ProviderNotDispatched:
            raise
        except Exception:
            self.verification_diagnostic = verification_diagnostic()
            raise ScanError('Verification could not be confirmed. No search was performed.'
                            + verification_diagnostic_text(self.verification_diagnostic)) from None
        if status != 200 or not self.providers.valid_verification(payload, self.phone, self.sid, 'approved'):
            self.verification_diagnostic = verification_diagnostic(status, payload)
            raise ScanError('The provider did not approve this code. No search was performed.'
                            + verification_diagnostic_text(self.verification_diagnostic))
        self.phase = 'verified'
        return self.state()

    def scan(self, *, brave_consent=False, serper_consent=False):
        self.expire()
        provider = self.providers.settings.search_provider
        consent = serper_consent if provider == 'serper' else brave_consent
        if consent is not True:
            name = 'Serper' if provider == 'serper' else 'Brave Search'
            raise ScanError('Explicit consent to send your number to ' + name + ' is required.')
        if self.phase == 'report':
            return self.state()  # Repeated click/response loss never repeats paid queries.
        if self.phase != 'verified' or not self.phone:
            raise ScanError('Current Twilio verification is required before scanning.')
        self.phase = 'scanning'
        phone = self.phone
        self.phone = None
        self.sid = None
        try:
            sources = []
            for site in sorted(SITES):
                if self.clock() >= self.expires:
                    sources.append({'site': site, 'provider': provider, 'live': True, 'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'source_unavailable', 'candidates': [], 'reason': 'local_test_expired', 'query_attempted': False})
                else:
                    sources.append(self.providers.discover(phone, site))
            self.report = build_report(sources, provider, self.last_four)
            self.phase = 'report'
            return self.state()
        finally:
            phone = None

    def current_report(self):
        self.expire()
        if self.phase != 'report' or self.report is None:
            raise ScanError('A current completed report is required. Cleared or expired reports cannot be recovered.')
        return self.report

    def review_listing(self, candidate_id, action, confirmed=False):
        report = self.current_report()
        if confirmed is not True:
            raise ScanError('Explicit confirmation is required to change your local listing checklist.')
        try:
            update_manual_action(report, candidate_id, action)
        except ValueError as error:
            raise ScanError(str(error)) from None
        return self.state()
