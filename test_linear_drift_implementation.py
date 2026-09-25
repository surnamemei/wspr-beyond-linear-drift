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
    
    # Compare symbol centers (every 256th sample) 
    print("Symbol center values comparison:")
    print("Symbol Index | Old Function | WSPR-d Function | Exact Function | Difference (Old-WSPR)")
    print("-" * 70)
    
    symbol_centers = [i * samples_per_symbol for i in range(symbol_count)]
    
    max_diff_old_wspr = 0.0
    max_diff_exact_wspr = 0.0
    
    for i, center_idx in enumerate(symbol_centers[:10]):  # Show first 10 centers
        old_val = old_traj[center_idx]
        wsprd_val = wsprd_traj[center_idx]
        exact_val = exact_traj[center_idx]
        
        diff_old_wspr = abs(old_val - wsprd_val)
        diff_exact_wspr = abs(exact_val - wsprd_val)
        
        max_diff_old_wspr = max(max_diff_old_wspr, diff_old_wspr)
        max_diff_exact_wspr = max(max_diff_exact_wspr, diff_exact_wspr)
        
        print(f"{i:10d} | {old_val:10.6f} | {wsprd_val:10.6f} | {exact_val:10.6f} | {diff_old_wspr:10.6f}")
    
    print()
    print("Max differences:")
    print(f"Old vs WSPR-d: {max_diff_old_wspr:.8f} Hz")
    print(f"Exact vs WSPR-d: {max_diff_exact_wspr:.8f} Hz")
    
    # Test the actual formula from WSPR-d
    print()
    print("Testing WSPR-d exact formula:")
    print("delta_f[i] = (drift/2) * (i - 81) / 81")
    print()
    
    # Test a few specific values using the exact WSPR-d formula
    test_indices = [0, 40, 81, 120, 161]
    print("Index | WSPR-d Formula | Exact Function | Match?")
    print("-" * 45)
    
    all_match = True
    for i in test_indices:
        expected = (drift/2) * (i - 81) / 81
        actual = exact_traj[i]
        match = abs(expected - actual) < 1e-10
        if not match:
            all_match = False
        print(f"{i:5d} | {expected:10.6f} | {actual:10.6f} | {'✓' if match else '✗'}")
    
    print()
    if all_match:
        print("✓ All formula tests passed - exact implementation matches WSPR-d")
    else:
        print("✗ Some formula tests failed")
        
    # Test that the old function and exact function differ
    print()
    print("Comparing old vs exact implementations:")
    diff_count = 0
    for i in range(total_sample_count):
        if abs(old_traj[i] - exact_traj[i]) > 1e-10:
            diff_count += 1
    
    print(f"Number of differing samples: {diff_count}")
    
    # Test with zero drift to see if they're the same
    print()
    print("Testing with zero drift:")
    zero_old = linear_drift_trajectory(total_sample_count, 0.0)
    zero_exact = exact_wsprd_linear_drift_trajectory(symbol_count, samples_per_symbol, 0.0)
    
    zero_match = all(abs(a - b) < 1e-10 for a, b in zip(zero_old, zero_exact))
    print(f"Zero drift case matches: {zero_match}")
    
    return max_diff_exact_wspr < 1e-10  # Should be essentially zero

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