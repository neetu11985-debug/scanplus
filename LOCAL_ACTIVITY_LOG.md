# View the safe local activity log

In the ScanPlus project folder, double-click **Open ScanMyDigits Logs.command**.
It shows the latest 50 safe entries and follows new ones. Control-C stops the viewer,
not the app. The viewer makes no network calls and never starts an SMS or search.

The updated server writes `.data/scanmydigits-local.log`, an owner-only 600 file.
Entries contain UTC time, a fixed event name, local HTTP response status, app phase,
and, on failed verification actions, the provider HTTP status and numeric Twilio
error code when received. No phone, OTP, credentials, headers, request URLs, provider
message, raw response body, report/listing details, or request/session identifiers
are logged. The viewer independently validates the schema and never prints raw or
unknown file fields. The log is not served through any app HTTP route.

A `sms_start` or `code_check` line identifies a local request/response, not confirmed
SMS delivery or a charge. Local HTTP status and provider HTTP status are distinct.
A rejected consent/validation request has no provider status. Reload/session-read
entries do not mean another provider request occurred. The original failed request
cannot be reconstructed from this new log.

Logging is prepared but does not become active in an already-running Python process.
A deliberate user-approved restart is required. Until then the viewer reports that
no readable log exists, while the current app and in-page numeric diagnostics keep
working. Merely opening the viewer does not restart the app. No credential file or
startup opt-in is changed by this feature.

The log is capped at 1 MiB. At the cap it stops appending rather than deleting or
truncating old entries. It remains on this Mac after app sessions clear/expire until
the owner moves or deletes it. Logging refuses symlinks, hard links, nonregular
files or files with non-private permissions. A logging failure never retries a
provider request or blocks the app. Do not paste credentials into this log file.

Command-line alternative from this folder: `python3 -B tool/view_local_log.py --follow`.
Omit `--follow` for a one-time read. Tests use synthetic data and temporary log files.
