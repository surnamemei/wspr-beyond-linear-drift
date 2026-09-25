#!/usr/bin/env python3
"""Analysis-only orthogonal random-walk frequency shape preflight."""

from __future__ import annotations

import csv
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

SIGMA_STEP_GRID_HZ = (0.005, 0.01, 0.02, 0.04, 0.08)
N_TRAJECTORIES_PER_SIGMA = 1000
RNG_SEED = 2026100400
OUTPUT_DIR = ROOT / "results/analysis/random_walk_preflight"
METRICS_PATH = OUTPUT_DIR / "random_walk_trajectory_metrics.csv"
SUMMARY_PATH = OUTPUT_DIR / "random_walk_distribution_summary.csv"
FIGURES = {
    "examples": OUTPUT_DIR / "random_walk_example_residuals.png",
    "distributions": OUTPUT_DIR / "random_walk_descriptor_distributions.png",
    "phase_frequency": OUTPUT_DIR / "random_walk_phase_vs_frequency.png",
    "scaling": OUTPUT_DIR / "random_walk_descriptor_scaling.png",
}
DESCRIPTORS = (
    "max_abs_frequency_hz", "frequency_rms_hz", "frequency_peak_to_peak_hz",
    "max_abs_phase_rad", "phase_rms_rad", "final_phase_rad",
    "phase_peak_to_peak_rad", "raw_start_hz", "raw_end_hz",
    "raw_peak_to_peak_hz", "fitted_constant_hz", "fitted_linear_coefficient",
)
METRIC_FIELDS = (
    "trajectory_id", "sigma_step_hz", "trajectory_index", *DESCRIPTORS,
    "dot_with_constant", "dot_with_x",
)


def metrics_for(raw: np.ndarray, basis: np.ndarray, x: np.ndarray) -> tuple[dict[str, float], np.ndarray]:
    beta = np.linalg.lstsq(basis, raw, rcond=None)[0]
    residual = raw - basis @ beta
    dot_constant = float(np.dot(residual, basis[:, 0]))
    dot_x = float(np.dot(residual, x))
    if abs(dot_constant) >= 1e-10 or abs(dot_x) >= 1e-10:
        raise AssertionError(f"Residual orthogonality failed: {dot_constant}, {dot_x}")
    frequency_samples = np.repeat(residual, SAMPLES_PER_SYMBOL)
    phase_steps = (2 * np.pi / SAMPLE_RATE_HZ) * frequency_samples
    phase_edges = np.concatenate(([0.0], np.cumsum(phase_steps)))
    phase_samples = phase_edges[:-1]
    return {
        "max_abs_frequency_hz": float(np.max(np.abs(residual))),
        "frequency_rms_hz": float(np.sqrt(np.mean(residual ** 2))),
        "frequency_peak_to_peak_hz": float(np.ptp(residual)),
        "max_abs_phase_rad": float(np.max(np.abs(phase_samples))),
        "phase_rms_rad": float(np.sqrt(np.mean(phase_samples ** 2))),
        "final_phase_rad": float(phase_edges[-1]),
        "phase_peak_to_peak_rad": float(np.ptp(phase_edges)),
        "raw_start_hz": float(raw[0]),
        "raw_end_hz": float(raw[-1]),
        "raw_peak_to_peak_hz": float(np.ptp(raw)),
        "fitted_constant_hz": float(beta[0]),
        "fitted_linear_coefficient": float(beta[1]),
        "dot_with_constant": dot_constant,
        "dot_with_x": dot_x,
    }, residual


