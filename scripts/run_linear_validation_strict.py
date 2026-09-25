#!/usr/bin/env python3
"""Strict linear drift validation experiment runner."""

import sys
import os
import time
import csv
import subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import random

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / ".." / "src"))

def run_experiment():
    """Run the strict linear drift validation experiment."""
    
    print("=== STRICT LINEAR DRIFT VALIDATION EXPERIMENT ===")
    print()
    
    # Experiment specification
    noiseless_conditions = [0, 1, -1, 2, -2, 3, -3, 4, -4]
    high_snr_conditions = [0, 1, -1, 2, -2, 3, -3, 4, -4]
    N_NOISELESS = 1
    N_HIGH_SNR = 20
    N_PAIRED = 200
    
    print("Experiment Specification:")
    print(f"  Noiseless conditions: {noiseless_conditions}")
    print(f"  High-SNR conditions: {high_snr_conditions}")
    print(f"  N (noiseless): {N_NOISELESS}")
    print(f"  N (high-SNR): {N_HIGH_SNR}")
    print(f"  N (paired): {N_PAIRED}")
    print()
    
    # Assertions
    assert len(noiseless_conditions) == 9
    assert len(high_snr_conditions) == 9
    assert N_PAIRED == 200
    
    print("Experiment specification validated.")
    print()
    
    # Create results directory if it doesn't exist
    results_dir = Path(__file__).parent.parent / "results" / "csv" / "stages"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Prepare the experiment runner script path
    runner_script = Path(__file__).parent / "run_frequency_experiment.sh"
    
    # Execute noiseless experiments without invoking the AWGN path.
    print("Running noiseless experiments...")
    noiseless_results = []
    for i, drift in enumerate(noiseless_conditions):
        print(f"[NOISELESS {i+1}/{len(noiseless_conditions)}] Drift: {drift} Hz")
        try:
            cmd = [
                str(runner_script),
                "--kind", "linear",
                "--values", str(drift),
                "--no-noise",
                "--trials", str(N_NOISELESS),
                "--prefix", f"linear_strict_noiseless_{drift}",
                "--base-seed", str(2026092500 + i),
                "--workers", "1"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            noiseless_results.append((drift, result.stdout))
        except subprocess.CalledProcessError as e:
            print(f"Error running noiseless experiment for drift {drift}: {e}")
            sys.exit(1)
    
    # Execute high-SNR experiments
    print("Running high-SNR experiments...")
    high_snr_results = []
    for i, drift in enumerate(high_snr_conditions):
        print(f"[SNR20 {i+1}/{len(high_snr_conditions)}] Drift: {drift} Hz")
        try:
            cmd = [
                str(runner_script),
                "--kind", "linear",
                "--values", str(drift),
                "--snrs", "-20",
                "--trials", str(N_HIGH_SNR),
                "--prefix", f"linear_strict_snr20_{drift}",
                "--base-seed", str(2026092510 + i),
                "--workers", "2"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            high_snr_results.append((drift, result.stdout))
        except subprocess.CalledProcessError as e:
            print(f"Error running high-SNR experiment for drift {drift}: {e}")
            sys.exit(1)
    
    # Execute paired experiments at SNR = -31
    print("Running paired experiments...")
    paired_results = []
    
    # For paired experiments, we need to run 3 conditions with 200 trials each
    paired_conditions = [0, 2, -2]  # drift values for paired test
    
    for i, drift in enumerate(paired_conditions):
        print(f"[PAIRED {i+1}/{len(paired_conditions)}] Drift: {drift} Hz")
        try:
            cmd = [
                str(runner_script),
                "--kind", "linear",
                "--values", str(drift),
                "--snrs", "-31",
                "--trials", str(N_PAIRED),
                "--prefix", f"linear_strict_paired_{drift}",
                "--base-seed", str(2026092520 + i),
                "--workers", "2"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            paired_results.append((drift, result.stdout))
        except subprocess.CalledProcessError as e:
            print(f"Error running paired experiment for drift {drift}: {e}")
            sys.exit(1)
    
    print("All experiments completed successfully.")
    print()
    
    RAW_CSV_PATHS = []
    for drift in noiseless_conditions:
        prefix = f"linear_strict_noiseless_{drift}"
        RAW_CSV_PATHS.extend(
            [results_dir / f"{prefix}_trials.csv", results_dir / f"{prefix}_summary.csv"]
        )
    for drift in high_snr_conditions:
        prefix = f"linear_strict_snr20_{drift}"
        RAW_CSV_PATHS.extend(
            [results_dir / f"{prefix}_trials.csv", results_dir / f"{prefix}_summary.csv"]
        )
    for drift in paired_conditions:
        prefix = f"linear_strict_paired_{drift}"
        RAW_CSV_PATHS.extend(
            [results_dir / f"{prefix}_trials.csv", results_dir / f"{prefix}_summary.csv"]
        )

    print("Generated CSV files:")
    for path in RAW_CSV_PATHS:
        print(f"  {path}")

if __name__ == "__main__":
    run_experiment()
