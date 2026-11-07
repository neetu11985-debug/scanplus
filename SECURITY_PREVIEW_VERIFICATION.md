# Security preview verification

## Result

Local-only additions based on main commit
`c9a252e554fcc3cafee341753c1737ac9aa3a9de`. Existing runtime, staging entry point,
deployment workflow and existing tests were not changed. No publication, database
project, production key, provider call or deployment occurred.

Environment: cloud Linux, Python 3.12.14, Node 24.22.1, cryptography 50.0.0.

## Passed

- `SCANPLUS_DB_PATH=:memory: python3 -m unittest discover -s tests -v`:
  235 collected, 232 passed, 3 skipped. All 34 new tests passed (21 storage,
  13 HTTP/admin contracts).
- Python syntax compilation of application modules and the optional UI script.
- JavaScript syntax for existing static/tool scripts plus the new admin script.
- Six existing JavaScript harnesses and the new `node tool/test_security_ui.js`.

New coverage includes randomized ciphertext, encrypted on-disk phone/report/owner/
credential/expiry/payment data, HMAC lookup, wrong/missing keys, tamper/context swap,
restart, rotation rollback, expiry/deletion, unsafe paths, atomic paid storage,
concurrent replay, failed/unpaid/wrong-owner/expired payment evidence, absent/expired
identity, admin role/CSRF/origin/host/TLS checks, status-only credential responses,
owner-gated text-download bytes/headers, rejection of supplied real data, repeated
UI clicks, stale responses, back/forward restore and errors.

## Skipped or blocked

- Three existing Render Gunicorn integration tests skipped because Gunicorn is not
  installed in this environment. They previously passed on baseline CI; that is not
  a new local pass. These additions have no remote CI run.
- Actual visual browser QA did not run. Default Playwright browser binary was
  absent; installed Chromium failed to launch because its process socket is denied
  in this cloud execution environment, including the reviewed elevated attempt.
  No desktop/mobile screenshot or rendered-layout pass is claimed. An optional
  `tool/test_security_ui.py` uses fully intercepted synthetic HTTPS requests and
  can be run in an authorized environment that supports Chromium. It is unverified.
- Real TLS/host edge, identity provider, MFA, signed gateway-to-new-store integration,
  durable managed DB, backup restore, metrics/alert delivery and production key
  management remain unrun and unconfigured.

## Review/publishing caveat

Before publishing these files, update the test build to install
`requirements-security.txt`; otherwise test discovery will fail where cryptography
is absent. Decide the managed DB and authentication/payment adapters first. The
new admin application is disabled by default and accepts synthetic values only.
Do not change an existing deployment entry point to this preview.
