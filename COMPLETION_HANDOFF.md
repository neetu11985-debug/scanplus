# ScanPlus coding handoff — 7 November 2026

## What this release is

A tested, private **sandbox**, not a live customer launch. The release includes the
existing loopback Twilio/Serper self-test code, the protected offline demo, an
integrated Stripe-test-to-encrypted-Neon-report path, synthetic admin preview,
and deterministic storage-alert logic. The source destination remains
`neetu11985-debug/scanplus`; OwnlyAI was not changed.

**No new code was pushed or deployed.** GitHub write access previously returned
403. The provided patch is based on the retrieved `main` source snapshot
`c9a252e554fcc3cafee341753c1737ac9aa3a9de`. Check your current branch before
applying it. The source ZIP contains the complete source, not credentials,
dependencies, database files or local evidence.

## Newly finished code

- Server-confirmed Stripe sandbox payment at **$1.49 USD, one time** gates an
  explicit encrypted save. Browser paid/price/owner overrides are rejected.
- The fixed synthetic phone, report and payment claim are written atomically with
  AES-256-GCM. Retries after a lost database response return the same report and
  do not create another Checkout or extend expiry.
- A `.txt` download checks the current verified session, its paid order, expiry
  and the encrypted owner. Downloads use no-store and attachment headers.
- Render has explicit `demo` (default) and `sandbox` profiles. All browser routes
  require the owner-set staging login. Only exact signed Stripe webhook POSTs
  bypass Basic authentication in the sandbox profile.
- Configuration validation does not connect to Neon. The encrypted store opens
  lazily after verified sandbox payment and explicit Save report.
- Fixed SQLite stale-writer/key-rotation replay protection. Every transaction
  now verifies the active encryption marker, matching the Postgres protocol.
- Added owner-run expiry cleanup and 70%, 85%, 95% alert evaluation with duplicate
  suppression and below-60% rearming. Alerts are not scheduled or delivered yet.

## Put the tested source into the intended repository

Use a clean checkout, preserve your own changes and never overwrite secret files.
The patch includes additions to the existing project; the ZIP is a full source
snapshot. Do not upload the ZIP itself to Render as if it were a running service.

1. In your local checkout of `neetu11985-debug/scanplus`, inspect `git status`
   and `git rev-parse HEAD`. If main has moved or you have edits, review/merge the
   patch rather than forcing it.
2. Run `git apply --check /path/to/scanplus-completion.patch`, then
   `git apply /path/to/scanplus-completion.patch` only if the check passes.
3. Create a virtual environment, install `requirements-render.txt`, run `npm ci`,
   then `npm run build`, `npm test` and `npm run test:ui`.
4. Review `git diff`, commit to your own repository and push through your
   authorized GitHub login. Check CI for the new commit. The previous public
   commit does not contain this release.
5. Only then deploy that exact tested commit from Render.

## Render profile A: private demo, simplest first deployment

Use a **Python Web Service**, not a Static Site. Keep the existing repository and
branch selection. Build: `sh deployment/render-build.sh`. Start:
`sh deployment/render-start.sh`. Python is pinned by `.python-version` to 3.12.16.

Set these private environment values in Render:

- `SCANPLUS_RELEASE_PROFILE=demo`
- `SCANPLUS_STAGING_USER`: your chosen staging-only username
- `SCANPLUS_STAGING_PASSWORD`: a unique password-manager-generated staging password
- `SCANPLUS_MODE=demo`
- `SCANPLUS_STRIPE_TEST=0`

The username must be 3–64 ASCII letters, digits, underscore, dot or hyphen.
The password must be 24–128 printable ASCII characters without spaces, at least
12 different characters, and must not contain the username. Do not use any test
fixture credentials. The application reads Render's native hostname itself.
Leave the HTTP health-check path blank so Render uses its default TCP check.

This profile always forces in-memory state and disables Stripe and live providers.
The optional protected `/api/staging/database` probe uses `DATABASE_URL` for a
fixed read-only connection check; successful reachability is not persistence.

## Render profile B: optional private Stripe + Neon sandbox

Use only a separate **test Neon branch** and Stripe's test/sandbox workspace.
This profile intentionally makes Stripe TEST API calls and writes encrypted,
synthetic data to the configured Neon branch when you run the test. It does not
send SMS, search real phones or charge a real card.

Preparation:

1. Verify the exact Neon project and test branch. Review
   `migrations/001_encrypted_storage.sql`, then apply it to that branch in a
   transaction through Neon's SQL editor or a client using the **direct** URL.
   The runtime never applies migrations. Keep the app database role restricted
   to the `scanplus` schema and required table operations. No role is provisioned
   by this release.
