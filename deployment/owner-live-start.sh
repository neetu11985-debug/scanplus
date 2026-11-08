#!/bin/sh
set -eu
# This script is NOT referenced by the existing demo start script or deployment.
# One process owns transient sessions and the extra local safety ceiling.
# Attempt reservations are durable in Neon. Do not scale or enable preload.
export GUNICORN_CMD_ARGS=''
python - <<'CHECK'
import sys
try:
    import owner_live_wsgi
except Exception:
    print('Private live self-test startup refused: review explicit opt-in, owner login, exact Render host, approved provider configuration and allowance.', file=sys.stderr)
    sys.exit(1)
CHECK
exec python -m gunicorn --config gunicorn.conf.py --workers 1 --threads 1 --worker-class sync owner_live_wsgi:application
