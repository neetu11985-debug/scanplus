#!/bin/bash
# No keys are passed on the command line or printed.
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)" || exit 1
cd "$ROOT" || exit 1
PYTHON="/opt/anaconda3/bin/python3"
if [ ! -x "$PYTHON" ]; then
  printf '%s\n' 'The Python installation used for ScanPlus is unavailable.'
  exit 1
fi
"$PYTHON" -B "$ROOT/tool/local_keys.py" --check
STATUS=$?
printf '\n%s\n' 'Press Return to close this window.'
read -r _
exit "$STATUS"
