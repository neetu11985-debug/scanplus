"""Offline and loopback-only checks. Configured codes below are test fixtures, not offers."""
import copy
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from payments import DemoGateway, GoDaddyGateway
from pricing import LookupPricing
import server
import test_server


class Pricing(unittest.TestCase):
    def test_default_is_149_cent_one_time_usd_without_coupon(self):
        result = LookupPricing().quote()
        self.assertEqual(result, dict(list_price_cents=149, discount_cents=0, amount_cents=149,
                                     currency='USD', billing='one_time', coupon_code=None))
        self.assertEqual(LookupPricing().quote('  '), result)
        with self.assertRaises(ValueError):
            LookupPricing().quote('NOT-AN-OFFER')

    def test_configured_discounts_are_normalized_and_bounded(self):
        pricing = LookupPricing({'FIXTURE-ZERO': 0, 'fixture-part': 25, 'FIXTURE-FULL': 149})
        for code, amount in [('fixture-zero', 149), (' fixture-part ', 124), ('FIXTURE-FULL', 0)]:
            with self.subTest(code=code):
                quote = pricing.quote(code)
                self.assertEqual(quote['amount_cents'], amount)
                self.assertEqual(quote['discount_cents'] + amount, 149)
                self.assertEqual(quote['coupon_code'], code.strip().upper())

    def test_invalid_configuration_fails_closed(self):
        bad = [[], '', {'': 1}, {'INVALID CODE': 1}, {'A': -1}, {'A': 150},
               {'A': True}, {'A': 1.5}, {'A': '25'}, {'A': None}, {'A': 1, ' a ': 2}]
        for config in bad:
            with self.subTest(config=config), self.assertRaises(ValueError):
                LookupPricing(config)

    def test_invalid_user_codes_are_rejected(self):
        for code in [None, True, 1, [], {}, 'x' * 33, ' ' * 65, '<script>', 'A B', 'ß', 'A/B']:
            with self.subTest(code=code), self.assertRaises(ValueError):
                LookupPricing().quote(code)

    def test_configuration_and_return_values_are_defensive_copies(self):
        source = {'FIXTURE': 20}
        pricing = LookupPricing(source)
        source['FIXTURE'] = 149
        quote = pricing.quote('FIXTURE')
        quote['amount_cents'] = -100
        self.assertEqual(pricing.quote('FIXTURE')['amount_cents'], 129)
        with self.assertRaises(TypeError):
            pricing._coupons['FIXTURE'] = 149

    def test_quote_does_not_checkout_or_mutate_session(self):
        session = {'verified': True, 'paid': False}
        before = copy.deepcopy(session)
        quote = DemoGateway().quote(session)
        self.assertEqual(session, before)
        self.assertFalse(quote['locked'])
        self.assertEqual(quote['charged_cents'], 0)
        for operation in (DemoGateway().quote, DemoGateway().checkout):
            with self.assertRaises(ValueError):
                operation({'verified': False})

    def test_invalid_checkout_leaves_no_receipt(self):
        session = {'verified': True, 'paid': False}
        with self.assertRaises(ValueError):
            DemoGateway().checkout(session, 'UNAVAILABLE')
        self.assertEqual(session, {'verified': True, 'paid': False})

    def test_checkout_is_immutable_even_after_coupon_or_configuration_changes(self):
        session = {'verified': True}
        gateway = DemoGateway(LookupPricing({'FIXTURE': 25}))
        original = gateway.checkout(session, 'fixture')
        self.assertEqual(original['amount_cents'], 124)
        self.assertEqual(original['charged_cents'], 0)
        gateway = DemoGateway()  # The original coupon no longer exists.
        for code in ('', 'UNAVAILABLE', None, {}):
            self.assertEqual(gateway.checkout(session, code), original)
        returned = gateway.checkout(session)
        returned['amount_cents'] = 1000
        self.assertEqual(session['receipt'], original)
        self.assertEqual(gateway.quote(session)['amount_cents'], 124)
        self.assertTrue(gateway.quote(session)['locked'])
        self.assertTrue(session['paid'])

    def test_prior_100_cent_receipt_is_not_repriced_or_rewritten(self):
        original = dict(amount_cents=100, currency='USD', charged_cents=0, mode='test',
                        payment_id='prior-synthetic-receipt', created_at=time.time())
        session = {'verified': True, 'paid': True, 'receipt': original.copy()}
        gateway = DemoGateway()
        quote = gateway.quote(session)
        self.assertEqual(quote['amount_cents'], 100)
        self.assertEqual(quote['list_price_cents'], 100)
        self.assertTrue(quote['locked'])
        self.assertEqual(gateway.checkout(session, 'UNAVAILABLE'), original)
        self.assertEqual(session['receipt'], original)

    def test_prior_99_cent_receipt_remains_immutable(self):
        original = dict(list_price_cents=99, discount_cents=0, amount_cents=99,
                        currency='USD', charged_cents=0, mode='test',
                        payment_id='prior-99-cent-receipt', created_at=time.time())
        session = {'verified': True, 'paid': True, 'receipt': original.copy()}
        gateway = DemoGateway()
        self.assertEqual(gateway.quote(session)['amount_cents'], 99)
        self.assertEqual(gateway.checkout(session), original)
        self.assertEqual(session['receipt'], original)

    def test_real_payment_stays_disabled(self):
        with self.assertRaisesRegex(ValueError, 'Production checkout is disabled'):
            GoDaddyGateway().checkout({'verified': True}, '')


