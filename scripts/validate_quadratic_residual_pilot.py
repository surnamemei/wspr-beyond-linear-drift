#!/usr/bin/env python3
"""Preflight the exact Phase 2C symbolwise quadratic specification."""

from __future__ import annotations

import math
from pathlib import Path
import sys
import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from impairments.frequency import wspr_symbol_quadratic_residual_trajectory


def main() -> int:
    x = (np.arange(162) - 81.0) / 81.0
    basis = np.column_stack([np.ones_like(x), x])
    failed = False
    print("TRAJECTORY_VALIDATION")
    print("A_res_hz,mean_hz,max_abs_hz,linear_fit_c0,linear_fit_c1,dot_with_constant,dot_with_x")
    for amplitude in (0.125, 0.5, 1.0):
        trajectory = wspr_symbol_quadratic_residual_trajectory(
            n_symbols=162, samples_per_symbol=256, amplitude_hz=amplitude
        )
        assert len(trajectory) == 162 * 256
        assert trajectory == wspr_symbol_quadratic_residual_trajectory(
            n_symbols=162, samples_per_symbol=256, amplitude_hz=amplitude
        )
        symbols = trajectory[::256]
        assert all(trajectory[index * 256 : (index + 1) * 256] == (symbols[index],) * 256
                   for index in range(162))
        mean_y = math.fsum(symbols) / len(symbols)
        max_abs = max(abs(value) for value in symbols)
        c0, c1 = np.linalg.lstsq(basis, np.asarray(symbols), rcond=None)[0]
        dot_constant = math.fsum(symbols)
        dot_x = math.fsum(float(xi) * yi for xi, yi in zip(x, symbols))
        assert abs(mean_y) <= 1e-12
        assert math.isclose(max_abs, amplitude, rel_tol=0.0, abs_tol=1e-12)
        print(f"{amplitude},{mean_y:.17g},{max_abs:.17g},{c0:.17g},{c1:.17g},{dot_constant:.17g},{dot_x:.17g}")
        failed |= any(abs(value) >= 1e-12 for value in (c0, c1, dot_constant, dot_x))
    if failed:
        print("quadratic projection exceeds floating-point tolerance; Monte Carlo stopped", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
