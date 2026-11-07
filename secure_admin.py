"""Offline security preview. No production identity or provider configuration.

The factory requires an injected, server-side identity resolver and encrypted
store. It is intentionally NOT imported by server.py, wsgi.py or render_wsgi.py.
The default entry point denies all requests. Only fixed synthetic values can be
written through this preview; the owner must approve a production integration.
"""
from dataclasses import dataclass, field
import hmac
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

ASSETS = Path(__file__).parent / 'static' / 'security'
CREDENTIALS = {
    'serper_api_key': ('Serper', 'SYNTHETIC_SERPER_VALUE_NOT_A_KEY'),
    'twilio_auth_token': ('Twilio', 'SYNTHETIC_TWILIO_VALUE_NOT_A_TOKEN'),
    'stripe_test_key': ('Stripe test mode', 'SYNTHETIC_STRIPE_VALUE_NOT_A_KEY'),
}
REPORT = ('SCANMYDIGITS SYNTHETIC SECURITY TEST\n'
          'Phone: +12025550147\n'
          'No provider query, SMS, payment or removal occurred.\n'
          'Example result: fictional listing needs review.\n')
PHONE = '+12025550147'


@dataclass(frozen=True)
class Principal:
    """Only an authenticated server-side adapter may construct this object.

    Never take owner_id, role, verified_until or csrf from a request parameter.
    A real adapter must validate signed session state, expiry, account status,
    authentication freshness and role on every request. An admin role does not
    grant access to another customer's reports.
    """
    owner_id: str
    role: str
    verified_until: float
    csrf: str = field(repr=False)


@dataclass(frozen=True)
class PaidStorageGrant:
    """Trusted backend payment evidence, never constructed from client fields.

    A production verifier must reconcile a signed gateway event/server response,
    expected order, owner, final paid status, amount/currency, replay state and
    revocation/refund policy. This preview has no live verifier.
    """
    owner_id: str
    payment_ref: str
    amount_cents: int
    currency: str
    valid_until: float


