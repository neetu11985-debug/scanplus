"""Opt-in private owner SMS -> Stripe TEST -> consented search orchestration.

No customer billing, persistent report storage or public webhook is enabled.
The existing demo and payment-free owner entrypoints remain unchanged.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import time

from hosted_self_test import (Configuration, OwnerTestApplication, OwnerTestHandler,
                              TimedScanSession, configuration)
from live_scan import ScanError
from owner_test_checkout import OwnerTestCheckout, OwnerCheckoutError

ROOT = Path(__file__).parent / 'static'


@dataclass(frozen=True, repr=False)
class CheckoutConfiguration:
    owner: Configuration
    key: str
    coupon_id: str = ''
    coupon_code: str = ''


def checkout_configuration(environment=None):
    env = os.environ if environment is None else environment
    if env.get('SCANPLUS_OWNER_CHECKOUT_TEST') != '1':
        raise RuntimeError('Private owner checkout test is disabled.')
    # Keep the ordinary sandbox and encrypted-storage guards intact. This is a
    # new explicit private entrypoint, not a way to enable payments in the demo.
    owner = configuration(env)
    key = env.get('STRIPE_SECRET_KEY', '')
    coupon_id = env.get('SCANPLUS_OWNER_TEST_COUPON_ID', '')
    coupon_code = env.get('SCANPLUS_OWNER_TEST_COUPON_CODE', '')
    try:
        OwnerTestCheckout(key, 'https://' + owner.host,
                          coupon_id=coupon_id, coupon_code=coupon_code)
    except (OwnerCheckoutError, ValueError, TypeError):
        raise RuntimeError('Approved Stripe test key and optional test coupon configuration required.') from None
    return CheckoutConfiguration(owner, key, coupon_id, coupon_code)


class CheckoutScanSession(TimedScanSession):
    def __init__(self, providers, clock=time.monotonic):
        self.checkout = providers.owner_checkout
        self.checkout_owner = secrets.token_urlsafe(32)
        self.checkout_expires = None
        self._initializing = True
        super().__init__(providers, clock)
        self._initializing = False

    def clear(self):
        if not self._initializing:
            self.checkout.clear(self.checkout_owner)
        self.checkout_expires = None
        super().clear()

    def start(self, *args, **kwargs):
        super().start(*args, **kwargs)
        # One stable wall-clock bound. Redirect, reconciliation and refresh never
        # extend either the five-minute verification/search lifetime or this one.
        self.checkout_expires = time.time() + max(0, self.expires - self.clock())
        return self.state()

    def state(self):
        result = super().state()
        checkout = self.checkout.state(self.checkout_owner)
        result['checkout_test'] = dict(checkout, enabled=True)
        if self.phase == 'verified' and not checkout.get('authorized'):
            result['phase'] = 'checkout'
        if result.get('report'):
            result['report']['payment_notice'] = 'Private Stripe test only. No real payment was collected.'
        return result

    def checkout_action(self, action, data):
        self.expire()
        if self.phase != 'verified' or not self.phone or self.checkout_expires is None:
            raise ScanError('Current Twilio verification is required for the private Stripe test.')
        try:
            if action == 'create':
                if set(data) - {'accept_test', 'coupon_code'}:
                    raise ScanError('Checkout price and order are server-controlled; no extra fields accepted.')
                coupon_code = data.get('coupon_code')
                prior = self.checkout.state(self.checkout_owner)
                if ('coupon_code' not in data and prior['state'] != 'not_started'
                        and prior['discount_cents'] == 149):
                    # A return/reload must resume the same immutable coupon order,
                    # not silently switch it to the full-price card-test variant.
                    coupon_code = self.providers.owner_test_coupon_code
                result = self.checkout.create(self.checkout_owner, self.checkout_expires,
                                              accept_test=data.get('accept_test'),
                                              coupon_code=coupon_code)
            else:
                if data:
                    raise ScanError('No checkout or owner overrides are accepted.')
                result = self.checkout.reconcile(self.checkout_owner, self.checkout_expires)
        except OwnerCheckoutError as error:
            raise ScanError(str(error)) from None
        # An eight-second Stripe request may cross the local expiry boundary.
        self.expire()
        if self.phase != 'verified' or not self.phone:
            raise ScanError('Private test expired. No search or new checkout is authorized.')
        state = self.state()
        if result.get('checkout_url'):
            state['checkout_url'] = result['checkout_url']
        return state

    def scan(self, **kwargs):
        self.expire()
        if not self.checkout.state(self.checkout_owner).get('authorized'):
            raise ScanError('Server-confirmed Stripe test completion is required before search.')
        return super().scan(**kwargs)

    def current_report(self):
        report = super().current_report()
        if not self.checkout.state(self.checkout_owner).get('authorized'):
            raise ScanError('Current private test checkout authorization is required.')
        report['payment_notice'] = 'Private Stripe test only. No real payment was collected.'
        return report


class OwnerCheckoutHandler(OwnerTestHandler):
    scan_session_class = CheckoutScanSession

    @property
    def cookie_name(self):
        return 'scanplus_owner_checkout_sid'

    def get(self):
        if self.path == '/':
            raw = (ROOT / 'hosted-checkout.html').read_bytes()
            self.send_response(200)
            self.headers_common()
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        return super().get()

    def post(self):
        if self.path not in ('/api/checkout/create', '/api/checkout/reconcile'):
            return super().post()
        session = self.session()
        if session is None:
            return self.reply(401, {'error': 'Current private session required.'})
        csrf = self.headers.get('X-CSRF-Token', '')
        if (not isinstance(csrf, str) or not csrf.isascii() or len(csrf) > 128 or
                not secrets.compare_digest(csrf, session['csrf'])):
            return self.reply(403, {'error': 'Session security token required.'})
        # The outer authenticated application already bounded and copied the body.
        try:
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, UnicodeError, TypeError):
            return self.reply(400, {'error': 'Invalid JSON.'})
        scan = session['scan']
        try:
            return self.reply(200, scan.checkout_action(self.path.rsplit('/', 1)[1], data))
        except ScanError as error:
            return self.reply(409, {'error': str(error), 'state': scan.state()})


class OwnerCheckoutApplication(OwnerTestApplication):
    handler_class = OwnerCheckoutHandler

    def allow_cross_site_navigation(self, environment):
        # Stripe's return is a top-level GET, never completion proof. Permit the
        # authenticated shell only; its same-origin bootstrap can then send the
        # existing Strict cookie. Every API and mutation keeps the original gate.
        return (environment.get('REQUEST_METHOD') == 'GET' and
                environment.get('PATH_INFO') == '/' and
                not environment.get('QUERY_STRING') and not environment.get('SCRIPT_NAME') and
                environment.get('HTTP_ORIGIN') is None and
                environment.get('HTTP_SEC_FETCH_SITE') == 'cross-site' and
                environment.get('HTTP_SEC_FETCH_MODE') == 'navigate' and
                environment.get('HTTP_SEC_FETCH_DEST') == 'document')

    def __init__(self, config, transport=None, *, allowance=None, checkout_transport=None,
                 start_cleanup=True):
        self.checkout = OwnerTestCheckout(config.key, 'https://' + config.owner.host,
                                          coupon_id=config.coupon_id, coupon_code=config.coupon_code,
                                          transport=checkout_transport)
        super().__init__(config.owner, transport, allowance=allowance, start_cleanup=start_cleanup)
        self.state.providers.owner_checkout = self.checkout
        self.state.providers.owner_test_coupon_code = config.coupon_code
