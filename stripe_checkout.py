"""Opt-in Stripe sandbox Checkout. No live keys, browser payment flags or PII."""
import hashlib
import hmac
import json
import os
import re
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import URLError
from pricing import LOOKUP_PRICE_CENTS

API_VERSION = '2026-10-28.endive'
ORDER_TTL = 23 * 3600  # Never retry creation after Stripe's 24h idempotency window.

class StripeError(ValueError):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def settings():
    if os.environ.get('SCANPLUS_MODE', 'demo') != 'demo' or os.environ.get('SCANPLUS_STRIPE_TEST') != '1':
        raise StripeError('Stripe sandbox is disabled. No live checkout is supported.')
    key = os.environ.get('STRIPE_SECRET_KEY', '')
    secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    origin = os.environ.get('SCANPLUS_STRIPE_ORIGIN', '')
    try:
        url = urlsplit(origin)
    except ValueError:
        raise StripeError('Invalid Stripe return origin.') from None
    if not key.startswith('sk_test_') or not secret.startswith('whsec_'):
        raise StripeError('Stripe test credentials are not configured.')
    if (url.username or url.password or url.query or url.fragment or url.path or
        not url.hostname or (url.scheme != 'https' and not
        (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1')))):
        raise StripeError('Configure a trusted Stripe return origin without a path.')
    return key, secret, origin


def request(method, path, key, fields=None, idempotency_key=None):
    """Fixed HTTPS destination, bounded response, no redirect or secret/error logging."""
    if not key.startswith('sk_test_') or not re.fullmatch(r'/v1/checkout/sessions(?:/cs_test_[A-Za-z0-9_]+)?', path):
        raise StripeError('Unsupported Stripe test request.')
    headers = {'Authorization': 'Bearer ' + key, 'Stripe-Version': API_VERSION}
    if idempotency_key:
        headers['Idempotency-Key'] = idempotency_key
    raw = None if fields is None else urlencode(fields).encode()
    if raw is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    try:
        with build_opener(NoRedirect()).open(Request('https://api.stripe.com' + path, data=raw,
                                                    headers=headers, method=method), timeout=8) as response:
            body = response.read(262145)
        if len(body) > 262144:
            raise ValueError()
        result = json.loads(body)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (URLError, OSError, ValueError):
        raise StripeError('Stripe is unavailable. Retry the same checkout; payment is not confirmed.') from None


def verify_event(raw, signature, secret, now=None):
    if len(raw) > 65536 or len(signature) > 2048:
        raise StripeError('Invalid webhook.')
    parts = [part.split('=', 1) for part in signature.split(',')]
    stamps = [v for pair in parts if len(pair) == 2 for k, v in [pair] if k == 't']
    signatures = [v for pair in parts if len(pair) == 2 for k, v in [pair] if k == 'v1']
    try:
        if len(stamps) != 1 or not re.fullmatch(r'[0-9]{1,12}', stamps[0]):
            raise ValueError()
        if abs((time.time() if now is None else now) - int(stamps[0])) > 300:
            raise ValueError()
        expected = hmac.new(secret.encode(), stamps[0].encode() + b'.' + raw, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, sig) for sig in signatures):
            raise ValueError()
        event = json.loads(raw)
        if not isinstance(event, dict) or event.get('livemode') is not False or not re.fullmatch(r'evt_[A-Za-z0-9_]+', event.get('id', '')):
            raise ValueError()
        return event
    except (ValueError, TypeError, UnicodeError):
        raise StripeError('Invalid webhook.') from None


class StripeCheckout:
    """Call inside Store.transaction(). Persist only order/Checkout IDs, not payment details."""
    def __init__(self, store, transport=None):
        self.store = store
        self.transport = request if transport is None else transport
        self.key, self.secret, self.origin = settings()

    def order(self, sid):
        return self.store.get('stripe_order', sid, sid)

    def save(self, order):
        self.store.put('stripe_order', order['owner'], order['owner'], order['expires'], order)

    def create(self, sid, session):
        if not session.get('verified') or session.get('verified_until', 0) <= time.time():
            raise StripeError('Current synthetic ownership verification required.')
        order = self.order(sid)
        if order is None:
            # Deterministic per-session idempotency, also safe if local transaction rolls back.
            order_id = hashlib.sha256(('stripe-test:' + sid + ':' + session['report_id']).encode()).hexdigest()
            order = {'id': order_id, 'owner': sid, 'created': time.time(),
                     'expires': min(session['expires'], time.time() + ORDER_TTL),
                     'origin': self.origin, 'state': 'pending', 'checkout_id': None}
            self.save(order)
        if time.time() - order['created'] >= ORDER_TTL or order['origin'] != self.origin:
            raise StripeError('Checkout configuration changed or expired. Start a new synthetic session.')
        if order['state'] == 'expired':
            raise StripeError('Stripe test checkout expired. Start a new synthetic session after checking its outcome.')
        if order['state'] == 'paid':
            return {'state': 'paid', 'test_mode': True}
        if order.get('url'):
            return {'state': order['state'], 'checkout_url': order['url'], 'test_mode': True}
        fields = {'mode': 'payment', 'payment_method_types[0]': 'card',
                  'line_items[0][quantity]': '1',
                  'line_items[0][price_data][currency]': 'usd',
                  'line_items[0][price_data][unit_amount]': str(LOOKUP_PRICE_CENTS),
                  'line_items[0][price_data][product_data][name]': 'ScanPlus synthetic report - TEST ONLY',
                  'client_reference_id': order['id'], 'metadata[scanplus_order]': order['id'],
                  'success_url': order['origin'] + '/stripe-test#returned',
                  'cancel_url': order['origin'] + '/stripe-test#cancelled'}
        result = self.transport('POST', '/v1/checkout/sessions', self.key, fields, 'scanplus-' + order['id'])
        self.validate(result, order)
        try:
            if not isinstance(result.get('url'), str):
                raise ValueError()
            parsed = urlsplit(result['url'])
        except ValueError:
            raise StripeError('Stripe returned an unsupported checkout URL.') from None
        if parsed.scheme != 'https' or parsed.netloc != 'checkout.stripe.com' or parsed.username or parsed.password:
            raise StripeError('Stripe returned an unsupported checkout URL.')
        order['checkout_id'] = result['id']; order['url'] = result['url']; self.save(order)
        self.apply(result, order)
        return {'state': order['state'], 'checkout_url': order['url'], 'test_mode': True}

    def validate(self, result, order):
        if (not isinstance(result, dict) or result.get('object') != 'checkout.session' or
            not isinstance(result.get('id'), str) or
            not re.fullmatch(r'cs_test_[A-Za-z0-9_]+', result['id']) or
            result.get('livemode') is not False or result.get('mode') != 'payment' or
            type(result.get('amount_total')) is not int or result['amount_total'] != LOOKUP_PRICE_CENTS or
            result.get('currency') != 'usd' or result.get('client_reference_id') != order['id'] or
            not isinstance(result.get('metadata'), dict) or result['metadata'].get('scanplus_order') != order['id'] or
            (order.get('checkout_id') and result['id'] != order['checkout_id'])):
            raise StripeError('Stripe order validation failed. Access remains locked.')

    def apply(self, result, order):
        self.validate(result, order)
        if result.get('status') == 'complete' and result.get('payment_status') == 'paid':
            intent = result.get('payment_intent')
            if not isinstance(intent, str) or not re.fullmatch(r'pi_[A-Za-z0-9_]+', intent):
                raise StripeError('Stripe payment reference is missing.')
            if not self.store.claim('stripe_payment', intent, order['id'], order['expires']):
                raise StripeError('Stripe payment was already assigned to another order.')
            order['state'] = 'paid'
        elif order['state'] != 'paid' and result.get('status') == 'expired':
            order['state'] = 'expired'
        self.save(order)

    def reconcile(self, sid):
        order = self.order(sid)
        if order and order.get('checkout_id') and order['state'] != 'paid':
            result = self.transport('GET', '/v1/checkout/sessions/' + order['checkout_id'], self.key)
            self.apply(result, order)
        return self.status(sid)

    def status(self, sid):
        order = self.order(sid)
        return {'state': order['state'] if order else 'not_started', 'test_mode': True,
                'amount_cents': LOOKUP_PRICE_CENTS, 'currency': 'USD', 'charged_cents': 0}

    def webhook(self, raw, signature):
        event = verify_event(raw, signature, self.secret)
        if event.get('type') not in ('checkout.session.completed', 'checkout.session.async_payment_succeeded', 'checkout.session.expired'):
            return {'received': True}
        obj = event.get('data', {}).get('object') if isinstance(event.get('data'), dict) else None
        if not isinstance(obj, dict):
            raise StripeError('Invalid webhook object.')
        order_id = obj.get('metadata', {}).get('scanplus_order') if isinstance(obj.get('metadata'), dict) else None
        # Only our existing orders can fulfill. Expired/cleared sessions never regain access.
        rows = self.store.conn.execute("SELECT id FROM records WHERE kind='stripe_order'").fetchall()
        order = next((o for row in rows if (o := self.order(row[0])) and o['id'] == order_id), None)
        if not order:
            return {'received': True}
        self.validate(obj, order)
        if self.store.get('stripe_event', event['id'], order['id']):
            return {'received': True}
        if not order.get('checkout_id'):
            # Creation may have timed out before saving the response. Bind the signed ID.
            order['checkout_id'] = obj['id']
        self.apply(obj, order)
        self.store.put('stripe_event', event['id'], order['id'], order['expires'], {'processed': True})
        return {'received': True}
