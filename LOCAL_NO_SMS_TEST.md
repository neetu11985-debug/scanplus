# ScanMyDigits: real Serper report with SMS off

This is a separate owner-only local self-test. SMS stays off, no OTP is requested, and phone ownership is always labeled **self-attested, not verified**. It does not change production verification or the existing SMS-enabled live runner.

## Real search and report, once free credits are confirmed

1. Check the Serper account dashboard: at least **three active free queries** must remain and no paid top-up may be enabled. The app cannot independently verify billing or account credit. Do not proceed if that is uncertain.
2. Double-click **Start ScanMyDigits Serper No SMS.command** in this project folder. Read the confirmation and enter the exact requested phrase only after checking those facts. The launcher uses the existing owner-private `scanplus.local.properties` file, retains only `SERPER_API_KEY`, never prints/exports credentials, and does not construct or call a Twilio client. Startup makes no provider call.
3. Open exactly **http://127.0.0.1:4176** in your chosen browser. Only one browser session is accepted at a time. Do not expose the server through a tunnel, proxy or public hosting.
4. Leave **US (+1)** selected and enter only the **10 digits of your own number**, confirm the ownership declaration and explicit unverified/SMS-bypass acknowledgment, then choose **Continue without SMS**. This does not send the number outside this Mac.
5. Separately approve sending the number to **Serper** and confirm the three-query free allowance. Choose **Run one real Serper scan**.
6. Review the real response report and optional **Download PDF report / Plain-text alternative** links. Each source distinguishes potential matches, no exact match in the checked indexed results, and source unavailable. Listing URLs are retained; personal snippets/names/addresses are discarded. A missing search result does not prove the number is absent online.
7. Clear or stop the process with Ctrl+C when finished. No payment or removal is submitted. Opening any listed URL yourself contacts that site and may transmit personal information in its URL.

The three fixed source queries are Spokeo, TruePeopleSearch and Whitepages, up to ten indexed results each through Serper Google Search. This is not direct broker database access or a full Internet scan. These sources are US-focused; international coverage is not assured. Each listing still needs your own confirmation before taking action.

### Bounded behavior

- By default exactly one scan authorization per process, with at most **three attempted queries**. Explicit repeat mode below is the only exception; its finite allowance is configured before startup. Failed/uncertain requests consume allowance. Clear, expiry, another tab/browser or another number cannot replenish it. Any process restart creates a fresh in-memory allowance and requires separate approval and checking free credits again. This is not a durable billing limit and must not be hosted or automatically restarted.
- No retries, no Brave/provider fallback, no Twilio endpoint, no background search. A provider error/quota/timeout/malformed response stops later source queries and marks them unattempted/unavailable.
- An identical repeated scan returns the held report without another query. If a response is lost, reload the existing session to check its result; do not start a second process automatically.
- The number is held only in process memory for up to five minutes after entry, then cleared after scan, Clear, expiry or exit. A request already in progress uses a five-second socket inactivity timeout, not a guaranteed wall-clock deadline; later queries do not start after expiry. The report is available only within that five-minute test; the browser also clears report data at expiry and whenever the page becomes hidden, and rechecks server state when it returns. The security cookie expires after 15 minutes. Explicit downloaded reports remain on your device.
- Exact 127.0.0.1 binding and Host/Origin checks, rejected proxy-forwarding headers, SameSite/HttpOnly cookies, CSRF checks, bounded JSON, no HTTP/request-body logging, fixed HTTPS destination/certificate checks, and session-protected downloads remain enforced. This is not production authentication and cannot defeat privileged local software or an intentionally configured tunnel.

### Equivalent terminal command

Only after the same free-credit/no-top-up confirmation:

```sh
cd '/Users/rajeshkumar/dev/scanplus-checkin-2026-11-07'
python3 -B local_no_sms_server.py --local-no-sms --serper-live --confirmed-free-queries 3 --no-paid-topup-confirmed
```

By default this command expects the approved owner-private properties file in this updated checkout. To read an existing approved file in place, explicitly supply `--properties-file` with its path. It is never copied, printed or exported; the same owner-only regular-file validation applies. The option is rejected without explicit live startup. No path is loaded automatically from another checkout. If port 4176 is occupied, use an unused port such as `--port 4177`. Do not stop another running server. The CLI refuses missing/mismatched allowance confirmation before reading the properties file. Nothing in the file or environment silently enables live mode.

## Optional repeated own-number tests (disabled by default)

