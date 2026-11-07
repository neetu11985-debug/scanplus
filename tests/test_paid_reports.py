"""Offline payment → encrypted-storage → owner-download integration, no services."""
import copy
import os
import time
from unittest.mock import patch
from encrypted_storage import EncryptedStore, SecureStorageError
from secure_reports import SandboxReports
from storage import digest
import test_stripe_checkout as stripe_tests


class PaidReportsTests(stripe_tests.StripeHTTPTests):
    def setUp(self):
        super().setUp()
        self.encrypted = EncryptedStore(':memory:', {1: b'S' * 32}, 1)
        self.addCleanup(self.encrypted.close)
        self.factory_calls = 0
        def factory():
            self.factory_calls += 1
            return self.encrypted
        self.reports = SandboxReports(factory)
        p = patch('secure_reports.REPORTS', self.reports)
        p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, SCANPLUS_ENCRYPTED_REPORTS='1', SCANPLUS_DB_PATH=':memory:')
        p.start(); self.addCleanup(p.stop)

    def paid(self):
        self.start()
        self.call('/api/stripe/checkout', {'accept_test': True})
        self.fake.paid()
        self.assertEqual(self.call('/api/stripe/reconcile', {})['body']['state'], 'paid')

    def save_report(self):
        return self.call('/api/stripe/report/save', {'confirm_synthetic': True})

    def sid(self):
        return digest(self.cookie.split('=', 1)[1])

    def test_unpaid_demo_receipt_and_tampering_never_open_store(self):
        self.start()
        self.assertEqual(self.save_report()['status'], 402)
        self.call('/api/checkout', {'accept': True})
        self.assertEqual(self.save_report()['status'], 402)
        self.assertEqual(self.call('/api/stripe/report/save', {'confirm_synthetic': True, 'paid': True})['status'], 400)
        self.assertEqual(self.call('/api/stripe/reconcile', {'owner': 'someone_else'})['status'], 400)
        self.assertEqual(self.factory_calls, 0)

    def test_paid_atomic_save_retry_owner_download_and_ciphertext(self):
        self.paid()
        first = self.save_report()
        self.assertEqual(first['status'], 200)
        self.assertEqual(first['body']['report_id'], self.save_report()['body']['report_id'])
        self.assertEqual(self.factory_calls, 1)
        report = self.call('/api/stripe/report/download')
        self.assertEqual(report['status'], 200)
        self.assertIn(b'SYNTHETIC STRIPE SANDBOX', report['raw'])
        self.assertIn('attachment;', report['headers']['Content-Disposition'])
        self.assertEqual(report['headers']['Cache-Control'], 'no-store')
        raw = b''.join(bytes(r[0]) for r in self.encrypted._conn.execute('SELECT ciphertext FROM encrypted_records'))
        self.assertNotIn(b'+12025550147', raw)
        self.assertNotIn(b'SYNTHETIC STRIPE SANDBOX', raw)
        self.assertEqual(self.encrypted._conn.execute("SELECT COUNT(*) FROM encrypted_records WHERE purpose='report'").fetchone()[0], 1)
        self.assertIsNone(self.encrypted.get_report(first['body']['report_id'], 'another-owner'))
        self.call('/api/clear', {})
        self.assertEqual(self.call('/api/stripe/report/download')['status'], 403)

    def test_lost_storage_response_retry_never_recharges_or_duplicates(self):
        self.paid()
        real = self.encrypted.put_paid_bundle
        def save_then_lose_response(*args, **kwargs):
            real(*args, **kwargs)
            raise SecureStorageError('Synthetic lost response')
        with patch.object(self.encrypted, 'put_paid_bundle', save_then_lose_response):
            self.assertEqual(self.save_report()['status'], 503)
        self.assertEqual(self.save_report()['status'], 200)
        self.assertEqual(self.encrypted._conn.execute("SELECT COUNT(*) FROM encrypted_records WHERE purpose='report'").fetchone()[0], 1)
        self.assertEqual(sum(call[0] == 'POST' for call in self.fake.calls), 1)

    def test_expired_wrong_owner_invalid_price_and_real_phone_fail_before_factory(self):
        self.paid()
        sid = self.sid()
        session = self.store.get('session', sid, sid)
        order = self.store.get('stripe_order', sid, sid)
        cases = [({'verified': False}, {}), ({'expires': time.time() - 1}, {}),
                 ({'phone_ref': digest('+14158675309')}, {}), ({}, {'owner': 'wrong'}),
                 ({}, {'amount_cents': 0}), ({}, {'amount_cents': -1}),
                 ({}, {'amount_cents': True}), ({}, {'amount_cents': '149'}),
                 ({}, {'state': 'pending'}),
                 ({}, {'payment_ref': None}), ({}, {'expires': float('nan')})]
        for change_session, change_order in cases:
            with self.subTest(change=list(change_session) + list(change_order)):
                with self.assertRaises(SecureStorageError):
                    self.reports.fulfill(sid, dict(session, **change_session), dict(order, **change_order))
        self.assertEqual(self.factory_calls, 0)

    def test_disabled_or_plaintext_prestate_configuration_fails_closed(self):
        self.paid()
        for changes in ({'SCANPLUS_ENCRYPTED_REPORTS': '0'}, {'SCANPLUS_DB_PATH': '/tmp/not-memory'}):
            with patch.dict(os.environ, changes):
                self.assertEqual(self.save_report()['status'], 503)
        self.assertEqual(self.factory_calls, 0)

    def test_paid_session_loss_does_not_reopen_report(self):
        self.paid(); self.assertEqual(self.save_report()['status'], 200)
        self.cookie = ''; self.csrf = ''
        self.assertEqual(self.call('/api/stripe/report/download')['status'], 403)
        self.start()
        self.assertEqual(self.call('/api/stripe/report/download')['status'], 403)

    def test_catalog_price_change_preserves_paid_save_and_download(self):
        self.paid()
        # Model updated catalog imports alongside an existing paid order.
        with patch('pricing.LOOKUP_PRICE_CENTS', 199), patch('stripe_checkout.LOOKUP_PRICE_CENTS', 199), patch('secure_reports.LOOKUP_PRICE_CENTS', 199, create=True):
            saved = self.save_report()
            self.assertEqual(saved['status'], 200)
            self.assertEqual(self.call('/api/stripe/status')['body']['amount_cents'], 149)
            self.assertEqual(self.call('/api/stripe/report/download')['status'], 200)
            self.assertEqual(self.save_report()['body']['report_id'], saved['body']['report_id'])
        self.assertEqual(sum(call[0] == 'POST' for call in self.fake.calls), 1)

    def test_legacy_99_cent_paid_order_can_save_and_download(self):
        self.start()
        with patch('stripe_checkout.LOOKUP_PRICE_CENTS', 99):
            self.assertEqual(self.call('/api/stripe/checkout', {'accept_test': True})['status'], 200)
        sid = self.sid()
        order = self.store.get('stripe_order', sid, sid)
        del order['amount_cents']  # Persisted legacy schema, before price snapshots.
        with self.store.transaction():
            self.store.put('stripe_order', sid, sid, order['expires'], order)
        self.fake.paid()
        self.assertEqual(self.call('/api/stripe/reconcile', {})['body']['state'], 'paid')
        self.assertEqual(self.call('/api/stripe/status')['body']['amount_cents'], 99)
        self.assertEqual(self.save_report()['status'], 200)
        self.assertEqual(self.call('/api/stripe/report/download')['status'], 200)
        self.assertEqual(sum(call[0] == 'POST' for call in self.fake.calls), 1)
