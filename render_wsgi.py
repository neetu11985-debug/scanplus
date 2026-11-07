"""Private, disposable synthetic staging. Never use as a production entry point."""
import base64
import binascii
import hashlib
import hmac
import os
import re


def configure():
    host = os.environ.get('SCANPLUS_STAGING_HOST') or os.environ.get('RENDER_EXTERNAL_HOSTNAME', '')
    user = os.environ.get('SCANPLUS_STAGING_USER', '')
    password = os.environ.get('SCANPLUS_STAGING_PASSWORD', '')
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
                      SCANPLUS_ALLOWED_ORIGINS='https://' + host, SCANPLUS_DB_PATH=':memory:')
    return host, hashlib.sha256((user + ':' + password).encode('ascii')).digest()


HOST, AUTH_DIGEST = configure()  # Validate BEFORE application import opens SQLite.
from wsgi import application as demo_application

REVISION = os.environ.get('RENDER_GIT_COMMIT', '')
if not re.fullmatch(r'[0-9a-f]{40}', REVISION):
    REVISION = ''
BANNER = (b'<aside role="note"><strong>PRIVATE SYNTHETIC STAGING</strong> '
          b'Use only the displayed example numbers. No real scans, SMS, charges or removals. '
          b'Disposable in-memory history is lost on sleep, restart or redeploy. '
          b'No persistence or retention guarantee.</aside>')


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
    if not authenticated(environ.get('HTTP_AUTHORIZATION', '')):
        return deny('401 Unauthorized', 'Private synthetic staging login required.', True)
    path = environ.get('PATH_INFO', '/')
    if path.startswith('/api/stripe/') or path in ('/stripe-test', '/stripe-test.js'):
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
