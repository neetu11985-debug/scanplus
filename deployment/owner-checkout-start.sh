#!/bin/sh
set -eu
# Opt-in private test only. Existing Render demo start command is unchanged.
export GUNICORN_CMD_ARGS=''
python - <<'CHECK'
import sys
try:
    import owner_checkout_wsgi
except Exception:
    print('Private owner checkout test startup refused: review explicit opt-in, private login, provider allowance, Stripe test key and optional test coupon.', file=sys.stderr)
    sys.exit(1)
CHECK
exec python -m gunicorn --config gunicorn.conf.py --workers 1 --threads 1 --worker-class sync owner_checkout_wsgi:application
