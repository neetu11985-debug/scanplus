"""Private, explicitly configured owner self-test; never imported by demo deployment.

No provider calls occur during configuration or construction. This is not a
production customer service, checkout or removal adapter. Attempt reservations
use a separately provisioned durable allowance ledger.
"""
import base64
import binascii
from dataclasses import dataclass
from email.message import Message
import hashlib
import hmac
from http import HTTPStatus
import io
import os
from pathlib import Path
import re
import threading
import time

from live_scan import Settings, Providers, HTTPSJSONTransport, ScanError, ScanSession
from local_live_server import LiveHandler
from owner_test_allowance import PostgresAllowance, validate_run_id, AllowanceUnavailable
from neon_storage import validate_database_url
from search_diagnostics import SearchTransportFailure

ROOT = Path(__file__).parent / 'static'


@dataclass(frozen=True, repr=False)
class Configuration:
    host: str
    auth_digest: bytes
    providers: Settings
    allowance_url: str
    run_id: str
    revision: str = ''


def configuration(environment=None):
    env = os.environ if environment is None else environment
    if env.get('SCANPLUS_HOSTED_SELF_TEST') != '1':
        raise RuntimeError('Private hosted self-test is disabled.')
    if env.get('SCANPLUS_HOSTED_FREE_ALLOWANCE_CONFIRMED') != '1':
        raise RuntimeError('Owner confirmation of provider allowance is required.')
    host = env.get('RENDER_EXTERNAL_HOSTNAME', '')
    if (env.get('RENDER') != 'true' or
            not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.onrender\.com', host)):
        raise RuntimeError('Exact native Render HTTPS host required.')
    user = env.get('SCANPLUS_OWNER_TEST_USER', '')
    password = env.get('SCANPLUS_OWNER_TEST_PASSWORD', '')
    if (not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}', user) or
            not 24 <= len(password) <= 128 or
            any(ord(c) < 33 or ord(c) > 126 for c in password) or
            len(set(password)) < 12 or user.lower() in password.lower()):
        raise RuntimeError('A separate owner-set private-test login is required.')
    if env.get('SCANPLUS_SEARCH_PROVIDER') != 'serper':
        raise RuntimeError('This private self-test requires explicit Serper selection.')
    if env.get('SCANPLUS_STRIPE_TEST', '0') != '0' or env.get('SCANPLUS_ENCRYPTED_REPORTS', '0') != '0':
        raise RuntimeError('Checkout and persisted reports must remain disabled for this self-test.')
    account = env.get('TWILIO_ACCOUNT_SID', '')
    service = env.get('TWILIO_VERIFY_SERVICE_SID', '')
    token = env.get('TWILIO_AUTH_TOKEN', '')
    search = env.get('SERPER_API_KEY', '')
    if not re.fullmatch(r'AC[0-9a-fA-F]{32}', account) or not re.fullmatch(r'VA[0-9a-fA-F]{32}', service):
        raise RuntimeError('Approved Twilio account and Verify service configuration required.')
    if any(not 1 <= len(value) <= 256 or any(ord(c) < 33 or ord(c) > 126 for c in value) for value in (token, search)):
        raise RuntimeError('Approved server-side Twilio and Serper credentials required.')
    try:
        allowance_url = validate_database_url(env.get('SCANPLUS_OWNER_TEST_DATABASE_URL', ''))
        run_id = validate_run_id(env.get('SCANPLUS_OWNER_TEST_RUN_ID', ''))
    except Exception:
        raise RuntimeError('Approved durable allowance database and run ID required.') from None
    revision = env.get('RENDER_GIT_COMMIT', '')
    if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        revision = ''
    return Configuration(host, hashlib.sha256((user + ':' + password).encode('ascii')).digest(),
                         Settings(account, token, service, search_provider='serper', serper_key=search),
                         allowance_url, run_id, revision)


