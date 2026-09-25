#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
runtime="$root/.cache/runtime"
binary="$runtime/usr/bin/wsprd"
[[ -x "$binary" ]] || { echo 'Run bash scripts/setup_wsprd.sh first.' >&2; exit 1; }

library_path="$runtime/usr/lib/x86_64-linux-gnu"
export LD_LIBRARY_PATH="$library_path${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$binary" "$@"
