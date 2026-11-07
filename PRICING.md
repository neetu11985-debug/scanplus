# Local one-time pricing and optional coupons

New synthetic lookups use a server-owned intended price of **$0.99 USD, one time**. The demo still charges **$0.00**, accepts no payment details, and has no live gateway. No subscription or public coupon offer has been added.

`pricing.py` accepts a trusted, injected mapping of coupon codes to whole-cent discounts from 0 through 99. Its default is empty. Codes are normalized case-insensitively; unavailable or malformed codes are rejected. No browser amount, discount, currency, or code definition is trusted. There is no coupon administration endpoint, environment setting, external request, expiry promise, or redemption-limit claim. Test fixtures are not public offers.

`POST /api/quote` requires a current verified demo session, same origin and CSRF token. It shows the base price, discount, intended total and separate zero-dollar demo charge without creating a receipt or unlocking a report. `POST /api/checkout` revalidates the code against current server configuration. A removed code must be cleared or replaced before checkout. Production would need independently reviewed offer terms and price-change acceptance before any real payment integration.

The first completed checkout fixes its receipt. Repeated checkout, changed codes and changed configuration return that original receipt. Existing receipts, including prior $1.00 intended prices, are not migrated or repriced. All newly calculated prices are 0–99 cents. The server's existing transaction serializes concurrent checkouts. Retained receipt and refund history follow the existing lifecycle.

The UI obtains totals from the quote endpoint, disables checkout until a quote succeeds, invalidates the displayed total after editing a code, and supports applying or clearing an optional code. Late quote/checkout responses do not replace a screen the user has left. A previously completed session reopens its existing report rather than creating another charge.

Checks (all synthetic/offline or local loopback):

```sh
SCANPLUS_DB_PATH=:memory: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_pricing.py' -v
node --check static/app.js
node tool/test_phone_entry.js
node tool/test_pricing_ui.js
```

These checks do not qualify a live gateway, an actual coupon campaign, production pricing economics, deployment, or legal terms. No credentials or persistent database records are modified by the pricing tests.
