# ScanMyDigits data-flow review

Source baseline: main `c9a252e554fcc3cafee341753c1737ac9aa3a9de` from
https://github.com/neetu11985-debug/scanplus . This is code review, not inspection of
the owner's credentials, customer databases, provider accounts or hosted logs.

## Current protected Render staging

`render_wsgi.py` forces synthetic demo mode, disables Stripe and live search/SMS,
and overrides the database to `:memory:`. All routes require the owner-set staging
Basic-auth login and exact HTTPS hostname/origin. The demo accepts only reserved
fixture numbers. No Serper, Brave, Twilio or Stripe request originates from this
entry point. The hosting provider still processes web requests and may retain
infrastructure/network metadata; this review cannot verify its account-level logs
or retention. The app disables request logging in its handlers/Gunicorn config.

`server.py`/`storage.py` currently persist synthetic session, receipt, report-related
and removal-test state as JSON when a file DB is used locally. They store an
ordinary SHA-256 reference to the synthetic number, not an encrypted real phone.
Session default is 15 minutes; challenge default five minutes; demo receipt history
defaults to eight days. These are demo settings, not production customer policy.

The separate “enter my own number” input-only panel in `static/app.js` validates in
the browser and clears its input. It does not send that number to the backend or
save it to browser storage. Browser/autofill behavior is outside the app's control.

## Optional local live self-test, only if separately enabled

- **Twilio Verify**: `live_scan.py` sends a phone number and SMS channel to
  `https://verify.twilio.com/v2/Services/{service}/Verifications`; verification sends
  verification SID plus entered OTP to `VerificationCheck`. Twilio returns state
  including the phone. SMS delivery involves Twilio and the relevant carriers.
  This code does not implement Twilio Lookup/line-type enrichment.
- **Serper**: sends the phone inside a quoted search string plus a target site to
  `https://google.serper.dev/search`. It currently issues at most one query for each
  of three sites: Spokeo, TruePeopleSearch and Whitepages. Serper supplies Google
  search-index results. The code directly contacts Serper; it does not establish
  Serper's onward-processing, logging, subprocessor or retention behavior.
- **Brave Search**, only if explicitly selected instead: sends the corresponding
  phone query to `https://api.search.brave.com/res/v1/web/search`. No automatic
  provider fallback is coded.
- **No-SMS local self-test**: `no_sms_scan.py` deliberately has no Twilio operation;
  only separately authorized Serper search is possible, bounded to three attempts.
  Ownership is self-attested, not verified; that is not a production customer gate.

These local paths keep phone/report state in process memory with a five-minute
lifetime. The raw phone is dropped from session state when a scan begins; report
URLs can themselves contain a phone or other personal information, so reports
must be treated as personal data. Clear/expiry removes held state, but does not
erase providers' copies or downloaded files. Local logs allow only timestamps,
event types, phases, numeric HTTP/Twilio error codes, with a size bound; no phone,
OTP, credential or report payload is intentionally logged. No time-based log
retention schedule is implemented.

## Payments, links and exports

Optional `stripe_checkout.py` sends the fixed test price/currency, opaque order and
reference IDs, product label and return/cancel URLs to `https://api.stripe.com`.
It does not include the user's phone in Checkout creation. The browser visits
`https://checkout.stripe.com` and supplies its test payment information directly to
Stripe. App storage retains selected order/Checkout/payment IDs and statuses, not
card details. Current Render staging disables this entire flow. No production
charging is implemented or verified.

The app never automatically visits discovered listings or submits real removals.
When the user deliberately follows a listing/removal link, that website receives
the browser request and any personal data present in its URL or entered in its
form. `no-referrer` limits referrer leakage but does not remove data in the target
URL. A report download goes to the requesting user's device and remains there
independently of app expiry/deletion. The demo JSON export and optional local text
exports are not encrypted downloadable files.

No AI model, analytics service or external-font destination appears in the reviewed
app code. That is a code-scope statement, not a claim about browser extensions,
hosting infrastructure or every third-party service's internal processing.

## Required privacy decisions before launch

Disclose exact recipients and purposes before live phone transmission. Verify
provider/host terms, retention, location and subprocessors directly for the chosen
accounts. Do not promise data “never leaves our database.” Encryption protects
stored copies, while an authorized verification/search operation necessarily
decrypts the phone in server memory and shares it with its approved provider.

The new local proposal encrypts paid-user phone and complete report content before
DB persistence, but is not connected to any existing runtime. See
`SECURE_STORAGE_DESIGN.md` for payment gates, retention choices, migration and the
unconfigured 70% usage-alert plan.
