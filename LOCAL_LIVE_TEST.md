# ScanPlus local live self-test

This path is implemented but **disabled and not live-qualified**. It is separate from the synthetic demo at port 4173. All development checks use reserved numbers and injected provider responses. No real SMS, search API query, payment, or removal submission has been made.

## Selected no-card route

The local process now defaults to **Serper for Google Search results**, following the no-card provider choice. On November 6, 2026, https://serper.dev advertised 2,500 free queries with no credit card required. That is a trial offer, not unlimited free production capacity or proof of this owner's eligibility/remaining credits. There is no automatic paid top-up, provider fallback, or automatic retry in ScanPlus. Brave is retained only as an explicitly selected alternative and is not required for the selected route.

Twilio Verify remains the separate ownership-verification provider. Serper's no-card offer does not establish Twilio eligibility, trial restrictions, price, destination permissions, or available balance. If usable no-card SMS verification is unavailable, the live test stays blocked. Do not bypass ownership verification.

## What the approved local test can do

1. Run the ScanPlus self-test backend on `127.0.0.1:4175` on this Mac.
2. Select US (+1) and enter only the 10 digits of your own number in the local page and separately authorize one Twilio Verify SMS and its verification-code check.
3. After Twilio confirms control, separately authorize three Serper queries, restricted to Spokeo, TruePeopleSearch and Whitepages. The page names the actual configured provider; consent to Brave cannot authorize Serper or vice versa.
4. Review indexed source links, timestamps and potential matches. Unavailable responses are not no-match results. Current phone control does not prove an indexed listing belongs to you.
5. Confirm or reject each listing locally, use official manual guides, and optionally download the readable/JSON report. Recording a manually submitted request only changes a checklist; it is not a submission or verified deletion.

This is a bounded web-index lookup, not direct broker database access, a full Internet scan, removal, or production qualification. The three sources are US-focused; international coverage is not assured. No checkout or real removal is in this path. The domain is not needed for this Mac-only test.

## Setup gates

- Confirm an eligible Serper account with active free credits, no card requirement and no paid top-up. Review its terms/privacy and approve sending your number for the three queries. Owner/account setup remains pending.
- Confirm an eligible Twilio Verify account/service, usable authentication, SMS destination permissions and approved no-card/trial allowance or cost ceiling. Country, trial-number and account restrictions can block SMS delivery. Review current terms/privacy before use.
- Approve secure creation/configuration of credentials separately. Never paste provider secrets or verification codes into chat, source, this document, browser developer tools, or shell history. Enter the SMS code only in the matching local self-test.
- A usable approved browser is required for actual visual/interactive validation. Safari was declined and was not retried. The JavaScript DOM harness is not visual or physical-device QA.
- Keep the Mac awake/connected for the local session. No tunnel, public binding, deployment or DNS change is implied.

## Configuration contract (names only; no values supplied)

Required server-side environment variables after secure setup is approved:
- `SCANPLUS_LOCAL_LIVE_TEST=1` (explicit opt-in).
- `SCANPLUS_SEARCH_PROVIDER=serper` (Serper is also the environment default).
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VERIFY_SERVICE_SID`.
- `SERPER_API_KEY`.
- Optional `SCANPLUS_LOCAL_LIVE_PORT` (default 4175).

Only an explicitly selected `SCANPLUS_SEARCH_PROVIDER=brave` uses `BRAVE_SEARCH_API_KEY`. Missing Serper configuration does not fall back to Brave. Unsupported provider values fail closed. The app does not load `.env`, does not create accounts/keys, and does not send secrets to the browser. For owner-edited properties and double-click launchers instead of pasting keys in Terminal, see [LOCAL_KEYS_SETUP.md](LOCAL_KEYS_SETUP.md). The new file starts empty and disabled; the existing environment-only command below is unchanged.

After all setup and live-action approvals are completed:

```sh
cd '/Users/rajeshkumar/dev/ScanPlus codes'
python3 local_live_server.py
```

Open the exact printed `http://127.0.0.1:4175` address (or selected port). `localhost` and other hosts are rejected. Stop with Ctrl+C. This development server must not be deployed or exposed publicly.

## Privacy and safety boundaries

