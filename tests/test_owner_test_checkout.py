"""Offline owner-checkout contracts. All keys, owners and Stripe replies are fixtures."""
import copy
import json
import unittest
from unittest.mock import patch

from owner_test_checkout import OwnerCheckoutError, OwnerTestCheckout

KEY = 'sk_test_fixture_not_a_credential'
ORIGIN = 'https://fixture.onrender.com'
OWNER = 'a' * 64
OTHER = 'b' * 64
COUPON = 'coupon_fixture_owner_100'


class FakeStripe:
    def __init__(self):
        self.calls = []
        self.response = None
        self.fail = False
        self.mutate = None
        self.before_return = None
        self.serial = 0

    def __call__(self, method, path, key, fields=None, idempotency_key=None):
        self.calls.append((method, path, key, copy.deepcopy(fields), idempotency_key))
        if self.fail:
            raise RuntimeError('DO NOT ECHO RAW PROVIDER DATA')
        if method == 'POST':
            self.serial += 1
            sid = 'cs_test_fixture_' + str(self.serial)
            coupon = fields.get('discounts[0][coupon]')
            self.response = {'object': 'checkout.session', 'id': sid,
                             'livemode': False, 'mode': 'payment', 'currency': 'usd',
                             'amount_subtotal': 149, 'amount_total': 0 if coupon else 149,
                             'total_details': {'amount_discount': 149 if coupon else 0,
                                               'amount_tax': 0, 'amount_shipping': 0},
                             'discounts': [{'coupon': coupon, 'promotion_code': None}] if coupon else [],
                             'metadata': {'scanplus_owner_test_order': fields['metadata[scanplus_owner_test_order]']},
                             'client_reference_id': fields['client_reference_id'],
                             'payment_intent': None, 'status': 'open',
                             'payment_status': 'no_payment_required' if coupon else 'unpaid',
                             'url': 'https://checkout.stripe.com/c/pay/' + sid + '#fixture'}
        result = copy.deepcopy(self.response)
        if self.mutate:
            self.mutate(result)
        if self.before_return:
            self.before_return()
        return result

    def paid(self):
        self.response.update(status='complete', payment_status='paid', payment_intent='pi_fixture_' + str(self.serial))

    def complimentary(self):
        self.response.update(status='complete', payment_status='no_payment_required', payment_intent=None)


class OwnerCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.expiry = self.now + 300
        self.fake = FakeStripe()
        self.checkout = self.adapter()

    def adapter(self, **kwargs):
        return OwnerTestCheckout(KEY, ORIGIN, transport=self.fake, clock=lambda: self.now, **kwargs)

    def create(self, owner=OWNER, **kwargs):
        return self.checkout.create(owner, self.expiry, accept_test=True, **kwargs)

    def reconcile(self, owner=OWNER):
        return self.checkout.reconcile(owner, self.expiry)

    def test_construction_state_and_clear_make_no_provider_call(self):
        with patch('owner_test_checkout.request', side_effect=AssertionError('unexpected call')):
            adapter = OwnerTestCheckout(KEY, ORIGIN)
            self.assertEqual(adapter.state(OWNER)['state'], 'not_started')
            self.assertFalse(adapter.clear(OWNER)['authorized'])
        self.assertFalse(self.fake.calls)

    def test_keys_origins_and_coupon_configuration_fail_closed(self):
        for key in ('', 'sk_live_fixture_not_real', 'rk_live_fixture_not_real', 'pk_test_fixture_not_real', KEY + '\n', None, True):
            with self.subTest(key_type=type(key).__name__), self.assertRaises(OwnerCheckoutError):
                OwnerTestCheckout(key, ORIGIN)
        for origin in ('http://fixture.onrender.com', ORIGIN + '/', ORIGIN + '?key=x',
                       ORIGIN + '#x', 'https://user:pass@fixture.onrender.com', ORIGIN + ':443',
                       'https://[broken', None, 'https://fixture.onrender.com\n'):
            with self.subTest(origin=origin), self.assertRaises(OwnerCheckoutError):
                OwnerTestCheckout(KEY, origin)
        for config in ({'coupon_id': COUPON}, {'coupon_code': 'OWNER100'},
                       {'coupon_id': COUPON, 'coupon_code': 'bad code'},
                       {'coupon_id': '../bad', 'coupon_code': 'OWNER100'}):
            with self.subTest(config=config), self.assertRaises(OwnerCheckoutError):
                self.adapter(**config)

    def test_owner_consent_expiry_and_coupon_fail_before_call(self):
        for owner in ('+12025550147', 'owner', '', None, []):
            with self.subTest(owner=owner), self.assertRaises(OwnerCheckoutError):
                self.create(owner)
        for consent in (False, 1, 'true', None):
            with self.subTest(consent=consent), self.assertRaises(OwnerCheckoutError):
                self.checkout.create(OWNER, self.expiry, accept_test=consent)
        for expiry in (True, None, float('nan'), float('inf'), self.now, self.now - 1, self.now + 901):
            with self.subTest(expiry=expiry), self.assertRaises(OwnerCheckoutError):
                self.checkout.create(OWNER, expiry, accept_test=True)
        for code in ('OWNER100', 'bad code', [], True):
            with self.subTest(code=code), self.assertRaises(OwnerCheckoutError):
                self.create(coupon_code=code)
        self.assertFalse(self.fake.calls)

    def test_card_order_is_fixed_bound_opaque_and_idempotent(self):
        created = self.create()
        self.assertEqual(created, self.create())
        self.assertFalse(created['authorized'])
        self.assertEqual(len(self.fake.calls), 1)
        _, path, key, fields, idem = self.fake.calls[0]
        self.assertEqual(path, '/v1/checkout/sessions')
        self.assertEqual(key, KEY)
        self.assertEqual(fields['line_items[0][price_data][unit_amount]'], '149')
        self.assertEqual(fields['line_items[0][price_data][currency]'], 'usd')
        self.assertEqual(fields['mode'], 'payment')
        self.assertNotIn('payment_method_types[0]', fields)
        self.assertEqual(fields['allowed_payment_method_types[0]'], 'card')
        self.assertRegex(fields['integration_identifier'], r'^scanplus-owner-test-[a-z]{8}$')
        self.assertEqual(fields['client_reference_id'], fields['metadata[scanplus_owner_test_order]'])
        self.assertEqual(idem, 'scanplus-owner-test-' + fields['client_reference_id'])
        self.assertNotIn(OWNER, json.dumps(fields))
        self.assertFalse(any(name in fields for name in ('customer', 'customer_email', 'phone', 'payment_intent_data[setup_future_usage]', 'allow_promotion_codes')))
        self.assertTrue(created['checkout_url'].startswith('https://checkout.stripe.com/'))
        self.assertNotIn('checkout_url', self.checkout.state(OWNER))
        self.assertFalse(self.checkout.state(OTHER)['authorized'])

    def test_restricted_test_key_is_accepted_without_weakening_test_mode(self):
        restricted = 'rk_test_fixture_not_a_credential'
        self.checkout = OwnerTestCheckout(restricted, ORIGIN, transport=self.fake, clock=lambda: self.now)
        self.create(); self.fake.paid()
        self.assertTrue(self.reconcile()['authorized'])
        self.assertEqual(self.fake.calls[0][2], restricted)
        self.assertNotIn(restricted, json.dumps(self.checkout.state(OWNER)))

    def test_integration_identifier_is_stable_across_manual_retry(self):
        self.fake.fail = True
        with self.assertRaises(OwnerCheckoutError): self.create()
        first = copy.deepcopy(self.fake.calls[0])
        self.fake.fail = False
        with patch('owner_test_checkout.INTEGRATION_IDENTIFIER', 'scanplus-owner-test-abcdefgh'):
            self.create()
        self.assertEqual(first, self.fake.calls[1])

    def test_only_server_reconciliation_grants_card_entitlement(self):
        self.create()
        self.fake.paid()
        self.assertFalse(self.checkout.state(OWNER)['authorized'])
        self.assertEqual(self.reconcile()['state'], 'paid_test')
        self.assertTrue(self.reconcile()['authorized'])
        self.assertEqual(len(self.fake.calls), 2)
        state = self.checkout.state(OWNER)
        self.assertEqual(state['charged_cents'], 0)
        for secret in (KEY, OWNER, 'pi_fixture', 'cs_test_fixture'):
            self.assertNotIn(secret, json.dumps(state))

    def test_coupon_requires_configured_identity_and_distinct_zero_entitlement(self):
        self.checkout = self.adapter(coupon_id=COUPON, coupon_code='OWNER100')
        created = self.create(coupon_code='owner100')
        self.assertEqual(created['amount_cents'], 0)
        self.assertEqual(created['discount_cents'], 149)
        self.assertFalse(created['authorized'])
        self.assertEqual(self.fake.calls[0][3]['discounts[0][coupon]'], COUPON)
        self.assertNotIn('payment_method_collection', self.fake.calls[0][3])
        self.fake.complimentary()
        result = self.reconcile()
        self.assertEqual(result['state'], 'complimentary_test')
        self.assertTrue(result['authorized'])
        self.assertNotIn('payment_ref', result)
        self.assertNotIn(COUPON, json.dumps(result))
        self.assertNotIn('OWNER100', json.dumps(result))

    def test_unknown_coupon_and_changing_reserved_discount_never_send(self):
        self.checkout = self.adapter(coupon_id=COUPON, coupon_code='OWNER100')
        with self.assertRaises(OwnerCheckoutError): self.create(coupon_code='OTHER100')
        self.assertFalse(self.fake.calls)
        self.create(coupon_code='OWNER100')
        with self.assertRaises(OwnerCheckoutError): self.create()
        self.assertEqual(len(self.fake.calls), 1)

    def test_create_uncertainty_is_sanitized_manual_same_idempotency_and_bounded(self):
        self.fake.fail = True
        for _ in range(2):
            with self.assertRaises(OwnerCheckoutError) as error:
                self.create()
            self.assertNotIn('RAW PROVIDER', str(error.exception))
        self.assertEqual(self.checkout.state(OWNER)['state'], 'uncertain')
        with self.assertRaises(OwnerCheckoutError): self.create()
        self.assertEqual(len(self.fake.calls), 2)
        self.assertEqual(self.fake.calls[0][3:], self.fake.calls[1][3:])
        self.assertFalse(self.checkout.state(OWNER)['authorized'])

    def test_uncertain_create_can_be_manually_recovered_once(self):
        self.fake.fail = True
        with self.assertRaises(OwnerCheckoutError): self.create()
        self.fake.fail = False
        self.assertEqual(self.create()['state'], 'pending')
        self.assertEqual(self.fake.calls[0][4], self.fake.calls[1][4])
        self.fake.paid()
        self.assertTrue(self.reconcile()['authorized'])

    def test_reconcile_unknown_owner_or_unknown_checkout_never_calls(self):
        with self.assertRaises(OwnerCheckoutError): self.reconcile()
        self.fake.fail = True
        with self.assertRaises(OwnerCheckoutError): self.create()
        with self.assertRaises(OwnerCheckoutError): self.reconcile()
        self.assertEqual(len(self.fake.calls), 1)

    def test_reconcile_is_bounded_including_uncertain_requests(self):
        self.create()
        self.fake.fail = True
        for _ in range(5):
            with self.assertRaises(OwnerCheckoutError): self.reconcile()
        with self.assertRaises(OwnerCheckoutError): self.reconcile()
        self.assertEqual(len(self.fake.calls), 6)
        self.assertFalse(self.checkout.state(OWNER)['authorized'])

    def test_tampered_order_fields_block_without_authorization(self):
        cases = ({'id': 'cs_live_bad'}, {'id': 'cs_test_other'}, {'livemode': True},
                 {'object': 'payment_intent'}, {'mode': 'subscription'}, {'currency': 'eur'},
                 {'client_reference_id': 'other'}, {'metadata': {}}, {'amount_total': 0},
                 {'amount_subtotal': True}, {'amount_subtotal': 150}, {'amount_total': True},
                 {'total_details': {'amount_discount': 0, 'amount_shipping': 1, 'amount_tax': 0}},
                 {'total_details': {'amount_discount': 0, 'amount_shipping': 0, 'amount_tax': True}},
                 {'payment_status': 'no_payment_required'}, {'payment_intent': None},
                 {'payment_intent': 'bad'}, {'discounts': [{'coupon': COUPON}]})
        for change in cases:
            with self.subTest(change=change):
                self.fake = FakeStripe(); self.checkout = self.adapter()
                self.create(); self.fake.paid(); self.fake.response.update(change)
                with self.assertRaises(OwnerCheckoutError): self.reconcile()
                self.assertEqual(self.checkout.state(OWNER)['state'], 'blocked')
                self.assertFalse(self.checkout.state(OWNER)['authorized'])

    def test_coupon_mismatch_payment_or_missing_discount_fails_closed(self):
        cases = ({'amount_total': 149}, {'discounts': []}, {'discounts': [{'coupon': 'other'}]},
                 {'discounts': [{'coupon': COUPON, 'promotion_code': 'promo_unapproved'}]},
                 {'discounts': [{'coupon': {'id': COUPON, 'livemode': True, 'percent_off': 100}}]},
                 {'discounts': [{'coupon': {'id': COUPON, 'livemode': False, 'percent_off': 99}}]},
                 {'payment_intent': 'pi_unexpected'}, {'payment_status': 'paid'},
                 {'payment_status': 'unpaid'})
        for change in cases:
            with self.subTest(change=change):
                self.fake = FakeStripe(); self.checkout = self.adapter(coupon_id=COUPON, coupon_code='OWNER100')
                self.create(coupon_code='OWNER100'); self.fake.complimentary(); self.fake.response.update(change)
                with self.assertRaises(OwnerCheckoutError): self.reconcile()
                self.assertFalse(self.checkout.state(OWNER)['authorized'])

    def test_expanded_sandbox_coupon_is_supported(self):
        self.checkout = self.adapter(coupon_id=COUPON, coupon_code='OWNER100')
        self.create(coupon_code='OWNER100'); self.fake.complimentary()
        self.fake.response['discounts'] = [{'coupon': {'id': COUPON, 'livemode': False, 'percent_off': 100}}]
        self.assertTrue(self.reconcile()['authorized'])

    def test_missing_payment_evidence_never_grants_free_entitlement(self):
        self.checkout = self.adapter(coupon_id=COUPON, coupon_code='OWNER100')
        self.create(coupon_code='OWNER100'); self.fake.complimentary()
        del self.fake.response['payment_intent']
        with self.assertRaises(OwnerCheckoutError): self.reconcile()
        self.assertFalse(self.checkout.state(OWNER)['authorized'])

    def test_checkout_redirects_are_restricted_and_invalid_reply_cannot_be_retried(self):
        for url in (None, [], 'https://evil.test/pay', 'http://checkout.stripe.com/pay',
                    'https://checkout.stripe.com.evil.test/pay', 'https://user@checkout.stripe.com/pay',
                    'https://checkout.stripe.com:443/pay', 'https://[broken',
                    'https://checkout.stripe.com/c/pay/cs_test_other',
                    'https://checkout.stripe.com/\nfoo', 'https://checkout.stripe.com/\\foo'):
            with self.subTest(url=url):
                self.fake = FakeStripe(); self.checkout = self.adapter()
                self.fake.mutate = lambda data: data.update(url=url)
                with self.assertRaises(OwnerCheckoutError): self.create()
                with self.assertRaises(OwnerCheckoutError): self.create()
                self.assertEqual(len(self.fake.calls), 1)
                self.assertEqual(self.checkout.state(OWNER)['state'], 'blocked')

    def test_card_unpaid_and_expired_never_authorize(self):
        self.create()
        self.assertFalse(self.reconcile()['authorized'])
        self.fake.response['status'] = 'expired'
        self.assertEqual(self.reconcile()['state'], 'expired')
        with self.assertRaises(OwnerCheckoutError): self.create()

    def test_clear_revokes_and_preserves_replay_tombstone(self):
        self.create(); self.fake.paid(); self.reconcile()
        self.assertEqual(self.checkout.clear(OWNER)['state'], 'cleared')
        self.assertFalse(self.checkout.state(OWNER)['authorized'])
        with self.assertRaises(OwnerCheckoutError): self.create()
        with self.assertRaises(OwnerCheckoutError): self.reconcile()
        self.assertEqual(len(self.fake.calls), 2)

    def test_checkout_reference_cannot_be_reused_by_another_owner(self):
        self.create()
        original_sid = self.fake.response['id']
        self.fake.mutate = lambda data: data.update(id=original_sid, url='https://checkout.stripe.com/c/pay/' + original_sid)
        with self.assertRaises(OwnerCheckoutError): self.create(OTHER)
        self.assertFalse(self.checkout.state(OTHER)['authorized'])

    def test_payment_reference_cannot_be_reused_after_first_owner_clears(self):
        self.create(); self.fake.paid(); self.reconcile()
        intent = self.fake.response['payment_intent']; self.checkout.clear(OWNER)
        self.create(OTHER); self.fake.paid(); self.fake.response['payment_intent'] = intent
        with self.assertRaises(OwnerCheckoutError): self.reconcile(OTHER)
        self.assertFalse(self.checkout.state(OTHER)['authorized'])

    def test_expiry_revokes_and_cannot_be_extended(self):
        self.create(); self.fake.paid(); self.reconcile()
        self.now = self.expiry
        self.assertEqual(self.checkout.state(OWNER)['state'], 'expired')
        with self.assertRaises(OwnerCheckoutError):
            self.checkout.reconcile(OWNER, self.now + 300)
        self.assertEqual(len(self.fake.calls), 2)

    def test_expiry_during_provider_reply_never_authorizes(self):
        self.create(); self.fake.paid()
        self.fake.before_return = lambda: setattr(self, 'now', self.expiry)
        with self.assertRaises(OwnerCheckoutError): self.reconcile()
        self.assertFalse(self.checkout.state(OWNER)['authorized'])
        self.assertEqual(self.checkout.state(OWNER)['state'], 'expired')

    def test_shorten_deadline_does_not_replace_checkout(self):
        self.create()
        self.checkout.create(OWNER, self.now + 20, accept_test=True)
        self.now += 21
        self.assertEqual(self.checkout.state(OWNER)['state'], 'expired')
        self.assertEqual(len(self.fake.calls), 1)

    def test_owner_reservations_and_tombstones_are_bounded(self):
        for number in range(10):
            owner = ('owner-fixture-' + str(number)).ljust(32, 'x')
            self.create(owner); self.checkout.clear(owner)
        with self.assertRaises(OwnerCheckoutError): self.create(OWNER)
        self.assertEqual(len(self.fake.calls), 10)

    def test_new_adapter_has_no_recovered_entitlement(self):
        self.create(); self.fake.paid(); self.reconcile()
        replacement = self.adapter()
        self.assertFalse(replacement.state(OWNER)['authorized'])
        with self.assertRaises(OwnerCheckoutError): replacement.reconcile(OWNER, self.expiry)


if __name__ == '__main__':
    unittest.main()
