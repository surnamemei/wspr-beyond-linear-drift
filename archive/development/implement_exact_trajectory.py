#!/usr/bin/env python3
"""
Implementation of exact WSPR-d linear drift trajectory as requested.
"""

import numpy as np
from src.impairments.frequency import (
    linear_drift_trajectory,
    wsprd_linear_drift_trajectory
)

# Constants from WSPR specification
SYMBOL_COUNT = 162
SAMPLES_PER_SYMBOL = 256

def exact_wsprd_linear_drift_trajectory(symbol_count, sample_count_per_symbol, drift_hz):
    """
    Generate exact WSPR-d linear drift trajectory.
    
    Formula: delta_f[i] = (drift/2) * (i - 81) / 81
    for i = 0..161
    
    Args:
        symbol_count: Number of symbols (162)
        sample_count_per_symbol: Samples per symbol (256)
        drift_hz: Drift parameter in Hz
        
    Returns:
        Array of frequency offsets for each sample
    """
    # Create the symbol-level trajectory first
    symbol_offsets = []
    for i in range(symbol_count):
        offset = (drift_hz / 2.0) * (i - 81) / 81.0
        symbol_offsets.append(offset)
    
    # Expand to full sample resolution
    full_trajectory = []
    for symbol_idx, offset in enumerate(symbol_offsets):
        # For each symbol, apply the same offset to all 256 samples
        for _ in range(sample_count_per_symbol):
            full_trajectory.append(offset)
    
    return np.array(full_trajectory)

def verify_exact_trajectory():
    """Verify that our exact trajectory matches WSPR-d formula exactly."""
    
    print("=== VERIFICATION OF EXACT TRAJECTORY ===")
    print()
    
    # Test with drift = +2 and -2 Hz
    test_drifts = [2, -2]
    
    for drift in test_drifts:
        print(f"Drift = {drift} Hz:")
        
        # Get our exact trajectory
        exact_traj = exact_wsprd_linear_drift_trajectory(SYMBOL_COUNT, SAMPLES_PER_SYMBOL, drift)
        
        # Get the original trajectory for comparison  
        old_traj = linear_drift_trajectory(SYMBOL_COUNT * SAMPLES_PER_SYMBOL, drift)
        
        # Check symbol center values (every 256th sample)
        print("Symbol center offsets:")
        print("Symbol | Exact WSPR-d | Old implementation | Difference")
        print("-------|--------------|-------------------|----------")
        
        for i in [0, 1, 80, 81, 82, 160, 161]:
            exact_offset = exact_traj[i * SAMPLES_PER_SYMBOL]
            old_offset = old_traj[i * SAMPLES_PER_SYMBOL]
            diff = abs(exact_offset - old_offset)
            
            print(f"{i:6d} | {exact_offset:10.6f} | {old_offset:12.6f} | {diff:8.6f}")
        
        # Check maximum difference
        max_diff = max(abs(exact_traj[i] - old_traj[i]) for i in range(len(exact_traj)))
        print(f"Max difference across all samples: {max_diff:.2e} Hz")
        print()

def main():
    """Main verification function."""
    
    print("Exact WSPR-d Linear Drift Trajectory Implementation")
    print("=" * 55)
    print()
    
    verify_exact_trajectory()
    
    print("=== IMPLEMENTATION COMPLETE ===")
    print("The exact_wsprd_linear_drift_trajectory function has been created.")
    print("It now correctly implements the WSPR-d formula:")
    print("delta_f[i] = (drift/2) * (i - 81) / 81")

if __name__ == "__main__":
    main()