def make_figures(frame: pd.DataFrame, examples: dict[float, list[np.ndarray]],
                 center_times: np.ndarray) -> None:
    colors = plt.get_cmap("viridis")(np.linspace(0.12, 0.9, len(SIGMA_STEP_GRID_HZ)))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})

    fig, axes = plt.subplots(5, 1, figsize=(10, 11), sharex=True, constrained_layout=True)
    for axis, sigma, color in zip(axes, SIGMA_STEP_GRID_HZ, colors):
        for index, residual in enumerate(examples[sigma]):
            axis.plot(center_times, residual, lw=1, alpha=0.8,
                      label=f"trajectory {index + 1}")
        axis.axhline(0, color="0.55", lw=0.7)
        axis.set_ylabel(f"σ={sigma:g} Hz\nResidual (Hz)")
    axes[0].legend(ncol=3, frameon=False, loc="upper right")
    axes[-1].set_xlabel("WSPR symbol-center time (s)")
    fig.suptitle("Orthogonal random-walk frequency residuals")
    fig.savefig(FIGURES["examples"], dpi=180)
    plt.close(fig)

    selected = ("max_abs_frequency_hz", "frequency_rms_hz", "max_abs_phase_rad")
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), constrained_layout=True)
    for axis, descriptor in zip(axes, selected):
        for sigma, color in zip(SIGMA_STEP_GRID_HZ, colors):
            values = frame.loc[frame["sigma_step_hz"] == sigma, descriptor]
            axis.hist(values, bins=35, density=True, histtype="step", lw=1.5,
                      color=color, label=f"{sigma:g}")
        axis.set_xlabel(descriptor.replace("_", " "))
        axis.set_ylabel("Density")
    axes[0].legend(title="σ step (Hz)", frameon=False)
    fig.suptitle("Random-walk residual descriptor distributions")
    fig.savefig(FIGURES["distributions"], dpi=180)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(8, 6), constrained_layout=True)
    for sigma, color in zip(SIGMA_STEP_GRID_HZ, colors):
        subset = frame.loc[frame["sigma_step_hz"] == sigma]
        axis.scatter(subset["max_abs_frequency_hz"], subset["max_abs_phase_rad"],
                     s=8, alpha=0.35, color=color, label=f"{sigma:g}", rasterized=True)
    axis.set_xlabel("Max absolute residual frequency (Hz)")
    axis.set_ylabel("Max absolute residual phase (rad)")
    axis.legend(title="σ step (Hz)", frameon=False)
    fig.savefig(FIGURES["phase_frequency"], dpi=180)
    plt.close(fig)

    medians = frame.groupby("sigma_step_hz", sort=True)[list(selected)].median()
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    for axis, descriptor in zip(axes, selected):
        axis.plot(medians.index, medians[descriptor], "o-", color="#245a81")
        axis.set_xlabel("σ step (Hz)")
        axis.set_ylabel(f"Median {descriptor.replace('_', ' ')}")
    fig.suptitle("Median residual descriptors by step standard deviation")
    fig.savefig(FIGURES["scaling"], dpi=180)
    plt.close(fig)