Use this only for an explicitly approved local test. `--test-max-scans N` accepts **1 through 5**, defaults to **1**, and requires `--serper-live` plus confirmation of exactly **3 × N available free queries** and no paid top-up. This does not alter hosted/production quotas. There is no unlimited mode or browser control to increase the limit.

For example, only after confirming **six remaining free queries**, no paid top-up, and approval for **two** scans, run the updated checkout's interpreter and runner with:

```sh
cd '/Users/rajeshkumar/dev/scanplus-checkin-2026-11-07'
.venv/bin/python -B local_no_sms_server.py --local-no-sms --serper-live --test-max-scans 2 --confirmed-free-queries 6 --no-paid-topup-confirmed --port 4178
```

This example defaults to the approved owner-private properties file in **that checkout**. You may explicitly select an existing approved file with `--properties-file`; it is read in place without copying secrets. Do not run a different old checkout merely to make this command work. A missing file is a setup blocker. Never restart or reset an old spent process to add allowance; leave it unchanged. Check DNS/TLS connectivity independently before approving live testing. Do not bypass network or certificate restrictions. A successful TLS check does not establish API acceptance or a free balance.

- The page shows scans started, scans remaining and cumulative query attempts. Each scan allows at most three attempts. A failed/uncertain scan consumes one scan authorization; unused requests from that scan do not carry forward to add scans.
- **Clear report to test the same number again** deletes the previous report and entry. You must re-enter your own number, reconfirm ownership/self-attestation, and separately approve Serper transmission and the remaining free allowance for each new scan. No new scan runs automatically. Repeating the scan request while a report exists only returns that report.
- The first consented scan binds this process to that normalized number. Only a random-keyed fingerprint is kept in process memory until exit, not the full number. Clear, expiry, a fresh browser session or another tab cannot change the binding or refill the budget. This is a self-attested local test, **not verified ownership** or a defense against a local operator changing the code.
- Report query counts apply to that scan; the separate process counter is cumulative. Download before clearing if you want to keep a report. Downloaded files remain on your device.
- New process launches require a fresh approved budget. Account balances and paid top-up settings are owner attestations, not independently enforced by this app. Do not use this mode on a public host or with an automatic restart supervisor.

## Offline input-only mode remains available

**Start ScanMyDigits No SMS.command** or `python3 -B local_no_sms_server.py --local-no-sms` runs the earlier input-only check without reading keys. Leave US (+1) selected and enter the reserved example 2025550147. It cannot perform a real search and shows the approval blocker instead of fabricated results. Use the separately named **Serper No SMS** launcher for the real flow after confirmation.

## Verification and remaining limits

Synthetic tests use reserved numbers and injected provider responses. They cover the real flow, consent, exact Serper endpoint, default one-scan budget, optional finite repeat budgets, same-number locking, concurrent attempt limits, failure stopping, ownership labels, report downloads, session isolation and expiry. They do not establish current API acceptance, actual account balance/billing, live source coverage, or real-number results. No real keys were read or provider requests made during implementation. The real account/free-credit gate remains pending until the owner confirms it.

```sh
PYTHONDONTWRITEBYTECODE=1 SCANPLUS_DB_PATH=:memory: python3 -B -m unittest discover -s tests -v
node --check static/no_sms.js
node tool/test_no_sms_ui.js
```

Browser visual/mobile QA remains unrun because no permitted browser was available; Safari was not used. Existing application, live-SMS adapters, keys/properties and servers were not changed or restarted.

## Optional private connection-error log

Add `--diagnostic-log` only for an approved local live startup. It creates or appends to `scanplus-local-diagnostics.log` beside this updated runner, with owner-only mode 600. The existing `*.log` ignore rule excludes it from Git. Startup rejects links, nonregular files, multiple links, wrong owner or broader permissions; it never changes an existing file's permissions.

Only fixed allowlisted failure categories, numeric HTTP status (or null if unavailable), UTC timestamp and bounded scan/query counters are written. No raw exception, phone, key, URL, search query, personal result or response body is accepted. Successful requests and skipped source queries are not logged. The diagnostics cannot prove the cause of an older failure that occurred before logging was enabled.

The file is capped at 64 KiB. It is never automatically truncated, rotated or deleted. Once full or unavailable, logging stops and the page shows that status; the sanitized report remains available. The file persists after Clear, expiry and process exit. Do not expect a complete log after a process crash, file-system failure or the cap. This option changes only the private local no-SMS runner, not hosted or production logging.
