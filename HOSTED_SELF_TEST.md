# Private hosted own-number self-test: prepared, disabled

This is a separate opt-in implementation, not an enabled service or a production
launch. The ordinary `render_wsgi:application` and `deployment/render-start.sh`
are unchanged. Deploying this branch with the existing start command still runs
the synthetic demo. Nothing in this preparation reads live credential values,
configures a provider account, sends SMS/searches, commits, publishes or deploys.

## What it can do after approved setup

1. Require a separate owner login, the exact native Render HTTPS hostname and
   same-origin requests before any page, asset or API is available.
2. Accept the owner's own US number and explicit consent to send it to Twilio.
   A real Twilio Verify approval bound to that phone and challenge is required.
   The synthetic demo code cannot unlock this route.
3. Ask separately to send the verified number to Serper for at most three
   Google-index queries: Spokeo, TruePeopleSearch and Whitepages, ten results each.
4. Show source timestamps and possible matches, not an exhaustive search or proof
   of absence. Users must confirm individual listings themselves. There is no
   automatic removal, payment, refund or phone/report database-persistence route.
5. Hold phone/challenge/report state only in server memory. Five-minute scan
   expiry begins at SMS start; an idle cleanup runs each second. The raw
   phone is cleared after search. A provider request already in progress can
   delay cleanup. The transport timeout is an inactivity timeout, not a strict
   five-second wall-clock limit; the worker also has a 30-second watchdog. Browser report content is wiped on expiry and
   page leave. Downloads remain on the user's device.

## Limits and remaining blockers

The attempt budget is one SMS start, five code checks and three search requests
per **operator-approved run ID**. An additive Neon ledger stores only that opaque
ID, creation/expiry times, an enabled flag and counters. It stores no phone, OTP,
provider key, report or login identity. A server-side SQL function locks the grant
row and increments the relevant fixed counter. The transaction must confirm its
commit before any provider call begins.

Clear, expiry, other browser sessions, redeployment and automatic worker recovery
cannot replenish the same run. Missing/expired/disabled grants, database failures
and uncertain commits block the provider request. An uncertain commit may use an
allowance without sending anything; it is never automatically retried. The first
HTTP/transport error or malformed search response stops later search calls.
The app has no grant-creation or reset operation. A new run requires a separate
operator approval, a new grant row and an explicit environment update. Do not
edit counters downward or reuse a consumed run ID.

This is an attempt limit, not a provider-account dollar spending cap. Confirm
free allowance and billing restrictions before use. The supplied start script
still forces one sync worker with one thread because phone/challenge/report
sessions are intentionally memory-only. A restart can lose the active challenge
or report; it does not permit another SMS against the same durable grant.

The ledger migration, dedicated-role permissions and actual PostgreSQL behavior
remain unverified until separately approved setup. The test suite emulates its
transaction contract locally; it does not connect to Neon. Do not activate this
entrypoint merely by setting environment flags.

Provider credits, account eligibility, SMS destination restrictions, billing,
retention, actual API acceptance and current guide workflows are not established
by the mocked tests. No paid usage or top-up is authorized by this code.

This is for a private consenting owner test only. HTTP Basic login is not
production customer authentication. Clear does not log the browser out of Basic
authentication. Use a private browser window and close it afterward. Hosting and
provider infrastructure retention is outside the app's control. A real public
service needs a separately reviewed authentication, abuse prevention, durable
quota/idempotency, privacy, consent-retention and operational design.

## Setup must be reviewed and authorized first

No live enablement or deployment is authorized by this document.

- Verify the Twilio account/Verify service, permitted destination, sufficient
  approved no-card/trial allowance, and no paid usage/top-up requirement.
- Verify the Serper account has at least three approved free queries and no
  paid top-up requirement. Confirm the actual provider terms and privacy notices.
- Obtain approval to configure the specified existing credentials persistently
  in the chosen private service. Enter values directly in its secure dashboard;
  never paste secrets into source, command history, logs, this file or chat.
- Obtain approval for the additive ledger migration, a dedicated least-privilege
  database role and one short-lived grant on the exact Neon project/branch.
  Confirm the database service allowance/cost as well. Review the new code and
  tests, then make an explicit deployment decision.
  A merge to this project's main branch may trigger deployment; do not merge
  merely to try a code change. Keep the existing demo until the owner chooses
  the separate self-test entrypoint.
- Obtain the test user's consent in the page before each named transmission.
  Running tests against mocks does not supply permission to send real data.

Required environment variable names for a later owner-approved deployment:

- `RENDER=true` and the platform's native `RENDER_EXTERNAL_HOSTNAME`.
- `SCANPLUS_HOSTED_SELF_TEST=1`.
- `SCANPLUS_HOSTED_FREE_ALLOWANCE_CONFIRMED=1` (an operator attestation, not an
  API-verified account balance).
- `SCANPLUS_OWNER_TEST_USER`, `SCANPLUS_OWNER_TEST_PASSWORD` (new private-test
  login; use an independently generated strong password, no values supplied).
