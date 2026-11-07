"""Private, disposable synthetic staging. Never use as a production entry point."""
import base64
import binascii
import hashlib
import hmac
import json
import os
import re


def configure():
    host = os.environ.get('SCANPLUS_STAGING_HOST') or os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
    user = os.environ.get('SCANPLUS_STAGING_USER', '')
    password = os.environ.get('SCANPLUS_STAGING_PASSWORD', '')
    profile = os.environ.get('SCANPLUS_RELEASE_PROFILE', 'demo')
    if profile not in ('demo', 'sandbox'):
        raise RuntimeError('Select the demo or sandbox release profile.')
    if (os.environ.get('RENDER') != 'true' or
            not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.onrender\.com', host) or
            host != os.environ.get('RENDER_EXTERNAL_HOSTNAME')):
        raise RuntimeError('Configure the exact native Render staging hostname.')
    if (not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}', user) or
            not 24 <= len(password) <= 128 or
            any(ord(c) < 33 or ord(c) > 126 for c in password) or
            len(set(password)) < 12 or user.lower() in password.lower()):
        raise RuntimeError('Owner-set staging credentials are missing or insufficiently strong.')
    os.environ.update(SCANPLUS_MODE='demo', SCANPLUS_STRIPE_TEST='0',
                      SCANPLUS_LOCAL_LIVE_TEST='0', SCANPLUS_SEARCH_PROVIDER='disabled',
                      SCANPLUS_ALLOWED_ORIGINS='https://' + host, SCANPLUS_DB_PATH=':memory:',
                      SCANPLUS_ENCRYPTED_REPORTS='0')
    if profile == 'sandbox':
        os.environ.update(SCANPLUS_STRIPE_TEST='1', SCANPLUS_ENCRYPTED_REPORTS='1',
                          SCANPLUS_STRIPE_ORIGIN='https://' + host,
                          SCANPLUS_SESSION_TTL='900')
        # Validate configuration only: no connection, schema or key-marker write.
        from stripe_checkout import settings
        from neon_storage import settings_from_environment
        settings()
        settings_from_environment()
    return host, hashlib.sha256((user + ':' + password).encode('ascii')).digest()


HOST, AUTH_DIGEST = configure()  # Validate BEFORE application import opens SQLite.
SANDBOX = os.environ.get('SCANPLUS_RELEASE_PROFILE', 'demo') == 'sandbox'
from wsgi import application as demo_application
from staging_database import DATABASE_PROBE

REVISION = os.environ.get('RENDER_GIT_COMMIT', '')
if not re.fullmatch(r'[0-9a-f]{40}', REVISION):
    REVISION = ''
BANNER = (b'<aside role="note"><strong>PRIVATE SYNTHETIC STAGING</strong> '
          b'Use only the displayed example numbers. No real scans, SMS, charges or removals. '
          b'Disposable in-memory history is lost on sleep, restart or redeploy. '
          b'No persistence or retention guarantee.</aside>')
if SANDBOX:
    BANNER = (b'<aside role="note"><strong>PRIVATE STRIPE SANDBOX</strong> '
              b'Test data only. No real phone scans, SMS or charges. '
              b'Encrypted synthetic reports expire with the 15-minute browser session. '
              b'Restart clears access; this is not customer authentication. '
              b'<a href="/stripe-test">Open sandbox checkout and encrypted report test</a>.</aside>')


def authenticated(value):
    if not isinstance(value, str) or len(value) > 512:
        return False
    try:
        scheme, encoded = value.split(' ', 1)
        if scheme.lower() != 'basic' or not encoded or len(encoded) > 260:
            return False
        raw = base64.b64decode(encoded, validate=True)
        candidate = hashlib.sha256(raw).digest()
    except (ValueError, UnicodeError, binascii.Error):
        return False
    return hmac.compare_digest(candidate, AUTH_DIGEST)


