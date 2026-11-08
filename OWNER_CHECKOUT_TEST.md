# Private owner SMS, Stripe test checkout and search

This is a new **disabled-by-default private test entrypoint**, not a public or
paid service. The ordinary demo, existing Stripe sandbox, payment-free owner
test, and local no-SMS test remain separate and unchanged in purpose. Do not
remove their guards or use a live Stripe key.

## Exact test journey

1. Open the private Render service in a private browser window and authenticate.
2. Enter only the account owner's own US number and explicitly consent to Twilio.
   One real SMS and at most five code checks share the approved durable run.
3. After Twilio approval, explicitly choose one Stripe **test** variant:
   - Card test: $1.49 USD test amount. Stripe's official success test number is
     `4242 4242 4242 4242`, with a future expiration and any three-digit test CVC.
     Use only synthetic billing fields. Never enter a real card.
   - Optional no-payment test: enter the operator-provided code mapped to an
     already-created Stripe test coupon for 100% off. Subtotal is 149 cents,
     discount 149 cents, total zero. No card payment is proved by this variant.
4. Return from Stripe and deliberately select **Check test completion with Stripe**.
   The server retrieves the known checkout and validates its test mode, owner/order
   reference, immutable amount, coupon identity and completion. A return URL,
   browser flag or displayed success page cannot unlock search.
5. Separately consent to send the verified number to Serper. At most three bounded
   indexed-source queries run, with no automatic retry or fallback.
6. Read/download the accurately labeled report. Clear or expiry revokes access.

The card/coupon selection is locked when the order is reserved, even if the
creation response is uncertain. Reopening resumes the same order and cannot
switch variants. Testing both end to end needs separately approved provider
runs. Do not reset an existing run's counters or restart to obtain more allowance.

## Privacy and safety boundaries

- Stripe receives an opaque test-order reference, fixed test product/amount and
  return origin. It receives no phone, OTP, listing, report or application cookie.
- Only `rk_test_` restricted or `sk_test_` secret keys and validated `cs_test_`
  test-mode responses are accepted. Prefer a least-privilege restricted test key;
  both live-key prefixes are rejected.
  Positive card-test completion requires a valid unique payment intent. Zero-total
  completion is a separate `complimentary_test` entitlement with no invented
  payment intent. Existing encrypted paid-report rules remain positive paid-only.
- Every API retains private authentication, same-origin/CSRF protection and bounded
  input. Only the authenticated root HTML shell permits cross-site top-level GET
  navigation for Stripe's return; it makes no payment/provider request. The
  same-origin bootstrap subsequently reads the existing Strict session cookie.
- No public webhook is added. Completion is retrieved explicitly, at most five
  times per order. Creation permits at most two explicit attempts using the same
  idempotency key and fixed integration identifier; no automatic retry occurs.
  The current Checkout API card filter (`allowed_payment_method_types`) retains
  this private fixture's card-only scope. At most ten local owner reservations
  are held. Uncertain or malformed responses never authorize search.
- The five-minute lifetime begins at SMS start and is **not extended by checkout**.
  A provider response crossing expiry cannot restore access or a redirect. Clear,
  expiry and restart revoke local checkout/report state. An external Stripe test
  session may outlive local access; this is acceptable only because no real money
  is collected. Inspect uncertain outcomes before approving another run.
- SMS/search reservations remain durable under the existing Neon allowance ledger.
  Stripe test-order state is memory-only. This is not production payment recovery,
  customer authentication, refund handling, long-term storage or a spending cap.

## Owner setup and deployment gates

No real coupon was created and no deployed configuration changed merely by adding
this code. `OWNER100` is a suggested local display code, not an activated Stripe
promotion code. It works only after an actual approved Stripe **test coupon ID**
is configured and Stripe confirms the exact discount. Do not claim a configured
coupon has passed its hosted acceptance test.

Use the existing private owner setup in `HOSTED_SELF_TEST.md`: exact native Render
hostname, separate strong private login, approved Twilio/Serper settings and
allowances, dedicated least-privilege Neon role, migration and a short-lived
operator-approved run grant. Verify those settings on the chosen service. Do not
copy a properties file into the repo or deployment, paste secrets in chat, or
log environment values. Persistent credential configuration requires approval.

Additional environment **names**, entered privately in the service dashboard:

```text
SCANPLUS_OWNER_CHECKOUT_TEST=1
STRIPE_SECRET_KEY=<approved restricted test key, or existing test secret key>
SCANPLUS_OWNER_TEST_COUPON_ID=<optional existing Stripe test coupon ID>
SCANPLUS_OWNER_TEST_COUPON_CODE=<matching local code, for example OWNER100>
```

