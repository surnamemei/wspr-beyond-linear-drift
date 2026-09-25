#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
export PYTHONPATH="$root/src"

echo "=== LINEAR DRIFT VALIDATION TESTS ==="

# First, run noiseless tests (drift = 0, ±1, ±2, ±3, ±4)
echo ""
echo "1. RUNNING NOISELESS TESTS (SNR = ∞)"
echo "-----------------------------------"
bash scripts/run_frequency_experiment.sh \
    --kind linear \
    --values 0 1 2 3 4 \
    --no-noise \
    --trials 1 \
    --prefix linear_noiseless \
    --base-seed 2026092500 \
    --workers 1

echo ""
echo "2. RUNNING SNR = -20 dB TESTS"
echo "----------------------------"
bash scripts/run_frequency_experiment.sh \
    --kind linear \
    --values 0 1 2 3 4 \
    --snrs -20 \
    --trials 20 \
    --prefix linear_snr20 \
    --base-seed 2026092510 \
    --workers 2

echo ""
echo "3. RUNNING CRITICAL PAIRED A/B TESTS AT SNR = -31 dB"
echo "---------------------------------------------------"
# Run the critical paired tests with exact seeds
bash scripts/run_frequency_experiment.sh \
    --kind linear \
    --values 0 2 -2 \
    --snrs -31 \
    --trials 200 \
    --prefix linear_paired \
    --base-seed 2026092520 \
    --workers 2

echo ""
echo "=== VALIDATION TESTS COMPLETE ==="
