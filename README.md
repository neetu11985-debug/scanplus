# ScanPlus — local website MVP

A standalone, synthetic-data web prototype prepared November 2, 2026. Provisional brand; not a live scanning or removal service. Target launch Friday November 6 is a goal, not an established readiness claim.

## Repository safety and hosting

This repository contains application source and synthetic tests only. Local
credentials (`scanplus.local.properties` and `.env`), databases, logs, report
exports, screenshots and historical test evidence are intentionally excluded.
References to `evidence/` below describe local-only verification records.

The app requires a Python backend. Netlify static hosting alone can display the
frontend but cannot run these Python API servers, enforce verification/payment,
or complete report flows. No Netlify deployment configuration is included.
Do not set the repository root as a static publish directory. Public deployment
requires a separately reviewed backend and the launch gates documented below.

## Run tonight

Requires Python 3.11+ (tested on 3.14.7). No dependencies or install step.

```sh
cd scanplus
python3 server.py
```

Open http://127.0.0.1:4173 . Use the fixed reserved number +1 202-555-0147, check the demo declaration, and enter **246810**. Complete the $0 test checkout to see the report. Expand site guides. Expand the synthetic automation panel, authorize the fictional request and check its status twice. No SMS, payment, search query or removal submission leaves the server. External guide links open only on deliberate clicks and contain no phone number. Use Clear session to restart. Reload resumes the current unexpired demo step. Clear session deletes the demo record.

If the port is busy, `PORT=4174 python3 server.py`. Stop with Ctrl+C. Local sandbox may require loopback permission; this is not permission to expose the server publicly. The Python HTTP server is for local testing only.

## Checks

```sh
python3 -m py_compile *.py
node --check static/app.js
python3 -m unittest discover -s tests -v
```

Node is needed only for the optional JavaScript syntax check, not to run the app. No bundler or build artifact is required: static files are served directly. No dedicated lint package is installed; syntax checks are not a full lint pass. See evidence/QA.md for exact results and unrun checks.

## Architecture

Vanilla HTML/CSS/JavaScript + Python standard-library JSON backend. No AI, external fonts, analytics, npm dependencies or background external work. `providers.py` defines discovery/removal contracts, three candidate official removal guides, fixture discovery, disabled live removal, and a fictional automatic-removal adapter. `payments.py` separates the server-owned, idempotent demo payment boundary from a fail-closed GoDaddy placeholder. `server.py` gates report access on verification and test checkout. The fixed fixture number is enforced server-side; changing browser inputs cannot query a real number.

Session cookies are random, HttpOnly and SameSite Strict, with a configurable 15-minute default lifetime. SQLite stores hashed session/CSRF tokens, a hash of the synthetic number, verification expiry/attempt/consumption state, a per-session report ID, test receipt and simulated removal job state. No raw phone, OTP, card or raw nonce is persisted. Reload resumes the appropriate demo step. Clear session deletes its record; restart preserves unexpired records. Downloaded JSON remains on the tester’s Mac independently. Demo HTTP cookies are not Secure; HTTPS WSGI cookies are Secure. No real personal data is enabled; this is not encrypted storage and does not establish production privacy readiness. See SECURITY.md for limits, deletion and configuration.

API: POST /api/start, /api/verify, /api/checkout, /api/removal, /api/removal/status, /api/clear; GET /api/report. POST requires a configured/loopback host, same-origin Origin and session-bound CSRF token after starting. Session bootstrap rotates the token; stale tabs must reload. Checkout amount is server-controlled, repeated demo checkout returns the same receipt, and report access never trusts a browser payment flag. There is no production payment route. A separate opt-in Stripe sandbox flow now implements signed test webhooks and server reconciliation; see [STRIPE_TEST.md](STRIPE_TEST.md). It does not enable live charging or qualify production payment capture.

## Honest coverage and removal

Two example listings, one unqueried source, zero live sources checked. No real listing URLs exist. The official destinations are supported by the brokers’ California Data Broker Registry filings (registry updated October 30, 2026; reviewed November 6). They are not validated removal integrations. Direct research access to current forms was blocked/unreadable; current form workflows must be manually verified before production. Instructions deliberately defer to the site's current official flow. There is no verified broker removal API in this release. Website restrictions must be established from actual terms/API access, not inferred from a blocked research tool.

