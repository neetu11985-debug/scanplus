"""Single-use Serper-only owner self-test. Not imported by production routes.

No Twilio operation exists here. Production verification is not replaced. The
real transport is constructed only by explicit approved local startup; tests
inject synthetic transports and never read the owner's credential file.
"""
from datetime import datetime, timezone
import time
from live_scan import HTTPSJSONTransport, ScanError, SerperSearch, normalize_phone
from discovery import SITES
from scan_report import build_report, report_text

BLOCKER = ('Real Serper lookup is blocked: available free credits and the approved '
           'query allowance have not been confirmed. No search ran and no results '
           'about your number are available.')
OWNERSHIP_NOTICE = ('Local owner self-test only. SMS was deliberately disabled. '
                    'Ownership is self-attested, not verified. Confirm every listing '
                    'belongs to you before taking any action.')


class SerperOnlyTransport:
    """Exact endpoint, one explicit authorization, three attempts per process.

    Spending allowance is consumed before requests, including failed/uncertain
    requests. Clear, new browser sessions and expiry cannot replenish it.
    """
    def __init__(self, delegate):
        self.delegate = delegate
        self.authorized = False
        self.attempts = 0

    def authorize_once(self):
        if self.authorized:
            raise ScanError('The one-scan allowance for this process has been used. No automatic retry is allowed.')
        self.authorized = True

    def request(self, method, url, *, headers, body=None):
        if method != 'POST' or url != 'https://google.serper.dev/search':
            raise ScanError('Only the exact Serper search endpoint is allowed. SMS and other providers are disabled.')
        if not self.authorized or self.attempts >= 3:
            raise ScanError('No approved Serper query allowance remains.')
        self.attempts += 1
        return self.delegate.request(method, url, headers=headers, body=body)


class SerperOnlySearch:
    def __init__(self, key, transport):
        self.transport = SerperOnlyTransport(transport)
        self.adapter = SerperSearch(key, self.transport)

    @property
    def used(self):
        return self.transport.authorized

    @property
    def attempts(self):
        return self.transport.attempts

    def authorize_once(self):
        self.transport.authorize_once()

    def discover(self, phone, site):
        return self.adapter.discover(phone, site)


def load_approved_search(path, *, confirmed_free_queries, no_paid_topup_confirmed):
    # Reject before reading any secret file. This is owner/account attestation,
    # not an API-verified balance. A connected worker must not invoke this until
    # the owner has confirmed the available free allowance and approved this test.
    if type(confirmed_free_queries) is not int or confirmed_free_queries != 3 or no_paid_topup_confirmed is not True:
        raise ScanError('Confirm three available free Serper queries and no paid top-up before live startup.')
    from tool.local_keys import read_properties, ConfigurationError
    values = {}
    try:
        values = read_properties(path)
        key = values.get('SERPER_API_KEY', '')
        if not key or len(key) > 256:
            raise ScanError('A valid Serper key is required in the owner-private local properties file.')
        # No Twilio Settings or Providers object is constructed. No environment
        # fallback, key display, network request, or persistent write occurs here.
        return SerperOnlySearch(key, HTTPSJSONTransport())
    except ConfigurationError as error:
        raise ScanError(str(error)) from None
    finally:
        values.clear()


class NoSMSSession:
    def __init__(self, search=None, clock=time.monotonic):
        self.search = search
        self.clock = clock
        self.clear()

    def clear(self):
        self.phase = 'entry'
        self.phone = None
        self.last_four = None
        self.expires = 0
        self.report = None

    def expire(self):
        if self.expires and self.clock() >= self.expires:
            self.clear()

    def state(self):
        self.expire()
        return {'mode': 'local_no_sms_live' if self.search else 'local_no_sms_preflight',
                'sms_enabled': False, 'ownership_verified': False,
                'ownership_notice': OWNERSHIP_NOTICE,
                'search_enabled': self.search is not None,
                'allowance_used': bool(self.search and self.search.used),
                'queries_attempted': self.search.attempts if self.search else 0,
                'sources_checked': self.report['sources_checked'] if self.report else 0,
                'report': self.report, 'blocker': None if self.search else BLOCKER,
                'phase': self.phase, 'last_four': self.last_four,
                'expires_in_ms': max(0, int((self.expires - self.clock()) * 1000)) if self.expires else 0}

    def start(self, phone, *, own_number=False, no_sms_acknowledged=False):
        self.expire()
        if self.phase != 'entry':
            raise ScanError('Clear this test before entering another number.')
        if own_number is not True or no_sms_acknowledged is not True:
            raise ScanError('Confirm your own number and acknowledge that ownership is not verified.')
        if self.search and self.search.used:
            raise ScanError('The one-scan allowance for this process has been used. No new lookup is allowed.')
        phone = normalize_phone(phone)
        self.last_four = phone[-4:]
        self.phone = phone if self.search else None
        self.phase = 'ready'
        self.expires = self.clock() + 300
        return self.state()

    def scan(self, *, serper_consent=False, free_allowance_confirmed=False):
        self.expire()
        if self.search is None:
            if self.phase not in ('ready', 'blocked'):
                raise ScanError('Complete the local input check first.')
            self.phase = 'blocked'
            raise ScanError(BLOCKER)
        if serper_consent is not True or free_allowance_confirmed is not True:
            raise ScanError('Explicit consent to send your own number to Serper and confirmation of three free queries with no paid top-up are required.')
        if self.phase == 'report':
            return self.state()  # A repeated submission only returns the held report.
        if self.phase != 'ready' or not self.phone:
            raise ScanError('Enter your own number again in a current local session before searching.')
        self.search.authorize_once()
        self.phase = 'scanning'
        phone, self.phone = self.phone, None
        try:
            sources = []
            stop_reason = None
            for site in sorted(SITES):
                if self.clock() >= self.expires:
                    stop_reason = 'local_test_expired'
                if stop_reason:
                    source = {'site': site, 'provider': 'serper', 'live': True,
                              'checked_at': datetime.now(timezone.utc).isoformat(),
                              'status': 'source_unavailable', 'candidates': [],
                              'reason': stop_reason, 'query_attempted': False}
                else:
                    source = self.search.discover(phone, site)
                    source['query_attempted'] = True
                    if source['status'] == 'source_unavailable':
                        stop_reason = 'not_attempted_after_provider_error'
                sources.append(source)
            self.report = build_report(sources, 'serper', self.last_four)
            self.report.update(ownership_verified=False, ownership_method='self_attestation_only',
                               ownership_notice=OWNERSHIP_NOTICE, sms_sent=False, local_only=True,
                               queries_attempted=self.search.attempts,
                               coverage=('At most three Serper Google Search web-index queries, up to ten results each, '
                                         'limited to Spokeo, TruePeopleSearch and Whitepages. '
                                         'Queries attempted: ' + str(self.search.attempts) + '. '
                                         'This is not direct broker access or a full Internet scan. Missing indexed '
                                         'matches do not prove absence online. Results can be stale.'))
            self.phase = 'report'
            return self.state()
        except Exception:
            self.phase = 'error'
            self.report = None
            raise ScanError('The scan could not complete. Its query allowance remains spent; no automatic retry or fallback will occur.') from None
        finally:
            phone = None

    def current_report(self):
        self.expire()
        if self.phase != 'report' or not self.report:
            raise ScanError('A current completed report is required. Clear or expiry removes it.')
        return self.report


def no_sms_report_text(report):
    return ('SCANMYDIGITS PRIVATE NO-SMS SELF-TEST\n' + report['ownership_notice'] + '\n\n' + report_text(report))
