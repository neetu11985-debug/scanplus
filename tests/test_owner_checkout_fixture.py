"""Synthetic combined UI runner cannot redirect or dispatch to providers."""
import unittest
import test_hosted_fixture_server as fixture
from tool.owner_checkout_fixture_server import CheckoutFixtureApplication


class CheckoutFixtureTests(unittest.TestCase):
    call = fixture.HostedFixtureTests.call

    def setUp(self):
        self.app = CheckoutFixtureApplication(4177)
        self.addCleanup(self.app.close)
        self.cookie = self.csrf = ''

    def test_card_and_coupon_variants_use_only_local_mock_completion(self):
        for coupon in (False, True):
            with self.subTest(coupon=coupon):
                if coupon:
                    self.app.close()
                    self.app = CheckoutFixtureApplication(4177)
                    self.addCleanup(self.app.close)
                    self.cookie = self.csrf = ''
                self.assertIn(b'MOCK CHECKOUT ONLY', self.call('/')['raw'])
                self.call('/api/session')
                self.call('/api/start', {'phone': '+12025550147', 'own_number': True, 'twilio_consent': True})
                self.assertEqual(self.call('/api/verify', {'code': '123456'})['body']['phase'], 'checkout')
                data = dict(accept_test=True)
                if coupon:
                    data['coupon_code'] = 'OWNER100'
                result = self.call('/api/checkout/create', data)
                self.assertEqual(result['status'], 200)
                self.assertNotIn('checkout_url', result['body'])
                self.assertEqual(self.call('/api/scan', {'serper_consent': True})['status'], 409)
                self.assertEqual(self.call('/fixture/complete', {'confirm_mock': True})['status'], 200)
                state = self.call('/api/checkout/reconcile', {})['body']
                self.assertEqual(state['phase'], 'verified')
                self.assertEqual(state['checkout_test']['state'], 'complimentary_test' if coupon else 'paid_test')
                self.assertEqual(self.call('/api/scan', {'serper_consent': True})['body']['report']['sources_checked'], 3)

    def test_mock_controls_are_not_available_cross_site_or_without_session(self):
        self.assertEqual(self.call('/fixture/complete', {'confirm_mock': True})['status'], 400)
        self.assertEqual(self.call('/fixture/complete', {'confirm_mock': True}, HTTP_ORIGIN='https://evil.example')['status'], 403)
        self.assertEqual(self.call('/fixture-checkout.js', HTTP_HOST='evil.example')['status'], 403)
        self.assertEqual(self.call('/fixture-checkout.js')['status'], 200)
        self.assertEqual(self.app.stripe.calls, [])
        self.assertEqual(self.app.transport.searches, 0)
