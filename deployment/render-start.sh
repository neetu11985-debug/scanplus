#!/bin/sh
set -eu
# Override Render's --preload and access logging defaults, including dashboard values.
export GUNICORN_CMD_ARGS=''
# Fail with a sanitized actionable message rather than printing config or secrets.
python - <<'CHECK'
import sys
try:
    import render_wsgi
except Exception:
    print('Staging startup refused: check owner-set login, exact Render hostname and runtime configuration.', file=sys.stderr)
    sys.exit(1)
CHECK
exec python -m gunicorn --config gunicorn.conf.py render_wsgi:application "$@"
