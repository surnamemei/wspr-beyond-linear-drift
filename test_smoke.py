#!/usr/bin/env python3
"""Smoke test for true noiseless operation."""

import subprocess
import sys
import os

def main():
    print("Running smoke test for true noiseless operation...")
    
    # Run a single smoke test with drift = 0, N = 1, --no-noise flag
    cmd = [
        sys.executable, "experiments/02_frequency_model_mismatch.py",
        "--kind", "linear",
        "--values", "0",
        "--trials", "1",
        "--prefix", "smoke_test",
        "--base-seed", "42",
        "--workers", "1",
        "--no-noise"
    ]
    
    print("Command executed:")
    print(" ".join(cmd))
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print(f"Exit code: {result.returncode}")
    
    if result.stdout:
        print("STDOUT:")
        print(result.stdout[-1000:])  # Show last 1000 chars
    if result.stderr:
        print("STDERR:")  
        print(result.stderr[-1000:])  # Show last 1000 chars
    
    # Check if wsprd decoded the correct message
    if "K1ABC FN42 33" in result.stdout:
        print("SUCCESS: wsprd decoded the correct message")
    else:
        print("WARNING: Message not found in output")
        
    # Look for CSV output file
    import glob
    csv_files = glob.glob("results/csv/stages/smoke_test_*.csv")
    if csv_files:
        print(f"Output CSV files created: {csv_files}")
        for f in csv_files:
            print(f"  - {f}")
    else:
        print("No CSV output files found")
        
    return result.returncode

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"Smoke test failed: {e}")
        raise SystemExit(1)
