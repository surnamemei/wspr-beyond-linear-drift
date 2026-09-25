#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
export PYTHONPATH="$root/src"
exec python3 experiments/02_frequency_model_mismatch.py "$@"
