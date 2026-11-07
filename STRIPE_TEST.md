# Stripe sandbox Checkout (not production)

The offline demo remains the default. A separate `/stripe-test` page is linked
from the main demo. It can create **Stripe test-mode** hosted Checkout Sessions
and reconcile test payments when the owner separately supplies test credentials.
It charges no real money, uses synthetic reports and synthetic ownership, and
cannot be enabled with a live secret key or `SCANPLUS_MODE=live`.

## What is implemented

- Standard-library HTTPS transport to Stripe's fixed API host. API version pinned
  to `2026-10-28.endive`. No redirects, eight-second timeout, bounded responses,
  and generic errors without credentials or provider response bodies.
- Server-owned one-time **99 cents USD** price; card payments only; no coupons,
  subscriptions, price fields or order IDs accepted from the browser.
- A deterministic opaque order/idempotency key per synthetic session. Local
  pending orders survive network failures. Retry the same checkout after an
  uncertain result; do not create a new session to hide a timeout.
- SQLite-backed order state, payment assignment and event deduplication in the
  existing transaction boundary. Signed raw-body webhook verification uses
  HMAC-SHA256, constant-time comparison and a five-minute timestamp tolerance.
- `POST /api/stripe/webhook` is the only endpoint exempt from browser Origin and
  CSRF, and verifies its signature before processing data. Existing host/scheme
  checks and the live-mode block still apply. No public deployment is included.
- Fulfillment checks the Checkout object type, test-mode flag, session ID, order
  reference, metadata, mode, exact amount/currency, complete/paid state and unique
  payment-intent assignment. Duplicate or reordered events cannot double-fulfill
  or move a paid order backward. Unpaid/expired sessions do not unlock access.
- `POST /api/stripe/reconcile` retrieves the known Checkout Session from Stripe
  to recover from a delayed webhook. Browser return URLs, query strings, hashes,
  supplied session IDs and payment flags are never proof of payment.
- `GET /api/stripe/report` requires the current verified synthetic session AND
  its paid Stripe test order. Ordinary `$0` demo checkout cannot unlock it.
- The browser never receives secret keys, payment details or full webhook data.
  ScanPlus sends only the fixed product/price, configured return URLs and opaque
  order reference. It does not send the synthetic phone or session cookie.

## Separate owner setup (not performed)

This repository does not load `.env` automatically. Use your private process
manager/environment, not committed files, to supply these variable names:

- `SCANPLUS_MODE=demo`
- `SCANPLUS_STRIPE_TEST=1` (default: disabled)
- `STRIPE_SECRET_KEY`: a Stripe **test** secret key, never a live key
- `STRIPE_WEBHOOK_SECRET`: the signing secret for this test endpoint
- `SCANPLUS_STRIPE_ORIGIN`: exact trusted origin, such as
  `http://127.0.0.1:4173`, with no path/trailing slash
- For HTTPS WSGI, configure the same origin in `SCANPLUS_ALLOWED_ORIGINS`.

No account, API key, webhook endpoint, CLI installation or tunnel was created.
Owner-approved Stripe account/test setup and test webhook delivery still need
validation. Account creation, terms, credential generation and public hosting
are separate actions. Do not paste secrets in chat or Git. A publishable key is
not needed for the hosted redirect flow.

After that separate setup, open `/stripe-test`, start the reserved synthetic
session, verify with the fixed fixture, and explicitly choose test Checkout.
Use only official Stripe sandbox card/customer fixtures, never real card or
personal data. Return to the page and select **Check payment with Stripe** if
confirmation is pending, then open the synthetic report. Cancelled returns do
not imply payment. No automatic polling or background API work is performed.

For approved webhook setup, route test snapshot events
`checkout.session.completed`, `checkout.session.async_payment_succeeded` and
`checkout.session.expired` to `/api/stripe/webhook`, with the matching API version
and signing secret. Stripe CLI forwarding or an HTTPS endpoint would require
separate setup; neither was enabled or exercised here.

## Deliberate limits and recovery

This is a bounded local sandbox integration, **not production-ready billing**.
The fixed ownership code is not secure authentication. Live mode remains
blocked, real provider scans/removals are not part of this flow, and no real
payment or actual Stripe sandbox call was made during implementation.

Order access ends with the original synthetic session (15 minutes by default).
An expired, revoked or cleared session cannot regain access from a late webhook.
Stripe-hosted checkout may outlive that local session; finish testing promptly.
Do not clear/restart while a payment outcome is uncertain. Resolve uncertain
sandbox outcomes in the Stripe test dashboard before a new session. No
cross-session payment recovery, cancellation API, refund API, dispute handling,
settlement reconciliation or production financial retention is implemented.
The original demo refund screen handles only synthetic demo receipts, not Stripe.