class PricingHTTP(unittest.TestCase):
    # Reuse the loopback fixture transport, not Journey's unrelated test methods.
    setUpClass = classmethod(test_server.Journey.setUpClass.__func__)
    tearDownClass = classmethod(test_server.Journey.tearDownClass.__func__)
    req = test_server.Journey.req
    start = test_server.Journey.start

    def setUp(self):
        test_server.Journey.setUp(self)
        configured = patch.object(server, 'PRICING', LookupPricing())
        configured.start()
        self.addCleanup(configured.stop)

    def verify(self):
        self.assertEqual(self.start()[0], 200)
        self.assertEqual(self.req('verify', {'code': '246810'})[0], 200)

    def test_quote_requires_current_verification_origin_and_csrf(self):
        self.assertEqual(self.req('quote', {})[0], 401)
        self.start()
        self.assertEqual(self.req('quote', {})[0], 403)
        self.req('verify', {'code': '246810'})
        self.assertEqual(self.req('quote', {}, origin=False)[0], 403)
        token = self.csrf
        self.csrf = 'wrong'
        self.assertEqual(self.req('quote', {})[0], 403)
        self.csrf = token
        self.assertEqual(self.req('quote', {})[0], 200)
        with server.STORE.transaction():
            server.STORE.conn.execute("UPDATE records SET expires=0 WHERE kind='session'")
        self.assertEqual(self.req('quote', {})[0], 401)

    def test_quote_does_not_unlock_report_or_create_payment(self):
        self.verify()
        status, quote = self.req('quote', {'amount_cents': 0, 'discount_cents': 149, 'currency': 'EUR'})
        self.assertEqual(status, 200)
        self.assertEqual((quote['amount_cents'], quote['discount_cents'], quote['currency']), (149, 0, 'USD'))
        self.assertEqual(self.req('report')[0], 403)
        self.assertEqual(self.req('history')[1]['payments'], [])
        self.assertFalse(self.req('session')[1]['paid'])
        self.assertEqual(self.req('quote')[0], 404)  # No GET/query-string coupon path.

    def test_invalid_codes_cannot_checkout_and_empty_code_is_optional(self):
        self.verify()
        for code in ('UNAVAILABLE', None, True, [], {}):
            with self.subTest(code=code):
                self.assertEqual(self.req('quote', {'coupon_code': code})[0], 400)
                self.assertEqual(self.req('checkout', {'accept': True, 'coupon_code': code})[0], 400)
        self.assertEqual(self.req('history')[1]['payments'], [])
        self.assertEqual(self.req('checkout', {'accept': False})[0], 400)
        status, receipt = self.req('checkout', {'accept': True, 'coupon_code': '', 'amount_cents': -1,
                                              'discount_cents': 149, 'currency': 'EUR'})
        self.assertEqual(status, 200)
        self.assertEqual((receipt['amount_cents'], receipt['charged_cents'], receipt['currency']), (149, 0, 'USD'))

    def test_coupon_quote_checkout_and_duplicate_keep_exact_receipt(self):
        self.verify()
        server.PRICING = LookupPricing({'FIXTURE': 24})
        quote = self.req('quote', {'coupon_code': ' fixture '})[1]
        self.assertEqual((quote['amount_cents'], quote['discount_cents']), (125, 24))
        status, first = self.req('checkout', {'accept': True, 'coupon_code': 'fixture', 'amount_cents': 0})
        self.assertEqual(status, 200)
        self.assertEqual(first['amount_cents'], quote['amount_cents'])
        self.assertEqual(first['charged_cents'], 0)
        server.PRICING = LookupPricing()
        self.assertEqual(self.req('checkout', {'accept': True, 'coupon_code': 'REMOVED'})[1], first)
        self.assertEqual(self.req('checkout', {'accept': True})[1], first)
        locked = self.req('quote', {'coupon_code': 'REMOVED'})[1]
        self.assertTrue(locked['locked'])
        self.assertEqual(locked['amount_cents'], 125)
        self.assertEqual(len(self.req('history')[1]['payments']), 1)

    def test_checkout_revalidates_a_revoked_quote(self):
        self.verify()
        server.PRICING = LookupPricing({'FIXTURE': 149})
        self.assertEqual(self.req('quote', {'coupon_code': 'FIXTURE'})[1]['amount_cents'], 0)
        server.PRICING = LookupPricing()
        self.assertEqual(self.req('checkout', {'accept': True, 'coupon_code': 'FIXTURE'})[0], 400)
        self.assertEqual(self.req('history')[1]['payments'], [])
        self.assertEqual(self.req('checkout', {'accept': True})[1]['amount_cents'], 149)

    def test_concurrent_checkouts_issue_one_receipt(self):
        self.verify()
        results = []
        threads = [threading.Thread(target=lambda: results.append(self.req('checkout', {'accept': True})))
                   for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(results), 4)
        self.assertTrue(all(status == 200 for status, _ in results))
        self.assertTrue(all(receipt == results[0][1] for _, receipt in results))
        self.assertEqual(len(self.req('history')[1]['payments']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
