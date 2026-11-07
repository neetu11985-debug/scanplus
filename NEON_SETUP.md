> Current release: see COMPLETION_HANDOFF.md and VERIFICATION_2026-11-07.md. They supersede older integration/readiness statements below. Default demo remains unchanged; the new sandbox profile is explicitly opt-in.

# Neon setup: prepared, not deployed

This copy is based on `neetu11985-debug/scanplus` main commit
`c9a252e554fcc3cafee341753c1737ac9aa3a9de` plus the separate encrypted-storage
preview. The original preview copy was not changed. This directory is a source
snapshot, not a Git checkout. Nothing was pushed, published or deployed.

## Verified setup status

- `npm i -g neon@latest` failed because the global install directory was not
  writable/available. The requested `npx neon@latest` fallback works, version 9.2.0.
- The installed Neon skills all reported up to date. The official connection
  guide recommends a native TCP driver and a pooled connection for Python:
  https://neon.com/docs/connect/choose-connection
- `neon init -y --no-agent-setup --org-id org-fancy-cake-12896136 --project-id
  still-dust-45114966 --branch production --services postgres` succeeded offline.
  `--no-agent-setup` is the one deliberate safety difference from the requested
  command: it avoids global coding-agent/MCP installation or credential creation.
  The CLI wrote `.neon`, `neon.ts`, `package.json` and the dependency lockfile.
- Exact CLI output: `Written offline (--no-checks): nothing was verified.`
  The local project/branch link has **not** been verified against Neon.
- No authenticated Neon profile or database URL was present. `neon config plan`
  started browser OAuth using a loopback callback in this cloud executor; that
  pending login was canceled (exit 130), without completing OAuth. An unrelated
  local-computer login would not authenticate this cloud process.
- `neon deploy`, env pull, schema migration and real Neon end-to-end verification
  have **not** completed. No Neon resource, customer data or real key was created.

## App and build

ScanPlus is a Python WSGI backend with static JavaScript, not a Node web app.
The new npm manifest is for Neon configuration and explicit build/test commands.
`npm run build` parses Python source, checks all shipped JavaScript, and type-checks
`neon.ts`. It does not pretend to bundle or host the Python app.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-neon.txt -r requirements-render.txt
npm ci
npm run build
npm test
npm run test:ui
```

`npm test` includes started HTTP servers and the secure paid-report path with an
explicitly mocked database driver. That is offline contract evidence, not a real
Postgres connection. The original synthetic app can still start with:

```sh
SCANPLUS_DB_PATH=:memory: python3 server.py
```

## What is wired

`neon_storage.py` supplies `PostgresEncryptedStore` and `create_neon_preview`.
The latter reads `.env` if present, otherwise `.env.local`, with actual process
environment taking priority. It passes `DATABASE_URL` into Psycopg 3's small
connection pool. Database values are never exposed to browser JavaScript.

- TLS verifies the server certificate and requires channel binding.
- Pooled connections use explicit transactions and bound parameters.
- Transaction-scoped advisory locking preserves paid-bundle replay/rotation
  semantics across processes. This is intentionally serialized for correctness,
  not a high-throughput performance claim.
- The existing AES-GCM encryption, HKDF keys, HMAC blind indexes, atomic paid
  phone/report bundle, owner checks and expiry behavior are reused.
- App encryption keys are injected externally as base64-encoded 32-byte values
  in `SCANPLUS_STORAGE_KEYS_JSON`, with `SCANPLUS_STORAGE_ACTIVE_VERSION` naming
  the active version. No real key was generated, configured or committed.
- The schema is an explicit migration in `migrations/001_encrypted_storage.sql`.
  Runtime startup never creates a schema or imports existing plaintext data.

The existing demo and Render customer flows remain in memory. The Render wrapper
now also offers a protected, read-only connection probe described in
`STAGING_DB_CHECK.md`; it does not use this encrypted store. The secure preview
factory still requires a trusted server-side identity resolver and payment
verifier. Its public default remains HTTP 503. Do not replace it with fixture
identity/payment adapters on a public server. This Neon step does not establish
real customer authentication, signed payment reconciliation, credential-admin
authorization, the retention/refund policy, backup recovery or the requested
70% capacity-alert service. Those remain launch gates.

## Resume on the authenticated project computer

1. Run `neon login` (or `npx neon@latest login`) in the same environment as the
   project commands, and finish the browser sign-in there. Do not paste API
   keys, database URLs, OAuth tokens or encryption keys into chat.
2. Verify the organization, project, actual `production` branch and existing
   services. The generated starter's `auth: false` was removed so this
   Postgres-only config does not explicitly disable an existing identity service.
3. Run `neon config plan`. Stop on unexpected service deletions, pricing or access
   changes. The request targets the existing project, not a replacement project.
4. After the required approval to configure ongoing credentials, run `neon deploy`.
   It applies the service configuration and pulls branch env variables. Preserve
   existing `.env` values, keep that file private and out of source control.
   Postgres-only deployment does not deploy the Python frontend/backend host.
5. Review/test the schema migration in an isolated database branch before applying
   it to production. Use the **direct** `DATABASE_URL_UNPOOLED` for migrations,
   not the pooled app URL. Keep keys outside the database and use a reviewed
   application role. No role or database credential is provisioned by this code.
6. Supply the real server identity/payment adapters and approved retention policy
   before enabling customer persistence. Repeat all security checks.

## Real service verification, still pending

After the intended target and credentials have been verified:

```sh
SCANPLUS_NEON_SMOKE=1 npm run test:neon
```

This command uses `DATABASE_URL_UNPOOLED` and real Psycopg/Postgres. It creates
only a connection-local TEMP table, starts a loopback WSGI HTTP server, exercises
unpaid rejection, paid encrypted storage, replay and owner download, inspects
ciphertext, then rolls back everything. It does not migrate a persistent table,
use a production encryption key, test a real payment, or send a real phone.
The identity/payment and TLS-termination flag in this test are synthetic.

The smoke test exits 2 rather than claiming success when its explicit opt-in is
absent. Full deployed verification still needs real hosted authentication,
approved payment testing, actual HTTPS and a restart/durability check against
the final configured database. No such live results are claimed here.
