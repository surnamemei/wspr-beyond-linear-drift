#!/usr/bin/env python3
"""Execute the refined WSPR-2 linear-drift boundary sweep."""

from __future__ import annotations

import run_linear_drift_map as sweep


sweep.SNR_GRID = (-29.5, -30.0, -30.5, -31.0, -31.5)
sweep.DRIFT_GRID = (0.0, 0.25, -0.25, 0.5, -0.5, 0.75, -0.75, 1.0, -1.0)
sweep.N_PER_CONDITION = 200
sweep.EXPECTED_CONDITIONS = 45
sweep.EXPECTED_TOTAL_TRIALS = 9000
sweep.BASE_SEED = 2026092600
sweep.OUTPUT_DIR = sweep.ROOT / "results" / "csv" / "linear_drift_boundary"
sweep.TRIAL_CSV = sweep.OUTPUT_DIR / "linear_drift_boundary_trials.csv"
sweep.SUMMARY_CSV = sweep.OUTPUT_DIR / "linear_drift_boundary_summary.csv"
sweep.MATRIX_CSV = sweep.OUTPUT_DIR / "linear_drift_boundary_matrix.csv"


def validate_boundary_specification() -> None:
    assert len(sweep.SNR_GRID) == 5
    assert len(sweep.DRIFT_GRID) == 9
    assert sweep.N_PER_CONDITION == 200
    assert (
        len(sweep.SNR_GRID) * len(sweep.DRIFT_GRID) * sweep.N_PER_CONDITION
        == sweep.EXPECTED_TOTAL_TRIALS
        == 9000
    )


sweep.validate_specification = validate_boundary_specification


if __name__ == "__main__":
    raise SystemExit(sweep.main())