Each session has one order. Expired checkout requires a new synthetic session,
not a new idempotency key on the old order. Orders are bounded to less than the
24-hour Stripe idempotency-key retention window. API calls run inside the local
SQLite transaction and hold its lock for up to the transport timeout, so this is
not a throughput or production concurrency design. No production capacity claim
is made. Keys are not bound to a durable merchant/account identity across runtime
reconfiguration; keep the same sandbox credentials throughout a test session.

Before live enablement: replace synthetic authentication, establish available
service and refund/legal policy, review account binding and durable reconciliation,
add proper job/transaction separation, deploy a reviewed HTTPS backend, validate
actual sandbox success/decline/cancel/delayed/duplicate/timeout/refund journeys,
and explicitly approve launch. Changing an environment flag does not remove
these gates or make a live key usable.

## Verification

`tests/test_stripe_checkout.py` uses only fake transport, fake credentials and
synthetic Stripe-shaped objects. It covers creation, repeat clicks, timeout
recovery, signature/timestamp/raw-body tampering, duplicate/out-of-order events,
amount/currency/order/live-mode mismatches, unpaid/expired/cleared sessions,
payment reuse, CSRF/origin guards, return-page non-fulfillment, reconciliation
and the independent report authorization boundary. Passing these tests does not
prove compatibility with an actual configured Stripe account.

Run with a temporary/ignored database, never the existing user's local store:

```sh
SCANPLUS_DB_PATH=:memory: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_stripe_checkout.py' -v
node --check static/stripe-test.js
```

Official references reviewed for request fields, fulfillment, webhook signatures
and idempotency behavior:
- https://docs.stripe.com/api/checkout/sessions/create
- https://docs.stripe.com/checkout/fulfillment
- https://docs.stripe.com/events/manage-webhook-endpoints
- https://docs.stripe.com/api/idempotent_requests

Implementation verification on November 7, 2026: **190 Python tests passed**,
including 20 Stripe tests; all seven `tool/test_*.js` offline harnesses passed;
Python AST syntax, JavaScript syntax and `git diff --check` passed. The Stripe UI
harness checks explicit redirect, repeated clicks, cancelled/pending/expired and
disabled states, server reconciliation, safe report text and URL rejection.
Desktop/mobile rendered browser checks and screenshots were **unrun** because
no browser automation instance was available. No actual Stripe API compatibility,
account setup, live charge, refund or production deployment was tested.


## Owner online decline test checklist (not yet executed)

Use Stripe's official **generic-decline sandbox card**, not a generated number:
**4000 0000 0000 0002**, a valid future expiration (for example **12/34**), and
any three-digit test CVC (for example **123**). Stripe documents the expected
`card_declined` error with `generic_decline`. These are public test fixtures,
not real payment credentials. Use them only in the Stripe-hosted **test-mode**
Checkout form, never on a live checkout or in ScanPlus API requests. If contact
fields appear, use synthetic values such as `test@example.com`.

1. First complete separately approved Stripe sandbox/account setup and inject
   the test secret and matching webhook signing secret privately. For an online
   site, a reviewed HTTPS Python backend, private writable SQLite location,
   exact approved origin and test webhook delivery must exist. Static hosting
   alone is insufficient. None of those online prerequisites were established
   by this change.
2. Open `/stripe-test`, confirm the synthetic/test disclosures, complete the
   fixed fixture verification and open hosted Checkout. Confirm Stripe displays
   test mode and the one-time **$0.99 USD** test amount before entering the
   official decline fixture.
3. Submit the fixture once. Expected: Stripe shows a declined-payment message;
   the Checkout remains unpaid. Do not substitute a real card or switch modes.
4. Return to `/stripe-test` within the original synthetic session and choose
   **Check payment with Stripe**. Expected: state remains pending/unpaid, and
   `/api/stripe/report` still returns **403**. Reloading or following a success
   URL must not unlock the report. Inspect the Stripe sandbox dashboard for the
   matching failed attempt if needed; this does not represent a real charge.
5. Record the observed decline, reconciliation and access-denial results before
   calling this online scenario passed. An offline regression now models the
   unpaid Checkout plus a signed `payment_intent.payment_failed` event, then
   confirms reconciliation/reload cannot unlock access. It does not simulate
   the actual card network or prove the online card scenario was run.

Official Stripe instructions verified November 7, 2026:
[declined-payment test cards](https://docs.stripe.com/testing#declined-payments)
and [interactive test-card usage](https://docs.stripe.com/testing#testing-interactively).
