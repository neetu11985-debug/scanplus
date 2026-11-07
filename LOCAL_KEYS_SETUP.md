# Paste keys into a local file, not Terminal

The owner-edited file is `/Users/rajeshkumar/dev/ScanPlus codes/scanplus.local.properties`.
It starts with **empty credential values** and live startup **disabled**. No key was created,
entered, copied, read from another app, verified or transmitted during this setup.

## Without pasting in Terminal

1. Open Finder, choose **Go > Go to Folder**, and enter `/Users/rajeshkumar/dev/ScanPlus codes`.
2. Double-click **Open ScanPlus Keys.command**. It opens the properties file in TextEdit.
   Alternatively, right-click `scanplus.local.properties`, choose **Open With > TextEdit**.
3. Paste each value after its `=`: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
   `TWILIO_VERIFY_SERVICE_SID`, and `SERPER_API_KEY`. Leave `BRAVE_SEARCH_API_KEY` empty.
   One value per line. Do not add `export`, a shell command, or extra comments after values.
4. Save with Command-S as **plain text**, keeping the exact name and local folder.
   Do not save to iCloud, email, chat, a shared drive, or a public web folder.
5. Double-click **Check ScanPlus Keys.command**. This checks only local syntax/completeness.
   It does not call Twilio/Serper, verify that a key works, check credits, or send an SMS.
6. Only after provider accounts, no-card/free allowance or costs, and the live actions are
   approved, change `SCANPLUS_LOCAL_LIVE_TEST=0` to `SCANPLUS_LOCAL_LIVE_TEST=1` yourself.
   Then double-click **Start ScanPlus Local.command**. It starts only the loopback self-test.
   Open the printed `http://127.0.0.1:4175` address in your approved browser yourself.
   No browser opens automatically. Stop the server with Control-C in its Terminal window.

The two check/start launchers open Terminal but require **no key pasting there**.
If macOS blocks a launcher, do not bypass a security warning. Open the properties file
with TextEdit and ask for help with the specific warning.

## What the file does and does not protect

- The file is created with owner-only `600` permissions. The loader rejects files owned
  by another user, group/world-readable files, symlinks, hard links, and oversized files.
  It never changes an existing credential file or its permissions automatically.
- This is **plaintext storage, not encryption or Keychain**. Other programs running as you,
  admins, malware, editor recovery files, and backups may read it. Close TextEdit after
  saving. Do not screenshot or send the file, and avoid cloud-synced editors/backups.
- `.gitignore` excludes the local properties file and similarly named editor/backup copies;
  the blank `.example` template is safe to track. Git ignore is not encryption, does not
  protect against other sync tools, and cannot untrack an already committed secret.
  This project currently has no Git repository, so exclusions take effect if one is added.
- Values are parsed as data, never sourced/evaluated as shell commands. Keys are passed
  directly in server memory, not shell history, command-line arguments, logs or exported
  environment variables. The app does not load `.env` automatically.
- The loader does not read saved browser credentials or create/configure any provider
  account. Startup alone sends no provider request. The page still requires consent for
  Twilio SMS/code checks and the selected search provider. Actual calls transmit the
  relevant credential to its matching provider and may incur provider costs.
- Format success is not proof of valid credentials, eligible accounts, live operation,
  billing limits, or production readiness. Do not share the populated file for debugging.
- If TextEdit adds `.txt`/`.rtf`, saves rich text, or changes file permissions, the check
  fails closed. Keep the original filename, use plain text, and ask for help if needed.

## Optional commands (no secret values)

From the project folder: `python3 -B tool/local_keys.py --check`.
After approvals and explicit opt-in: `python3 -B tool/local_keys.py --start`.
Running `local_live_server.py` directly retains its existing environment-only behavior;
use the new loader or the double-click launcher to read the properties file.

See `LOCAL_LIVE_TEST.md` for the live-action gates and privacy limitations.