class OneTestTransport:
    """Durable reservation plus a process-local safety ceiling before dispatch.

    The durable ledger survives worker/process restart. It is not a provider
    account balance or dollar limit. Only an operator can grant a new run ID.
    """
    def __init__(self, settings, delegate, allowance):
        self.delegate = delegate
        self.allowance = allowance
        self.sms_url = 'https://verify.twilio.com/v2/Services/' + settings.verify_service_sid + '/Verifications'
        self.check_url = self.sms_url[:-len('Verifications')] + 'VerificationCheck'
        self.counts = {'sms': 0, 'checks': 0, 'searches': 0}
        self.search_stopped = False
        self.allowance_blocked = False
        self.lock = threading.RLock()

    def request(self, method, url, **kwargs):
        with self.lock:
            kind = {self.sms_url: 'sms', self.check_url: 'checks',
                    'https://google.serper.dev/search': 'searches'}.get(url)
            if method != 'POST' or kind is None:
                raise ScanError('Only the approved Twilio and Serper operations are available.')
            if self.allowance_blocked:
                raise AllowanceUnavailable('This test allowance needs operator review. No provider request was sent.')
            limit = {'sms': 1, 'checks': 5, 'searches': 3}[kind]
            if kind == 'searches' and self.search_stopped:
                raise SearchTransportFailure('not_attempted_after_provider_error')
            if self.counts[kind] >= limit:
                raise ScanError('The private test allowance is used or stopped. No retry was sent.')
            try:
                self.allowance.consume(kind)  # Commit must succeed before dispatch.
            except AllowanceUnavailable:
                self.allowance_blocked = True
                raise
            self.counts[kind] += 1
            try:
                result = self.delegate.request(method, url, **kwargs)
            except Exception:
                if kind == 'searches':
                    self.search_stopped = True
                raise
            if kind == 'searches':
                valid = isinstance(result, tuple) and len(result) == 2 and result[0] == 200
                payload = result[1] if valid else None
                valid = valid and isinstance(payload, dict) and isinstance(payload.get('organic'), list)
                if valid:
                    valid = all(isinstance(item, dict) and isinstance(item.get('link'), str) and item['link']
                                and any(isinstance(item.get(field), str) for field in ('title', 'snippet'))
                                for item in payload['organic'][:10])
                if not valid:
                    self.search_stopped = True
            return result


class OwnerTestState:
    def __init__(self, config, transport, allowance, clock=time.monotonic):
        self.providers = Providers(config.providers, OneTestTransport(config.providers, transport, allowance))
        self.host = config.host
        self.release_revision = config.revision
        self.activity_log = None
        self.sessions = {}
        self.starts = []
        self.lock = threading.RLock()
        self.clock = clock

    def service_actions(self):
        now = self.clock()
        for token, session in list(self.sessions.items()):
            session['scan'].expire()
            if session['expires'] <= now:
                session['scan'].clear()
                del self.sessions[token]
        self.starts = [stamp for stamp in self.starts if stamp > now - 600]


class TimedScanSession(ScanSession):
    def validate_start(self, phone, *, own_number=False, twilio_consent=False):
        phone = super().validate_start(phone, own_number=own_number, twilio_consent=twilio_consent)
        if not re.fullmatch(r'\+1[0-9]{10}', phone):
            raise ScanError('This self-test supports +1 numbers with exactly 10 national digits.')
        if self.providers.transport.allowance_blocked:
            raise AllowanceUnavailable('This test allowance needs operator review. No provider request was sent.')
        if self.providers.transport.counts['sms'] >= 1:
            raise ScanError('The one-SMS test allowance is already used. No new request was sent.')
        return phone

    def state(self):
        result = super().state()
        result['expires_in_ms'] = max(0, int((self.expires - self.clock()) * 1000)) if self.expires else 0
        result['test_scope'] = 'private_owner'
        result['allowance_blocked'] = self.providers.transport.allowance_blocked
        result['sms_allowance_remaining'] = max(0, 1 - self.providers.transport.counts['sms'])
        if result.get('report'):
            result['report']['test_scope'] = 'private_owner'
            result['report']['payment_notice'] = 'No checkout or payment is part of this private self-test.'
        return result


class OwnerTestHandler(LiveHandler):
    """Adapt the reviewed local JSON routes to an already authenticated WSGI call."""
    scan_session_class = TimedScanSession
    def __init__(self, environment, state):
        self.server = state
        self.path = environment.get('PATH_INFO', '/')
        self.headers = Message()
        for key, value in environment.items():
            if key.startswith('HTTP_'):
                self.headers[key[5:].replace('_', '-')] = value
        for key in ('CONTENT_LENGTH', 'CONTENT_TYPE'):
            if environment.get(key):
                self.headers[key.replace('_', '-')] = environment[key]
        self.rfile = environment['wsgi.input']
        self.wfile = io.BytesIO()
        self.response_headers = []
        self.status = 500

    @property
    def cookie_name(self):
        # Hosted owner-test cookies must not reuse a loopback test cookie name.
        return 'scanplus_owner_sid'

    @property
    def origin(self):
        return 'https://' + self.server.host

    def send_response(self, status, message=None):
        self.status = status
        self.response_headers = []

    def send_header(self, name, value):
        if name.lower() == 'set-cookie' and '; secure' not in value.lower():
            value += '; Secure'
        self.response_headers.append((name, str(value)))

    def end_headers(self):
        pass

    def headers_common(self):
        super().headers_common()
        self.send_header('X-Robots-Tag', 'noindex, nofollow, noarchive')
        if self.server.release_revision:
            self.send_header('X-ScanPlus-Release', self.server.release_revision)

    def get(self):
        if self.path == '/':
            raw = (ROOT / 'hosted-live.html').read_bytes()
            self.send_response(200)
            self.headers_common()
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        return super().get()


