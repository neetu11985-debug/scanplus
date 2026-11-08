"""Private owner-test Stripe adapter; not customer billing or paid-report storage.

The caller must authenticate the owner and verify their phone before create or
reconcile, then enforce the same unexpired identity before granting a search.
Only opaque owner/order identifiers cross this boundary. No phone, OTP, report,
card data, environment reads, database, webhook, or coupon creation lives here.
Orders and replay claims are process-local: a restart revokes all entitlements.
"""
import hashlib
import math
import re
from threading import RLock
import time
from urllib.parse import urlsplit

from stripe_checkout import StripeError, is_test_api_key, request

PRICE_CENTS = 149
INTEGRATION_IDENTIFIER = 'scanplus-owner-test-bjmwenrj'
MAX_OWNERS = 10
MAX_CREATE_ATTEMPTS = 2
MAX_RECONCILIATIONS = 5
MAX_LIFETIME = 900
ENTITLED = frozenset(('paid_test', 'complimentary_test'))


class OwnerCheckoutError(StripeError):
    """Static, sanitized errors safe to show in the private test page."""


def _owner(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{22,128}', value):
        raise OwnerCheckoutError('A current opaque owner session is required.')
    return value


def _code(value):
    if value is None or value == '':
        return ''
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9]{1,32}', value):
        raise OwnerCheckoutError('The private test coupon is unavailable.')
    return value.upper()


