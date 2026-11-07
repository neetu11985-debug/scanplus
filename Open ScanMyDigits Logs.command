#!/bin/bash
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)" || exit 1
exec /opt/anaconda3/bin/python3 -B -u "$ROOT/tool/view_local_log.py" --follow