2. In Render, use the **pooled** URL as the private `DATABASE_URL`. TLS certificate
   verification and channel binding are required. Do not paste it into chat,
   GitHub source, browser JavaScript or a public URL.
3. Generate and back up a fresh random 32-byte encryption key in your private
   password manager/secret system. Set `SCANPLUS_STORAGE_KEYS_JSON` to a JSON
   object whose key is `"1"` and whose value is that key encoded as base64. Set
   `SCANPLUS_STORAGE_ACTIVE_VERSION=1`. There is no supplied deployable key.
   Keep the key separate from the database. Losing it makes reports unreadable;
   simply replacing it does not rotate existing data.
4. Add private `STRIPE_SECRET_KEY` from the **test** workspace (`sk_test_...`) and
   `STRIPE_WEBHOOK_SECRET` from that workspace's webhook endpoint (`whsec_...`).
   Register `https://<your-service>.onrender.com/api/stripe/webhook` for
   `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
   and `checkout.session.expired`. Do not add Basic credentials to this URL.
   The application itself verifies the signature and rejects live events.
5. Keep your staging login, then set `SCANPLUS_RELEASE_PROFILE=sandbox` and
   redeploy. No Twilio or Serper keys belong in this profile. The app sets the
   trusted return origin, test flag, encrypted-report flag, in-memory prepayment
   state, and 900-second session lifetime itself.

The build/start commands stay the same. Selecting sandbox without valid
configuration fails before the app starts; it does not fall back to a live mode.

Acceptance using only test data:

1. Open the HTTPS site privately, log in, and confirm the PRIVATE STRIPE SANDBOX
   notice. `/stripe-test` explains the test-only flow.
2. Start the reserved synthetic phone session and use displayed code `246810`.
3. Continue to Stripe only with Stripe test-card data. Confirm $1.49 USD in the
   sandbox, return and use **Check payment with Stripe** if still pending. A
   return redirect alone never proves payment.
4. Choose **Save synthetic paid report to encrypted storage**, then download the
   `.txt`. Repeated Save must return the same report; do not pay again if storage
   fails. Retry Save while the same session remains active.
5. Check that an anonymous/new session cannot download it. Clearing the session
   immediately removes access. Encrypted rows expire with the original session,
   not 15 minutes from Save. A restart also loses the in-memory identity/order.
6. Verify actual TLS, the serving commit, rejected wrong origins, Stripe's event
   delivery, Neon ciphertext and provider-side errors privately. These live
   acceptance checks have **not** been run by this coding task.

The sandbox is not customer account recovery. Test reports intentionally cannot
be recovered after session loss. Free-host sleep/restarts can interrupt payment
confirmation; no real money is involved. Do not market it as a paid service.

## Cleanup and capacity alerts

Expiry immediately blocks reads. A subsequent save prunes expired encrypted rows.
For a quiet sandbox, the owner can run/schedule this explicit cleanup with the
same branch/keyring after checking the target:

`SCANPLUS_RELEASE_PROFILE=sandbox SCANPLUS_ENCRYPTED_MAINTENANCE=1 python tool/prune_encrypted.py`

It deletes only expired encrypted rows. No schedule has been created. Provider
backups/snapshots are separate and follow the provider's configured retention.

`storage_usage.py` and `STORAGE_ALERTS.md` define the tested threshold behavior.
A provider metrics adapter, actual plan quota, durable alert state/outbox,
scheduler and notification recipient must be connected before claiming alerts
are active. It never purchases storage or automatically deletes user data.

## Remaining production decisions and gates

- Real customer identity/login, reauthentication, return-user recovery and
  admin MFA. A synthetic verification code is not authentication of a person.
- Confirm whether “admin credentials” means service API keys or login passwords.
  Real credential entry remains disabled; the admin preview accepts synthetic
  constants only. Passwords must not be stored as reversible credentials.
- Approved retention, refunds/revocation, payment recovery and durable minimal
  order state. Current Stripe integration is TEST-only and does not implement
  production refunds/disputes or live merchant checkout.
- Authorized Twilio/Serper live testing, consent and privacy review. These remain
  separate loopback self-tests, not part of the hosted customer flow.
- Real Neon/Stripe/host acceptance, least privilege, restore/key rotation testing,
  operational alerts and rendered browser/mobile QA.

No deployment, real keys, real database query, real payment, SMS, phone lookup,
third-party access change or removal submission occurred during this task.
