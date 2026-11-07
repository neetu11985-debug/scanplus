# Limited staging database check: verification

Prepared locally; no publish, Render deployment, secret read or real Neon
connection occurred. Remote main was verified at
`c9a252e554fcc3cafee341753c1737ac9aa3a9de` before preparing the release.

Local runtime: Python 3.12.14, Node 24.22.1. Deployment remains pinned to Python
3.12.16, whose actual CI/Render execution is still pending.

## Passing final commands

With the project `.venv` activated:

`PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 sh deployment/render-build.sh`

```text
Ran 269 tests in 12.059s
OK
PASS: running WSGI app rejects unpaid persistence (HTTP 402).
PASS: paid save, idempotent retry and owner text download over HTTP; other user 404, anonymous 401.
```

Pinned dependencies were installed into the local virtualenv first. The build
rerun used no package index. All 269 tests passed, with no skips. DB operations
were mocked; tests also launched the real Gunicorn app on loopback.

`npm run build`

```text
> python3 tool/build.py && tsc --noEmit
BUILD PASS: 59 Python files parsed; 12 JavaScript files checked.
```

`npm run test:ui` passed all seven existing JavaScript harnesses. These are
offline DOM tests, not browser-render or live-provider evidence.

## Focused protection checks

Eight probe/boundary tests and nine Render/Gunicorn tests passed:

- No database call or DATABASE_URL read on import/startup.
- Missing/wrong login, HTTP, wrong host/origin and cross-site requests are denied
  before the probe.
- Only parameterless GET reaches the fixed read-only transaction.
- TLS certificate verification/channel binding and connection/SQL timeouts set.
- Missing configuration, invalid URL, connect/query failures and unexpected
  results return 503 rather than false success.
- No credentials, hostname, DB contents or exception text appear in responses
  or application logs. Cache status/age is explicit and expires after 30 seconds.
- The authenticated loopback route reports missing config as 503, rejects query
  parameters with 400 and POST with 405; existing synthetic journeys still pass.

Independent code review found no blocking defect. It noted that the configured
connection/statement timeouts are not a total request deadline; a stalled probe
may occupy the one synchronous worker until Gunicorn's timeout. This is a
private on-demand diagnostic, not a frequent health monitor.

## Failure recovered during preparation

The earlier temporary virtualenv was no longer present, so the first focused
test attempt failed to import Psycopg/Gunicorn. A new project-local virtualenv
was created and the pinned Render requirements were installed. The full final
Render build and regression passed afterward. This was a local dependency setup
failure, not a live Neon authentication or connectivity result.

## Not verified

The exact Render service, whether its environment form is saved, current serving
commit, CI execution, Render installation, Neon reachability, schema/pool
integration and complete customer flow are not verified. Do not call a saved
environment field a deployment or connection success. Follow `STAGING_DB_CHECK.md`
for the approval scope and post-deployment evidence.
