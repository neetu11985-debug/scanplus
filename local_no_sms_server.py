"""Isolated loopback-only no-SMS owner self-test, never production verification.
Default startup is offline. Explicit approved Serper-only startup can run one
bounded three-query scan by default, or explicitly configured repeat tests. No Twilio operation or payment/removal route exists.
"""
import argparse
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time

from no_sms_scan import (BLOCKER, NoSMSSession, ScanError, load_approved_search,
                         no_sms_report_text)

from scan_report_pdf import report_pdf
from local_diagnostic_log import LocalDiagnosticLog, DiagnosticLogError

ROOT = Path(__file__).resolve().parent / 'static'


def token_matches(value, expected):
    # Header/cookie input is untrusted. Non-ASCII strings otherwise raise in
    # compare_digest and turn an ordinary authentication rejection into a 503.
    return isinstance(value, str) and value.isascii() and secrets.compare_digest(value, expected)


class NoSMSServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, search=None):
        if address[0] != '127.0.0.1':
            raise ValueError('This private test may only bind to 127.0.0.1.')
        self.lock = threading.RLock()
        self.session = None
        self.search = search
        super().__init__(address, NoSMSHandler)

    def service_actions(self):
        with self.lock:
            if self.session:
                self.session['scan'].expire()
                if self.session['expires'] <= time.monotonic():
                    self.session['scan'].clear()
                    self.session = None


class NoSMSHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        pass

    @property
    def cookie_name(self):
        # Browser cookies are host-scoped, not port-scoped. Distinct local test
        # ports must not overwrite one another's session cookie.
        return 'scanplus_no_sms_' + str(self.server.server_port) + '_sid'

    @property
    def origin(self):
        return 'http://127.0.0.1:' + str(self.server.server_port)

    def reply(self, status, payload, *, cookie=None, content_type='application/json', download=None):
        raw = json.dumps(payload).encode() if content_type == 'application/json' else payload
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if download:
            self.send_header('Content-Disposition', 'attachment; filename=' + download)
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(raw)

    def state(self):
        return dict(self.server.session['scan'].state(), csrf_token=self.server.session['csrf'])

    def owns_session(self):
        try:
            cookies = SimpleCookie(self.headers.get('Cookie', ''))
            token = cookies[self.cookie_name].value if self.cookie_name in cookies else ''
        except CookieError:
            return False
        return self.server.session is not None and token_matches(token, self.server.session['token'])

    def do_GET(self):
        self.dispatch(False)

    def do_POST(self):
        self.dispatch(True)

    def dispatch(self, post):
        try:
            if (self.client_address[0] != '127.0.0.1' or
                self.headers.get_all('Host') != [self.origin[7:]] or
                any(name.lower() == 'forwarded' or name.lower().startswith('x-forwarded-')
                    for name in self.headers)):
                return self.reply(403, {'error': 'Direct loopback access is required. Proxies and public hosting are unsupported.'})
            if self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
                return self.reply(403, {'error': 'Same-origin access is required.'})
            origins = self.headers.get_all('Origin')
            if origins != [self.origin] and (post or origins is not None):
                return self.reply(403, {'error': 'Same-origin access is required.'})
            with self.server.lock:
                self.server.service_actions()
                return self.post() if post else self.get()
        except (OSError, TimeoutError):
            return
        except Exception:
            return self.reply(503, {'error': 'The private local test could not complete. Reload before retrying.'})

    def get(self):
        if self.path == '/api/session':
            cookie = None
            if self.server.session is None:
                token = secrets.token_urlsafe(32)
                self.server.session = {'token': token, 'csrf': secrets.token_urlsafe(32),
                                       'expires': time.monotonic() + 900,
                                       'scan': NoSMSSession(self.server.search)}
                cookie = self.cookie_name + '=' + token + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=900'
            elif not self.owns_session():
                return self.reply(409, {'error': 'This single-user test is already open in another browser session. Use that session or wait 15 minutes.'})
            return self.reply(200, self.state(), cookie=cookie)
        if self.path in ('/api/report', '/api/export.txt', '/api/export.pdf'):
            if not self.owns_session():
                return self.reply(401, {'error': 'A current local session is required.'})
            try:
                report = self.server.session['scan'].current_report()
            except ScanError as error:
                return self.reply(409, {'error': str(error)})
            if self.path == '/api/report':
                return self.reply(200, report)
            as_text = self.path.endswith('.txt')
            raw = no_sms_report_text(report).encode('utf-8') if as_text else report_pdf(report)
            try:
                self.server.session['scan'].current_report()
            except ScanError as error:
                return self.reply(409, {'error': str(error)})
            return self.reply(200, raw, content_type='text/plain; charset=utf-8' if as_text else 'application/pdf',
                              download='scanmydigits-no-sms-report.' + ('txt' if as_text else 'pdf'))
        files = {'/': ('no_sms.html', 'text/html; charset=utf-8'),
                 '/no_sms.js': ('no_sms.js', 'text/javascript; charset=utf-8'),
                 '/no_sms.css': ('no_sms.css', 'text/css; charset=utf-8')}
        if self.path not in files:
            return self.reply(404, {'error': 'Page not found.'})
        name, mime = files[self.path]
        return self.reply(200, (ROOT / name).read_bytes(), content_type=mime)

    def post(self):
        if self.path not in ('/api/start', '/api/scan', '/api/clear'):
            return self.reply(404, {'error': 'Operation not available in the no-SMS local test.'})
        if not self.owns_session():
            return self.reply(401, {'error': 'Reload the original local session.'})
        if not token_matches(self.headers.get('X-CSRF-Token', ''), self.server.session['csrf']):
            return self.reply(403, {'error': 'A current session security token is required.'})
        if (self.headers.get('Content-Type') != 'application/json' or
            self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1):
            return self.reply(400, {'error': 'A bounded JSON request is required.'})
        try:
            length = int(self.headers['Content-Length'])
            if not 0 < length <= 2048:
                return self.reply(413, {'error': 'Invalid request size.'})
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError()
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            return self.reply(400, {'error': 'Invalid JSON.'})
        scan = self.server.session['scan']
        try:
            if self.path == '/api/clear':
                scan.clear()
            elif self.path == '/api/start':
                scan.start(data.get('phone'), own_number=data.get('own_number'),
                           no_sms_acknowledged=data.get('no_sms_acknowledged'))
            else:
                scan.scan(serper_consent=data.get('serper_consent'),
                          free_allowance_confirmed=data.get('free_allowance_confirmed'))
            return self.reply(200, self.state())
        except ScanError as error:
            return self.reply(409, {'error': str(error), 'state': self.state()})


