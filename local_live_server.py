"""Explicitly enabled, loopback-only ScanPlus self-test. Not a production server.
No SQLite, fixture results, payment, removal submissions, or deployed WSGI routes.
Report exports require a current completed session and are deliberate downloads.
"""
import json
import os
from pathlib import Path
import secrets
import threading
import time
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from live_scan import Settings, Providers, ScanSession, ScanError, HTTPSJSONTransport
from scan_report import report_text
from scan_report_pdf import report_pdf
from safe_local_log import SafeLocalLog

ROOT = Path(__file__).parent / 'static'

class LocalLiveServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, providers, activity_log=None):
        if address[0] != '127.0.0.1':
            raise ScanError('The live self-test may only bind to 127.0.0.1.')
        self.providers = providers
        self.activity_log = activity_log
        self.sessions = {}
        self.starts = []
        self.lock = threading.RLock()
        super().__init__(address, LiveHandler)
    def service_actions(self):
        with self.lock:
            now = time.monotonic()
            for key, session in list(self.sessions.items()):
                session['scan'].expire()
                if session['expires'] <= now:
                    session['scan'].clear()
                    del self.sessions[key]
            self.starts = [stamp for stamp in self.starts if stamp > now - 600]

class LiveHandler(BaseHTTPRequestHandler):
    scan_session_class = ScanSession
    def setup(self):
        super().setup()
        self.connection.settimeout(5)
    def log_message(self, *_):
        pass  # Never log URLs, phone numbers, OTPs, tokens or provider responses.
    @property
    def cookie_name(self):
        # Browser cookies are host-scoped; local test ports must not overwrite
        # each other's sessions. This is not isolation from hostile local apps.
        return 'scanplus_live_' + str(self.server.server_port) + '_sid'
    @property
    def origin(self):
        return 'http://127.0.0.1:' + str(self.server.server_port)
    def headers_common(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    def record_activity(self, status, data=None):
        log = self.server.activity_log
        if log is None:
            return
        events = {'/api/session': 'session_read', '/api/start': 'sms_start',
                  '/api/verify': 'code_check', '/api/scan': 'search',
                  '/api/clear': 'session_clear', '/api/listing/review': 'listing_review',
                  '/api/report': 'report_read', '/api/export.pdf': 'report_export',
                  '/api/export.txt': 'report_export', '/': 'page_read',
                  '/live.js': 'page_read', '/live.css': 'page_read'}
        event = events.get(self.path, 'unknown_route')
        state = data.get('state', data) if isinstance(data, dict) else {}
        if not isinstance(state, dict):
            state = {}
        diagnostic = state.get('verification_diagnostic', {}) if event in ('sms_start', 'code_check') else {}
        if not isinstance(diagnostic, dict):
            diagnostic = {}
        try:
            log.write(event, local_status=status, phase=state.get('phase'),
                      provider_status=diagnostic.get('http_status'),
                      twilio_error_code=diagnostic.get('twilio_error_code'))
        except Exception:
            pass  # A logging problem must not change the operation or expose data.

    def reply(self, status, data, cookie=None):
        self.record_activity(status, data)
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.headers_common()
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        if cookie: self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self): self.dispatch(False)
    def do_POST(self): self.dispatch(True)
    def dispatch(self, post):
        try:
            if self.headers.get('Host') != self.origin.removeprefix('http://'):
                return self.reply(403, {'error': 'Local self-test host required.'})
            if self.headers.get('Sec-Fetch-Site') not in (None, 'same-origin', 'none'):
                return self.reply(403, {'error': 'Same-origin request required.'})
            if self.headers.get('Origin') not in ((self.origin,) if post else (None, self.origin)):
                return self.reply(403, {'error': 'Same-origin request required.'})
            with self.server.lock:
                self.server.service_actions()
                if post: return self.post()
                return self.get()
        except (OSError, TimeoutError):
            return  # Disconnected client, do not log/echo request data or resend.
        except Exception:
            return self.reply(503, {'error': 'Local test could not confirm this operation. Reload to check its state before retrying.'})
    def session(self):
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
        except CookieError:
            return None
        token = cookie[self.cookie_name].value if self.cookie_name in cookie else ''
        return self.server.sessions.get(token)
    def get(self):
        if self.path in ('/api/report', '/api/export.pdf', '/api/export.txt'):
            session = self.session()
            if session is None:
                return self.reply(401, {'error': 'A current local session is required.'})
            try:
                report = session['scan'].current_report()
            except ScanError as error:
                return self.reply(409, {'error': str(error)})
            if self.path == '/api/report':
                return self.reply(200, report)
            as_text = self.path.endswith('.txt')
            raw = report_text(report).encode('utf-8') if as_text else report_pdf(report)
            # Generation can span the expiry boundary; authorize again before sending.
            try:
                session['scan'].current_report()
            except ScanError as error:
                return self.reply(409, {'error': str(error)})
            self.record_activity(200)
            self.send_response(200)
            self.headers_common()
            self.send_header('Content-Type', 'text/plain; charset=utf-8' if as_text else 'application/pdf')
            self.send_header('Content-Disposition', 'attachment; filename=scanplus-local-report.' + ('txt' if as_text else 'pdf'))
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if self.path == '/api/session':
            session = self.session()
            cookie = None
            if session is None:
                if len(self.server.sessions) >= 10:
                    return self.reply(429, {'error': 'Too many local sessions. Close unused sessions and wait 15 minutes.'})
                token = secrets.token_urlsafe(32)
                session = {'csrf': secrets.token_urlsafe(32), 'expires': time.monotonic() + 900, 'scan': self.scan_session_class(self.server.providers)}
                self.server.sessions[token] = session
                cookie = self.cookie_name + '=' + token + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=900'
            return self.reply(200, dict(session['scan'].state(), csrf_token=session['csrf']), cookie)
        paths = {'/': ('live.html', 'text/html'), '/live.js': ('live.js', 'text/javascript'), '/live.css': ('live.css', 'text/css')}
        if self.path not in paths:
            return self.reply(404, {'error': 'Page not found.'})
        filename, content_type = paths[self.path]
        raw = (ROOT / filename).read_bytes()
        self.record_activity(200)
        self.send_response(200)
        self.headers_common()
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def post(self):
        if self.path not in ('/api/start', '/api/verify', '/api/scan', '/api/clear', '/api/listing/review'):
            return self.reply(404, {'error': 'Endpoint not found.'})
        session = self.session()
        if session is None:
            return self.reply(401, {'error': 'Local session expired. Reload to start again.'})
        csrf = self.headers.get('X-CSRF-Token', '')
        if not isinstance(csrf, str) or not csrf.isascii() or len(csrf) > 128 or not secrets.compare_digest(csrf, session['csrf']):
            return self.reply(403, {'error': 'Session security token required. Reload the page.'})
        if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
            return self.reply(400, {'error': 'A bounded JSON request is required.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 2048:
                return self.reply(413, {'error': 'Invalid request size.'})
            raw = self.rfile.read(length)
            if len(raw) != length:
                return self.reply(400, {'error': 'Incomplete request.'})
            data = json.loads(raw)
            if not isinstance(data, dict): raise ValueError()
        except (ValueError, UnicodeError):
            return self.reply(400, {'error': 'Invalid JSON.'})
        scan = session['scan']
        try:
            if self.path == '/api/clear':
                scan.clear()
                return self.reply(200, scan.state())
            if self.path == '/api/start':
                scan.validate_start(data.get('phone'), own_number=data.get('own_number'), twilio_consent=data.get('twilio_consent'))
                if len(self.server.starts) >= 3:
                    return self.reply(429, {'error': 'Local safety limit: at most 3 SMS attempts per 10 minutes across all tabs. Wait before retrying.'})
                self.server.starts.append(time.monotonic())
                result = scan.start(data.get('phone'), own_number=data.get('own_number'), twilio_consent=data.get('twilio_consent'))
            elif self.path == '/api/verify':
                result = scan.verify(data.get('code'))
            elif self.path == '/api/listing/review':
                result = scan.review_listing(data.get('candidate_id'), data.get('action'), data.get('confirmed'))
            else:
                result = scan.scan(brave_consent=data.get('brave_consent'), serper_consent=data.get('serper_consent'))
            return self.reply(200, result)
        except ScanError as error:
            return self.reply(409, {'error': str(error), 'state': scan.state()})

def main():
    try:
        settings = Settings.from_environment()
        port = int(os.environ.get('SCANPLUS_LOCAL_LIVE_PORT', '4175'))
        if not 1024 <= port <= 65535: raise ScanError('Choose a local port between 1024 and 65535.')
    except (ScanError, ValueError) as error:
        raise SystemExit(str(error)) from None
    serve(settings, port)

def serve(settings, port):
    """Start explicitly configured local serving; construction makes no provider call."""
    activity_log = SafeLocalLog(Path(__file__).parent / '.data' / 'scanmydigits-local.log')
    server = LocalLiveServer(('127.0.0.1', port), Providers(settings, HTTPSJSONTransport()), activity_log=activity_log)
    if activity_log.write('server_started'):
        print('Safe local activity log: .data/scanmydigits-local.log (numeric diagnostics only)', flush=True)
    else:
        print('Safe local logging unavailable; in-page diagnostics still work.', flush=True)
    print('ScanPlus local live self-test: http://127.0.0.1:' + str(port), flush=True)
    print('Use only previously approved no-card trial allowance. The app does not verify provider billing. No payment/removal submission features.', flush=True)
    try:
        server.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:
        pass
    finally:
        for session in server.sessions.values(): session['scan'].clear()
        server.server_close()
        activity_log.write('server_stopped')

if __name__ == '__main__': main()
