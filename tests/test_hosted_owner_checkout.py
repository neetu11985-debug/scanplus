"""Combined private journey with synthetic Twilio, Stripe and Serper only."""
import copy
import time
import unittest
from unittest.mock import patch
import test_hosted_self_test as hosted_fixture

from hosted_owner_checkout import checkout_configuration, OwnerCheckoutApplication
from test_hosted_self_test import (MemoryAllowance, environment,
                                   HOST, PHONE, FakeTransport, organic, verification)


def checkout_environment(coupon=False):
    env = dict(environment(), SCANPLUS_OWNER_CHECKOUT_TEST='1',
               STRIPE_SECRET_KEY='sk_test_SYNTHETIC_OWNER_ONLY')
    if coupon:
        env.update(SCANPLUS_OWNER_TEST_COUPON_ID='fixture_coupon', SCANPLUS_OWNER_TEST_COUPON_CODE='OWNER100')
    return env


class SyntheticCheckout:
    def __init__(self):
        self.calls = []
        self.completed = False
        self.result = None
        self.after_request = lambda: None

    def __call__(self, method, path, key, fields=None, idempotency_key=None):
        self.calls.append((method, path, fields, idempotency_key))
        if method == 'POST':
            coupon = fields.get('discounts[0][coupon]')
            self.result = {'object': 'checkout.session', 'id': 'cs_test_owner_fixture', 'livemode': False,
                           'mode': 'payment', 'currency': 'usd',
                           'client_reference_id': fields['client_reference_id'],
                           'metadata': {'scanplus_owner_test_order': fields['metadata[scanplus_owner_test_order]']},
                           'amount_subtotal': 149, 'amount_total': 0 if coupon else 149,
                           'total_details': {'amount_discount': 149 if coupon else 0, 'amount_tax': 0, 'amount_shipping': 0},
                           'discounts': [{'coupon': coupon, 'promotion_code': None}] if coupon else [],
                           'status': 'open', 'payment_status': 'unpaid', 'payment_intent': None,
                           'url': 'https://checkout.stripe.com/c/pay/cs_test_owner_fixture'}
        elif method != 'GET' or path != '/v1/checkout/sessions/cs_test_owner_fixture':
            raise AssertionError('Unexpected synthetic Stripe operation')
        result = copy.deepcopy(self.result)
        if self.completed:
            result.update(status='complete', payment_status='paid' if result['amount_total'] else 'no_payment_required',
                          payment_intent='pi_fixture_owner' if result['amount_total'] else None, url=None)
        self.after_request()
        return result