class OwnerTestCheckout:
    """One immutable test order per owner, with explicitly bounded manual retries.

    transport(method, path, key, fields=None, idempotency_key=None) uses the
    existing fixed-host, test-key-only Stripe transport unless injected by tests.
    Optional coupon settings map one local display code to an already-created,
    approved Stripe sandbox coupon. They do not create a promotion code or
    establish that a configured coupon exists; Stripe must confirm the discount.
    """
    def __init__(self, key, origin, *, coupon_id='', coupon_code='', transport=None,
                 clock=time.time):
        if not is_test_api_key(key):
            raise OwnerCheckoutError('A Stripe sandbox restricted or secret API key is required.')
        try:
            if not isinstance(origin, str) or any(ord(c) <= 32 or ord(c) == 127 or c == '\\' for c in origin):
                raise ValueError()
            parsed = urlsplit(origin)
            if (parsed.scheme != 'https' or
                    not parsed.hostname or parsed.netloc != parsed.hostname or
                    parsed.path or parsed.query or parsed.fragment or
                    not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,251}[a-z0-9]', parsed.hostname)):
                raise ValueError()
        except (TypeError, ValueError):
            raise OwnerCheckoutError('An exact trusted HTTPS return origin is required.') from None
        code = _code(coupon_code)
        if (not isinstance(coupon_id, str) or bool(coupon_id) != bool(code) or
                (coupon_id and not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', coupon_id))):
            raise OwnerCheckoutError('Configure both the approved test coupon ID and its display code.')
        self._key, self._origin = key, origin
        self._coupon_id, self._coupon_code = coupon_id, code
        self._transport = request if transport is None else transport
        self._clock = clock
        self._orders, self._claims = {}, {}
        self._revoked = set()
        self._lock = RLock()

    def _deadline(self, value):
        now = self._clock()
        if (type(value) not in (int, float) or not math.isfinite(value) or
                not now < value <= now + MAX_LIFETIME):
            raise OwnerCheckoutError('Current, bounded owner verification is required.')
        return value

    def _expire(self, order):
        if self._clock() >= order['expires']:
            order['state'] = 'expired'
            order.pop('url', None)
        return order['state'] == 'expired'

    def state(self, owner_id):
        owner_id = _owner(owner_id)
        with self._lock:
            order = self._orders.get(owner_id)
            if order:
                self._expire(order)
            status = order['state'] if order else ('cleared' if owner_id in self._revoked else 'not_started')
            discount = PRICE_CENTS if order and order['coupon'] else 0
            return {'state': status, 'authorized': status in ENTITLED, 'test_mode': True,
                    'subtotal_cents': PRICE_CENTS, 'discount_cents': discount,
                    'amount_cents': PRICE_CENTS - discount, 'currency': 'USD',
                    'charged_cents': 0, 'coupon_available': bool(self._coupon_id)}

    def _existing(self, owner_id, expires_at_wall):
        owner_id = _owner(owner_id)
        deadline = self._deadline(expires_at_wall)
        if owner_id in self._revoked:
            raise OwnerCheckoutError('This checkout was cleared and cannot be reopened.')
        order = self._orders.get(owner_id)
        if order:
            # Caller may shorten an identity's lifetime, never renew a checkout.
            order['expires'] = min(order['expires'], deadline)
            if self._expire(order):
                raise OwnerCheckoutError('This private checkout expired. No search is authorized.')
            if order['state'] == 'blocked':
                raise OwnerCheckoutError('Checkout validation failed. Operator review is required.')
        return owner_id, deadline, order

    def create(self, owner_id, expires_at_wall, *, accept_test, coupon_code=None):
        if accept_test is not True:
            raise OwnerCheckoutError('Confirm Stripe sandbox testing; never enter real card details.')
        selection = _code(coupon_code)
        if selection and (not self._coupon_id or selection != self._coupon_code):
            raise OwnerCheckoutError('The private test coupon is unavailable.')
        with self._lock:
            owner_id, deadline, order = self._existing(owner_id, expires_at_wall)
            if order is None:
                if len(self._orders) + len(self._revoked) >= MAX_OWNERS:
                    raise OwnerCheckoutError('Private checkout session allowance exhausted.')
                order = {'id': hashlib.sha256(('owner-test:' + self._origin + ':' + owner_id).encode()).hexdigest(),
                         'expires': deadline, 'coupon': bool(selection), 'state': 'pending',
                         'checkout_id': None, 'payment_ref': None, 'creates': 0, 'reconciles': 0,
                         'integration_identifier': INTEGRATION_IDENTIFIER}
                self._orders[owner_id] = order
            elif order['coupon'] != bool(selection):
                raise OwnerCheckoutError('The reserved checkout discount cannot be changed.')
            if order['state'] in ENTITLED:
                return self.state(owner_id)
            if order.get('url'):
                return dict(self.state(owner_id), checkout_url=order['url'])
            if order['creates'] >= MAX_CREATE_ATTEMPTS:
                raise OwnerCheckoutError('Checkout outcome needs operator review. No new request was sent.')
            # Keep this short-lived, retrieval-only owner fixture card-scoped;
            # the public sandbox uses dynamic methods and signed webhooks.
            fields = {'mode': 'payment', 'allowed_payment_method_types[0]': 'card',
                      'integration_identifier': order['integration_identifier'],
                      'line_items[0][quantity]': '1',
                      'line_items[0][price_data][currency]': 'usd',
                      'line_items[0][price_data][unit_amount]': str(PRICE_CENTS),
                      'line_items[0][price_data][product_data][name]': 'ScanPlus private owner test - NO REAL CHARGE',
                      'client_reference_id': order['id'], 'metadata[scanplus_owner_test_order]': order['id'],
                      'success_url': self._origin + '/#checkout-returned',
                      'cancel_url': self._origin + '/#checkout-cancelled'}
            if order['coupon']:
                fields['discounts[0][coupon]'] = self._coupon_id
            order['creates'] += 1  # Reserve before IO, including failed attempts.
            result = self._call(order, 'POST', '/v1/checkout/sessions', fields,
                                'scanplus-owner-test-' + order['id'])
            self._accept(order, result, creating=True)
            if self._clock() >= order['expires']:
                self._expire(order)
                raise OwnerCheckoutError('Owner verification expired during checkout. No search is authorized.')
            state = self.state(owner_id)
            return dict(state, checkout_url=order['url']) if order.get('url') and not state['authorized'] else state

    def reconcile(self, owner_id, expires_at_wall):
        with self._lock:
            owner_id, _, order = self._existing(owner_id, expires_at_wall)
            if order is None or not order['checkout_id']:
                raise OwnerCheckoutError('No known Stripe checkout can be checked. Do not create a different order.')
            if order['state'] in ENTITLED:
                return self.state(owner_id)
            if order['reconciles'] >= MAX_RECONCILIATIONS:
                raise OwnerCheckoutError('Manual checkout-check allowance exhausted. No request was sent.')
            order['reconciles'] += 1
            result = self._call(order, 'GET', '/v1/checkout/sessions/' + order['checkout_id'])
            self._accept(order, result, creating=False)
            if self._clock() >= order['expires']:
                self._expire(order)
                raise OwnerCheckoutError('Owner verification expired during checkout. No search is authorized.')
            return self.state(owner_id)

    def _call(self, order, method, path, fields=None, idempotency_key=None):
        try:
            return self._transport(method, path, self._key, fields, idempotency_key)
        except Exception:
            order['state'] = 'uncertain'
            raise OwnerCheckoutError('Stripe test outcome is uncertain. No automatic retry or search occurred.') from None

    def _claim(self, kind, value, order):
        owner = self._claims.get((kind, value))
        if owner is not None and owner != order['id']:
            raise OwnerCheckoutError('Checkout reference was already assigned. Access remains locked.')
        self._claims[(kind, value)] = order['id']

    def _validate(self, result, order):
        if (not isinstance(result, dict) or result.get('object') != 'checkout.session' or
                not isinstance(result.get('id'), str) or not re.fullmatch(r'cs_test_[A-Za-z0-9_]+', result['id']) or
                result.get('livemode') is not False or result.get('mode') != 'payment' or
                result.get('currency') != 'usd' or result.get('client_reference_id') != order['id'] or
                not isinstance(result.get('metadata'), dict) or
                result['metadata'].get('scanplus_owner_test_order') != order['id'] or
                (order['checkout_id'] and result['id'] != order['checkout_id'])):
            raise OwnerCheckoutError('Stripe test order validation failed. Access remains locked.')
        discount = PRICE_CENTS if order['coupon'] else 0
        details = result.get('total_details')
        if (type(result.get('amount_subtotal')) is not int or result['amount_subtotal'] != PRICE_CENTS or
                type(result.get('amount_total')) is not int or result['amount_total'] != PRICE_CENTS - discount or
                not isinstance(details, dict) or
                any(type(details.get(name)) is not int or details[name] != expected for name, expected in
                    (('amount_discount', discount), ('amount_shipping', 0), ('amount_tax', 0)))):
            raise OwnerCheckoutError('Stripe test amount or discount did not match the reserved order.')
        discounts = result.get('discounts')
        if order['coupon']:
            if not isinstance(discounts, list) or len(discounts) != 1 or not isinstance(discounts[0], dict):
                raise OwnerCheckoutError('Stripe did not confirm the configured test coupon.')
            coupon = discounts[0].get('coupon')
            if isinstance(coupon, dict):
                if coupon.get('livemode') is not False or coupon.get('percent_off') != 100:
                    raise OwnerCheckoutError('Stripe did not confirm a 100 percent test coupon.')
                coupon = coupon.get('id')
            if coupon != self._coupon_id or discounts[0].get('promotion_code') is not None:
                raise OwnerCheckoutError('Stripe did not confirm the configured test coupon.')
        elif discounts not in (None, []):
            raise OwnerCheckoutError('An unexpected Stripe discount was returned.')
        status, payment = result.get('status'), result.get('payment_status')
        if status not in ('open', 'complete', 'expired') or payment not in ('unpaid', 'paid', 'no_payment_required'):
            raise OwnerCheckoutError('Unsupported Stripe checkout state.')
        if 'payment_intent' not in result:
            raise OwnerCheckoutError('Stripe checkout payment evidence is incomplete.')
        intent = result.get('payment_intent')
        if order['coupon']:
            if intent is not None or payment == 'paid' or (status == 'complete' and payment != 'no_payment_required'):
                raise OwnerCheckoutError('Expected a completed no-payment-required test order, not a card payment.')
        else:
            if payment == 'no_payment_required' or (intent is not None and
                    (not isinstance(intent, str) or not re.fullmatch(r'pi_[A-Za-z0-9_]+', intent))):
                raise OwnerCheckoutError('Unsupported Stripe test payment reference.')
            if payment == 'paid' and (status != 'complete' or intent is None):
                raise OwnerCheckoutError('Stripe test payment completion was not confirmed.')
            if order['payment_ref'] is not None and intent != order['payment_ref']:
                raise OwnerCheckoutError('Stripe test payment reference changed.')

    def _accept(self, order, result, *, creating):
        try:
            self._validate(result, order)
            url = None
            if creating and result['status'] == 'open':
                url = result.get('url')
                if (not isinstance(url, str) or len(url) > 4096 or
                        any(ord(c) <= 32 or ord(c) == 127 or c == '\\' for c in url)):
                    raise OwnerCheckoutError('Stripe returned an unsupported checkout destination.')
                parsed = urlsplit(url)
                if (parsed.scheme != 'https' or parsed.netloc != 'checkout.stripe.com' or
                        parsed.path not in ('/c/pay/' + result['id'], '/pay/' + result['id'])):
                    raise OwnerCheckoutError('Stripe returned an unsupported checkout destination.')
            self._claim('checkout', result['id'], order)
            intent = result.get('payment_intent')
            if intent:
                self._claim('payment', intent, order)
            order['checkout_id'] = result['id']
            if intent:
                order['payment_ref'] = intent
            order['state'] = 'expired' if result['status'] == 'expired' else 'pending'
            if result['status'] == 'complete':
                if order['coupon']:
                    order['state'] = 'complimentary_test'
                elif result['payment_status'] == 'paid':
                    order['state'] = 'paid_test'
            if url:
                order['url'] = url
            if order['state'] in ENTITLED or order['state'] == 'expired':
                order.pop('url', None)
        except (OwnerCheckoutError, ValueError, TypeError):
            order['state'] = 'blocked'
            order.pop('url', None)
            raise OwnerCheckoutError('Stripe checkout validation failed. Access remains locked; operator review is required.') from None

    def clear(self, owner_id):
        owner_id = _owner(owner_id)
        with self._lock:
            if owner_id in self._orders:
                del self._orders[owner_id]
                self._revoked.add(owner_id)
            # Keep bounded opaque replay claims until process exit.
            return self.state(owner_id)
