#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:---full}
if [[ "$mode" != "--quick" && "$mode" != "--full" ]]; then
    echo 'Usage: bash scripts/run_awgn_baseline.sh [--quick|--full]' >&2
    exit 2
fi

bash "$root/scripts/validate_python_generator.sh"
PYTHONPATH="$root/src" python3 "$root/experiments/01_awgn_baseline.py" "$mode"
