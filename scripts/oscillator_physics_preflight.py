#!/usr/bin/env python3
"""Fractional-frequency oscillator-noise shape preflight; no decoder calls.

The three synthetic processes are scaling probes, not metrology references.
Allan-variance convention and expected power-law slopes follow NIST SP 1065:
https://doi.org/10.6028/NIST.SP.1065
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wspr.waveform import SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT, SYMBOL_DURATION_S

NOISE_TYPES = ("white_FM", "flicker_FM", "random_walk_FM")
F_CARRIER_HZ = (7e6, 10e6, 14e6, 28e6)
SIGMA_Y_REF = (1e-10, 3e-10, 1e-9, 3e-9, 1e-8)
N_TRAJECTORIES_PER_CELL = 500
TAU_SECONDS = (1, 2, 4, 8, 16, 32)
SLOPE_TAUS = (1, 2, 4, 8, 16)
EXPECTED_SLOPES = {"white_FM": -0.5, "flicker_FM": 0.0, "random_walk_FM": 0.5}
SLOPE_TOLERANCE = 0.18
SEED_BASE = 2026101000
OUTPUT_DIR = ROOT / "results/analysis/oscillator_physics_preflight"
METRICS_PATH = OUTPUT_DIR / "oscillator_preflight_trajectory_metrics.csv"
SUMMARY_PATH = OUTPUT_DIR / "oscillator_preflight_summary.csv"
ALLAN_PATH = OUTPUT_DIR / "oscillator_allan_deviation.csv"
FIGURE_PATHS = {
    "allan": OUTPUT_DIR / "allan_deviation_by_noise_type.png",
    "stability": OUTPUT_DIR / "residual_rms_vs_stability.png",
    "carrier": OUTPUT_DIR / "residual_rms_vs_carrier.png",
    "distributions": OUTPUT_DIR / "residual_descriptor_distributions.png",
    "examples": OUTPUT_DIR / "projected_example_trajectories.png",
}
DESCRIPTORS = (
    "frequency_rms_hz", "max_abs_frequency_hz", "peak_to_peak_hz",
    "residual_frequency_rms_hz", "residual_max_abs_frequency_hz",
    "residual_peak_to_peak_hz", "max_abs_phase_rad", "phase_rms_rad",
    "fitted_constant_hz", "fitted_linear_coefficient",
)


def allan_variance(y: np.ndarray, m: int, axis: int = -1) -> np.ndarray:
    """Overlapping Allan variance from contiguous averages of m frequency samples."""
    y = np.asarray(y, dtype=np.float64)
    n = y.shape[axis]
    if m < 1 or 2 * m >= n:
        raise ValueError(f"Averaging factor {m} lacks valid support in {n} samples")
    sums = np.cumsum(y, axis=axis, dtype=np.float64)
    zero_shape = list(y.shape)
    zero_shape[axis] = 1
    sums = np.concatenate((np.zeros(zero_shape), sums), axis=axis)
    first = np.take(sums, np.arange(m, n - m + 1), axis=axis) - np.take(
        sums, np.arange(0, n - 2 * m + 1), axis=axis
    )
    second = np.take(sums, np.arange(2 * m, n + 1), axis=axis) - np.take(
        sums, np.arange(m, n - m + 1), axis=axis
    )
    return 0.5 * np.mean(((second - first) / m) ** 2, axis=axis)


def base_process(kind: str, seed: int, n_seconds: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if kind == "white_FM":
        return rng.standard_normal(n_seconds)
    if kind == "random_walk_FM":
        return np.concatenate(([0.0], np.cumsum(rng.standard_normal(n_seconds - 1))))
    if kind == "flicker_FM":
        # Long finite 1/f realization, then a WSPR-length interior segment.
        # The explicit low-frequency cutoff is 1/8192 Hz; no DC term.
        n_fft = 8192
        white = rng.standard_normal(n_fft)
        spectrum = np.fft.rfft(white)
        frequencies = np.fft.rfftfreq(n_fft, d=1.0)
        scale = np.zeros_like(frequencies)
        scale[1:] = frequencies[1:] ** -0.5
        colored = np.fft.irfft(spectrum * scale, n=n_fft)
        start = (n_fft - n_seconds) // 2
        return colored[start:start + n_seconds].copy()
    raise ValueError(kind)


def project(raw: np.ndarray, basis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    beta = np.linalg.lstsq(basis, raw, rcond=None)[0]
    return beta, raw - basis @ beta


def phase_descriptors(residual: np.ndarray) -> tuple[float, float]:
    """Match samplewise phase accumulator without allocating 41,472 samples."""
    m = SAMPLES_PER_SYMBOL
    step = 2 * np.pi * residual / SAMPLE_RATE_HZ
    start = np.concatenate(([0.0], np.cumsum(step[:-1] * m)))
    last_sample = start + (m - 1) * step
    max_abs = float(np.maximum(np.abs(start), np.abs(last_sample)).max())
    sum_k = m * (m - 1) / 2
    sum_k2 = m * (m - 1) * (2 * m - 1) / 6
    sum_square = np.sum(m * start**2 + 2 * start * step * sum_k + step**2 * sum_k2)
    return max_abs, float(np.sqrt(sum_square / (len(residual) * m)))


def slope_check(base_by_family: dict[str, np.ndarray], sampled_index: np.ndarray,
                basis: np.ndarray) -> tuple[list[dict[str, float | str]], dict[str, np.ndarray]]:
    checks = []
    projected = {}
    projected_taus = np.array((2, 4, 8, 16))
    for kind, block in base_by_family.items():
        raw_adev = np.array([np.sqrt(np.mean(allan_variance(block, m, axis=1)))
                             for m in TAU_SECONDS])
        slope = float(np.polyfit(np.log(SLOPE_TAUS), np.log(raw_adev[:len(SLOPE_TAUS)]), 1)[0])
        sampled = block[:, sampled_index]
        beta = np.linalg.lstsq(basis, sampled.T, rcond=None)[0]
        residual = sampled - (basis @ beta).T
        projected[kind] = residual
        projected_adev = np.array([
            np.sqrt(np.mean(allan_variance(residual, m, axis=1)))
            for m in projected_taus
        ])
        projected_slope = float(np.polyfit(np.log(projected_taus), np.log(projected_adev), 1)[0])
        row = {
            "noise_type": kind, "expected_slope": EXPECTED_SLOPES[kind],
            "raw_slope": slope, "projected_slope": projected_slope,
            "raw_error": slope - EXPECTED_SLOPES[kind],
            "projected_error": projected_slope - EXPECTED_SLOPES[kind],
            "tau_ref_seconds": 1.0, "base_adev_at_1s": float(raw_adev[0]),
        }
        checks.append(row)
        if not np.isfinite(raw_adev).all() or not np.isfinite(projected_adev).all():
            raise AssertionError(f"Nonfinite Allan deviation for {kind}")
        if abs(row["raw_error"]) > SLOPE_TOLERANCE:
            raise AssertionError(f"{kind}: raw Allan slope {slope:.4f} not near {EXPECTED_SLOPES[kind]:+.1f}")
        if abs(row["projected_error"]) > SLOPE_TOLERANCE:
            raise AssertionError(f"{kind}: projected Allan slope {projected_slope:.4f} not near {EXPECTED_SLOPES[kind]:+.1f}")
    if not (checks[0]["projected_slope"] < checks[1]["projected_slope"] < checks[2]["projected_slope"]):
        raise AssertionError("Projection did not preserve the family slope ordering")
    return checks, projected


def plot_figures(metrics: pd.DataFrame, summary: pd.DataFrame, allan: pd.DataFrame,
                 examples: dict[str, np.ndarray], times: np.ndarray,
                 slope_rows: list[dict[str, float | str]]) -> None:
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    colors = dict(zip(NOISE_TYPES, ("#24639a", "#a25c12", "#7b3e93")))
    reference = allan[(allan.f_carrier_hz == 10e6) & (allan.sigma_y_ref == 1e-9)]
    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    for kind in NOISE_TYPES:
        group = reference[reference.noise_type == kind].groupby("tau_seconds").allan_deviation.apply(
            lambda values: float(np.sqrt(np.mean(values.to_numpy() ** 2)))
        )
        ax.loglog(group.index, group.values, "o-", label=kind.replace("_", " "), color=colors[kind])
        anchor = group.loc[2]
        guide = anchor * (group.index.to_numpy() / 2) ** EXPECTED_SLOPES[kind]
        ax.loglog(group.index, guide, "--", color=colors[kind], alpha=0.5)
    ax.set(xlabel="Averaging time τ (s)", ylabel="Fractional Allan deviation",
           title="Fractional-frequency Allan deviation (10 MHz, target 1e-9 at 1 s)")
    ax.legend(frameon=False)
    fig.savefig(FIGURE_PATHS["allan"], dpi=180)
    plt.close(fig)

    med = summary[summary.descriptor == "residual_frequency_rms_hz"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True, sharey=True)
    for ax, kind in zip(axes, NOISE_TYPES):
        for carrier in F_CARRIER_HZ:
            group = med[(med.noise_type == kind) & (med.f_carrier_hz == carrier)].sort_values("sigma_y_ref")
            ax.loglog(group.sigma_y_ref, group["median"], "o-", label=f"{carrier/1e6:g} MHz")
        ax.set(title=kind.replace("_", " "), xlabel="Target σy(1 s)")
    axes[0].set_ylabel("Median residual frequency RMS (Hz)")
    axes[-1].legend(frameon=False, title="Carrier")
    fig.savefig(FIGURE_PATHS["stability"], dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True, sharey=True)
    for ax, kind in zip(axes, NOISE_TYPES):
        for stability in SIGMA_Y_REF:
            group = med[(med.noise_type == kind) & (med.sigma_y_ref == stability)].sort_values("f_carrier_hz")
            ax.plot(group.f_carrier_hz / 1e6, group["median"], "o-", label=f"{stability:.0e}")
        ax.set(title=kind.replace("_", " "), xlabel="Carrier (MHz)")
    axes[0].set_ylabel("Median residual frequency RMS (Hz)")
    axes[-1].legend(frameon=False, title="Target σy(1 s)")
    fig.savefig(FIGURE_PATHS["carrier"], dpi=180)
    plt.close(fig)

    representative = metrics[(metrics.f_carrier_hz == 10e6) & (metrics.sigma_y_ref == 1e-9)]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
    for ax, descriptor in zip(axes, ("residual_frequency_rms_hz", "residual_max_abs_frequency_hz", "max_abs_phase_rad")):
        for kind in NOISE_TYPES:
            vals = representative.loc[representative.noise_type == kind, descriptor]
            ax.hist(vals, bins=30, density=True, histtype="step", linewidth=1.5,
                    color=colors[kind], label=kind.replace("_", " "))
        ax.set(xlabel=descriptor.replace("_", " "), ylabel="Density")
    axes[0].legend(frameon=False)
    fig.savefig(FIGURE_PATHS["distributions"], dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), constrained_layout=True, sharex=True)
    for ax, kind in zip(axes, NOISE_TYPES):
        ax.plot(times, examples[kind], color=colors[kind], linewidth=1)
        ax.axhline(0, color="0.6", linewidth=0.7)
        ax.set(ylabel="Residual (Hz)", title=kind.replace("_", " "))
    axes[-1].set_xlabel("WSPR symbol-center time (s)")
    fig.savefig(FIGURE_PATHS["examples"], dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slope-only", action="store_true", help="Check process/projection slopes without creating outputs")
    args = parser.parse_args()
    assert len(NOISE_TYPES) == 3
    assert len(F_CARRIER_HZ) == 4
    assert len(SIGMA_Y_REF) == 5
    assert N_TRAJECTORIES_PER_CELL >= 500
    assert (SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT) == (375, 256, 162)
    expected_rows = len(NOISE_TYPES) * len(F_CARRIER_HZ) * len(SIGMA_Y_REF) * N_TRAJECTORIES_PER_CELL
    assert expected_rows == 30000
    assert not OUTPUT_DIR.exists(), f"Refusing to overwrite existing {OUTPUT_DIR}"

    symbol_index = np.arange(SYMBOL_COUNT)
    center_times = (symbol_index + 0.5) * SYMBOL_DURATION_S
    sampled_index = np.floor(center_times).astype(int)
    n_seconds = int(sampled_index.max()) + 2
    assert center_times[-1] < n_seconds and sampled_index.min() == 0
    x = (symbol_index - 81.0) / 81.0
    basis = np.column_stack((np.ones_like(x), x))
    blocks = {}
    seeds = {}
    for kind_index, kind in enumerate(NOISE_TYPES):
        family_seeds = [SEED_BASE + kind_index * 100000 + j for j in range(N_TRAJECTORIES_PER_CELL)]
        seeds[kind] = family_seeds
        blocks[kind] = np.stack([base_process(kind, seed, n_seconds) for seed in family_seeds])

    slope_rows, projected = slope_check(blocks, sampled_index, basis)
    if args.slope_only:
        print("ALLAN_SLOPE_CHECK")
        print(pd.DataFrame(slope_rows).to_string(index=False))
        return

    metric_rows = []
    allan_rows = []
    examples = {}
    max_dot_one = 0.0
    max_dot_x = 0.0
    for kind in NOISE_TYPES:
        block = blocks[kind]
        ref_adev = next(item["base_adev_at_1s"] for item in slope_rows if item["noise_type"] == kind)
        per_trace_adev = np.stack([np.sqrt(allan_variance(block, m, axis=1)) for m in TAU_SECONDS], axis=1)
        for carrier in F_CARRIER_HZ:
            for stability in SIGMA_Y_REF:
                multiplier = stability / ref_adev
                for j in range(N_TRAJECTORIES_PER_CELL):
                    trajectory_id = f"{kind}_t{j + 1:04d}_f{int(carrier)}_s{stability:.0e}"
                    raw = carrier * multiplier * block[j, sampled_index]
                    beta, residual = project(raw, basis)
                    dot_one = float(np.dot(residual, basis[:, 0]))
                    dot_x = float(np.dot(residual, x))
                    max_dot_one = max(max_dot_one, abs(dot_one))
                    max_dot_x = max(max_dot_x, abs(dot_x))
                    if abs(dot_one) >= 1e-10 or abs(dot_x) >= 1e-10:
                        raise AssertionError(f"Orthogonality failed for {trajectory_id}")
                    max_phase, rms_phase = phase_descriptors(residual)
                    metric_rows.append({
                        "trajectory_id": trajectory_id, "noise_type": kind,
                        "f_carrier_hz": carrier, "sigma_y_ref": stability,
                        "tau_ref_seconds": 1.0, "trajectory_index": j + 1,
                        "seed": seeds[kind][j],
                        "frequency_rms_hz": float(np.sqrt(np.mean(raw**2))),
                        "max_abs_frequency_hz": float(np.max(np.abs(raw))),
                        "peak_to_peak_hz": float(np.ptp(raw)),
                        "residual_frequency_rms_hz": float(np.sqrt(np.mean(residual**2))),
                        "residual_max_abs_frequency_hz": float(np.max(np.abs(residual))),
                        "residual_peak_to_peak_hz": float(np.ptp(residual)),
                        "max_abs_phase_rad": max_phase, "phase_rms_rad": rms_phase,
                        "fitted_constant_hz": float(beta[0]),
                        "fitted_linear_coefficient": float(beta[1]),
                        "dot_with_constant": dot_one, "dot_with_x": dot_x,
                    })
                    for tau_index, tau in enumerate(TAU_SECONDS):
                        allan_rows.append({
                            "trajectory_id": trajectory_id, "noise_type": kind,
                            "f_carrier_hz": carrier, "sigma_y_ref": stability,
                            "trajectory_index": j + 1, "seed": seeds[kind][j],
                            "tau_seconds": tau,
                            "allan_deviation": float(multiplier * per_trace_adev[j, tau_index]),
                        })
                    if carrier == 10e6 and stability == 1e-9 and j == 0:
                        examples[kind] = residual.copy()

    metrics = pd.DataFrame(metric_rows)
    allan = pd.DataFrame(allan_rows)
    assert len(metrics) == expected_rows and metrics.trajectory_id.is_unique
    assert len(allan) == expected_rows * len(TAU_SECONDS)
    assert metrics.groupby(["noise_type", "f_carrier_hz", "sigma_y_ref"]).size().eq(N_TRAJECTORIES_PER_CELL).all()
    assert allan.groupby("trajectory_id").size().eq(len(TAU_SECONDS)).all()
    assert np.isfinite(metrics[list(DESCRIPTORS) + ["dot_with_constant", "dot_with_x"]]).all().all()
    assert np.isfinite(allan.allan_deviation).all() and (allan.allan_deviation > 0).all()
    assert max_dot_one < 1e-10 and max_dot_x < 1e-10

    summary_rows = []
    for (kind, carrier, stability), group in metrics.groupby(["noise_type", "f_carrier_hz", "sigma_y_ref"], sort=False):
        for descriptor in DESCRIPTORS:
            vals = group[descriptor].to_numpy()
            summary_rows.append({
                "noise_type": kind, "f_carrier_hz": carrier, "sigma_y_ref": stability,
                "n": len(vals), "descriptor": descriptor, "mean": float(vals.mean()),
                "std": float(vals.std(ddof=1)), "median": float(np.median(vals)),
                "p05": float(np.percentile(vals, 5)), "p25": float(np.percentile(vals, 25)),
                "p75": float(np.percentile(vals, 75)), "p95": float(np.percentile(vals, 95)),
            })
    summary = pd.DataFrame(summary_rows)
    assert len(summary) == len(NOISE_TYPES) * len(F_CARRIER_HZ) * len(SIGMA_Y_REF) * len(DESCRIPTORS)
    # Paired base shapes make these exact linear-scaling checks across carrier and target ADEV.
    pivot = metrics.pivot_table(index=["noise_type", "trajectory_index"],
                                columns=["f_carrier_hz", "sigma_y_ref"],
                                values="residual_frequency_rms_hz")
    base = pivot[(F_CARRIER_HZ[0], SIGMA_Y_REF[0])].to_numpy()
    maximum_scaling_rel_error = 0.0
    for carrier in F_CARRIER_HZ:
        for stability in SIGMA_Y_REF:
            expected = base * (carrier / F_CARRIER_HZ[0]) * (stability / SIGMA_Y_REF[0])
            observed = pivot[(carrier, stability)].to_numpy()
            maximum_scaling_rel_error = max(maximum_scaling_rel_error,
                                            float(np.max(np.abs(observed - expected) / expected)))
    assert maximum_scaling_rel_error < 1e-10
    assert len({round(row["projected_slope"], 2) for row in slope_rows}) == 3

    OUTPUT_DIR.mkdir(parents=True)
    metrics.to_csv(METRICS_PATH, index=False)
    summary.to_csv(SUMMARY_PATH, index=False)
    allan.to_csv(ALLAN_PATH, index=False)
    plot_figures(metrics, summary, allan, examples, center_times, slope_rows)
    assert all(path.is_file() and path.stat().st_size > 0 for path in
               (METRICS_PATH, SUMMARY_PATH, ALLAN_PATH, *FIGURE_PATHS.values()))

    print("OSCILLATOR_PREFLIGHT_SPEC")
    print(f"noise_types={list(NOISE_TYPES)} carriers_hz={list(F_CARRIER_HZ)} sigma_y_ref={list(SIGMA_Y_REF)}")
    print(f"trajectories_per_cell={N_TRAJECTORIES_PER_CELL} total={expected_rows} seed_base={SEED_BASE}")
    print(f"fractional_cadence_seconds=1 symbol_duration_seconds={SYMBOL_DURATION_S} symbol_center_sampling=zero_order_hold")
    print(f"allan_tau_seconds={list(TAU_SECONDS)} slope_fit_tau_seconds={list(SLOPE_TAUS)} slope_tolerance={SLOPE_TOLERANCE}")
    print("ALLAN_SLOPE_CHECK")
    print(pd.DataFrame(slope_rows).to_csv(index=False).strip())
    print("SCALING_CHECK")
    print(f"max_relative_residual_rms_scaling_error={maximum_scaling_rel_error:.6g}; projection_family_slope_order=white<flicker<random_walk")
    print("RESIDUAL_DESCRIPTOR_SUMMARY")
    selected = summary[summary.descriptor == "residual_frequency_rms_hz"]
    print(selected[["noise_type", "f_carrier_hz", "sigma_y_ref", "n", "median", "p05", "p95"]].to_csv(index=False).strip())
    print("ORTHOGONALITY_CHECK")
    print(f"max_abs_dot_with_constant={max_dot_one:.6g} max_abs_dot_with_x={max_dot_x:.6g} tolerance=1e-10")
    print("OUTPUT_PATHS")
    for path in (METRICS_PATH, SUMMARY_PATH, ALLAN_PATH, *FIGURE_PATHS.values()):
        print(path)


if __name__ == "__main__":
    main()