- `SCANPLUS_SEARCH_PROVIDER=serper` (no fallback).
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`,
  `SERPER_API_KEY` (server-only existing provider configuration).
- `SCANPLUS_STRIPE_TEST=0`, `SCANPLUS_ENCRYPTED_REPORTS=0`.
- `SCANPLUS_OWNER_TEST_DATABASE_URL`: dedicated-role Neon DSN. The connection
  forces certificate verification, TLS channel binding and bounded SQL timeouts.
- `SCANPLUS_OWNER_TEST_RUN_ID`: the exact approved UUIDv4 grant, never generated
  or inserted automatically by application startup.

The separate start command, **only after approval and secure setup**, is
`sh deployment/owner-live-start.sh`. No current deployment selects this script.
Missing opt-in, invalid host/login, missing credentials or conflicting payment
configuration refuses startup. Syntactically valid credentials do not prove an
account is usable. Do not display or claim “live ready” until a separately
approved real test succeeds.

## Separate allowance setup after approval

Review and apply `migrations/002_owner_test_allowance.sql` with its included BEGIN/COMMIT transaction
against the exact authorized database. It creates a new table/function only and
revokes their default PUBLIC access. It does not modify the existing encrypted
storage schema or create any account, role or grant. A name collision fails;
do not replace an existing table/function without inspecting it.

Use an owner-reviewed dedicated app role with USAGE on schema `scanplus` and
EXECUTE on `scanplus.consume_owner_test_allowance(uuid, text)` only. Explicitly
verify actual role membership, ownership, inherited permissions and any existing
default-privilege grants; revoking PUBLIC alone does not prove least privilege. It must not
own the function/table or have CREATE/INSERT/UPDATE/DELETE rights. The function
must be owned by a trusted operator role. Never give the app an owner/admin DSN.
After reviewing the exact test and allowance, the operator may insert one new
UUIDv4 row with `enabled=true` and a short expiry (for example 30 minutes).
The schema rejects lifetimes over 24 hours. No production UUID or fixture grant
is provided in this repository. A duplicate ID must not reset old counters.

Verify the role cannot insert or reset grants, the same run survives a worker
restart, missing/expired grants cause no provider dispatch, and a reservation
is committed before its provider request. Do not perform a real SMS/search as
part of database verification without the separately approved in-page consent.

## Verification

Run the existing full Python suite, build and all UI suites. The new
`tests/test_hosted_self_test.py` covers strict configuration, disabled defaults,
unchanged demo startup, exact HTTPS/auth/origin/CSRF/body gates, explicit consent,
phone-bound verification, a complete mocked scan and export, wrong-session and
expired access, global budgets, uncertain SMS, search throttling, idle cleanup
and secret minimization. `tool/test_hosted_live_ui.js` covers browser expiry,
late responses, spent allowance and timeout uncertainty. These use synthetic
numbers and mocked transport, never real provider calls.
`tests/test_owner_test_allowance.py` also checks reopen/restart, concurrent
reservations, missing/expired/disabled grants, connection failure, uncertain
commit, fixed bound SQL and no automatic schema/grant creation. Its SQLite
driver emulator is not proof of PostgreSQL function or permission behavior.

Hosted TLS/proxy behavior and real account/provider acceptance still require a
separately authorized deployed acceptance test. The new page passed rendered iPhone 17 / iOS 26.3 Safari QA with the isolated
synthetic runner on November 8, including wrong code, required search consent,
three-source report, manual checklist validation, visible errors and Clear.
Rendered desktop QA remains unrun. These screenshots and checks do not establish
real provider, login, ingress or database behavior.

### Isolated rendered-browser QA

Run `.venv/bin/python -B tool/hosted_fixture_server.py --port 4177` from this
checkout, then open `http://127.0.0.1:4177` in the dedicated test browser. A visible
**SYNTHETIC BROWSER QA ONLY** banner distinguishes the fixture from live testing.
Only `2025550147` is accepted; code `123456` approves the synthetic challenge and
`000000` exercises the unapproved-code path. Search produces three synthetic
matches. Do not open external result or guide links during fixture QA.

The runner uses an explicit fake allowance and provider transport, reads no
credential configuration, and blocks outbound socket connections. Its HTTP
adapter supplies fixture ingress/auth headers and removes Secure from the
fixture cookie only. It therefore does not prove real HTTPS/proxy behavior,
Basic login, provider acceptance or PostgreSQL permissions. It is never imported
by either deployment entrypoint. Stop it with Ctrl-C when QA finishes; restart
only this fixture process to reset its synthetic allowance for another test.

At the November 8 verification pass, no PostgreSQL server or CLI was found on
the checked PATH or standard Homebrew/Postgres.app binary locations. Nothing was
installed. Actual PostgreSQL tests remain unrun; the mocked ledger tests are not
a substitute for them.


### Desktop QA attempt limits

The November 8 desktop attempt could not render the page on the Mac: the browser
API listed no browser and rejected both Chrome and in-app browser creation.
A separate cloud attempt transferred only the three static UI source files
internally with matching SHA-256 hashes. Cloud Chrome was available, but both
browser and shell localhost connections to the synthetic server were refused;
no supported local mapping was available. No public endpoint, credential, real
provider or external database was used. Desktop rendering remains unverified.
Both synthetic servers were stopped after these attempts.

Offline UI checks also cover unreadable/non-JSON and null server responses.
These now produce a sanitized uncertainty warning and never automatically retry
an operation; raw parser/response details are not shown to the user.

### Additional synthetic visual scenarios

The isolated runner accepts `--scenario matches` (default), `--scenario empty`
(three valid empty responses) or `--scenario unavailable` (one synthetic HTTP503,
then two explicitly unattempted sources). The banner labels the scenario. All
use the same reserved number/code, mock-only transports and blocked outbound
network. Stop only the controlled fixture process before changing scenarios;
never reset a live test allowance. These choices do not change production code
or qualify real provider behavior.
