# Neon verification: local preparation complete, live service blocked

This records the earlier adapter milestone. For the later limited Render
connection-check change and its current verification, see `STAGING_DB_CHECK.md`.

Environment: isolated cloud source copy, Python 3.12, Node/npm, Neon CLI 9.2.0.
No changes were made to the original security-preview copy or a deployed site.

## Exact final passing evidence

Commands ran with the test virtualenv activated (`/tmp/scanplus-neon-venv`).

`npm run build` — exit 0:

```text
> python3 tool/build.py && tsc --noEmit
BUILD PASS: 57 Python files parsed; 12 JavaScript files checked.
```

`npm test` — exit 0:

```text
Ran 260 tests in 12.697s
OK
PASS: running WSGI app rejects unpaid persistence (HTTP 402).
PASS: paid save, idempotent retry and owner text download over HTTP; other user 404, anonymous 401.
```

All 260 collected Python tests passed, including 25 new Neon adapter/WSGI
contracts. No tests were skipped in this final run. The database driver in the
new adapter tests is a deliberately labeled SQLite mock, not a Neon connection.

`npm run test:ui` — exit 0: all seven existing JavaScript harnesses passed
(live, report, no-SMS, security, Stripe, phone entry, pricing). They are offline
DOM tests, not rendered-browser or live-provider proof.

The original Python application was also started in a subprocess on loopback:

```text
START PASS: original Python app started on loopback; GET / returned HTTP 200. Synthetic-only, SQLite memory backend. No Neon service proof.
```

Independent review reproduced a key-generation/replay defect in the initial
adapter. It was fixed before delivery: the database marker now establishes the
active key generation, every operation rejects mixed row versions, and only an
atomic rotation may change the active generation. Reproduction and all 25
adapter tests passed after the fix, including replay after successful rotation.

## Failed or incomplete steps

- `npm i -g neon@latest`: exit 254, `ENOENT` creating the unavailable global
  `/home/agent/.local/lib` directory. Used the user-requested npx fallback.
- Init ran with `--no-agent-setup`, deliberately avoiding global MCP/OAuth/API-key
  setup. It exited 0 but explicitly reported `Project linked, not verified` and
  `Written offline (--no-checks): nothing was verified.`
- `neon config plan` could not read the live project without authentication.
  It launched a cloud-loopback browser OAuth flow, which could not be completed
  from the user's separate browser. Canceled at exit 130. No credential file
  or `.env`/`.env.local` was created.
- `neon deploy` was not run because the live target and plan could not be verified
  and the necessary ongoing credential setup was not approved/completed.
- No schema migration, real Neon database write, production pool test, database
  restart/durability test or hosted app deployment took place.
- `npm run test:neon`: exit 2, correctly reported:

```text
NOT RUN: set SCANPLUS_NEON_SMOKE=1 after verifying the target and secure credentials.
```

- One intermediate HTTP test failed because the SQLite mock disallowed its
  server thread. Its fixture was corrected to allow the already-locked test
  connection across threads; the real adapter uses Psycopg. The final full
  regression passed afterward.

## Remaining acceptance gates

The requested step 5 is **only partially satisfied**: the build and local app
flows pass, but the actual Neon service has not been tested end to end.
Complete same-environment sign-in, approve/configure ongoing credentials, verify
the exact production target and plan, deploy, apply the reviewed migration, and
run the real-service smoke and final hosted-flow checks. Read `NEON_SETUP.md`.

Do not claim this result enables production paid customers. Real identity,
payment reconciliation, external key management, retention/refund policy and
the final hosted authentication/download path remain required. No real phone,
SMS, payment, provider lookup or removal request was used for these checks.
