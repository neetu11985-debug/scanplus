# ScanPlus per-listing removal permission

## What this change does

Prepared against `neetu11985-debug/scanplus` main commit `5b60d4181dc70d6d34e3b04d087d9ffde7a4af04`.

The main phone field is now editable. Any number other than the reserved example receives only a local format check, is cleared afterward, and causes no API call. The form does not name the editable input, so native form fallback cannot serialize it. The later November 7 entry-flow fix removes the duplicate browser-only panel and advances non-example entries to an explicit live-lookup-unavailable screen. See README.md for the current behavior. This is not a real scan.

The synthetic report now has a separate permission screen for one fictional listing. It names the local recipient, exact reserved phone/listing data, purpose, scope, cost, retention and cancellation limits. Both confirmations start unchecked. Cancel invalidates the permission; nothing is submitted by opening the screen.

The server issues a five-minute permission token bound to the current session, report, listing, disclosure and version. Current demo verification, checkout, active identity, CSRF and same-origin checks remain required. Arbitrary data fields, live providers, stale or cancelled tokens, another user's listing and malformed Unicode tokens fail closed.

An authorized POST makes one local adapter call and saves a synthetic receipt. Retries return that same receipt. An uncertain outcome stays uncertain and is not automatically retried. Polling is read-only: it never advances to “removed.” A receipt is not deletion evidence. Old polling-based demo completion claims are no longer exported as evidence. Requests already recorded cannot be cancelled as if they were unsent.

This is provider-neutral preparation, **not a live broker API integration**. The only allowed adapter is the existing local fixture; there is no live-enable switch, invented endpoint or provider credential. Real report/manual guide paths are unchanged.

## Apply and test locally

The accompanying patch changes only ScanPlus. It does not push, commit or deploy anything.

1. Make a clean branch or backup of the ScanPlus checkout at the base commit above. If main has moved, review the differences before applying.
2. Run `git apply --check scanplus-removal-consent.patch`, then `git apply scanplus-removal-consent.patch` from the repository root.
3. Use the project's Python environment with `requirements-render.txt` installed. Use its existing npm dependencies, or `npm ci` in the normal development workflow. No provider secrets are required for these tests.
4. Run `python3 -m unittest discover -s tests -v`, `npm run build` and `npm run test:ui`.
5. Run the optional rendered QA with `python3 tool/qa_removal_browser.py` on a development computer with Playwright and Chromium installed. `PLAYWRIGHT_CHROMIUM_PATH` can select an installed Chromium. The script starts its own temporary local server with in-memory synthetic storage, blocks external page requests, and writes local screenshots and a report. It does not target Render.
6. Start `server.py` in demo mode and review the report using only the displayed reserved phone and test code. Try cancel, missing confirmation, duplicate clicks, reload, clear session and repeated status checks. No external provider submission should occur.

Application and deployment are the owner's steps. Do not deploy this patch as a claim of production readiness. Render's current synthetic staging guards remain intact.

## Verification

- Full Python suite: 316 tests passed, no skips.
- Build: Python/JavaScript syntax and TypeScript check passed.
- All existing offline UI suites plus the new removal-consent DOM suite passed.
- Independent read-only security review found a non-ASCII token error path; it was fixed and tested. Review found no remaining blocker for this synthetic-only scope.
- Rendered desktop/mobile QA: **not run successfully**. Chromium failed before loading the app because this execution environment forbids its local process socket. The script is supplied for execution in a supported development environment. Offline DOM tests are not visual or accessibility proof.
- No real numbers, SMS, search queries, external removal APIs, payments, credentials, database calls to Neon, GitHub writes or deployment were used for this change. Python gateway/database suites use fakes and local fixtures.

An initial full-suite run used a Python interpreter missing psycopg and failed dependency imports. The suite was then rerun using the existing project dependency environment; the final result is the relevant regression evidence. An initial UI harness failure from separate pagehide listener registration was fixed by keeping input and consent cleanup together.

## What blocks a real removal test

No permitted direct broker removal API is configured or verified. A possible partner service is not an API contract or permission to send customer data. Account creation, commercial terms, fees, credentials and personal-data transmission require their own owner/customer approvals.

Before any real end-to-end removal test:

1. Select a permitted provider and verify its official API/partner contract, allowed purpose, supported sites, payload, status semantics, authentication, test environment and cost. Do not invent an API or automate consumer suppression tools contrary to their terms.
2. Implement a separate reviewed adapter with fixed trusted destinations and secrets only on the server. Display the actual recipient, exact required data and purpose for the one reviewed listing. Material changes require new consent. Phone control alone does not establish listing ownership; CAPTCHA, email and identity verification must follow the provider's supported flow.
3. Replace demo identity and disposable sessions with production authentication and an approved encrypted audit/outbox design. Never insert a live HTTP call into the current SQLite transaction: an external side effect could succeed even if local commit fails. Persist an idempotency key before dispatch, reconcile ambiguous results and define retention, withdrawal, deletion and access controls.
4. Add provider contract tests and staged sandbox checks for success, rejection, timeout after acceptance, duplicate/replayed submission, rate limit, cancellation where supported, webhook authentication and evidence-backed verification. “Submitted,” “pending,” “needs verification,” “unknown,” “failed” and “verified removed” must remain distinct. A missing search result or success HTTP code is not independent removal evidence.
5. Complete desktop/mobile/accessibility review and owner-approved deployment. Then obtain a consenting test user's approval for the exact live data/recipient and run a limited test. Verify the actual listing after the provider's processing period before reporting removal.

Current feasible next step: local or owner-deployed **synthetic consent-flow testing**. Real removal testing remains blocked by the provider contract and production submission/authentication work above.
