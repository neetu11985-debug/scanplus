#!/bin/bash
# Opens only the owner-edited local file, not a website or provider.
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)" || exit 1
/usr/bin/open -a TextEdit "$ROOT/scanplus.local.properties"
