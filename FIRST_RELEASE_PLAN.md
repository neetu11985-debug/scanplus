# ScanPlus: first release plan

Prepared 8 November 2026 from the current local source. See [MORNING_RELEASE_REVIEW.md](MORNING_RELEASE_REVIEW.md) for the completed simulator checks, later 393-test checkpoint and current go/no-go recommendation. This plan does not authorize publication, provider calls, account changes or charging customers.

## Release decision

The current app is a synthetic demo plus separate private testing paths. It is **not ready for a public paid launch**. The fastest defensible first release is a small, invited, free owner-testing pilot after the live-operation gates below pass. A five-scan no-SMS local test is a development tool, not the customer release.

Recommended first-release promise, subject to product approval:

> Check selected indexed sources for possible listings of your verified phone number, see exactly what was checked, and follow official self-service removal instructions.

Do not promise a complete Internet scan, identity matching from a phone alone, automatic deletion, guaranteed removal, or fewer spam calls. Search indexing can miss or retain stale listings. Self-service opt-outs are normally free. The current three-source scope is Spokeo, TruePeopleSearch and Whitepages via Serper-indexed results, not direct access to those brokers' databases.

Market comparison and customer-preference research should validate the proposed emphasis on trust, clear scope, low effort and useful proof. These are product hypotheses, not findings established by the code review. Do not invent survey results or treat competitor feature claims as evidence of customer preference.

## Phase 0: finish the private owner test

**Purpose:** prove the real connection and report are useful before recruiting customers.

- Preserve the existing running test and its spent allowance. Do not reset or restart it to add attempts.
- The explicitly configured local tool supports up to five same-number scans and at most fifteen attempted queries in a process. Every scan requires fresh consent. Failure counts; Clear/reload cannot refill the allowance. A restart is a new approval and budget, not a durable spending limit.
- Complete the owner-run DNS/TLS check and confirm the actual remaining free allowance/no paid top-up before any further approved test. TLS success alone does not prove API acceptance, billing state or usable results.
- Read the existing approved private properties file in place. Never copy credentials into source, browser code, a report or a command argument.
- Review a real successful response, a no-indexed-match response and an unavailable response without overstating what each proves. Record only safe category/status diagnostics.
- Review the current PDF/plain-text report, source URLs, timestamps, limitations and manual-removal steps. The illustrated roadmap is guidance, not screenshots of validated current broker forms.

**Exit gate:** owner confirms the report is understandable; real provider behavior and costs are evidenced; errors are actionable; no unapproved transmission or paid usage occurs. A failed lookup is not a no-match result.

## Phase 1: first invited release, free and bounded

**Scope:** a small approved tester group, verified own-number search, three stated sources, honest outcomes, PDF/plain-text report, official manual guides and explicit deletion/expiry controls. No subscriptions, automatic removals, household/address enrichment, AI, native app or background monitoring.

Required work and acceptance:

1. **Ownership and abuse:** qualify real SMS delivery and number/session binding, expiry, invalid codes, repeated attempts and recovery. Add/review public-facing fraud/rate/spend limits before admitting anyone beyond the private owner. Self-attestation and a shared Basic login are not customer authentication.
2. **Provider and budget:** verify permitted use, recipients, retention and actual unit cost. Maintain per-query/provider consent, commit-before-dispatch limits, no automatic retry/fallback and truthful coverage. Verify allowance persistence and least-privilege roles in the selected deployed database, including restart/concurrency and uncertain commits.
3. **Report:** show which sources were attempted, usable/unavailable counts, exact listing links and timestamps. Require the customer to confirm a listing is theirs. A manual-request checklist must never become verified deletion. Handle long/untrusted content safely in UI and downloads.
4. **Privacy:** finalize operator identity, contact, purpose/recipient notices, retention and deletion behavior. Validate actual host logs, backups, TLS, secrets, access restrictions and cleanup. The app must not collect unnecessary names, addresses or personal snippets.
5. **Experience and recovery:** complete final rendered desktop/mobile, keyboard, focus, error visibility, back/refresh, interrupted requests, expired/cleared downloads and repeated-action checks. Lightweight DOM tests are not rendered-browser proof.
6. **Support and operations:** provide a clear unavailable/failed-scan explanation, support channel and incident stop procedure. Do not collect sensitive reports by default for support.

