"""Server-owned one-time lookup pricing; no active coupons or external services."""
from collections.abc import Mapping
import re
from types import MappingProxyType

LOOKUP_PRICE_CENTS = 149
CURRENCY = 'USD'
COUPON_ERROR = 'Coupon code is invalid or unavailable.'


def normalize_coupon(code):
    if not isinstance(code, str) or len(code) > 64:
        raise ValueError(COUPON_ERROR)
    code = code.strip()
    if code and not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', code):
        raise ValueError(COUPON_ERROR)
    return code.upper()


class LookupPricing:
    """Copy trusted server configuration. Values are whole-cent discounts, 0..LOOKUP_PRICE_CENTS.

    No code is enabled by default. A caller cannot supply a price or a discount.
    Configuration injection is for local tests until actual offers are approved.
    """
    def __init__(self, coupons=None):
        if coupons is None:
            coupons = {}
        if not isinstance(coupons, Mapping):
            raise ValueError('Coupon configuration must be a server-owned mapping.')
        configured = {}
        for raw_code, discount in coupons.items():
            code = normalize_coupon(raw_code)
            if not code or code in configured:
                raise ValueError('Coupon configuration needs unique, nonempty codes.')
            if type(discount) is not int or not 0 <= discount <= LOOKUP_PRICE_CENTS:
                raise ValueError(f'Coupon discounts must be whole cents from 0 to {LOOKUP_PRICE_CENTS}.')
            configured[code] = discount
        self._coupons = MappingProxyType(configured)

    def quote(self, coupon_code=''):
        code = normalize_coupon(coupon_code)
        if code and code not in self._coupons:
            raise ValueError(COUPON_ERROR)
        discount = self._coupons[code] if code else 0
        return {
            'list_price_cents': LOOKUP_PRICE_CENTS,
            'discount_cents': discount,
            'amount_cents': LOOKUP_PRICE_CENTS - discount,
            'currency': CURRENCY,
            'billing': 'one_time',
            'coupon_code': code or None,
        }