- Phone/challenge state is in memory only, expires five minutes after SMS start, and clears after search, explicit Clear, or process exit. A request already in progress may finish within its five-second timeout; no later query starts after expiry. Security sessions expire in fifteen minutes.
- Reload resumes an active session. Leaving the page clears browser form fields; the server retains an active challenge until expiry/clear. It cannot retract an SMS already sent. No claim of cryptographic memory/OS-swap erasure is made.
- Raw names, addresses, household data, snippets and provider error text are discarded. For a failed Twilio operation, only the HTTP status and a strictly numeric Twilio error code are retained in the existing expiring in-memory session and shown in the local page. Missing fields are shown as unavailable; no response message, phone, OTP, credential, provider request ID or raw body is included in these diagnostics. Results retain source URLs, which may themselves contain personal information. They open only on deliberate clicks with no referrer; opening contacts that source site.
- Fixed HTTPS provider destinations, certificate validation, bounded responses, no redirects, no retries and no fallback. Serper is restricted to `POST https://google.serper.dev/search`, at most ten organic results per query. Malformed responses and access/quota failures are unavailable, not evidence of absence.
- No analytics, third-party browser scripts, or URL/body/key/OTP logging. Report downloads are deliberate, session-protected text/JSON attachments; downloaded files can contain personal information in listing URLs and are not erased by Clear/expiry. Loopback, Host/Origin, HttpOnly/SameSite cookies and session-bound CSRF checks remain. These are local safeguards, not production authentication or protection from compromised local software.
- At most three Twilio SMS starts in ten minutes across tabs, five code checks per challenge, and three search queries per completed scan. Repeated scan submission returns the held report rather than repeating queries.
- Provider retention and billing are outside ScanPlus's control. Free credits must be confirmed in the provider account before the live test. No result is automatically removal-eligible.

## Synthetic verification

```sh
PYTHONDONTWRITEBYTECODE=1 SCANPLUS_DB_PATH=:memory: python3 -m unittest discover -s tests -v
node --check static/app.js
node --check static/live.js
node tool/test_phone_entry.js
node tool/test_live_ui.js brave
node tool/test_live_ui.js serper
```

`test_serper_scan.py` adds configuration, provider-specific consent, exact request shape, response privacy, malformed/quota/error handling, result bounds, destination restrictions and full HTTP flow checks. Existing Brave and demo tests remain. Tests inject fake transport or mock HTTPS; none qualify live availability, billing, schemas, SMS delivery or coverage.

Current evidence and all remaining public-launch prerequisites: `MORNING_READINESS.md` and `evidence/morning-readiness-2026-11-06/`.

Sources reviewed: https://serper.dev (trial offer and organic-result example), https://serper.dev/playground (interactive documentation still requires owner/account review), https://www.twilio.com/docs/verify/api/verification and https://www.twilio.com/docs/verify/api/verification-check. The request contract must still be checked against the authenticated Serper playground and qualified by the authorized live test.

## Report and checklist routes

- GET `/api/report`: current report for the active completed session.
- GET `/api/export.txt` and `/api/export.json`: no-store attachments after current-session/report checks. Other sessions, cleared reports and expired reports cannot export the original report.
- POST `/api/listing/review`: session/Origin/CSRF protected. Requires explicit confirmation and a report-specific candidate ID. Supported actions are `confirm_mine`, `not_mine`, `reset`, and `record_manual_request`. Recording a request requires the listing to be confirmed first. No action sends data outside the local app, and no action marks removal verified.

The official guide destinations are supported by the brokers’ California registry filings; the current site form steps remain unverified. In-page consent now asks the operator to confirm sufficient no-card/free allowance, not accept unlimited provider charges. This is an operator prerequisite, not an API-verified quota or spending cap. Stop before live use unless the account and costs have been checked and authorized.


## Safe Twilio diagnostics (November 6, 2026)

Future failed SMS-start or verification-code requests show only a bounded numeric HTTP
status and Twilio error code, when received. The same fields remain visible after a
read-only page reload until the existing session expires or is cleared. Successful
code verification clears the previous diagnostic. There is no telemetry, automatic retry, additional provider request, or change to the SMS budget.
The optional local activity log described in `LOCAL_ACTIVITY_LOG.md` retains only
fixed event names, numeric statuses/error codes and app phase on this Mac.
A timeout before response headers shows unavailable fields; a malformed/unreadable
response after headers preserves only the known HTTP status. These fields do not
prove SMS delivery, non-delivery, billing, or the specific reason without the matching
provider documentation. They cannot recover an earlier discarded response.

The Python backend loads this change only on a deliberate restart. Editing files or
refreshing the browser does not update an already-running backend. Do not stop an
active user test without permission. Once the user approves ending that session,
stop that exact local process, restart through the already approved local launcher
or properties loader, and reload the local page. The properties loader still requires
explicit live opt-in; this diagnostic change never edits that file, enables live use,
or approves any subsequent SMS or search. Restart alone sends no provider request.
Testing a real request later still requires the existing provider allowance and
per-operation consent. No deployment or public exposure is required.