**Exit gate:** every required journey below passes on the exact reviewed build, launch owner approves scope/claims/privacy, and publication is explicitly authorized. Keep the initial audience and provider budget bounded. Pilot findings determine expansion; do not set a launch date by ignoring a failed gate.

## Phase 2: paid one-time release, only after the pilot

Validate willingness to pay and full unit economics first: verification, failed lookups, search, hosting, processing, refunds and support. The code's current intended $1.49 quote is not proof of profitable pricing or customer demand.

Use a selected, approved production payment provider with signed callbacks, immutable order amounts, idempotency, lost-response reconciliation, refunds/disputes, secure return-user access and legally reviewed policies. Test the provider sandbox end to end before enabling live charges. Current Stripe code is test-only; the older Poynt contract is not an operational alternative.

Define what happens for unavailable/no-result scans and non-delivery before charging. Do not sell free opt-out access as the paid service. No subscription or recurring charge is implied.

**Exit gate:** actual merchant/provider approval, payment/refund evidence, understandable pricing/policy, approved retention/recovery and explicit limited paid-launch decision.

## Phase 3: expand only from evidence

Consider more sources, supported partner removal integrations and consented recurring rechecks only after confirming demand, source permissions, accuracy, costs and operational capacity. Each new provider adds disclosure, matching, error, budget and privacy tests. Never automate CAPTCHA or identity checks, or claim verified removal from request submission alone.

## Required release journeys

- New user understands scope, sends no phone before explicit provider consent, verifies own number, receives an accurately labeled report.
- Wrong/expired code, rate limit and provider outage fail clearly, without a retry loop or budget reset.
- No indexed match is distinct from a failed or unattempted source; no false completion or deletion claim appears.
- Clear, expiry, browser Back/refresh and lost responses cannot restore expired private content or create duplicate operations.
- Other sessions cannot read reports; stale report actions cannot affect a newer report. Downloads recheck authorization/expiry after rendering.
- Manual guide links open only on deliberate action, and checklist progress remains explicitly unverified.
- Public/demo/default entrypoints remain unable to enable private live or no-SMS testing by accident.
- Deployment records the exact approved commit and passing CI; rollback/disable steps preserve financial and quota integrity.

## Work completed in this readiness pass

- Preserved the completed illustrated PDF guidance and report security checks.
- Fixed accidental session-cookie collisions between local no-SMS test ports. This prevents browser cookie overwrites; it is not a security boundary against other localhost services.
- Malformed non-ASCII session/CSRF tokens now reject as unauthorized/forbidden rather than producing an internal error.
- Added two-server synthetic regression tests covering cookie separation, foreign/legacy-cookie rejection and invalid-token recovery.
- Left the owner's running 4176/4178 processes, budgets, providers, credentials and deployment unchanged. Backend fixes apply only on a future authorized launch.

The release candidate is not yet a commit: local branch `feature/removal-consent-input-test` is based on `2dd5d81f50e000026fafc559aef6b7c58840909c` with accumulated uncommitted changes. Preserve and review those changes. Do not merge to main merely to publish this plan; main is reported to trigger deployment.

## Decisions and evidence still needed

- Final product/brand name and domain: the repository says ScanPlus while several screens say ScanMyDigits.
- Intended audience and geography, exact first-release promise, initial tester group and support/legal identity.
- Current provider permissions, live SMS/search success and billing evidence.
- Selected hosted entrypoint, actual database role/TLS/retention/restore checks and public authentication/abuse design.
- Final rendered desktop QA and recheck of the exact combined build. Prior iPhone synthetic-flow evidence does not establish live integration readiness.
- Product research conclusions and pricing choice. Keep these separate from code-test results.

## Verification of this combined local source

On 8 November 2026, the final combined local code passed **388 Python tests**, **10 UI harness suites**, syntax checks for **84 Python files and 15 JavaScript files**, TypeScript checking, and `git diff --check`. The commands were:

```sh
PYTHONDONTWRITEBYTECODE=1 SCANPLUS_DB_PATH=:memory: python -B -m unittest discover -s tests -q
npm run test:ui
npm run build
git diff --check
```

Tests use synthetic transports, temporary stores and isolated loopback fixtures. The three new isolation tests also received an independent read-only review and passed with the existing focused local suites (27 tests). These results do not establish current provider acceptance, real customer authentication, production payment/refund operation, deployed database permissions or final rendered-browser quality.
