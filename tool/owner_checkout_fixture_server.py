"""Isolated loopback mock UI for the combined private checkout. Never deploy.

No external Stripe navigation is performed. A clearly labeled fixture control
marks the fake checkout complete; the normal manual reconciliation gate remains.
This does not validate Stripe's hosted page or cross-site browser return.
"""
import argparse
from http.cookies import SimpleCookie, CookieError
import io
import json
from pathlib import Path
import secrets
import socket
import sys
from unittest.mock import patch
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from tool.hosted_fixture_server import FixtureApplication, FixtureTransport, QuietHandler, deny_outbound
from hosted_owner_checkout import OwnerCheckoutApplication, checkout_configuration
from test_hosted_owner_checkout import SyntheticCheckout, checkout_environment
from test_hosted_self_test import MemoryAllowance
from live_scan import HTTPSJSONTransport

SCRIPT = b"""'use strict';document.querySelector('#complete-mock').onclick=async()=>{
 const button=document.querySelector('#complete-mock');button.disabled=true;
 try{const response=await fetch('/fixture/complete',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({confirm_mock:true})});
 document.querySelector('#mock-status').textContent=response.ok?'Mock checkout marked complete. Choose Check test completion with Stripe below. No provider was contacted.':'Create the mock checkout first. No external operation occurred.';
 }finally{button.disabled=false;}};"""


class CheckoutFixtureApplication(FixtureApplication):
    def __init__(self, port, scenario='matches'):
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('Choose an unprivileged local port')
        self.origin = 'http://127.0.0.1:' + str(port)
        self.transport = FixtureTransport(scenario)
        self.scenario = scenario
        self.stripe = SyntheticCheckout()
        self.application = OwnerCheckoutApplication(checkout_configuration(checkout_environment(True)),
                                                    self.transport, allowance=MemoryAllowance(),
                                                    checkout_transport=self.stripe)

    def __call__(self, env, start_response):
        path = env.get('PATH_INFO')
        if path in ('/fixture/complete', '/fixture-checkout.js'):
            status, raw = '403 Forbidden', b'Loopback same-origin fixture only.'
            method = env.get('REQUEST_METHOD')
            if (env.get('HTTP_HOST') == self.origin.removeprefix('http://') and
                    env.get('HTTP_ORIGIN') in ((self.origin,) if method == 'POST' else (None, self.origin)) and
                    env.get('HTTP_SEC_FETCH_SITE') in (None, 'none', 'same-origin') and not env.get('QUERY_STRING')):
                if path == '/fixture-checkout.js' and method == 'GET':
                    status, raw = '200 OK', SCRIPT
                elif path == '/fixture/complete' and method == 'POST':
                    try:
                        length = int(env.get('CONTENT_LENGTH', '0'))
                        cookie = SimpleCookie(env.get('HTTP_COOKIE', ''))
                        token = cookie['scanplus_owner_checkout_sid'].value
                        session = self.application.state.sessions.get(token)
                        csrf = env.get('HTTP_X_CSRF_TOKEN', '')
                        if (not session or not isinstance(csrf, str) or not csrf.isascii() or
                                not secrets.compare_digest(csrf, session['csrf']) or
                                not 0 < length <= 128 or env.get('CONTENT_TYPE') != 'application/json' or
                                env.get('HTTP_TRANSFER_ENCODING')):
                            raise ValueError()
                        body = json.loads(env['wsgi.input'].read(length))
                        if body != {'confirm_mock': True} or self.stripe.result is None:
                            raise ValueError()
                        self.stripe.completed = True
                        status, raw = '200 OK', b'Mock completion only. No external request.'
                    except (ValueError, KeyError, CookieError, TypeError):
                        status, raw = '400 Bad Request', b'Create the synthetic checkout first.'
            content_type = 'text/javascript' if path.endswith('.js') else 'text/plain'
            start_response(status, [('Content-Type', content_type), ('Cache-Control', 'no-store'),
                                    ('X-Content-Type-Options', 'nosniff'), ('Content-Length', str(len(raw)))])
            return [raw]
        captured = {}
        def capture(status, headers):
            captured.update(status=status, headers=headers)
        body = b''.join(super().__call__(env, capture))
        if path == '/' and captured['status'].startswith('200'):
            fixture = ('<aside><strong>MOCK CHECKOUT ONLY</strong><p>No external Stripe page or redirect is used. '
                       'Use the mock code OWNER100 for the separate coupon path. First create checkout below, '
                       'then use this fixture control, then Check test completion.</p>'
                       '<button type="button" id="complete-mock">Complete synthetic checkout</button>'
                       '<p id="mock-status" role="status"></p></aside>')
            body = body.replace(b'<main>', b'<main>' + fixture.encode(), 1)
            body = body.replace(b'</body>', b'<script src="/fixture-checkout.js" defer></script></body>', 1)
        elif path == '/api/checkout/create' and captured['status'].startswith('200'):
            payload = json.loads(body)
            payload.pop('checkout_url', None)  # This fixture must never navigate externally.
            body = json.dumps(payload).encode()
        headers = [(k, v) for k, v in captured['headers'] if k.lower() != 'content-length']
        headers.append(('Content-Length', str(len(body))))
        start_response(captured['status'], headers)
        return [body]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4177)
    args = parser.parse_args()
    app = CheckoutFixtureApplication(args.port)
    try:
        with patch.object(socket.socket, 'connect', deny_outbound), patch.object(socket.socket, 'connect_ex', deny_outbound), patch.object(HTTPSJSONTransport, 'request', deny_outbound):
            with make_server('127.0.0.1', args.port, app, handler_class=QuietHandler) as server:
                print('MOCK SMS/CHECKOUT/SEARCH ONLY http://127.0.0.1:' + str(args.port) + ' | 2025550147 / 123456 | coupon OWNER100', flush=True)
                server.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:
        pass
    finally:
        app.close()


if __name__ == '__main__':
    main()
