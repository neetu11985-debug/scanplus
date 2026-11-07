# Limited Render database check: ready for approved deployment

This is a small staging milestone, not the full Neon/customer integration.
It preserves the private synthetic demo and its disposable in-memory history.
No customer storage, payment, SMS, provider query, schema migration or real-key
generation is enabled.

## Current source and service status

Read-only GitHub verification found `neetu11985-debug/scanplus` main still at
`c9a252e554fcc3cafee341753c1737ac9aa3a9de`. The 96 original files matched the
materialized baseline, apart from one extra trailing newline per local file.
Main does not yet contain the encrypted-storage preview or Neon adapter.

The user reported entering a new DATABASE_URL in Render but said they had not
saved/deployed it. The exact service URL/ID and running revision are unverified.
No dashboard, stored secret, database credential or live database was inspected.

Redeploying the current remote main would still run the memory-only demo and
ignore DATABASE_URL. This source change must be published and deployed before
its new endpoint exists. No push or deploy has been performed.

## Scope of the change

`GET /api/staging/database`, on the verified existing Render service:

- Requires the existing private staging login and trusted HTTPS/host/origin.
- Rejects other methods and query parameters before any database access.
- Reads DATABASE_URL only on an authorized probe request, never on import/startup.
- Accepts only a TLS-required Neon URL. Psycopg verifies the server certificate
  and requires channel binding.
- Runs a fixed `SELECT 1` inside an explicitly read-only transaction. It cannot
  accept SQL, connection strings or customer data from the browser.
- Returns a small status with `customer_storage_enabled: false`; it never returns
  the URL, password, hostname, username, database contents or raw exception.
- Caches success/failure for 30 seconds and labels cached results with their age.
- Sets a five-second connection timeout and five-second SQL timeout. These are
  not an overall five-second deadline: a stalled connection may occupy the single
  synchronous worker until Gunicorn's existing timeout. This private diagnostic
  is not intended as a frequent uptime monitor.

The existing start command, private authentication, provider disabling and
memory-only customer demo remain unchanged. The build now installs the required
Psycopg/cryptography packages, so adding the reviewed tests does not break it.
GitHub CI additionally runs `npm ci` and the actual `npm run build` gate.

## Verification before publication

Local verification uses Python 3.12.14 and Node 24.22.1. The deployment pin remains
Python 3.12.16; that exact patch version still needs the actual CI/Render build.
All DB-driver calls in these local tests are mocks. Loopback Gunicorn tests start
the real app and confirm unauthenticated and invalid requests cannot probe, while
a missing configured URL reports 503 rather than a false success.

Final command evidence will be supplied with the prepared release. Passing these
tests does not establish real Render installation, real TLS to Neon or actual
database reachability. Those are post-deployment checks.

## Approval and rollout

First verify the exact existing Render service URL/ID. Obtain approval to publish
this limited source update to `neetu11985-debug/scanplus` and deploy it to that
service. Publishing main may trigger configured auto-deploy, so do not push before
the deployment scope is approved. If saving the new environment value is still
needed, the owner should save it directly in Render or explicitly approve that
specific persistent-credential configuration. Never share it in chat.

Suggested approval scope: publish and deploy only this protected staging update,
use the newly entered DATABASE_URL for the read-only connection check, and retain
all customer/provider/payment flows as synthetic and in-memory. Saving that URL
gives the deployed app ongoing database access; its secrecy must be preserved.

After approval:

1. Publish the reviewed source and require CI on the exact resulting commit.
2. Save the new credential in the approved Render service without exposing it.
   Do not use, recover or test the previously exposed credential.
3. Deploy the intended passing commit. Verify the service's Live status and
   `X-ScanPlus-Release` header match that exact commit. A saved field is not proof
   of a completed deployment.
4. In the already authenticated private staging session, open the service's
   `/api/staging/database` endpoint. It should return HTTP 200 with
   `database: reachable` and `customer_storage_enabled: false`. A 401 means the
   private login is required, not that Neon failed. A 404 generally means the old
   source is still serving. A 503 is an unavailable or unconfigured connection,
   never success. Respect the 30-second cache before repeating.
5. Recheck the synthetic demo and private/source-path protections. Do not call the
   complete customer flow ready: schema, app encryption keys, real identity,
   signed payment reconciliation, owner-download durability, retention/refunds,
   recovery and capacity monitoring remain separate launch gates.
