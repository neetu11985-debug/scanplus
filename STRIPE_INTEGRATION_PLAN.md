# ScanPlus Stripe integration plan

Prepared 8 November 2026. This is a draft implementation plan, not an accepted
Stripe planner decision tree, a deployment approval or permission to charge.
The user wants customers to pay through ScanPlus and explicitly forbids actual
payments during this work. All implemented behavior remains test-mode only.

## First phase: one-time direct Checkout

The existing product is a $1.49 one-time report, so the provisional first phase is
a customer paying the ScanPlus business through Stripe-hosted Checkout. The
user's checkout preference does not establish whether future independent sellers
or service providers will receive funds. No Connect configuration is selected.

The Stripe planner's unaccepted draft recommends hosted Checkout for a web
one-time purchase, signed webhook fulfillment, server-side retrieval and
idempotency. This aligns with the existing sandbox architecture. Retain the
server-owned amount, opaque order references, explicit test consent, fixed Stripe
HTTPS destination, live-key rejection and no phone/report data sent to Stripe.

## Implemented local changes

- Both adapters accept restricted test API keys (`rk_test_`) and existing secret
  test keys (`sk_test_`); malformed, publishable and live keys fail closed.
- New normal-sandbox Checkouts use dynamic payment methods, with a stable
  integration identifier stored in the order. The private owner fixture keeps
  a card filter through the current `allowed_payment_method_types` parameter.
- New normal-sandbox sessions commit a nonsecret request contract before any
  Checkout request: version, integration identifier, fixed price and return origin.
  Orders copy it, so rollback cannot silently adopt new request parameters. An
  incompatible version or legacy session without a contract fails closed. Unknown
  outcomes from the old create contract cannot be replayed with altered parameters or
  another idempotency key. Existing known sessions and signed webhooks still
  reconcile, including legacy price snapshots.
- Signed `checkout.session.async_payment_failed` events record failure without
  granting report access or reopening Checkout. Duplicate or stale failure
  events cannot downgrade a paid order. A later verified paid result can recover.
- The failed-state UI allows checking the existing outcome and does not offer
  another checkout. There are no background requests or automatic payment retries.

These are local source changes. No stored credentials, existing process, provider
allowance, deployed service, Stripe setting, product, price, coupon, tax
registration, connected account or payment was changed.

## Remaining work by product

### Payments

Before a customer release, design durable authenticated customer/order/payment
ownership and recovery independently of the current 5- or 15-minute test session.
Separate external requests from database locks; preserve immutable order prices,
account/sandbox binding, idempotency and verified payment assignments. Signed
webhooks are required for fulfillment and asynchronous outcomes, not optional.

Add operational handling for refunds, disputes and recovery after restart/expiry
without treating the existing demo refund screen as a Stripe refund. Decide the
no-result/service-failure refund policy before any paid launch. Verify actual
Checkout success, decline, cancel, delayed completion/failure, duplicate and
reordered webhook delivery, timeout and restricted-key permissions in the chosen
sandbox using synthetic data. No live payment is authorized.

### Billing

No recurring offer has been defined. Keep the current one-time amount unchanged.
If recurring scans or memberships are later selected, first define price, billing
interval, entitlements, cancellation and failure policy. Use subscription Checkout
plus Billing and a Customer Portal, durable Customer/Subscription ownership, and
lifecycle handlers for subscriptions, invoice payment and relevant risk events.
Do not invent a subscription or enable it from the product list alone.

### Connect

Connect is needed only if the chosen business flow involves connected accounts
receiving or managing payments. Confirm the sellers/providers, customer payment
relationship, fee economics, onboarding, disputes and negative balance liability
before selecting Accounts v2 configuration or a charge pattern. Direct ScanPlus
sales need no connected-account creation. Do not use subscriptions or invoices
to infer a marketplace or decide tax liability.

### Invoicing

Choose between an optional post-purchase invoice for the one-time Checkout and
an invoice-first payment workflow. The former uses Checkout `invoice_creation`;
the latter needs a Customer, invoice lifecycle, due dates and collection choices.
Confirm invoice identity/contact fields and delivery before sending anything.
Do not treat invoice generation as a separate additional customer charge.

### Tax

Read existing Tax Settings and registrations before making changes. The owner and
tax advisor must confirm the taxable product classification, tax-inclusive versus
exclusive price, liable business and jurisdictions where the business is already
registered. Choose a product tax code from Stripe's current canonical list, not
a guessed generic code. Do not overwrite existing settings.

Only enable automatic tax after verifying an active registration and a test
calculation with the selected product and location. Inspect taxability_reason;
zero tax can mean not_collecting rather than a working setup. The existing code
requires a fixed total and the owner fixture requires tax=0; adding tax needs
explicit subtotal/discount/tax/total validation and matching UI before enabling
collection. Tax calculation is not the same as filing or tax-authority registration.

## Credentials and rollout

Use a separate development sandbox where supported and a least-privilege restricted
test key. Keep the existing `STRIPE_SECRET_KEY` environment variable name for
compatibility; it now accepts either supported test-key kind. Store real secrets
in the host's secure secret store or private environment, never source, screenshots,
chat, logs or committed environment files. Do not generate, configure or expand
persistent access without explicit action-time approval. Hosted redirect Checkout
does not require exposing a publishable key.

No deployment, merge, process restart or real payment is part of this plan.
Preserve the existing pending owner test and provider budget. Review the exact
combined working tree and run full checks before any separately approved release.

## Official references

- [Create Checkout Sessions](https://docs.stripe.com/api/checkout/sessions/create)
- [Checkout fulfillment](https://docs.stripe.com/checkout/fulfillment)
- [Dynamic payment methods](https://docs.stripe.com/payments/payment-methods/dynamic-payment-methods)
- [Idempotent requests](https://docs.stripe.com/api/idempotent_requests)
- [Manage secret API keys](https://docs.stripe.com/keys-best-practices)
- [Subscription webhooks](https://docs.stripe.com/billing/subscriptions/webhooks)
- [Tax setup](https://docs.stripe.com/tax/set-up)
- [Tax codes](https://docs.stripe.com/tax/tax-codes)

## Verification

Final local verification on 8 November 2026, after review fixes:

- 446 Python tests passed using synthetic transports, isolated loopback fixtures
  and temporary/in-memory stores.
- All 10 UI contract harnesses passed, including delayed-failure behavior.
- Build passed: 91 Python files parsed, 15 JavaScript files syntax-checked, and
  TypeScript checking completed successfully.
- `git diff --check` passed.
- Independent read-only review found no remaining actionable issues after the
  rollback-contract and pre-checkout price-display fixes.

Commands used:

```sh
PYTHONDONTWRITEBYTECODE=1 SCANPLUS_DB_PATH=:memory: python -B -m unittest discover -s tests -q
npm run test:ui
npm run build
git diff --check
```

No live/sandbox Stripe account call, rendered-browser QA, credential configuration,
process restart, deployment or payment was performed for this code update. Tests
cannot establish hosted Stripe compatibility, actual key permissions, real
provider acceptance or production readiness. Do not downgrade an active checkout
run to old code that ignores the saved request contract; reconcile/drain uncertain
sessions before any separately authorized deployment or rollback.