Both coupon fields must be configured together or both omitted. Leave
`SCANPLUS_STRIPE_TEST=0` and `SCANPLUS_ENCRYPTED_REPORTS=0`: those flags belong
to different flows. The new private checkout opt-in is deliberately separate.
No Stripe webhook secret is required by this retrieval-only test path.

After code review, full passing checks, setup approval and an explicit publishing
decision, the selected service's commands are:

```text
Build: sh deployment/render-build.sh
Start: sh deployment/owner-checkout-start.sh
```

Do not select this start command before configuration is ready. It fails closed
on absent/invalid opt-in, login, provider setup, test key or coupon pairing. It
uses one sync worker/thread and clears default request logging. Leave the HTTP
health route blank/default TCP as for the existing private service. Retain access
protection, exact HTTPS origin and no-index headers. No public endpoint is exempt.

Switching the existing service replaces its current demo experience. Review the
exact release commit and CI, verify intended settings and rollback, then inspect
the deployed version before entering a real number. A source merge can trigger
deployment. Do not merge just to test a configuration.

## Required acceptance before calling it enabled

1. Exact reviewed commit passes CI and deployment starts privately without secrets
   in logs. Existing unauthorized requests stay blocked.
2. Selected Neon role/TLS/grant and restart/concurrency behavior are verified in
   the actual target; missing/used/uncertain reservations dispatch no provider call.
3. Approved Twilio verification succeeds for the owner's chosen destination.
4. Stripe hosted test-card completion, cancel/return, decline and manual recovery
   work. The 100% coupon path is separately accepted with no card required. Validate
   actual API response shape; synthetic tests alone are not provider proof.
5. Same owner/session remains bound after the real cross-site browser return.
   Invalid or late completion never unlocks another session or an expired report.
6. Separately consented Serper result and report accuracy/cost are inspected within
   the approved remaining allowance. An unavailable source is not a no-match.

Public customer release and live charging remain out of scope.

## Offline verification

The combined November 8 source passed **432 Python tests**, all **10 UI contract
suites**, syntax checks for **91 Python files / 15 JavaScript files**, TypeScript
and `git diff --check`. These include synthetic in-memory and isolated loopback
checks, not live provider, account or deployment validation. Independent review
also passed the 36 original new adapter/journey tests after correcting raw-origin
validation and the cross-site return shell exception; a later revision-header
regression is included in the full total.

`tests/test_owner_test_checkout.py` tests the additive payment adapter with fake
Stripe objects. `tests/test_hosted_owner_checkout.py` tests the combined WSGI
journey, ownership/expiry/clear, return navigation, consent and PDF gate.
`tool/test_hosted_live_ui.js` also covers checkout choice, fixed-host redirect,
manual reconciliation and stale/expired response suppression.

Optional rendered fixture:

```sh
python -B tool/owner_checkout_fixture_server.py --port 4177
```

Use only reserved `2025550147`, code `123456`, and mock coupon `OWNER100` there.
The banner says **MOCK CHECKOUT ONLY**. It blocks outbound sockets, removes the
external redirect and provides an explicit **Complete synthetic checkout** button.
That button is only a fixture state control. This runner cannot validate the
actual Stripe page, payment network, Render TLS, database or browser return.
Never point a deployment at the fixture or leave it running after QA.

### Rendered synthetic check, November 8

Both variants passed in the dedicated iPhone 17 / iOS 26.3 Safari simulator:
the coupon order locked at $0, and the blank-coupon card order locked at $1.49.
Unchecked checkout consent blocked submission. Pending reconciliation did not
unlock search. Explicit fixture completion plus normal manual reconciliation
revealed the separate search-consent stage; unchecked search consent blocked it.
The approved synthetic scan showed three usable source responses and three
possible matches. Clear removed the report and preserved the spent allowance.
The updated base-price wording and button spacing were visually checked.

Evidence is local under `evidence/mobile-owner-checkout-2026-11-08/`. The fixture
stripped external checkout URLs, so **no actual Stripe page, card submission,
coupon redemption or cross-site browser return was tested**. Only the managed
mock server on 4177 was restarted between variants and then stopped. The existing
owner test on 4178 was not restarted or reset.

Official references:
- https://docs.stripe.com/testing
- https://docs.stripe.com/payments/checkout/no-cost-orders
- https://docs.stripe.com/payments/checkout/discounts
- https://docs.stripe.com/api/checkout/sessions/retrieve

### Local integration update, 8 November

Restricted test-key support and a stable Checkout integration identifier have been
added without changing the private test's price, coupon validation, five-minute
journey, consent, provider allowances or memory-only recovery limitations. The
card filter uses the current `allowed_payment_method_types` API parameter.
No real Stripe request, credential setup or deployment was performed by this
change. This retrieval-only private fixture is not the customer-billing architecture;
signed lifecycle webhooks and durable recovery remain required before launch.
