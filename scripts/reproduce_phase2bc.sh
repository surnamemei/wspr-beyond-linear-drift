#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
export PYTHONPATH="$root/src"

bash scripts/validate_official_reference.sh
bash scripts/validate_python_generator.sh
python3 -m unittest discover -s tests -v

bash scripts/run_frequency_experiment.sh --kind cfo --values -150 -100 -50 -20 -10 -5 0 5 10 20 50 100 150 --snrs -29 -31 -32 --trials 20 --prefix cfo_quick --base-seed 2026100000 --workers 2
bash scripts/run_frequency_experiment.sh --kind cfo --values -100 0 100 --snrs -29 -31 -32 --trials 100 --prefix cfo_confirm --base-seed 2026400000 --workers 2
bash scripts/run_frequency_experiment.sh --kind linear --values -4 -2 0 2 4 --snrs -29 -31 --trials 20 --prefix linear_exact_check --base-seed 2026300000 --workers 4
bash scripts/run_frequency_experiment.sh --kind linear --values -2 0 2 --snrs -29 -31 -32 --trials 200 --prefix linear_confirm --base-seed 2026500000 --workers 2
python3 scripts/analyze_frequency_controls.py
