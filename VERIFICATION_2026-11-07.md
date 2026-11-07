# Coding verification — 7 November 2026

## Passed against the final code

Environment: isolated Linux cloud source snapshot, Python 3.12.14, Node 24.22.1.
Pinned runtime dependencies reused from the existing local virtualenv. Deployment
Python 3.12.16 remains a CI/Render gate; do not equate the two versions.

- `PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 sh deployment/render-build.sh`
  with that virtualenv on PATH: **300 Python tests passed, no skips**.
- `npm run build`: **66 Python files parsed, 12 JavaScript files checked**, and
  Neon TypeScript configuration type-check passed.
- `npm run test:ui`: all **7 offline JavaScript harnesses** passed.
- Independent code review of final payment/store/Render boundary found no further
  blocking security defect within the explicitly synthetic sandbox scope.

The checks include real loopback HTTP/Gunicorn processes, synthetic ownership and
payment fixtures, wrong owner/anonymous/expired access, encrypted rows, signed
webhook validation, repeated/lost-response delivery, fixed $1.49 pricing, demo
checkout isolation, wrong configuration and stale-key rotation/replay regression.
Postgres contracts use a deliberately labeled SQLite driver mock, not live Neon.

## Defect corrected

Two SQLite store instances could previously disagree about the active key version
after one rotated it. A stale writer could create another claim/report for the
same paid bundle. Startup and every transaction now verify the authenticated
active-key marker under the write lock; tests cover stale writers, mismatched
startup versions and mixed-version rows. Neon already enforced this protocol.

## Not run / blocked

- No remote push, commit, CI run, deployment or hosted acceptance. Previous GitHub
  write attempt returned 403; no retry or alternative credential route was used.
- No live Stripe API, Neon connection/schema change, SMS, Serper search, real key
  read, account login or production data.
- Browser-render screenshots were attempted locally, but Chromium could not
  create its required process socket (`Operation not permitted`). No browser
  permission escalation was attempted. Desktop/mobile visual QA and real hosted
  checkout/back-navigation remain unverified. Offline DOM tests are not rendered
  browser evidence.
- A 70% alert schedule/notification channel has not been activated.

See COMPLETION_HANDOFF.md for exact owner deployment instructions and remaining
product/security decisions. Passing this suite qualifies the private sandbox
source only, not a live paid-customer launch.
