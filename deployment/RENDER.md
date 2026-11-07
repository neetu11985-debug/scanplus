> Current release: see ../COMPLETION_HANDOFF.md and ../VERIFICATION_2026-11-07.md. They supersede older integration/readiness statements below. Default demo remains unchanged; the new sandbox profile is explicitly opt-in.

# Protected Render Free synthetic staging (prepared, not deployed)

The later optional, authenticated database connectivity check is described in
`../STAGING_DB_CHECK.md`. It only runs `SELECT 1`; it does not change the demo's
in-memory storage. Runtime dependencies now include `requirements-neon.txt`.

This is a private disposable demo, not production. Only displayed synthetic fixtures work. No real scans, SMS, charges, removals, provider keys, or durable history. SQLite is forced to memory and lost when the single worker restarts, sleeps, or redeploys. Render Free sleeps when idle and may take time to wake. No retention or availability guarantee. No persistent disk, paid add-ons, or custom DNS are needed.

## Owner setup after approval

1. Select a **Web Service**, Python runtime, **Free** instance and the approved ScanPlus GitHub repository/main branch. Do not create a static site. Connecting GitHub grants persistent access and requires owner approval. Review Render terms before accepting them. A public Git URL supports manual deployment only; it does not establish GitHub CI-gated auto-deployment.
2. Build command: `sh deployment/render-build.sh`. Start command: `sh deployment/render-start.sh`. Python is pinned by `.python-version` to **3.12.16** and runtime dependency to **gunicorn 26.2.0**. If setting `PYTHON_VERSION` in Render, use the full `3.12.16`. Build installs the dependency and runs the full synthetic Python/Gunicorn suite before serving. GitHub also runs JavaScript checks. A failed first build must not be promoted.
3. The exact native `<service>.onrender.com` hostname is read from Render's `RENDER_EXTERNAL_HOSTNAME`. No duplicate hostname setting is needed. Optionally set `SCANPLUS_STAGING_HOST` as an equality guard; if set it must match the native hostname exactly, without scheme, slash or port. Do not override Render's native `RENDER=true` or hostname. Set `SCANPLUS_MODE=demo` and `SCANPLUS_STRIPE_TEST=0`; the wrapper forces these regardless of contradictory values. It also forces provider disablement and in-memory SQLite. Do not supply `SCANPLUS_DB_PATH`, provider/Stripe keys, or copy local configuration files.
4. Enter `SCANPLUS_STAGING_USER` and `SCANPLUS_STAGING_PASSWORD` directly as secret environment values in the Render dashboard. No values are supplied in this repository. Use a unique password-manager-generated password, not an account password. Username: 3–64 ASCII letters, digits, underscore, dot or hyphen. Password: 24–128 printable ASCII characters without spaces, at least 12 distinct characters, and must not include the username. These checks enforce a minimum, not proven entropy. Never use test fixture strings as real credentials. Missing or insufficient configuration refuses startup before application/SQLite import. Missing or invalid platform hostname also fails closed; it is never inferred from a request.
5. Leave the HTTP health-check path blank (default TCP check). Every route, asset and API requires authentication. Do not bypass authentication for a health route, add static mappings, or configure a CDN asset bypass. Render is the sole ingress; this Gunicorn configuration trusts its proxy HTTPS header for all peers and must not be reused on an exposed server elsewhere. Render terminates TLS. Host and any Origin must exactly match the configured HTTPS origin. Plain HTTP at the application is rejected.
6. The start script explicitly clears Render's default `GUNICORN_CMD_ARGS` (including `--preload` and request logging), then uses one sync worker, one thread and no preload. It binds `0.0.0.0:$PORT`. Application access logs and Gunicorn request/error logs are disabled to avoid request URLs/authorization leakage. Startup configuration failures have a generic diagnostic; inspect configuration privately, never log secrets to debug. Render platform infrastructure logging is outside this application's control.
7. Once the connected Git provider, GitHub Actions workflow and passing checks actually exist, select Render **Auto-Deploy → After CI Checks Pass**. Do not claim automatic deployment until a new approved commit demonstrably passes checks and deploys. The workflow is test-only. PythonAnywhere is not selected; no deployment job for it is included. No token or deploy hook is needed for this plan. Branch protections and CI configuration are owner-managed settings, not yet changed here.

## First online acceptance and rollback

Use the assigned HTTPS URL in a private browser window. Verify anonymous and wrong-login requests to `/`, `/app.js` and `/api/session/status` are blocked. After login, verify the PRIVATE SYNTHETIC STAGING banner, no-store/noindex headers, and `X-ScanPlus-Release` equals the tested full Git SHA. Noindex is not the access control; Basic authentication is. Confirm desktop/mobile layout, synthetic start → verify → quote **$1.49** → mock checkout **$0 charged** → report → Clear session. Stripe routes remain disabled, including webhook. Wrong Host/Origin and app-level HTTP are rejected. Verify HTTP-to-HTTPS at the real Render edge separately. Private source/configuration/database paths must never be served.

Clear session deletes app state but **does not log the browser out of HTTP Basic authentication**. Close the private window to clear browser-cached login; changing the Render password and redeploying revokes old credentials. Shared browsers are inappropriate. Authenticated viewers must use only the displayed fixture numbers, including on the optional browser-only number-format UI.

Redeploy/restart intentionally discards all synthetic state. Roll back using Render's previously verified commit/deploy after owner approval, then verify the serving revision and authentication again. This is not a database backup or production recovery strategy.

## Blank environment example (fill only in Render)

SCANPLUS_STAGING_USER=
SCANPLUS_STAGING_PASSWORD=
SCANPLUS_MODE=demo
SCANPLUS_STRIPE_TEST=0
PYTHON_VERSION=3.12.16

Reference documentation: https://render.com/docs/deploy-flask (Python web-service commands, not a Flask dependency), https://render.com/docs/free, https://render.com/docs/deploys, https://render.com/docs/python-version, https://pypi.org/project/gunicorn/ .

## Local verification (2026-11-07)

- macOS Python **3.11.7**, isolated Gunicorn **26.2.0** installed from official PyPI. Python **3.12.16** is pinned but unavailable locally, so exact-version execution remains for CI/Render build.
- Final build command ran **214 Python tests, all passed**, including 8 Render tests and 13 retained local archived-host tests. An isolated clean publish snapshot excluding archived-host files passed **201 tests** and all six JavaScript harnesses. The clean snapshot exposed an existing evidence-directory assumption; its test now creates missing parent directories, and the full snapshot rerun passed.
- All six offline JavaScript harnesses, JavaScript syntax checks and `git diff --check` passed. No browser rendering or real-provider integration was performed.
- Gunicorn integration covers missing/wrong/malformed authentication, all public assets, private paths, wrong Host/Origin/plain HTTP, secure cookies, revision/banner headers, disabled Stripe and synthetic start/verify/$1.49 quote/$0 checkout/report/clear. HTTPS proxy semantics are simulated over local HTTP, not real TLS or the Render edge.
- An initial test incorrectly required Secure on the app's existing deletion cookie. The Render wrapper now adds Secure to deletion cookies while preserving other attributes; rerun passed.
- Initial local integration briefly used the production wildcard bind with synthetic test credentials/data. Its exact child was terminated and reaped by teardown. The final harness explicitly binds only 127.0.0.1; final full-suite rerun passed. No real secrets or data were used.
- No commit, push, GitHub Actions run, Render account/settings change, deployment, real credentials, online URL verification, TLS/browser QA or active auto-deploy verification was performed by this preparation.
