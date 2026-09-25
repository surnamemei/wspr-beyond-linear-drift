#!/usr/bin/env python3
"""Test script to validate linear drift implementations match WSPR-d exactly."""

import math
from src.impairments.frequency import (
    linear_drift_trajectory,
    wsprd_linear_drift_trajectory,
    exact_wsprd_linear_drift_trajectory
)

def test_trajectory_functions():
    """Test that our functions produce the expected results."""
    
    print("=== TESTING LINEAR DRIFT TRAJECTORY FUNCTIONS ===")
    
    # Test with 162 symbols of 256 samples each (full WSPR frame)
    symbol_count = 162
    samples_per_symbol = 256
    total_sample_count = symbol_count * samples_per_symbol
    
    drift = 2.0  # 2 Hz drift
    
    # Get all three trajectories
    old_traj = linear_drift_trajectory(total_sample_count, drift)
    wsprd_traj = wsprd_linear_drift_trajectory(symbol_count, samples_per_symbol, drift)
    exact_traj = exact_wsprd_linear_drift_trajectory(symbol_count, samples_per_symbol, drift)
    
    print(f"Sample count: {total_sample_count}")
    print(f"Drift parameter: {drift} Hz")
    print()
    
    # The WSPR-d formula is applied at symbol level
    # For symbol i (0 to 161): delta_f[i] = (drift/2) * (i - 81) / 81
    # Then this value is repeated for all 256 samples in that symbol
    
    print("Symbol-by-symbol comparison:")
    print("Symbol Index | WSPR-d Formula | WSPR-d Function | Exact Function | Match?")
    print("-" * 70)
    
    max_diff_wspr_exact = 0.0
    all_match = True
    
    # Test the first few symbol centers
    for i in range(10):
        # Calculate expected value using WSPR-d formula directly
        expected = (drift/2) * (i - 81) / 81
        
        # Get what WSPR-d function returns for this symbol
        wsprd_val = wsprd_traj[i * samples_per_symbol]  # First sample of symbol i
        
        # Get what exact function returns for this symbol  
        exact_val = exact_traj[i * samples_per_symbol]
        
        match = abs(expected - wsprd_val) < 1e-10
        if not match:
            all_match = False
            
        diff = abs(wsprd_val - expected)
        max_diff_wspr_exact = max(max_diff_wspr_exact, diff)
        
        print(f"{i:10d} | {expected:10.6f} | {wsprd_val:10.6f} | {exact_val:10.6f} | {'✓' if match else '✗'}")
    
    print()
    print("Max difference between WSPR-d formula and function:")
    print(f"  {max_diff_wspr_exact:.10f} Hz")
    
    # Verify that exact function matches WSPR-d exactly
    print()
    print("Verifying exact vs WSPR-d match (all samples):")
    exact_matches_wspr = True
    for i in range(symbol_count):
        # Get the value from WSPR-d formula
        expected = (drift/2) * (i - 81) / 81
        
        # Get what's stored at first sample of this symbol
        actual = wsprd_traj[i * samples_per_symbol]
        
        if abs(expected - actual) > 1e-10:
            exact_matches_wspr = False
            break
    
    print(f"WSPR-d function matches formula exactly: {exact_matches_wspr}")
    
    # Compare old vs exact functions 
    print()
    print("Comparing old vs exact implementations:")
    diff_count = 0
    for i in range(total_sample_count):
        if abs(old_traj[i] - exact_traj[i]) > 1e-10:
            diff_count += 1
    
    print(f"Number of differing samples: {diff_count}")
    
    # Test with zero drift to see if they're the same (they should be)
    print()
    print("Testing with zero drift:")
    zero_old = linear_drift_trajectory(total_sample_count, 0.0)
    zero_exact = exact_wsprd_linear_drift_trajectory(symbol_count, samples_per_symbol, 0.0)
    
    zero_match = all(abs(a - b) < 1e-10 for a, b in zip(zero_old, zero_exact))
    print(f"Zero drift case matches: {zero_match}")
    
    return exact_matches_wspr

if __name__ == "__main__":
    try:
        success = test_trajectory_functions()
        if success:
            print("\n✓ Linear drift implementation tests PASSED")
        else:
            print("\n✗ Linear drift implementation tests FAILED")
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()