class OwnerCheckoutConfigurationTests(unittest.TestCase):
    def test_disabled_and_conflicting_modes_fail_without_provider_access(self):
        for changes in ({'SCANPLUS_OWNER_CHECKOUT_TEST': '0'}, {'STRIPE_SECRET_KEY': 'sk_live_NO'},
                        {'STRIPE_SECRET_KEY': ''}, {'SCANPLUS_STRIPE_TEST': '1'},
                        {'SCANPLUS_ENCRYPTED_REPORTS': '1'}, {'SCANPLUS_OWNER_TEST_COUPON_ID': 'fixture'}):
            with self.subTest(change=list(changes)), self.assertRaises(RuntimeError):
                checkout_configuration(dict(checkout_environment(), **changes))
        self.assertNotIn('SYNTHETIC', repr(checkout_configuration(checkout_environment())))

    def test_existing_entrypoints_do_not_enable_combined_mode(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        for name in ('render_wsgi.py', 'owner_live_wsgi.py', 'deployment/render-start.sh', 'deployment/owner-live-start.sh'):
            self.assertNotIn('owner_checkout_wsgi', (root / name).read_text())
        self.assertIn('owner_checkout_wsgi:application', (root / 'deployment/owner-checkout-start.sh').read_text())

    def test_release_revision_is_only_a_valid_commit_identifier(self):
        for value in ('private-value', 'a' * 40 + '\n', None):
            self.assertEqual(checkout_configuration(dict(checkout_environment(), RENDER_GIT_COMMIT=value)).owner.revision, '')
        config = checkout_configuration(dict(checkout_environment(), RENDER_GIT_COMMIT='a' * 40))
        app = OwnerCheckoutApplication(config, FakeTransport(), allowance=MemoryAllowance(),
                                       checkout_transport=SyntheticCheckout(), start_cleanup=False)
        self.addCleanup(app.close)
        captured = {}
        response = app({'wsgi.url_scheme': 'https', 'HTTP_HOST': HOST},
                       lambda status, headers: captured.update(status=status, headers=dict(headers)))
        self.assertTrue(captured['status'].startswith('401'))
        self.assertEqual(captured['headers']['X-ScanPlus-Release'], 'a' * 40)
        self.assertNotIn(b'sk_test_', b''.join(response))


class OwnerCheckoutJourneyTests(unittest.TestCase):
    call = hosted_fixture.HostedJourneyTests.call
    start = hosted_fixture.HostedJourneyTests.start
    verified = hosted_fixture.HostedJourneyTests.verified

    def setUp(self):
        self.transport = FakeTransport()
        self.stripe = SyntheticCheckout()
        self.app = OwnerCheckoutApplication(checkout_configuration(checkout_environment()),
                                            self.transport, allowance=MemoryAllowance(),
                                            checkout_transport=self.stripe, start_cleanup=False)
        self.addCleanup(self.app.close)
        self.cookie = self.csrf = ''

    def scan_object(self):
        return next(iter(self.app.state.sessions.values()))['scan']

    def paid(self):
        response = self.call('/api/checkout/create', {'accept_test': True})
        self.assertEqual(response['status'], 200, response['body'])
        self.stripe.completed = True
        result = self.call('/api/checkout/reconcile', {})
        self.assertEqual(result['status'], 200, result['body'])
        self.assertEqual(result['body']['phase'], 'verified')

    def test_complete_card_test_then_independent_search_consent_and_download(self):
        self.verified(*[(200, organic(site)) for site in ('spokeo.com', 'truepeoplesearch.com', 'whitepages.com')])
        state = self.call('/api/session')['body']
        self.assertEqual(state['phase'], 'checkout')
        self.assertTrue(self.cookie.startswith('scanplus_owner_checkout_sid='))
        self.assertEqual(self.call('/api/scan', {'serper_consent': True})['status'], 409)
        self.assertEqual(len(self.transport.calls), 2)
        self.assertEqual(self.call('/api/checkout/create', {'accept_test': False})['status'], 409)
        self.assertEqual(self.stripe.calls, [])
        self.paid()
        self.assertEqual(self.call('/api/scan', {})['status'], 409)
        result = self.call('/api/scan', {'serper_consent': True})
        self.assertEqual(result['status'], 200, result['body'])
        self.assertEqual(result['body']['report']['sources_checked'], 3)
        self.assertIn('No real payment', result['body']['report']['payment_notice'])
        self.assertTrue(self.call('/api/export.pdf')['raw'].startswith(b'%PDF-'))
        self.assertEqual(self.call('/api/scan', {'serper_consent': True})['status'], 200)
        self.assertEqual(len(self.transport.calls), 5)
        payload = repr(self.stripe.calls)
        for value in (PHONE, '123456', 'SYNTHETIC_OWNER_ONLY', 'cs_test_owner_fixture'):
            # The known checkout ID is expected only in the explicit GET target.
            if value != 'cs_test_owner_fixture':
                self.assertNotIn(value, payload)
        self.assertNotIn('phone', repr(self.stripe.calls[0][2]).lower())

    def test_coupon_is_distinct_no_payment_entitlement(self):
        self.app.close()
        self.app = OwnerCheckoutApplication(checkout_configuration(checkout_environment(True)),
                                            self.transport, allowance=MemoryAllowance(),
                                            checkout_transport=self.stripe, start_cleanup=False)
        self.addCleanup(self.app.close)
        self.verified()
        self.assertEqual(self.call('/api/checkout/create', {'accept_test': True, 'coupon_code': 'WRONG'})['status'], 409)
        self.assertEqual(self.stripe.calls, [])
        result = self.call('/api/checkout/create', {'accept_test': True, 'coupon_code': 'OWNER100'})
        self.assertEqual(result['status'], 200)
        self.assertEqual(result['body']['checkout_test']['amount_cents'], 0)
        resumed = self.call('/api/checkout/create', {'accept_test': True})
        self.assertEqual(resumed['status'], 200)
        self.assertEqual(resumed['body']['checkout_test']['amount_cents'], 0)
        self.assertEqual(len(self.stripe.calls), 1, 'Resume must not create another checkout')
        self.stripe.completed = True
        state = self.call('/api/checkout/reconcile', {})['body']
        self.assertEqual(state['checkout_test']['state'], 'complimentary_test')
        self.assertTrue(state['checkout_test']['authorized'])
        self.assertEqual(state['phase'], 'verified')

    def test_no_verification_no_payment_or_search_and_no_public_webhook(self):
        self.call('/api/session')
        for route in ('create', 'reconcile'):
            self.assertEqual(self.call('/api/checkout/' + route, {'accept_test': True} if route == 'create' else {})['status'], 409)
        self.assertEqual(self.call('/api/scan', {'serper_consent': True})['status'], 409)
        self.assertEqual(self.call('/api/stripe/webhook', {})['status'], 404)
        self.assertEqual(self.stripe.calls, [])
        self.assertEqual(self.transport.calls, [])

    def test_pending_double_create_and_return_hash_never_unlock_search(self):
        self.verified()
        for _ in range(2):
            self.assertEqual(self.call('/api/checkout/create', {'accept_test': True})['status'], 200)
        self.assertEqual(len(self.stripe.calls), 1)
        self.assertEqual(self.call('/api/session')['body']['phase'], 'checkout')
        self.assertEqual(self.call('/api/checkout/reconcile', {})['body']['phase'], 'checkout')
        self.assertEqual(self.call('/api/scan', {'serper_consent': True})['status'], 409)
        self.assertEqual(len(self.transport.calls), 2)

    def test_cross_session_and_client_override_rejected(self):
        self.verified()
        for data in ({'accept_test': True, 'owner': 'override'}, {'accept_test': True, 'amount_cents': 0}):
            self.assertEqual(self.call('/api/checkout/create', data)['status'], 409)
        self.paid()
        first_cookie = self.cookie
        self.cookie = self.csrf = ''
        self.call('/api/session')
        self.assertNotEqual(first_cookie, self.cookie)
        self.assertEqual(self.call('/api/scan', {'serper_consent': True})['status'], 409)
        self.assertEqual(self.call('/api/checkout/reconcile', {})['status'], 409)
        self.assertFalse(self.call('/api/session')['body']['checkout_test']['authorized'])

    def test_api_security_and_late_completion_after_clear(self):
        self.verified()
        for change in ({'HTTP_X_CSRF_TOKEN': ''}, {'HTTP_X_CSRF_TOKEN': '\u2603'},
                       {'HTTP_ORIGIN': 'https://evil.example'}, {'HTTP_AUTHORIZATION': ''}):
            self.assertIn(self.call('/api/checkout/create', {'accept_test': True}, overrides=change)['status'], (401, 403))
        self.assertEqual(self.call('/api/checkout/create', raw=b'[]')['status'], 400)
        self.assertEqual(self.stripe.calls, [])
        self.paid()
        self.call('/api/clear', {})
        self.assertFalse(self.call('/api/session')['body']['checkout_test']['authorized'])
        count = len(self.stripe.calls)
        self.assertEqual(self.call('/api/checkout/reconcile', {})['status'], 409)
        self.assertEqual(self.call('/api/scan', {'serper_consent': True})['status'], 409)
        self.assertEqual(len(self.stripe.calls), count)

    def test_expiry_before_and_during_provider_response_revokes_redirect(self):
        self.verified()
        scan = self.scan_object()
        self.stripe.after_request = lambda: setattr(scan, 'expires', time.monotonic() - 1)
        result = self.call('/api/checkout/create', {'accept_test': True})
        self.assertEqual(result['status'], 409)
        self.assertNotIn('checkout_url', result['body'])
        self.assertEqual(result['body']['state']['phase'], 'entry')
        self.assertFalse(result['body']['state']['checkout_test']['authorized'])
        self.assertEqual(self.call('/api/checkout/create', {'accept_test': True})['status'], 409)
        self.assertEqual(len(self.stripe.calls), 1)

    def test_config_and_page_do_not_make_provider_requests(self):
        for path in ('/', '/live.js', '/live.css', '/api/session'):
            self.assertEqual(self.call(path)['status'], 200)
        self.assertIn(b'NO REAL CHARGE', self.call('/')['raw'])
        self.assertEqual(self.stripe.calls, [])
        self.assertEqual(self.transport.calls, [])

    def test_cross_site_return_can_only_read_authenticated_shell(self):
        changes = {'HTTP_SEC_FETCH_SITE': 'cross-site', 'HTTP_SEC_FETCH_MODE': 'navigate',
                   'HTTP_SEC_FETCH_DEST': 'document', 'HTTP_ORIGIN': None, 'HTTP_COOKIE': ''}
        self.assertEqual(self.call('/', overrides=changes)['status'], 200)
        self.assertEqual(self.app.state.sessions, {}, 'Shell must not create or fulfill a session')
        self.assertEqual(self.call('/', overrides=dict(changes, HTTP_AUTHORIZATION=''))['status'], 401)
        for path in ('/api/session', '/api/report', '/live.js'):
            self.assertEqual(self.call(path, overrides=changes)['status'], 403)
        self.assertEqual(self.call('/api/checkout/reconcile', {}, overrides=changes)['status'], 403)
        for override in ({'QUERY_STRING': 'paid=true'}, {'HTTP_SEC_FETCH_DEST': 'iframe'},
                         {'HTTP_SEC_FETCH_MODE': 'cors'}, {'HTTP_ORIGIN': 'https://checkout.stripe.com'}):
            self.assertEqual(self.call('/', overrides=dict(changes, **override))['status'], 403)
        self.assertEqual(self.stripe.calls, [])
        self.assertEqual(self.transport.calls, [])