def main() -> None:
    assert len(SIGMA_STEP_GRID_HZ) == 5
    assert N_TRAJECTORIES_PER_SIGMA == 1000
    expected_total_trajectories = len(SIGMA_STEP_GRID_HZ) * N_TRAJECTORIES_PER_SIGMA
    assert expected_total_trajectories == 5000
    assert (SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT) == (375, 256, 162)
    assert not OUTPUT_DIR.exists(), f"Refusing to overwrite {OUTPUT_DIR}"
    symbol_index = np.arange(SYMBOL_COUNT)
    center_times = (symbol_index + 0.5) * SYMBOL_DURATION_S
    x = (symbol_index - 81.0) / 81.0
    basis = np.column_stack((np.ones_like(x), x))
    rng = np.random.default_rng(RNG_SEED)
    rows: list[dict[str, float | str | int]] = []
    examples: dict[float, list[np.ndarray]] = {sigma: [] for sigma in SIGMA_STEP_GRID_HZ}
    for sigma_index, sigma in enumerate(SIGMA_STEP_GRID_HZ):
        for trajectory_index in range(1, N_TRAJECTORIES_PER_SIGMA + 1):
            raw = np.concatenate(([0.0], np.cumsum(rng.normal(0.0, sigma, SYMBOL_COUNT - 1))))
            descriptor, residual = metrics_for(raw, basis, x)
            rows.append({
                "trajectory_id": f"rw_s{sigma_index + 1:02d}_t{trajectory_index:04d}",
                "sigma_step_hz": sigma,
                "trajectory_index": trajectory_index,
                **descriptor,
            })
            if len(examples[sigma]) < 3:
                examples[sigma].append(residual)
    frame = pd.DataFrame(rows, columns=METRIC_FIELDS)
    assert len(frame) == 5000 and frame["trajectory_id"].is_unique
    assert frame.groupby("sigma_step_hz").size().eq(1000).all()
    assert set(frame["sigma_step_hz"]) == set(SIGMA_STEP_GRID_HZ)
    assert np.isfinite(frame[list(DESCRIPTORS) + ["dot_with_constant", "dot_with_x"]]).all().all()
    max_dot_constant = float(frame["dot_with_constant"].abs().max())
    max_dot_x = float(frame["dot_with_x"].abs().max())
    assert max_dot_constant < 1e-10 and max_dot_x < 1e-10
    summary_rows = []
    for sigma in SIGMA_STEP_GRID_HZ:
        subset = frame.loc[frame["sigma_step_hz"] == sigma]
        for descriptor in DESCRIPTORS:
            values = subset[descriptor].to_numpy()
            summary_rows.append({
                "sigma_step_hz": sigma, "descriptor": descriptor,
                "mean": float(np.mean(values)), "std": float(np.std(values, ddof=1)),
                "median": float(np.median(values)),
                "p05": float(np.percentile(values, 5)),
                "p25": float(np.percentile(values, 25)),
                "p75": float(np.percentile(values, 75)),
                "p95": float(np.percentile(values, 95)),
            })
    summary = pd.DataFrame(summary_rows)
    assert len(summary) == len(SIGMA_STEP_GRID_HZ) * len(DESCRIPTORS)
    correlation_names = ("max_abs_frequency_hz", "frequency_rms_hz", "max_abs_phase_rad")
    correlations = frame[list(correlation_names)].corr()

    OUTPUT_DIR.mkdir(parents=True)
    frame.to_csv(METRICS_PATH, index=False, mode="x", quoting=csv.QUOTE_MINIMAL)
    summary.to_csv(SUMMARY_PATH, index=False, mode="x", quoting=csv.QUOTE_MINIMAL)
    make_figures(frame, examples, center_times)
    assert all(path.is_file() and path.stat().st_size > 0 for path in
               (METRICS_PATH, SUMMARY_PATH, *FIGURES.values()))

    print("RANDOM_WALK_PREFLIGHT_SPEC")
    print(f"sigma_step_grid_hz={list(SIGMA_STEP_GRID_HZ)} n_per_sigma={N_TRAJECTORIES_PER_SIGMA} rng_seed={RNG_SEED}")
    print(f"symbol_count={SYMBOL_COUNT} samples_per_symbol={SAMPLES_PER_SYMBOL} sample_rate_hz={SAMPLE_RATE_HZ}")
    print("TOTAL_TRAJECTORIES")
    print(len(frame))
    print("ORTHOGONALITY_CHECK")
    print(f"max_abs_dot_with_constant={max_dot_constant:.12g} max_abs_dot_with_x={max_dot_x:.12g} tolerance=1e-10")
    print("DISTRIBUTION_SUMMARY")
    print(summary.to_csv(index=False).strip())
    print("DESCRIPTOR_CORRELATIONS")
    print(correlations.to_csv().strip())
    print("OUTPUT_PATHS")
    for path in (METRICS_PATH, SUMMARY_PATH, *FIGURES.values()):
        print(path)


if __name__ == "__main__":
    main()
