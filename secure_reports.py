"""Sandbox payment-to-encrypted-delivery boundary. Never accepts customer input.

Only server-owned synthetic fixtures are supported. This is not a production
identity system: the current verified, expiring demo session owns its report.
The Neon store opens lazily, only after a reconciled sandbox payment. All
prepayment session/order state must be in memory when this feature is enabled.
"""
import json
import math
import os
import re
from threading import RLock
import time

from encrypted_storage import SecureStorageError
from pricing import LOOKUP_PRICE_CENTS
from providers import FixtureDiscovery
from storage import digest

FIXTURE_PHONES = ('+12025550147', '+12025550148')


def enabled():
    return os.environ.get('SCANPLUS_ENCRYPTED_REPORTS', '0') == '1'


class SandboxReports:
    def __init__(self, factory=None, *, clock=time.time):
        self._factory = factory
        self._store = None
        self._lock = RLock()
        self._clock = clock

    def store(self):
        with self._lock:
            if self._store is None:
                if self._factory is None:
                    from neon_storage import PostgresEncryptedStore, settings_from_environment
                    self._store = PostgresEncryptedStore(settings_from_environment())
                else:
                    self._store = self._factory()
            return self._store

    def trusted_bundle(self, sid, session, order):
        """Arguments are read from server state, never from request JSON."""
        now = self._clock()
        if (not enabled() or os.environ.get('SCANPLUS_MODE', 'demo') != 'demo'
                or os.environ.get('SCANPLUS_STRIPE_TEST') != '1'
                or os.environ.get('SCANPLUS_DB_PATH') != ':memory:'):
            raise SecureStorageError('Sandbox encrypted delivery is unavailable.')
        if (not isinstance(sid, str) or not re.fullmatch(r'[a-f0-9]{64}', sid)
                or not isinstance(session, dict) or not isinstance(order, dict)
                or session.get('verified') is not True
                or order.get('owner') != sid or order.get('state') != 'paid'
                or type(order.get('amount_cents')) is not int
                or order['amount_cents'] != LOOKUP_PRICE_CENTS
                or not re.fullmatch(r'cs_test_[A-Za-z0-9_]+', str(order.get('checkout_id', '')))
                or not re.fullmatch(r'pi_[A-Za-z0-9_]+', str(order.get('payment_ref', '')))):
            raise SecureStorageError('A reconciled sandbox payment for this session is required.')
        deadlines = [session.get('expires'), session.get('verified_until'), order.get('expires')]
        if any(type(v) not in (int, float) or not math.isfinite(v) or v <= now for v in deadlines):
            raise SecureStorageError('The sandbox session or payment has expired.')
        phone = next((p for p in FIXTURE_PHONES if digest(p) == session.get('phone_ref')), None)
        if phone is None:
            raise SecureStorageError('Only a fixed synthetic phone is supported.')
        text = ('SCANPLUS SYNTHETIC STRIPE SANDBOX REPORT\n'
                'No real charge, phone query, SMS or removal occurred.\n'
                'Phone: ' + phone + '\n' +
                json.dumps(FixtureDiscovery().discover(), ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        return phone, text, min(deadlines)

    def fulfill(self, sid, session, order):
        phone, text, expiry = self.trusted_bundle(sid, session, order)
        # The store atomically commits phone/report/payment claim. A lost response
        # or a failed surrounding demo transaction retries the SAME payment.
        store = self.store()
        store.prune()
        report_id = store.put_paid_bundle(sid, order['payment_ref'], phone, text, expires_at=expiry)
        return {'report_id': report_id, 'download_url': '/api/stripe/report/download',
                'expires_at': expiry, 'encrypted_storage': True, 'test_mode': True}

    def download(self, sid, session, order):
        self.trusted_bundle(sid, session, order)
        report_id = order.get('encrypted_report_id')
        if not isinstance(report_id, str) or not re.fullmatch(r'[a-f0-9-]{36}', report_id):
            return None
        return self.store().get_report(report_id, sid)

    def close(self):
        with self._lock:
            if self._store is not None:
                self._store.close()
                self._store = None


REPORTS = SandboxReports()
