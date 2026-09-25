#!/usr/bin/env python3
"""Final validation of linear drift control results."""

import csv
from pathlib import Path

def parse_summary_file(file_path):
    """Parse a summary CSV file and return the data."""
    data = []
    with open(file_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data

def main():
    print("=== LINEAR DRIFT CONTROL VALIDATION ===")
    print()
    
    # Check if we have the full paired test results
    trial_file = Path("results/csv/stages/linear_full_paired_trials.csv")
    summary_file = Path("results/csv/stages/linear_full_paired_summary.csv")
    
    if not summary_file.exists():
        print("ERROR: No results found for linear_full_paired experiment")
        print("This indicates the full test did not complete or was not run.")
        return
    
    # Parse the summary data
    try:
        summary_data = parse_summary_file(summary_file)
        
        print("Results from linear_drift paired A/B test (SNR = -31 dB):")
        print("=" * 70)
        print(f"{'Condition':<15} {'Value (Hz)':<12} {'N':<6} {'Successes':<9} {'P_decode':<10} {'Wilson CI':<15}")
        print("-" * 70)
        
        conditions = {}
        for row in summary_data:
            value = float(row['value_hz'])
            conditions[value] = {
                'n': int(row['n']),
                'successes': int(row['successes']),
                'p_decode': float(row['p_decode']),
                'ci_low': float(row['ci_low']),
                'ci_high': float(row['ci_high'])
            }
        
        # Print results for all conditions
        for value in sorted(conditions.keys()):
            data = conditions[value]
            ci_str = f"[{data['ci_low']:.3f}, {data['ci_high']:.3f}]"
            print(f"{'A (0 Hz)':<15} {value:<12.1f} {data['n']:<6} {data['successes']:<9} {data['p_decode']:<10.3f} {ci_str}")
        
        print()
        print("PAIRED COMPARISON ANALYSIS:")
        print("-" * 40)
        
        # Compare A vs B and A vs C (where A=0, B=old, C=exact)
        if 0 in conditions and 2 in conditions:
            a_data = conditions[0]
            b_data = conditions[2]  # old implementation
            c_data = conditions[-2]  # exact implementation
            
            print("A (0 Hz) vs B (+2 Hz - old impl):")
            print(f"  P_decode: {a_data['p_decode']:.3f} vs {b_data['p_decode']:.3f}")
            
            print("A (0 Hz) vs C (-2 Hz - exact impl):")
            print(f"  P_decode: {a_data['p_decode']:.3f} vs {c_data['p_decode']:.3f}")
        
        print()
        print("RAW CSV FILES:")
        print("-" * 20)
        print(f"Trial data: {trial_file}")
        print(f"Summary data: {summary_file}")
        
    except Exception as e:
        print(f"Error reading results: {e}")

if __name__ == "__main__":
    main()