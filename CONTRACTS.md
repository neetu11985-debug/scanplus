# Offline integration contracts — stage 2

## Brave Search

Official references inspected November 2, 2026: [Web Search API reference](https://api-dashboard.search.brave.com/api-reference/web/search/get), [getting started](https://api-dashboard.search.brave.com/app/documentation/web-search/get-started).

The documented GET endpoint is `https://api.search.brave.com/res/v1/web/search`; authentication uses `X-Subscription-Token`. Implemented query fields: `q`, `count`, `result_filter`, `text_decorations`, `extra_snippets`. The parser reads `web.results` with `title`, `url`, and `description`. This is a web-index search, not a broker database integration.

`discovery.py` implements request construction, response normalization and error mapping behind an injected transport. It imports no HTTP client. Only `SyntheticTransport` and the reserved fixture number are allowed; a caller cannot enable networking by setting a key/environment variable. Nothing is connected to the public demo routes. Scope is three allowlisted catalog domains, one query, at most ten entries, no retries.

A returned candidate needs an exact formatted phone sequence and a same-source HTTPS link. Query strings/fragments are removed; titles/raw snippets and household/address attributes are discarded. The output exposes the source URL, a generic phone-text-evidence statement, and `match_needs_confirmation`; removal eligibility stays false. A recycled/shared-number candidate never proves identity. Exact matching may miss variants, unindexed pages or stale results; this adapter does not establish ownership or successful removal.

Empty results mean `not_found_in_checked_sources`; missing result structure, timeout, throttle and provider failure mean `source_unavailable`. No error is converted into an absence claim. URLs are links only: no page crawling, scraping or auto-opening occurs. Production still requires an approved provider account/terms, explicit phone-transmission disclosure, real control verification, and user-confirmed record matching. Provider retention, costs and service-level behavior remain unverified.

## GoDaddy / Poynt

Official references inspected: [Collect setup](https://docs.poynt.com/app-integration/poynt-collect/getting-started/), [nonce charging](https://docs.poynt.com/app-integration/poynt-collect/getting-started/nonce.html), [API reference](https://docs.poynt.com/api-reference/).

Collect produces a nonce; the server charges through `/businesses/{businessId}/cards/tokenize/charge` using OAuth bearer authorization. Documented payload areas include `action`, `context`, `amounts`, and `fundingSource.nonce`. The API standard headers include `Api-Version: 1.2` and `Poynt-Request-Id`. Transaction statuses distinguish authorization, capture, decline, refund and void. Setup requires developer and merchant identifiers; OTE and Test Lab environments differ.

`poynt_contract.py` is explicitly an **offline contract harness**, not a live gateway. No SDK, HTTP client, real nonce, token, card form, callback signature or production endpoint is enabled. It uses synthetic merchant identifiers and fixture-only nonces. The existing $0 demo checkout still uses `DemoGateway` and remains independent.

This historical offline gateway harness uses $1 USD synthetic orders, gated by verified control and available service. It is not wired to checkout. The current app’s intended price is $1.49 USD (see PRICING.md); any future real gateway must consume the validated server quote rather than this historical fixture amount. Each has a stable request ID. Duplicate submit does not call the transport again. Consumed nonces and transaction IDs cannot fund another order. A timeout leaves an uncertain order and prevents blind recharging. A trusted retrieval fixture must match the bound transaction, merchant/store, amounts/currency and captured state before an offline receipt is issued. Authorization or a client notification alone cannot mark payment complete. Reconciliation uses durable SQLite reservations and claims across harness instances sharing the store; refunded/voided results revoke its receipt.

**Unresolved contract details:** the large public API reference contains misaligned verb/heading examples, and the nonce example shows authorization status even alongside sale discussion. The GET retrieval route has a documented example elsewhere in that reference, but actual merchant sandbox behavior must be checked. No webhook signing schema was sufficiently established in this inspection, so none was invented. There is no HTTP callback route. Production must authenticate server retrieval, confirm the precise capture semantics and event contract, and test against the actual merchant sandbox. Without those checks, the harness cannot qualify real money movement.

**Durability update:** stage 3 stores orders, stable request IDs and hashed nonce/transaction claims transactionally in an explicitly supplied SQLite Store. Charge intent is committed before the offline transport, so a crash/restart leaves an uncertain order instead of repeating a charge. Session ownership gates both submission and reconciliation. Local tests cover restart, two connections/workers and cross-session access. The harness remains offline and requires actual sandbox validation, financial record/refund retention decisions and operator reconciliation before any real payment. A future network transport must release DB locks before remote I/O.

## WSGI / hosting portability

`wsgi.py:application` is a PEP 3333 entry point reusing the same handler, without opening sockets or importing Flask. Standard library only, Python 3.11+ syntax; verified locally on 3.14.7, not on GoDaddy's interpreter. WSGI tests use Python's validator and perform the complete fixture journey without a network listener. HTTPS uses Secure session cookies and same-origin checks honor the WSGI scheme supplied by the trusted host. Do not trust forwarded-scheme headers from arbitrary clients; configure the actual hosting layer correctly.

Entry point for host configuration: import `application` from `wsgi`, with this project directory on Python's module path. Serve at a separate domain root; subpath mounts deliberately return 503 because UI paths are root-relative. SCANPLUS_MODE other than demo returns 503. No live API is exposed by WSGI.

GoDaddy candidates: a cPanel plan with a supported Python application/WSGI manager may host this entry point after exact interpreter and environment verification. Plesk's advertised Python availability alone does not prove a suitable managed WSGI process. Managed WordPress/Website Builder does not establish arbitrary Python execution. The existing account product is unknown; do not deploy, upgrade, replace aiclubusa.co, or buy hosting based on this assessment.

The WSGI demo now shares a transactional SQLite store. Multiple workers must use the same private filesystem with reliable SQLite locks; that capability is unverified on the GoDaddy plan. WSGI invalidates expiry immediately and prunes on requests; schedule `python3 maintenance.py` for deletion while idle. The local loopback server also sweeps every 30 seconds. Before any public use configure production TLS/process supervision, session/abuse limits, durable payment/session storage, secure secrets, expiry cleanup, timeouts, sanitized host/proxy logs, support/refund policies and security review. Python's development HTTP server must remain loopback-only.


## Ownership verification contract

Official [Twilio start](https://www.twilio.com/docs/verify/api/verification) and [check](https://www.twilio.com/docs/verify/api/verification-check) docs were inspected November 2. The start POST is `/v2/Services/{ServiceSid}/Verifications`, with form `To` and `Channel`; check uses `/VerificationCheck` with `VerificationSid` and `Code`. Responses expose `sid`, `service_sid`, `to` and `status`; approval must come from the server-side check. `ownership.py` validates these fields behind a synthetic-only transport. Its challenge binds a session digest, number digest, provider SID, expiry and attempts; replay or different-session/number checks fail. No auth, credentials, SDK, SMS or live transport exists.

The existing demo uses an explicitly synthetic fixed code with separate durable expiry/attempt/consumption controls. It is never production ownership proof. To integrate Twilio later, configure the approved service/account/authentication and consent, persist the provider challenge binding, qualify failure/resend behavior and abuse protections in its actual sandbox, then replace the synthetic-only boundary deliberately. The entire application refuses live mode until this is explicitly implemented.
