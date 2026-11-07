# ScanPlus readiness and prerequisites — November 6, 2026

**Historical morning checkpoint.** Later same-day implementation and final test counts are in `IMPLEMENTATION_STATUS.md`. Its updated $0.99 pricing, report downloads and manual checklist supersede older scope descriptions below.

## Current verdict

**The local synthetic testing is complete for this code revision. Live testing and public launch are not complete.** A domain is useful for public deployment but does not enable the local SMS/search test or supply hosting, accounts, permissions, or production integrations. A public launch by morning cannot be promised from the current state.

The selected no-card search route is now implemented with **Serper**, behind the disabled local self-test. The ordinary demo remains synthetic. Brave is preserved only as an explicitly selected alternative, with separate consent and no fallback. No provider account, credential, payment, DNS, hosting or deployment change was made. No real phone number, SMS, search query, payment or removal submission was used.

## Completed on the Mac

- 84 Python tests passed: 76 previous tests plus 8 new Serper tests. Final result: `evidence/morning-readiness-2026-11-06/final-fixed-python-tests.txt`.
- JavaScript syntax passed for both apps; browser-only number-entry harness passed; live consent/repeated-click/error/clear/page-exit harness passed for both Serper and legacy Brave. Unknown provider fails closed in the UI. Evidence: `js-syntax-tests.txt`.
- Python AST syntax parsing passed for all 28 root/test/tool Python files. No new package installed. No dedicated lint/type-check framework exists here; syntax is not a full lint pass.
- Synthetic workload: all 240 authorized report reads passed across 2, 8 and 16 local workers; configured rate limits, Host, Origin, path traversal and cross-site rejection checks passed. Evidence: `quality-probe.json`. This in-process test with two synthetic identities is not production capacity or live provider performance.
- Direct startup with local opt-in removed refused to start, exit 1. Live demo mode and live WSGI refusal remain covered by regression tests.
- Focused review found a malformed Serper response could be mistaken for no match. Fixed with entry-shape validation and regressions. A test fixture boundary error was then corrected; the failed run is retained in `final-python-tests.txt`, and the passing replacement is `final-fixed-python-tests.txt`.

Coverage includes SMS ownership/session binding, expiry/attempt limits, consent gates, provider-specific consent, no retry/fallback, unknown/throttled/quota/malformed outcomes, safe source links, exact number matching, raw-data minimization, session isolation, cross-origin/CSRF protections, repeated scan and clear. Payment/refund tests exercise only the existing synthetic/offline contracts.

## Required for one real local no-card self-test

1. **Serper account:** owner-approved account, eligible active free credits, an API key through an approved secure setup route, terms/privacy review and confirmation no paid top-up is allowed. The public site currently advertises 2,500 free queries without a credit card, but the owner's eligibility and balance have not been checked. This is not a monthly/unlimited-free claim. The authenticated playground must confirm the current API contract before live qualification.
2. **Twilio Verify:** usable account/trial and Verify service, appropriate country/destination permissions, destination verification if the trial requires it, remaining allowance and a clear approved cost ceiling. Serper's no-card offer does not cover SMS. If SMS cannot be provided within the no-card constraint, stop and resolve that prerequisite rather than bypassing verification.
3. **Secure configuration approval:** server-side names are in `LOCAL_LIVE_TEST.md`. Credential creation or persistent/temporary process configuration needs explicit secure approval. Do not paste API keys, auth tokens or OTPs into chat, source files or shell history.
4. **Bounded action approval:** own number entered directly in the local app; separately approve one Twilio SMS/code check, then three Serper exact-number queries. Accept the limited indexed-source coverage and confirm any match manually. Tests must not use someone else's personal data.
5. **Usable approved browser and available Mac:** the owner previously declined Safari access, so it has not been retried. Use a separately approved controllable browser or an owner-run walkthrough for actual desktop/mobile, keyboard, focus, recovery and visual checks. Keep the Mac awake and connected during the session.

No domain, Poynt payment setup, checkout, automated removal, public host or DNS change is needed for this local self-test. Provider accounts are separate from the domain.

## Additional gates for a public product

- Provide the exact product domain and confirm registrar/DNS control. Domain readiness is owner-reported, not independently verified in this task. Do not modify unrelated sites.
- Identify the actual hosting product and its supported production runtime: maintained Python 3.11+, sqlite3/alternative SQL, managed WSGI/process manager, outbound HTTPS, TLS, secret management, private writable storage/locking, backups/deletion and scheduler. Static/WordPress-only hosting cannot run the current backend unchanged. The Mac development HTTP server must not be deployed as-is.
- Wire qualified SMS/search adapters to the production application. The new self-test is deliberately loopback-only and memory-only, while the WSGI/demo path still refuses live mode. They are not yet a deployable real service.
- Establish production ownership authentication, consent records, per-user limits/abuse protection, concurrency, session expiry/recovery, trusted proxy handling, secure cookies, safe redacted logs, retention/deletion, operator monitoring and incident/recovery procedures.
- Review source access/terms, intended US/international coverage, privacy disclosures, match confirmation for recycled/shared numbers and customer support identity. Do not promise full online coverage or reduced spam. Validate every current official removal guide; automation/removal verification remains unimplemented and separately gated.
- If the original $1 paid product proceeds, complete merchant/Poynt account and legal setup, actual sandbox transports/webhook contract, server-side order reconciliation, success/decline/cancel/timeout/replay/refund testing, available-service/no-charge behavior, refund/support policy and operating costs. These are not prerequisites for the local no-checkout self-test, but remain prerequisites for charging customers.
- Run staging real-provider end-to-end tests plus final accessibility, cross-browser, mobile, security, data deletion/recovery and host load checks against the final production revision. Confirm DNS/TLS and backup/rollback. Obtain an explicit publishing decision before deployment, then verify the published build and monitor a limited launch.

## Unrun and blocked

Real SMS delivery, provider setup, credentials, exact account quota/billing, live indexed matches, actual browser visuals/accessibility, physical-device testing, GoDaddy hosting capability, public domain/DNS/TLS, production integration, real payments/refunds, broker removal and deployment are unqualified. These were not attempted because setup/permission/production requirements remain, not because the synthetic tests failed.

## Source and evidence pointers

- Setup contract: `LOCAL_LIVE_TEST.md`.
- Existing paid-product gates: `LAUNCH.md`, `SECURITY.md`, `CONTRACTS.md`.
- Serper offer/result example: https://serper.dev/ (checked November 6, 2026).
- Provider contract review/live qualification still required: https://serper.dev/playground . The implemented request is POST to `https://google.serper.dev/search`, API-key header, bounded JSON query, organic result parsing; no live call was made.
- Twilio API reference: https://www.twilio.com/docs/verify/api/verification and https://www.twilio.com/docs/verify/api/verification-check .

No Git metadata is present in this ScanPlus directory, so no commit, push, remote CI or published revision is claimed. `evidence/morning-readiness-2026-11-06/code.sha256` records the tested local code files.
