#!/bin/bash
# Private no-SMS preflight. Does not read properties or provider credentials.
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)" || exit 1
cd "$ROOT" || exit 1
PYTHON="/opt/anaconda3/bin/python3"
if [ ! -x "$PYTHON" ]; then
  printf '%s\n' 'The Python installation used for ScanPlus is unavailable.'
  exit 1
fi
"$PYTHON" -B "$ROOT/local_no_sms_server.py" --local-no-sms
STATUS=$?
printf '\n%s\n' 'Press Return to close this window.'
read -r _
exit "$STATUS"
