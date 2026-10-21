#!/usr/bin/env bash
set -euo pipefail
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
command -v python3 >/dev/null || { echo 'OPRIT: lipsește python3. Nu instalez nimic.' >&2; exit 1; }
exec python3 "$HERE/export_safe.py" "$@"
