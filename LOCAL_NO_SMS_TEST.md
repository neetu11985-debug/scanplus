# ScanMyDigits: real Serper report with SMS off

This is a separate owner-only local self-test. SMS stays off, no OTP is requested, and phone ownership is always labeled **self-attested, not verified**. It does not change production verification or the existing SMS-enabled live runner.

## Real search and report, once free credits are confirmed

1. Check the Serper account dashboard: at least **three active free queries** must remain and no paid top-up may be enabled. The app cannot independently verify billing or account credit. Do not proceed if that is uncertain.
2. Double-click **Start ScanMyDigits Serper No SMS.command** in this project folder. Read the confirmation and enter the exact requested phrase only after checking those facts. The launcher uses the existing owner-private `scanplus.local.properties` file, retains only `SERPER_API_KEY`, never prints/exports credentials, and does not construct or call a Twilio client. Startup makes no provider call.
3. Open exactly **http://127.0.0.1:4176** in your chosen browser. Only one browser session is accepted at a time. Do not expose the server through a tunnel, proxy or public hosting.
4. Leave **US (+1)** selected and enter only the **10 digits of your own number**, confirm the ownership declaration and explicit unverified/SMS-bypass acknowledgment, then choose **Continue without SMS**. This does not send the number outside this Mac.
5. Separately approve sending the number to **Serper** and confirm the three-query free allowance. Choose **Run one real Serper scan**.
6. Review the real response report and optional **Download readable report / Download JSON** links. Each source distinguishes potential matches, no exact match in the checked indexed results, and source unavailable. Listing URLs are retained; personal snippets/names/addresses are discarded. A missing search result does not prove the number is absent online.
7. Clear or stop the process with Ctrl+C when finished. No payment or removal is submitted. Opening any listed URL yourself contacts that site and may transmit personal information in its URL.

The three fixed source queries are Spokeo, TruePeopleSearch and Whitepages, up to ten indexed results each through Serper Google Search. This is not direct broker database access or a full Internet scan. These sources are US-focused; international coverage is not assured. Each listing still needs your own confirmation before taking action.

### Bounded behavior

- Exactly one scan authorization per process, with at most **three attempted queries**. Failed/uncertain requests consume allowance. Clear, expiry, another tab/browser or another number cannot replenish it. Restarting is a deliberate new test and requires checking free credits again.
- No retries, no Brave/provider fallback, no Twilio endpoint, no background search. A provider error/quota/timeout/malformed response stops later source queries and marks them unattempted/unavailable.
- An identical repeated scan returns the held report without another query. If a response is lost, reload the existing session to check its result; do not start a second process automatically.
- The number is held only in process memory for up to five minutes after entry, then cleared after scan, Clear, expiry or exit. A request already in progress uses a five-second socket inactivity timeout, not a guaranteed wall-clock deadline; later queries do not start after expiry. The report is available only within that five-minute test; the browser also clears report data at expiry and whenever the page becomes hidden, and rechecks server state when it returns. The security cookie expires after 15 minutes. Explicit downloaded reports remain on your device.
- Exact 127.0.0.1 binding and Host/Origin checks, rejected proxy-forwarding headers, SameSite/HttpOnly cookies, CSRF checks, bounded JSON, no logging, fixed HTTPS destination/certificate checks, and session-protected downloads remain enforced. This is not production authentication and cannot defeat privileged local software or an intentionally configured tunnel.

### Equivalent terminal command

Only after the same free-credit/no-top-up confirmation:

```sh
cd '/Users/rajeshkumar/dev/ScanPlus codes'
python3 -B local_no_sms_server.py --local-no-sms --serper-live --confirmed-free-queries 3 --no-paid-topup-confirmed
```

If port 4176 is occupied, use an unused port such as `--port 4177`. Do not stop another running server. The CLI refuses missing/mismatched allowance confirmation before reading the properties file. Nothing in the file or environment silently enables live mode.

## Offline input-only mode remains available

**Start ScanMyDigits No SMS.command** or `python3 -B local_no_sms_server.py --local-no-sms` runs the earlier input-only check without reading keys. Leave US (+1) selected and enter the reserved example 2025550147. It cannot perform a real search and shows the approval blocker instead of fabricated results. Use the separately named **Serper No SMS** launcher for the real flow after confirmation.

## Verification and remaining limits

Synthetic tests use reserved numbers and injected provider responses. They cover the real flow, consent, exact Serper endpoint, one-scan budget, failure stopping, ownership labels, report downloads, session isolation and expiry. They do not establish current API acceptance, actual account balance/billing, live source coverage, or real-number results. No real keys were read or provider requests made during implementation. The real account/free-credit gate remains pending until the owner confirms it.

```sh
PYTHONDONTWRITEBYTECODE=1 SCANPLUS_DB_PATH=:memory: python3 -B -m unittest discover -s tests -v
node --check static/no_sms.js
node tool/test_no_sms_ui.js
```

Browser visual/mobile QA remains unrun because no permitted browser was available; Safari was not used. Existing application, live-SMS adapters, keys/properties and servers were not changed or restarted.
