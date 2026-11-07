"""Separate sandbox routes: demo checkout cannot unlock a Stripe test report."""
import time
from stripe_checkout import StripeCheckout, StripeError
from providers import FixtureDiscovery

class StripeRoutes:
    def stripe_webhook(self, store):
        try:
            if self.headers.get('Transfer-Encoding'):
                raise ValueError()
            n = int(self.headers.get('Content-Length', '0'))
            if not 0 < n <= 65536:
                raise ValueError()
            raw = self.rfile.read(n)
            if len(raw) != n:
                raise ValueError()
            result = StripeCheckout(store).webhook(raw, self.headers.get('Stripe-Signature', ''))
            return self.reply(200, result)
        except (ValueError, TypeError):
            return self.reply(400, {'error': 'Stripe test webhook rejected.'})

    def stripe_get(self, store):
        s = self.session()
        if not s or not s['verified'] or s['verified_until'] <= time.time():
            return self.reply(403, {'error': 'Current synthetic verification required.'})
        if not store.allow('session:' + self.sid, 60):
            return self.reply(429, {'error': 'Too many requests.'})
        try:
            gateway = StripeCheckout(store)
            status = gateway.status(self.sid)
            if self.path == '/api/stripe/status':
                return self.reply(200, status)
            if status['state'] != 'paid':
                return self.reply(403, {'error': 'Server-verified Stripe sandbox payment required.'})
            return self.reply(200, {'demo': True, 'test_mode': True, 'report_id': s['report_id'],
                                    'providers': FixtureDiscovery().discover(), 'live_sources_checked': 0})
        except StripeError as e:
            return self.reply(503, {'error': str(e)})

    def stripe_post(self, store, session, data):
        try:
            gateway = StripeCheckout(store)
            if self.path == '/api/stripe/checkout':
                if data.get('accept_test') is not True:
                    raise StripeError('Confirm sandbox-only Checkout. Never enter real payment details.')
                if set(data) != {'accept_test'}:
                    raise StripeError('Checkout price and order are server-controlled; no extra fields accepted.')
                result = gateway.create(self.sid, session)
            elif self.path == '/api/stripe/reconcile':
                result = gateway.reconcile(self.sid)
            else:
                return self.reply(404, {'error': 'Endpoint not found.'})
            return self.reply(200, result)
        except StripeError as e:
            # Commit any pending order reservation even if the remote result is uncertain.
            return self.reply(400, {'error': str(e)})