def secured_headers(headers):
    remove = {'cache-control', 'x-robots-tag', 'referrer-policy', 'x-scanplus-release'}
    result = [(k, v) for k, v in headers if k.lower() not in remove]
    # Include Secure even on the session-deletion cookie.
    result = [(k, v + '; Secure' if k.lower() == 'set-cookie' and '; secure' not in v.lower() else v)
              for k, v in result]
    result += [('Cache-Control', 'no-store'), ('X-Robots-Tag', 'noindex, nofollow, noarchive'),
               ('Referrer-Policy', 'no-referrer')]
    if REVISION:
        result.append(('X-ScanPlus-Release', REVISION))
    return result


def application(environ, start_response):
    def deny(status, message, challenge=False):
        body = message.encode('ascii')
        headers = [('Content-Type', 'text/plain; charset=utf-8'), ('Content-Length', str(len(body)))]
        if challenge:
            headers.append(('WWW-Authenticate', 'Basic realm="Private synthetic staging", charset="UTF-8"'))
        start_response(status, secured_headers(headers))
        return [body]
    # Gunicorn derives scheme only through Render ingress. Never inspect forwarded headers here.
    if (environ.get('wsgi.url_scheme') != 'https' or environ.get('HTTP_HOST') != HOST or
            environ.get('HTTP_ORIGIN') not in (None, 'https://' + HOST) or
            environ.get('HTTP_SEC_FETCH_SITE') == 'cross-site'):
        return deny('403 Forbidden', 'Trusted HTTPS origin required.')
    path = environ.get('PATH_INFO', '/')
    webhook = SANDBOX and path == '/api/stripe/webhook'
    if webhook and (environ.get('REQUEST_METHOD') != 'POST' or environ.get('QUERY_STRING')):
        return deny('405 Method Not Allowed', 'Parameterless signed webhook POST required.')
    # Stripe cannot use the browser's Basic login. Only this exact signed-event
    # endpoint bypasses it, and signature/raw-body checks remain mandatory.
    if not webhook and not authenticated(environ.get('HTTP_AUTHORIZATION', '')):
        return deny('401 Unauthorized', 'Private synthetic staging login required.', True)
    if environ.get('QUERY_STRING') and path.startswith('/api/'):
        return deny('400 Bad Request', 'API query parameters are unsupported.')
    if path == '/api/staging/database':
        # Existing HTTPS/host/origin and Basic-auth gates above run BEFORE any
        # credential access or database operation. No browser-supplied SQL/DSN.
        if environ.get('REQUEST_METHOD') != 'GET':
            return deny('405 Method Not Allowed', 'Read-only GET required.')
        if environ.get('QUERY_STRING'):
            return deny('400 Bad Request', 'This check does not accept parameters.')
        status, result = DATABASE_PROBE.check()
        body = json.dumps(result, separators=(',', ':')).encode('utf-8')
        headers = [('Content-Type', 'application/json'), ('Content-Length', str(len(body))),
                   ('X-Content-Type-Options', 'nosniff')]
        start_response('200 OK' if status == 200 else '503 Service Unavailable',
                       secured_headers(headers))
        return [body]
    if not SANDBOX and (path.startswith('/api/stripe/') or path in ('/stripe-test', '/stripe-test.js')):
        return deny('503 Service Unavailable', 'Stripe is disabled on synthetic staging.')
    captured = {}
    def capture(status, headers, exc_info=None):
        captured.update(status=status, headers=headers, exc_info=exc_info)
    iterable = demo_application(environ, capture)
    try:
        body = b''.join(iterable)
    finally:
        if hasattr(iterable, 'close'):
            iterable.close()
    headers = captured['headers']
    if path == '/' and captured['status'].startswith('200'):
        body = body.replace(b'<body>', b'<body>' + BANNER, 1)
        headers = [(k, v) for k, v in headers if k.lower() != 'content-length']
        headers.append(('Content-Length', str(len(body))))
    start_response(captured['status'], secured_headers(headers), captured['exc_info'])
    return [body]
