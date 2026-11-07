#!/bin/bash
# Owner-run Serper-only local self-test. Never prints or exports credentials.
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)" || exit 1
cd "$ROOT" || exit 1
PYTHON="/opt/anaconda3/bin/python3"
if [ ! -x "$PYTHON" ]; then
  printf '%s\n' 'The Python installation used for ScanPlus is unavailable.'
  exit 1
fi
printf '%s\n' 'SMS is OFF. Phone ownership will be self-attested, NOT verified.'
printf '%s\n' 'Before continuing, check your Serper dashboard: at least 3 active free queries must remain and no paid top-up may be enabled.'
printf '%s\n' 'This approves at most 3 free Serper queries for one local self-test. No paid usage is authorized. The page will separately ask permission to send your own number to Serper.'
printf '%s\n' 'Startup will use the Serper key in scanplus.local.properties. It will not use Twilio credentials or make any provider call by itself.'
printf '\n%s\n' 'Type FREE 3 NO TOPUP to confirm, or press Return to cancel:'
read -r CONFIRMATION
if [ "$CONFIRMATION" != 'FREE 3 NO TOPUP' ]; then
  printf '%s\n' 'Cancelled. No keys read and no providers called.'
  exit 0
fi
"$PYTHON" -B "$ROOT/local_no_sms_server.py" --local-no-sms --serper-live --confirmed-free-queries 3 --no-paid-topup-confirmed
STATUS=$?
printf '\n%s\n' 'Press Return to close this window.'
read -r _
exit "$STATUS"
