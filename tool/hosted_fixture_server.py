"""Loopback-only rendered QA for the private hosted page. Synthetic data only.

This does not validate HTTPS ingress, Basic login or real PostgreSQL/provider
behavior. The adapter supplies fixture ingress/auth headers and removes Secure
from the fixture cookie for localhost HTTP. Production entrypoints never import
this module. No credentials or environment configuration are read.
"""
import argparse
import io
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from hosted_self_test import OwnerTestApplication, configuration
from live_scan import HTTPSJSONTransport
from test_hosted_self_test import AUTH, HOST, MemoryAllowance, environment
from test_live_scan import PHONE, verification
from test_serper_scan import organic

BANNER = ('<aside role="note"><strong>SYNTHETIC BROWSER QA ONLY</strong>'
          '<p>No SMS, provider search or database connection is possible in this runner. '
          'Use 2025550147 and code 123456. Do not open external listing or guide links. '
          'The real-action labels below are being tested with mocks.</p></aside>')


class FixtureTransport:
    def __init__(self, scenario='matches'):
        if scenario not in ('matches', 'empty', 'unavailable'):
            raise ValueError('Choose a supported synthetic scenario')
        self.scenario = scenario
        self.searches = 0

    def request(self, method, url, **kwargs):
        if method != 'POST':
            raise AssertionError('Unexpected synthetic request method')
        if url.endswith('/Verifications'):
            data = parse_qs(kwargs.get('body', ''))
            if data.get('To') != [PHONE]:
                raise AssertionError('Only the synthetic number is allowed')
            return 201, verification()
        if url.endswith('/VerificationCheck'):
            data = parse_qs(kwargs.get('body', ''))
            return 200, verification('approved' if data.get('Code') == ['123456'] else 'pending')
        if url == 'https://google.serper.dev/search':
            query = json.loads(kwargs.get('body', '{}')).get('q', '')
            for site in ('spokeo.com', 'truepeoplesearch.com', 'whitepages.com'):
                if query == '"' + PHONE + '" site:' + site:
                    self.searches += 1
                    if self.scenario == 'unavailable':
                        return 503, None
                    if self.scenario == 'empty':
                        return 200, {'organic': []}
                    return 200, organic(site)
        raise AssertionError('Unexpected synthetic operation')


class FixtureApplication:
    def __init__(self, port, scenario='matches'):
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('Choose an unprivileged local port')
        self.origin = 'http://127.0.0.1:' + str(port)
        self.transport = FixtureTransport(scenario)
        self.scenario = scenario
        self.application = OwnerTestApplication(configuration(environment()), self.transport,
                                                allowance=MemoryAllowance())

    def close(self):
        self.application.close()

    def __call__(self, env, start_response):
        def refuse(status, text):
            raw = text.encode('ascii')
            start_response(status, [('Content-Type', 'text/plain'), ('Cache-Control', 'no-store'),
                                    ('Content-Length', str(len(raw)))])
            return [raw]
        method = env.get('REQUEST_METHOD')
        if (env.get('HTTP_HOST') != self.origin.removeprefix('http://') or
                env.get('HTTP_ORIGIN') not in ((self.origin,) if method == 'POST' else (None, self.origin)) or
                env.get('HTTP_SEC_FETCH_SITE') not in (None, 'none', 'same-origin')):
            return refuse('403 Forbidden', 'Loopback same-origin synthetic QA only.')
        if method == 'POST':
            try:
                length = int(env.get('CONTENT_LENGTH', '0'))
                if not 0 < length <= 2048 or env.get('HTTP_TRANSFER_ENCODING'):
                    raise ValueError()
                raw = env['wsgi.input'].read(length)
                if len(raw) != length:
                    raise ValueError()
                data = json.loads(raw)
                if env.get('PATH_INFO') == '/api/start' and (not isinstance(data, dict) or data.get('phone') != PHONE):
                    return refuse('400 Bad Request', 'Use the synthetic number 2025550147 only.')
                env = dict(env, **{'wsgi.input': io.BytesIO(raw)})
            except (ValueError, TypeError, OSError):
                return refuse('400 Bad Request', 'Invalid synthetic QA body.')
        env = dict(env, HTTP_HOST=HOST, HTTP_AUTHORIZATION=AUTH,
                   HTTP_ORIGIN='https://' + HOST, **{'wsgi.url_scheme': 'https'})
        captured = {}
        def capture(status, headers):
            captured.update(status=status, headers=headers)
        body = b''.join(self.application(env, capture))
        if env.get('PATH_INFO') == '/' and captured['status'].startswith('200'):
            body = body.replace(b'<main>', ('<main>' + BANNER + '<p><strong>Fixture scenario: ' + self.scenario + '</strong></p>').encode(), 1)
        headers = [(key, value.replace('; Secure', '') if key.lower() == 'set-cookie' else value)
                   for key, value in captured['headers'] if key.lower() != 'content-length']
        headers.append(('Content-Length', str(len(body))))
        start_response(captured['status'], headers)
        return [body]


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *_):
        pass


def deny_outbound(*_args, **_kwargs):
    raise AssertionError('Outbound connections are forbidden in synthetic browser QA')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4177)
    parser.add_argument('--scenario', choices=('matches', 'empty', 'unavailable'), default='matches')
    args = parser.parse_args()
    application = FixtureApplication(args.port, args.scenario)
    try:
        with patch.object(socket.socket, 'connect', deny_outbound), patch.object(socket.socket, 'connect_ex', deny_outbound), patch.object(HTTPSJSONTransport, 'request', deny_outbound):
            with make_server('127.0.0.1', args.port, application, handler_class=QuietHandler) as server:
                print('SYNTHETIC QA ONLY http://127.0.0.1:' + str(args.port) + ' | phone 2025550147 | code 123456 | scenario ' + args.scenario, flush=True)
                server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        application.close()


if __name__ == '__main__':
    main()