class OwnerTestApplication:
    handler_class = OwnerTestHandler

    def allow_cross_site_navigation(self, environment):
        return False
    def __init__(self, config, transport=None, *, allowance=None, start_cleanup=True):
        self.config = config
        self.state = OwnerTestState(config, HTTPSJSONTransport() if transport is None else transport,
                                    PostgresAllowance(config.allowance_url, config.run_id) if allowance is None else allowance)
        self._stop = threading.Event()
        self._cleanup = None
        if start_cleanup:
            self._cleanup = threading.Thread(target=self._prune_idle, daemon=True)
            self._cleanup.start()

    def _prune_idle(self):
        while not self._stop.wait(1):
            with self.state.lock:
                self.state.service_actions()

    def close(self):
        self._stop.set()
        if self._cleanup:
            self._cleanup.join(timeout=2)
        with self.state.lock:
            for session in self.state.sessions.values():
                session['scan'].clear()
            self.state.sessions.clear()

    def authenticated(self, value):
        if not isinstance(value, str) or len(value) > 512:
            return False
        try:
            scheme, encoded = value.split(' ', 1)
            if scheme.lower() != 'basic' or not encoded or len(encoded) > 260:
                return False
            candidate = hashlib.sha256(base64.b64decode(encoded, validate=True)).digest()
        except (ValueError, UnicodeError, binascii.Error):
            return False
        return hmac.compare_digest(candidate, self.config.auth_digest)

    def __call__(self, environment, start_response):
        def deny(status, message, challenge=False):
            body = message.encode('ascii')
            headers = [('Content-Type', 'text/plain; charset=utf-8'), ('Content-Length', str(len(body))),
                       ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
                       ('X-Robots-Tag', 'noindex, nofollow, noarchive'), ('Referrer-Policy', 'no-referrer')]
            if challenge:
                headers.append(('WWW-Authenticate', 'Basic realm="Private ScanPlus owner test"'))
            if self.config.revision:
                headers.append(('X-ScanPlus-Release', self.config.revision))
            start_response(status, headers)
            return [body]
        origin = 'https://' + self.config.host
        if (environment.get('wsgi.url_scheme') != 'https' or
                environment.get('HTTP_HOST') != self.config.host or
                environment.get('HTTP_ORIGIN') not in (None, origin) or
                (environment.get('HTTP_SEC_FETCH_SITE') not in (None, 'same-origin', 'none')
                 and not self.allow_cross_site_navigation(environment))):
            return deny('403 Forbidden', 'Trusted same-origin HTTPS access required.')
        if not self.authenticated(environment.get('HTTP_AUTHORIZATION', '')):
            return deny('401 Unauthorized', 'Private owner-test login required.', True)
        method = environment.get('REQUEST_METHOD', 'GET')
        if method not in ('GET', 'POST'):
            return deny('405 Method Not Allowed', 'Only GET and POST are supported.')
        if environment.get('QUERY_STRING') or environment.get('SCRIPT_NAME'):
            return deny('400 Bad Request', 'Query parameters and subpath mounting are unsupported.')
        if method == 'POST' and environment.get('HTTP_ORIGIN') != origin:
            return deny('403 Forbidden', 'Same-origin POST required.')
        if method == 'POST':
            # Read bounded input before taking the state lock. A slow authenticated
            # client must not prevent the independent expiry cleaner from running.
            if environment.get('CONTENT_TYPE') != 'application/json' or environment.get('HTTP_TRANSFER_ENCODING'):
                return deny('400 Bad Request', 'A bounded JSON request is required.')
            try:
                length = int(environment.get('CONTENT_LENGTH', '0'))
                if not 0 < length <= 2048:
                    return deny('413 Payload Too Large', 'Invalid request size.')
                raw = environment['wsgi.input'].read(length)
                if len(raw) != length:
                    return deny('400 Bad Request', 'Incomplete request.')
                environment = dict(environment, **{'wsgi.input': io.BytesIO(raw)})
            except (ValueError, TypeError, OSError):
                return deny('400 Bad Request', 'Invalid or incomplete request.')
        with self.state.lock:
            self.state.service_actions()
            handler = self.handler_class(environment, self.state)
            try:
                if method == 'POST':
                    # compare_digest must never receive non-ASCII attacker input.
                    csrf = environment.get('HTTP_X_CSRF_TOKEN', '')
                    if not isinstance(csrf, str) or not csrf.isascii() or len(csrf) > 128:
                        return deny('403 Forbidden', 'Session security token required.')
                    handler.post()
                else:
                    handler.get()
            except Exception:
                return deny('503 Service Unavailable', 'Operation outcome could not be confirmed. Reload to check before retrying.')
            body = handler.wfile.getvalue()
            start_response(f'{handler.status} {HTTPStatus(handler.status).phrase}', handler.response_headers)
            return [body]