def main(argv=None):
    parser = argparse.ArgumentParser(description='Private no-SMS owner self-test. Offline unless explicitly enabled after free-credit approval.')
    parser.add_argument('--local-no-sms', action='store_true', required=True,
                        help='Explicitly acknowledge this unverified local-only test.')
    parser.add_argument('--port', type=int, default=4176)
    parser.add_argument('--serper-live', action='store_true')
    parser.add_argument('--properties-file', type=Path,
                        help='Explicit existing owner-private ScanPlus properties file; read in place, never copied.')
    parser.add_argument('--confirmed-free-queries', type=int)
    parser.add_argument('--test-max-scans', type=int, choices=range(1, 6), default=1,
                        help='Local own-number testing only: one to five scans, each separately consented. Default: one.')
    parser.add_argument('--no-paid-topup-confirmed', action='store_true')
    parser.add_argument('--diagnostic-log', action='store_true',
                        help='Opt in to an owner-only local error-category log, bounded to 64 KiB. No phone/key/body logging.')
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a port from 1024 to 65535.')
    search = None
    try:
        if args.serper_live:
            search = load_approved_search(args.properties_file if args.properties_file is not None else Path(__file__).resolve().parent / 'scanplus.local.properties',
                                          confirmed_free_queries=args.confirmed_free_queries,
                                          no_paid_topup_confirmed=args.no_paid_topup_confirmed,
                                          max_scans=args.test_max_scans)
            if args.diagnostic_log:
                search.diagnostic_log = LocalDiagnosticLog(Path(__file__).resolve().parent / 'scanplus-local-diagnostics.log')
        elif args.confirmed_free_queries is not None or args.no_paid_topup_confirmed or args.test_max_scans != 1 or args.properties_file is not None or args.diagnostic_log:
            parser.error('Properties-file selection and test-budget confirmation require explicit --serper-live startup.')
    except (ScanError, DiagnosticLogError) as error:
        raise SystemExit(str(error)) from None
    with NoSMSServer(('127.0.0.1', args.port), search) as server:
        print('ScanMyDigits private no-SMS self-test: http://127.0.0.1:' + str(server.server_port), flush=True)
        print('SMS OFF. Ownership NOT verified. ' + (str(search.transport.max_scans) + ' local test scan(s), maximum ' + str(search.transport.query_limit) + ' queries total. Same number only; separate consent for each scan.' if search else 'Real Serper search BLOCKED. No keys are read.'), flush=True)
        if search and search.diagnostic_log:
            print('Private diagnostic log: scanplus-local-diagnostics.log (' + search.diagnostic_log.status + '). Maximum 64 KiB; safe categories and counters only.', flush=True)
        try:
            server.serve_forever(poll_interval=.5)
        except KeyboardInterrupt:
            pass
        finally:
            if server.session:
                server.session['scan'].clear()
            server.session = None


if __name__ == '__main__':
    main()
