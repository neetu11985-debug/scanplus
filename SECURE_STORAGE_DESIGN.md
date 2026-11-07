> Current release: see COMPLETION_HANDOFF.md and VERIFICATION_2026-11-07.md. They supersede older integration/readiness statements below. Default demo remains unchanged; the new sandbox profile is explicitly opt-in.

# Encrypted paid-user storage: local implementation and activation gates

Baseline reviewed: `neetu11985-debug/scanplus`, main commit
`c9a252e554fcc3cafee341753c1737ac9aa3a9de`.

## What exists in this local proposal

- `encrypted_storage.py`: tested AES-256-GCM database encryption for complete phone
  numbers, report text, credential values/names, owner identifiers, expiry, and
  payment-reference claims. Random nonces and authenticated context prevent silent
  tampering or ciphertext swaps. A separately derived HMAC key supports private
  lookups; an ordinary unsalted phone hash would be vulnerable to guessing.
- `secure_admin.py` and `static/security/`: administrator-only configuration preview,
  with status-only credential responses and no endpoint to reveal a saved secret.
  It accepts only predefined synthetic credential values, never real pasted keys.
  Default `application` returns 503. No existing entry point imports it.
- Owner-gated `.txt` download: the current authenticated identity must match the
  encrypted report's owner. Knowing its random URL is insufficient. Administrators
  have no automatic access to another user's report. Downloads have attachment,
  no-store and no-sniff headers, and use a constant filename without personal data.
- Paid-only write boundary: an injected trusted server payment verifier must supply
  evidence for this owner before `put_paid_bundle` atomically writes phone, report
  and encrypted idempotency claim. Zero/unpaid/expired/wrong-owner evidence fails
  before persistence. Matching retries reuse the same report without extending its
  expiry; conflicting content fails. No browser `paid`, `owner_id`, phone or report
  override is accepted by this preview.

This is a local synthetic security slice, not a completed production admin system.
The current Render/demo/live routes are unchanged and do not use this new store.
Nothing is published, deployed, activated or connected to real keys or customers.

## Payment and data lifecycle

1. Before payment, keep only the minimal verification/scan state needed in bounded
   process memory, with expiry. Do not persist user phones or report content.
   Do not add request-body logs, analytics events, browser storage or error payloads.
2. Before storage, the backend must reconcile an authenticated gateway response or
   signed event: expected merchant/order, final successful payment state, payer,
   amount, currency and replay/revocation status. A Checkout redirect, pending
   payment, test charge or browser flag is not production evidence of payment.
3. Commit the encrypted phone/report/claim atomically. Payment can succeed while
   storage fails; a recovery workflow must retry storage idempotently, then offer
   support/refund handling if delivery remains impossible. Never charge again just
   because a storage write failed.
4. On download, revalidate account/session and ownership, then decrypt in server
   memory and return text over HTTPS. The saved file is intentionally readable
   text. The service cannot remotely erase the customer's downloaded copy.
5. Apply the selected retention deadline and a scheduled prune job. Expiry checks
   deny reads immediately, but physical deletion while idle requires that job.
   Backup/snapshot retention and restores need their own expiry handling.

**Retention is not yet chosen.** The preview's 15-minute lifetime is only a test
fixture, not a product policy. The user has not decided whether refunds revoke
downloads, how long paid reports remain, whether future report revisions replace
old reports, or what minimally necessary payment records must survive deletion.
Do not silently retain phone/report content forever or delete it on refund.

Payment claims expire with this prototype's data. The production payment verifier
must reject reuse of expired/revoked old payments after claims are pruned. If longer
payment replay tracking is required, retain minimal non-content payment metadata
under a separate, documented policy rather than secretly keeping the report.

## Encryption and passwords

Supply a 32-byte master key from an owner-managed secret store/KMS, separately from
the database, backups, source tree and browser. Do not paste it in chat or commit
it. No production key is generated or configured by this work. Missing/wrong keys,
tampered rows and legacy schemas fail closed. Versioned keys support atomic local
rotation/reindexing; coordinate all instances and test restore before retiring old
keys. Losing every required key makes ciphertext unrecoverable.

Recoverable service API tokens need authenticated encryption because the backend
must use them. Login passwords need an established salted password-hashing method,
preferably Argon2id with appropriately tuned parameters, not recoverable encryption.
Prefer an established identity provider with MFA for administrators. The meaning of
“credentials” still needs confirmation before real credential-entry UI is enabled.

At-rest encryption does not hide data from the running authorized backend, its
memory, a compromised host with key access, or intended recipients of a live scan.
Database record counts, purpose labels and ciphertext sizes remain visible. TLS,
least-privilege access, operational security and a privacy policy still matter.

## Database and migration

The new implementation is a SQLite reference/test store. It is not a PostgreSQL
driver or a managed database deployment. Render Free's current `:memory:` store and
ephemeral disk cannot provide durable paid-user history. Select a durable database
and plan, then implement/test the corresponding repository adapter and backups.
No managed database project or ongoing credentials have been created.

For a private SQLite environment, require an owner-private directory and file,
reject symlinks/hardlinks and unsafe permissions, use atomic transactions, and keep
the file outside static roots. These checks are not protection against root or a
hostile same-user process. Multi-instance production needs an appropriate shared DB.

No real plaintext database was inspected. Current demo code stores synthetic phone
hashes; live self-test code keeps phones/reports in memory. Those hashes cannot be
reversed into phone numbers. Do not fabricate a backfill. If a real legacy store is
later identified, inventory only with permission, import into a new encrypted
schema transactionally, reconcile counts/ownership, then separately approve disposal
of old plaintext copies and backups. Never silently mix legacy and encrypted tables.

## 70% database-usage alert plan

- Metric: provider-reported database storage used divided by that plan's actual
  storage quota. Include indexes/metadata as the provider counts them. Do not use
  number of users or plaintext report size as a substitute.
- Sample every hour initially. Alert on first crossing of 70%, with used/limit,
  timestamp, project/environment, growth trend if available, and a direct console
  link. Example only: a 500 MB quota reaches 70% at 350 MB; use the provider's exact
  quota units for the chosen plan.
- Avoid duplicate hourly alerts. Re-arm below 60%. Escalate new crossings at 85%
  and 95%, or an unexpected fast increase; do not change plans, purchase capacity
  or delete customer data automatically. Alert if usage checks fail repeatedly.
- Recommended action: inspect legitimate growth, verify retention/pruning and
  backup sizes, then ask whether to increase capacity. “Delete old data” must obey
  the agreed retention and recovery policy.
- **Not configured:** no chosen database/project/quota, verified metrics read
  access, or recipient channel is connected to this proposal. No live monitoring
  or automated alert delivery is claimed. Provider free-plan expiry, connection,
  egress and compute limits are separate from this storage threshold.

## Before production activation

Confirm service API keys versus user/admin passwords; choose durable DB/host and
retention; integrate strong identities, verified payments and rate limiting;
review consent/data recipients; obtain approval for persistent credentials/key
configuration; implement least-privilege roles, redacted audit events and emergency
revocation; test restore/rotation, signed webhook replay, failed delivery, expired
sessions, wrong-owner access and actual TLS; review/publish explicitly. Update CI
to install `requirements-security.txt` before collecting these new tests. None of
these steps is implied by a local preview or by passing synthetic tests.