def respond(start_response, status, data, *, content_type='application/json', attachment=False):
    raw = json.dumps(data).encode() if content_type == 'application/json' else data
    headers = [('Content-Type', content_type), ('Content-Length', str(len(raw))),
               ('Cache-Control', 'no-store, private'), ('Pragma', 'no-cache'),
               ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'),
               ('X-Robots-Tag', 'noindex, nofollow, noarchive'),
               ('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")]
    if attachment:
        headers.append(('Content-Disposition', 'attachment; filename="scanmydigits-report.txt"'))
    start_response(status, headers)
    return [raw]


def application(environ, start_response):
    return respond(start_response, '503 Service Unavailable',
                   {'error': 'Security preview is not configured. Production activation is not available.'})


def create_preview(store, resolve_identity, *, origin, verify_payment=None, clock=time.time):
    """Create a synthetic-only app with explicit injected trust boundaries.

    No key generation, environment access, provider transport, account creation,
    real credential input, report enumeration or production activation exists.
    The production identity adapter, rate limiting, MFA/re-authentication, audit
    storage and durable deployment are deliberately unresolved launch gates.
    """
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path or not callable(resolve_identity)):
        raise ValueError('A trusted HTTPS origin and identity resolver are required.')

    def app(environ, start_response):
        def reply(status, data, **kwargs):
            return respond(start_response, status, data, **kwargs)
        try:
            if (environ.get('wsgi.url_scheme') != 'https' or environ.get('HTTP_HOST') != parsed.netloc
                    or environ.get('HTTP_ORIGIN') not in (None, origin)
                    or environ.get('HTTP_SEC_FETCH_SITE') == 'cross-site'
                    or environ.get('QUERY_STRING')):
                return reply('403 Forbidden', {'error': 'Trusted same-origin HTTPS request required.'})
            principal = resolve_identity(environ)
            if (not isinstance(principal, Principal) or principal.role not in ('admin', 'customer')
                    or not isinstance(principal.owner_id, str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', principal.owner_id)
                    or not isinstance(principal.csrf, str) or not 32 <= len(principal.csrf) <= 128
                    or type(principal.verified_until) not in (int, float)
                    or not math.isfinite(principal.verified_until)
                    or not principal.verified_until > clock()):
                return reply('401 Unauthorized', {'error': 'Current authenticated identity required.'})
            method, path = environ.get('REQUEST_METHOD'), environ.get('PATH_INFO')
            if method not in ('GET', 'POST'):
                return reply('405 Method Not Allowed', {'error': 'Unsupported method.'})
            admin_route = path in ('/admin', '/api/admin/status', '/api/admin/credential')
            if admin_route and principal.role != 'admin':
                return reply('403 Forbidden', {'error': 'Administrator access required.'})
            if method == 'GET':
                assets = {'/admin': ('admin.html', 'text/html; charset=utf-8'),
                          '/security.css': ('admin.css', 'text/css; charset=utf-8'),
                          '/security.js': ('admin.js', 'text/javascript; charset=utf-8')}
                if path in assets:
                    filename, mime = assets[path]
                    return reply('200 OK', (ASSETS / filename).read_bytes(), content_type=mime)
                if path == '/api/admin/status':
                    configured = set(store.list_credential_names())
                    return reply('200 OK', {'synthetic_only': True, 'csrf_token': principal.csrf,
                        'credentials': [{'name': name, 'label': label, 'configured': name in configured}
                                        for name, (label, _) in CREDENTIALS.items()],
                        'retention_seconds': 900, 'providers_enabled': False})
                match = re.fullmatch(r'/api/reports/([A-Za-z0-9_-]{1,128})/download', path or '')
                if match:
                    report = store.get_report(match[1], principal.owner_id)
                    if report is None:
                        return reply('404 Not Found', {'error': 'Report unavailable.'})
                    return reply('200 OK', report.encode('utf-8'),
                                 content_type='text/plain; charset=utf-8', attachment=True)
                return reply('404 Not Found', {'error': 'Page not found.'})
            if environ.get('HTTP_ORIGIN') != origin or not hmac.compare_digest(
                    environ.get('HTTP_X_CSRF_TOKEN', ''), principal.csrf):
                return reply('403 Forbidden', {'error': 'Current same-origin security token required.'})
            if (environ.get('CONTENT_TYPE') != 'application/json' or environ.get('HTTP_TRANSFER_ENCODING')):
                return reply('400 Bad Request', {'error': 'Bounded JSON request required.'})
            try:
                size = int(environ.get('CONTENT_LENGTH', '0'))
                if not 1 <= size <= 1024:
                    return reply('413 Payload Too Large', {'error': 'Request size is unsupported.'})
                raw = environ['wsgi.input'].read(size)
                data = json.loads(raw)
                if len(raw) != size or not isinstance(data, dict):
                    raise ValueError()
            except (ValueError, UnicodeError, KeyError):
                return reply('400 Bad Request', {'error': 'Invalid JSON request.'})
            if path == '/api/admin/credential':
                if set(data) != {'name', 'confirm_synthetic'} or data.get('confirm_synthetic') is not True or data.get('name') not in CREDENTIALS:
                    return reply('400 Bad Request', {'error': 'Only a predefined synthetic credential test is accepted.'})
                name = data['name']
                store.put_credential(name, CREDENTIALS[name][1], expires_at=clock() + 900)
                return reply('200 OK', {'saved': True, 'synthetic_only': True})
            if path == '/api/security/demo-record':
                if data != {'confirm_synthetic': True}:
                    return reply('400 Bad Request', {'error': 'Only the predefined synthetic record is accepted.'})
                grant = verify_payment(principal) if callable(verify_payment) else None
                if (not isinstance(grant, PaidStorageGrant) or grant.owner_id != principal.owner_id
                        or not isinstance(grant.payment_ref, str)
                        or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', grant.payment_ref)
                        or type(grant.amount_cents) is not int or grant.amount_cents <= 0
                        or grant.currency != 'USD' or type(grant.valid_until) not in (int, float)
                        or not math.isfinite(grant.valid_until) or grant.valid_until <= clock()):
                    return reply('402 Payment Required', {'error': 'Verified payment for this owner is required before persistent storage.'})
                # A duplicate request for the same verified payment returns the same
                # encrypted report. The browser cannot submit a paid/owner override.
                report_id = store.put_paid_bundle(principal.owner_id, grant.payment_ref,
                    PHONE, REPORT, expires_at=clock() + 900)
                return reply('201 Created', {'report_id': report_id, 'synthetic_only': True,
                    'download_url': '/api/reports/' + report_id + '/download'})
            return reply('404 Not Found', {'error': 'Endpoint not found.'})
        except Exception:
            # Never expose input, tokens, decrypted values or provider exception details.
            return reply('503 Service Unavailable', {'error': 'Operation not confirmed. Check saved state before retrying.'})
    return app
