# Security and retention — current synthetic build

The approved UI is preserved. These safeguards are a local foundation, not a production security certification. No real phone data, external calls or payments are enabled. `SCANPLUS_MODE=live` refuses the local process; WSGI returns 503. Missing production dependencies never fall back to fixtures.

## Stored data and isolation

Python sqlite3 and SQLite 3.53.4 were verified locally. `storage.py` uses bound SQL values and `BEGIN IMMEDIATE` transactions, a 2-second database busy timeout, and file creation mode 0600. The public handler only serves three explicit static files, never a DB file or arbitrary path. The default development store is `.data/scanplus-demo.sqlite3`; host configuration must put it outside any public document root. Existing database file permissions must be inspected by the owner/operator, not assumed from creation mode.

Sessions are keyed by a SHA-256 digest of a high-entropy bearer cookie. CSRF values and the fixed synthetic number are hashed separately. The record stores verification attempts/expiry/consumption, a unique report ID, test receipt and simulated removal status. A client-supplied report ID or session owner cannot change access: report lookup derives exclusively from the authenticated cookie. No raw phone, OTP, real nonce, card details, names, addresses or provider snippets are stored. Hashing a phone or IP is **not encryption or reliable anonymization**; this build accepts only the reserved fixture number. Production handling of phone hashes needs a reviewed privacy design rather than assuming they are anonymous.

The offline Poynt harness stores order/reservation state plus hashed nonce/transaction claims. An uncertain charge intent commits before transport invocation. Cross-worker duplicate charge calls cannot issue another request; uncertain records require reconciliation. No real financial ledger or gateway is enabled. Do not delete real financial idempotency records on demo TTLs in a future paid release: legal/refund/dispute retention and owner policy must be decided first.

## Request safeguards

- Same-origin Origin is required for every POST. Existing sessions also require a constant-time-checked CSRF token; `/api/session` rotates it on reload. A second tab can invalidate an older tab's token; reload the older tab to recover.
- Cookies are HttpOnly, SameSite Strict, root-scoped and time-limited. HTTPS WSGI adds Secure. Plain HTTP is loopback demo only.
- Default hosts are loopback only. HTTPS WSGI requires exact `SCANPLUS_ALLOWED_ORIGINS` entries. Cross-site fetch metadata is rejected. There is no CORS permission. Configure trusted scheme/host at the actual proxy; arbitrary forwarded headers are ignored.
- Bodies are limited to 2 KiB, transfer-encoded input is rejected, malformed JSON has a generic response, and local socket reads time out after 5 seconds. Browser requests abort after 10 seconds; adapter fixtures declare 5-second limits. The host must separately configure real WSGI worker/body/connection timeouts and concurrency.
- New sessions are limited to 10/minute per peer address, authenticated actions to 60/minute per session, verification to five guesses per challenge, active sessions to 1,000, and rate-counter keys to 4,096. Addresses exist only as short-lived hashed rate keys. Do not trust public forwarded-IP headers; configure real proxy limits after the host is known. These local controls do not qualify internet-scale abuse resistance.
- Demo verification expires after five minutes by default, is bound to the stored exact-number reference and session, and is consumed once. Verified access expires with the session. A current phone holder must still confirm a historical/recycled-number listing separately before any real removal.
- Responses are buffered until the transaction commits. On storage failure the handler returns a generic 503; it does not confirm an uncommitted action. The HTML uses CSP, no-referrer and no-store headers with no remote fonts/analytics.

## TTL and deletion

`SCANPLUS_SESSION_TTL`: default 900 seconds, allowed 60–86,400. `SCANPLUS_CHALLENGE_TTL`: default 300, allowed 30–600. `SCANPLUS_PAYMENT_TTL`: offline harness default 86,400, allowed 300–604,800. Invalid bounds fail configuration. Session TTL does not slide forward on activity.

Expired records cannot be accessed. Requests prune expiry, the loopback runner sweeps every 30 seconds, and `python3 maintenance.py` prunes idle stores for a host scheduler. Browser Clear session immediately deletes its session/report/test-receipt/job record. Restart preserves unexpired sessions and receipts. SQLite secure_delete is enabled, but that is not a promise of deletion from filesystem snapshots, journals, backups, Library screenshots or downloaded JSON. No home-grown encryption was introduced. Future real-data storage needs a reviewed host/platform encryption and backup/deletion policy.

## Logs

Application access/body/error logging is suppressed. Errors never echo arbitrary payloads or exception strings. `privacy.safe_event` allows only fixed event/reason values and integer status, discarding phone/code/token/exception fields. Tests check stdout/stderr payload exclusion and that database dumps omit raw phone, OTP, cookie, CSRF and nonce values. The actual host may independently log request metadata; inspect and minimize that configuration before real data.

## November 3 session-switch update

After successful synthetic verification, a transactional active-identity binding selects the latest session for that exact fixture number. Previous sessions remain stored until expiry but report/export/checkout/refund/removal access is rejected server-side. Failed/unverified attempts cannot revoke the current session. Different fixture identities remain isolated and concurrently valid. Already-viewed information cannot be recalled: the UI clears on focus/visibility or its 15-second status poll; exports always recheck server authorization.

This is phone-control-based synthetic identity, not production customer authentication. Shared/recycled numbers and a real provider/customer identity model still need review. Browser testing used localhost and 127.0.0.1 host-isolated cookies in one browser; it did not establish two real laptops or independently managed browser profiles.

## Demo-only return/refund history

Synthetic checkout receipts now have independent identity-scoped storage: eight days by default, bounded by SCANPLUS_DEMO_HISTORY_TTL. Clear session deletes authentication/session state, while those receipts remain available after a new verification. History and history-based refund actions require verification within the challenge freshness period and the current single-session binding. Known payment IDs cannot bypass ownership. A separate confirmed Delete synthetic history action deletes only that verified fixture identity's demo receipts/refund requests and clears its current checkout state. Tests use disposable stores for deletion; existing preview history is preserved.

No real phone values or real payment identifiers are accepted by the demo. The stable identity is a digest of one of two PUBLIC RESERVED fixture numbers, not an authentication secret or anonymous real-phone lookup. The known test code is not real ownership proof. Production mode remains blocked and must never use this fixture identity scheme. Real identity, provider verification, financial retention, account recovery and lawful deletion still need production design/configuration.
