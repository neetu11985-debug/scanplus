"""Server-owned payment boundary. Demo is idempotent and never calls a gateway."""
from typing import Protocol
from uuid import uuid4
import time
from pricing import LookupPricing


class PaymentGateway(Protocol):
    def checkout(self, session: dict, coupon_code: str = '') -> dict: ...


class DemoGateway:
    def __init__(self, pricing=None):
        self.pricing = pricing if pricing is not None else LookupPricing()

    def quote(self, session, coupon_code=''):
        if not session.get('verified'):
            raise ValueError('Ownership verification required.')
        receipt = session.get('receipt')
        if receipt is not None:
            # Preserve legacy receipts exactly, including their old intended price.
            return {
                'list_price_cents': receipt.get('list_price_cents', receipt['amount_cents']),
                'discount_cents': receipt.get('discount_cents', 0),
                'amount_cents': receipt['amount_cents'],
                'currency': receipt['currency'],
                'billing': receipt.get('billing', 'one_time'),
                'coupon_code': receipt.get('coupon_code'),
                'charged_cents': receipt['charged_cents'],
                'mode': receipt['mode'],
                'locked': True,
            }
        return dict(self.pricing.quote(coupon_code), charged_cents=0, mode='test', locked=False)

    def checkout(self, session, coupon_code=''):
        if not session.get('verified'):
            raise ValueError('Ownership verification required.')
        if 'receipt' not in session:
            session['receipt'] = dict(
                self.pricing.quote(coupon_code), charged_cents=0, mode='test',
                payment_id=str(uuid4()), created_at=time.time(),
            )
        # Retrying always returns the original receipt, even if a code or config changes.
        session['paid'] = True
        return session['receipt'].copy()


class GoDaddyGateway:
    def checkout(self, session, coupon_code=''):
        raise ValueError('Production checkout is disabled pending merchant configuration and signed server-side verification.')