Only a fictional provider can submit a simulated request. State progression: not requested → request submitted → pending → removal confirmed. All labels retain demo context. Real adapters must establish official authorization, per-listing match confirmation and explicit customer consent. Phone possession does not prove a historical/recycled/household listing belongs to the customer. CAPTCHA, identity and email verification must remain guided customer actions. No bypasses. PeopleConnect is not in this catalog: name-search suppression is not proof of phone-search removal. Its [terms](https://peopleconnect.us/terms-of-use/) restrict the suppression tool to personal non-commercial use and prohibit commercial/third-party service automation; do not add a paid connector absent separate permission.

Listings are not evidence of a spam caller's source. No promise of comprehensive coverage, guaranteed deletion or fewer calls. Self-service opt-outs are usually free; the intended $1.49 one-time price must describe bounded discovery/report convenience, not paid access to free opt-outs.

## Deployment choices and unresolved hosting

Protected disposable Render Free staging is prepared in [deployment/RENDER.md](deployment/RENDER.md). It requires an owner-set private login, forces synthetic-only operation and disables Stripe. It is not yet deployed; no online or production readiness is claimed.

Keep OwnlyAI and aiclubusa.co unchanged. Use a separate product domain/directory chosen with Rajesh. No public deployment, account creation, payment or credential creation was performed.

Preferred: inspect the existing GoDaddy product, Python version, application/WSGI support, HTTPS, outbound HTTPS, scheduled jobs and secret storage. GoDaddy's software support table lists Python for certain cPanel/Plesk offerings; this does not identify the user's plan or establish that this server can run there. Never upload this local HTTP server as production as-is.

If the plan supports a maintained Python WSGI app: retain the static UI and adapter boundaries, use the tested WSGI entry and replace the development socket runner with the host’s managed WSGI process, configure the host's process manager, and verify SQLite support, locking and a private writable store location. If it is WordPress-only, either implement the backend as a carefully scoped WordPress plugin with the same gates or keep GoDaddy domain/DNS and use a separately reviewed backend service. No new hosting purchase is implied. Static hosting alone cannot enforce ownership or payment.

GoDaddy Poynt Collect is a candidate custom checkout; developer/merchant test setup and contract-dependent API rates need verification. Do not substitute a generic payment link redirect for server verification of an order. Source references: [Poynt setup](https://docs.poynt.com/app-integration/poynt-collect/getting-started/), [Poynt pricing](https://docs.poynt.com/app-integration/poynt-collect/pricing.html), [GoDaddy fees](https://www.godaddy.com/help/what-are-the-charges-and-fees-for-godaddy-payments-40617), [hosting software](https://www.godaddy.com/en-uk/help/software-versions-installed-on-web-hosting-cpanel-windows-hosting-plesk-and-managed-hosting-for-wordpress-accounts-897), [FTC people-search guidance](https://consumer.ftc.gov/articles/what-know-about-people-search-sites-sell-your-information). These references do not verify this account's configuration.

## Friday launch checklist — blockers

- Confirm separate domain, provisional brand and actual legal merchant/support identity. Rajesh plans to register the domain himself.
- Inspect existing GoDaddy plan read-only; establish supported production runtime, HTTPS, secrets, backups and separate deployment location.
- Configure approved real ownership verification with expiry, resend/attempt limits, abuse controls, replay protection and recovery. Never ship the fixed demo code as verification.
- Establish permitted discovery access, source coverage and costs. Obtain explicit disclosure/consent before sending a phone to a search provider. Define match needs confirmation, not found in checked sources, and source unavailable separately. Show exact source links and timestamps; do not show unrelated household history.
- Validate each official removal flow. Enable automation only with a supported permitted API and explicit per-listing authorization; otherwise use guides. Verify removal independently of submission.
- Merchant onboarding/terms and production secrets require the owner's involvement. Implement signed server-side callbacks, amount/currency/order validation, duplicate/replayed callback handling, idempotency and reconciled order state. Test success, decline, cancellation, duplicate callback, timeout and refund in the real gateway sandbox. Charge only for an available service; plan no-result/unavailable refunds clearly.
- Finalize honest $1.49 scope and unit economics, refund/support/privacy/retention/deletion policies. Review recycled/shared number handling. Confirm production TLS, cookie/proxy configuration, approved sensitive-data storage, host concurrency/limits, backups and retention scheduling. The local synthetic foundation supplies CSRF, SQLite state and request limits; real integration behavior remains unqualified.
- Repeat desktop/mobile and accessibility checks against the final production build; staging review, explicit publishing decision, then limited monitored launch. No claim of readiness until these gates pass.

## Adapted project skills

User-authorized adaptations live under `.agents/skills/scanplus-verify` and `scanplus-release-review`. They derive from the actual OwnlyAI local feature, verification and release review skills; no app code, models, credentials or data were copied. Original files remained unchanged. The original `.agents/OWNLYAI_ROUTING.md` explicitly calls these original guidance, not copied from an unconfirmed Replica toolkit. These are the concrete local skills found and used.

## Stage 2 update: offline contracts and WSGI

See [CONTRACTS.md](CONTRACTS.md). `discovery.py` now builds/parses the verified Brave Web Search schema behind a synthetic-only injected transport, with bounded source matching and privacy-minimized candidates. `poynt_contract.py` adds an offline request/reconciliation harness with nonce/order/transaction replay guards and failure tests; it is not a real gateway and is not wired to demo routes. Live transports and credentials remain disabled. Existing provider/removal demos are unchanged.

`wsgi.py` supplies a shared PEP 3333 application entry without Flask or any new package. It is demo-only and does not qualify deployment by itself. A confirmed host WSGI manager may import `application`; exact GoDaddy product/interpreter and host storage configuration remain blockers. WSGI invalidates expired records immediately and deletes them on request; use the maintenance command for idle scheduled cleanup.

Updated syntax command: `python3 -m py_compile *.py`. The tests now include offline Brave response/error handling, payment replay/timeout/mismatch behavior, and the WSGI validator/full demo journey. None call an external API.


## Stage 3: durable demo and security foundation

See [SECURITY.md](SECURITY.md) and [LAUNCH.md](LAUNCH.md). Standard-library SQLite is verified locally (3.53.4), with transactional sessions, per-session reports/jobs, durable test receipts, durable offline payment reservations/replay claims, configurable expiry, CSRF/origin/host checks, bounded requests and rate counters. No service/framework added. `ownership.py` implements a synthetic-only Twilio Verify schema boundary; it cannot send SMS. Live startup remains refused and live WSGI requests return 503.

Run `python3 maintenance.py` for expiry deletion (or configure that command in a host scheduler after the plan is confirmed). The default local store is `.data/scanplus-demo.sqlite3`; keep it private and do not upload databases or host the whole project as static files. `.data` is excluded from source synchronization. Current tests and browser evidence are in evidence/QA.md and evidence/stage3-tests.txt.

## November 3 quality gates and new requested behavior

Gate records live in `evidence/tollgates-2026-11-03/`. Same synthetic user's successful verification in another session revokes prior report/API/export access. Independent users are tested with a second reserved fixture through service tests; the ordinary UI retains the original sample. Existing records are preserved until normal expiry; old pre-upgrade verified sessions need re-verification.

Pre-checkout copy now discloses a **proposed** voluntary seven-day refund less verified original processing fees, subject to legal/provider exceptions and final review. The report offers an authenticated **$0 test refund request** only. `refunds.py` is a separate offline contract harness: original-payment ownership, deadline, actual provided fee, currency agreement, one request/idempotency, original-method destination and pending/failed/succeeded/manual-review states. Unknown fees/currency, prior partial refund or duplicate/non-delivery/mandatory-remedy categories require review; no legal remedy is automatically denied or fee invented. Bank chargebacks are a separate bank/card dispute process, not this voluntary request. No real refund integration, signed settlement/webhook verification or finalized public legal policy exists.

Export now uses `/api/export` with server authorization and attachment headers rather than exporting a possibly revoked cached report. The controlled local quality probe is `python3 tool/quality_probe.py`: it uses temporary SQLite stores and two synthetic identities, never the preview database or external services. Its figures do not establish production capacity.

## Demo return after session expiry

Receipts created by the new demo are retained independently of sessions for eight days by default. After session expiry/sign-out, verify the same reserved sample again to see synthetic payment history without paying again. Request an eligible $0 refund there. The exact voluntary deadline is seven elapsed days inclusive; exception categories require review. Fresh verification and the active same-user binding guard history/refund access. Explicit synthetic-history deletion is separate from Clear session. Existing receipts that had already expired/pruned before this feature cannot be recovered; no recovery is fabricated.

New routes: GET `/api/history`, POST `/api/history/delete`; POST `/api/refund` can reference an owned retained synthetic payment after fresh verification, without a new checkout. Retention is controlled by `SCANPLUS_DEMO_HISTORY_TTL`; it is not a real financial/legal retention policy. The separate offline partial-refund harness tests actual supplied fee/currency and an explicit synthetic reviewer full-refund override; that override has no public HTTP route and cannot trigger a live refund.

Latest scoped evidence: `evidence/return-journey-2026-11-03/`. HTTP attachment bytes are now saved and parsed during a test; this is distinct from confirming an OS browser-download save location. Live provider, physical-device and production tests remain blocked.


## Browser-only number-entry test — November 6

The workspace now offers **Enter my own number · input test only** independently of the synthetic demo. It checks an international-style +country-code number locally in the browser, shows only its final four digits after acceptance, and clears the input. Explicit clearing, closing the panel, and leaving the page also clear the entry. ScanPlus does not send it to the backend, save it in browser storage, verify ownership, or use it in synthetic reports. This is a syntax/entry test, not phone validity, reachability, or online discovery. Browser/autofill behavior outside the app is not controlled.

The backend fixture restrictions, offline Brave/Twilio contracts, and no-live-mode guard remain unchanged. A real self-lookup needs a separately authorized provider setup, disclosed phone transmission, and verified ownership before search. Run `node tool/test_phone_entry.js` for the focused input/privacy regression in addition to existing Python tests and syntax checks.

## Local live self-test implementation — November 6

A separate, disabled-by-default API-backed discovery path is available in `local_live_server.py` and `live_scan.py`. It supports Twilio Verify ownership followed by separately consented Serper Google Search queries and real source URLs. Serper is the default selected no-card search route; Brave remains an explicit alternative, never a fallback. It preserves provider-specific consent, with memory-only phone state, no checkout/removal, and no synthetic fallback. Existing `server.py` and its demo are unchanged. Provider setup, recipient approval, secure credentials and live validation remain pending. See [LOCAL_LIVE_TEST.md](LOCAL_LIVE_TEST.md) before enabling anything. Passing its synthetic tests is not proof of a real scan.

## November 6 implementation: useful reports and 99-cent pricing

The local provider-backed path now produces a readable report and JSON download with source timestamps, indexed-match/absent/unavailable distinctions, ownership review for each listing, and site-specific official manual instructions. Download routes recheck the current session and report expiry. The app never opens listings or submits requests automatically. Listing URLs can contain personal information; downloads remain on the device after Clear or expiry.

A customer can mark a listing as theirs/not theirs, or record that they manually submitted a request on the official site. Those are local checklist entries only. They never become independently verified removal, never enable automated submission, and never call a provider. Report-specific listing IDs prevent an old tab from applying its decisions to a replacement report. Repeated confirmation preserves recorded progress.

No supported, permitted no-paid-services removal API was verified. Current automated removal count remains zero. Official destinations are confirmed from primary registry filings; current form interactions are not independently verified. Follow-up checks and CAPTCHA/email/phone/identity steps remain manual.

New synthetic checkouts now quote **$1.49 USD, one time**, with optional server-owned coupon mechanics and **$0 actually charged**. No active code or invented offer is included. Old receipts remain unchanged. See `PRICING.md`.

See `IMPLEMENTATION_STATUS.md` for delivered behavior, exact local evidence and remaining live-testing gates. Run the full regression suite plus `node tool/test_pricing_ui.js` and `node tool/test_report_ui.js`. No provider setup, credentials, real query/SMS, removal submission, payment, hosting migration or deployment was performed.

## Paste local provider keys without Terminal

See [LOCAL_KEYS_SETUP.md](LOCAL_KEYS_SETUP.md) for the empty owner-private
`scanplus.local.properties` file and double-click TextEdit, offline check and local
start launchers. Live startup remains disabled by default. The loader parses values
as data, never prints them, and passes them directly in server memory. This is
plaintext local storage, not encryption or Keychain. Account/credential entry and
live SMS/search approvals are still the owner's steps; no real key or provider was
used to build or test this setup.

## Stripe sandbox Checkout

A separate [Stripe sandbox flow](STRIPE_TEST.md) is implemented at `/stripe-test`, linked from the demo. It uses hosted Stripe test Checkout, fixed server-owned $1.49 USD pricing, idempotent orders, signed webhooks, and server-verified report access. Default operation remains offline; test keys are environment-only and live keys/mode are rejected. Existing demo checkout and refunds remain separate. Automated coverage uses only mocked transport. Actual Stripe account setup, sandbox gateway validation, refunds, production authentication and launch review are still pending. No real payment or Stripe API request was made during implementation.
