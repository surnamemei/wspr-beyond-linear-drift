#!/usr/bin/env python3
"""Analyze first-order thermal settling shapes without invoking a decoder."""

from __future__ import annotations

import csv
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from impairments.frequency import wspr_symbol_quadratic_residual_trajectory
from wspr.waveform import (
    FRAME_DURATION_S, SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT,
    SYMBOL_DURATION_S,
)

TAUS_SECONDS = (5, 15, 30, 60, 120, 300)
K_HZ = 1.0
OUTPUT_DIR = ROOT / "results/analysis/thermal_preflight"
METRICS_CSV = OUTPUT_DIR / "thermal_preflight_metrics.csv"
SHAPES_CSV = OUTPUT_DIR / "thermal_residual_shapes.csv"
RAW_FIGURE = OUTPUT_DIR / "thermal_raw_and_fit.png"
RESIDUAL_FIGURE = OUTPUT_DIR / "thermal_residual_shapes.png"
COMPARISON_FIGURE = OUTPUT_DIR / "thermal_vs_quadratic.png"

METRIC_FIELDS = (
    "tau_seconds", "raw_start_hz", "raw_end_hz", "fitted_constant_hz",
    "fitted_linear_coefficient", "residual_max_abs_hz",
    "residual_peak_to_peak_hz", "residual_rms_hz", "residual_mean_hz",
    "dot_with_constant", "dot_with_x", "pearson_correlation",
    "cosine_similarity", "rms_shape_difference", "max_abs_shape_difference",
)
SHAPE_FIELDS = (
    "tau_seconds", "symbol_index", "symbol_center_time_seconds", "x",
    "raw_hz", "constant_linear_fit_hz", "residual_hz",
    "normalized_thermal_residual", "normalized_quadratic_residual",
)

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 11,
    "axes.labelsize": 10, "figure.titlesize": 13,
    "axes.spines.top": False, "axes.spines.right": False,
})


def thermal_symbol_projection(
    tau_seconds: float, k_hz: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Evaluate the preflight thermal shape at symbol centers and remove [1, x]."""
    index = np.arange(SYMBOL_COUNT)
    x = (index - 81.0) / 81.0
    basis = np.column_stack((np.ones_like(x), x))
    center_time = (index + 0.5) * SYMBOL_DURATION_S
    raw = k_hz * (1.0 - np.exp(-center_time / tau_seconds))
    beta = np.linalg.lstsq(basis, raw, rcond=None)[0]
    fitted = basis @ beta
    residual = raw - fitted
    return center_time, x, raw, fitted, residual


def compute() -> tuple[list[dict[str, float]], list[dict[str, float]], dict[int, np.ndarray],
                       dict[int, np.ndarray], np.ndarray, np.ndarray]:
    assert SYMBOL_COUNT == 162 and SAMPLES_PER_SYMBOL == 256 and SAMPLE_RATE_HZ == 375
    assert np.isclose(FRAME_DURATION_S, SYMBOL_COUNT * SYMBOL_DURATION_S)
    assert len(TAUS_SECONDS) == 6 and all(tau > 0 for tau in TAUS_SECONDS)
    index = np.arange(SYMBOL_COUNT)
    x = (index - 81.0) / 81.0
    basis = np.column_stack((np.ones_like(x), x))
    center_time = (index + 0.5) * SYMBOL_DURATION_S

    validated = np.asarray(
        wspr_symbol_quadratic_residual_trajectory(SYMBOL_COUNT, SAMPLES_PER_SYMBOL, 1.0),
        dtype=float,
    ).reshape(SYMBOL_COUNT, SAMPLES_PER_SYMBOL)
    assert np.allclose(validated, validated[:, :1], rtol=0, atol=0)
    q_norm = validated[:, 0]
    assert np.isclose(np.max(np.abs(q_norm)), 1.0, atol=1e-14)
    assert abs(np.dot(q_norm, basis[:, 0])) < 1e-12
    assert abs(np.dot(q_norm, x)) < 1e-12

    metrics = []
    shapes = []
    raw_by_tau = {}
    fit_by_tau = {}
    for tau in TAUS_SECONDS:
        _, _, raw, fitted, residual = thermal_symbol_projection(tau, K_HZ)
        beta = np.linalg.lstsq(basis, raw, rcond=None)[0]
        max_abs = float(np.max(np.abs(residual)))
        assert max_abs > 0
        normalized = residual / max_abs
        dot_constant = float(np.dot(residual, basis[:, 0]))
        dot_x = float(np.dot(residual, x))
        assert abs(dot_constant) < 1e-12, (tau, dot_constant)
        assert abs(dot_x) < 1e-12, (tau, dot_x)
        assert abs(float(np.mean(residual))) < 1e-12
        assert np.isclose(np.max(np.abs(normalized)), 1.0, atol=1e-14)
        pearson = float(np.corrcoef(normalized, q_norm)[0, 1])
        cosine = float(np.dot(normalized, q_norm) /
                       (np.linalg.norm(normalized) * np.linalg.norm(q_norm)))
        difference = normalized - q_norm
        metrics.append({
            "tau_seconds": tau,
            "raw_start_hz": float(raw[0]),
            "raw_end_hz": float(raw[-1]),
            "fitted_constant_hz": float(beta[0]),
            "fitted_linear_coefficient": float(beta[1]),
            "residual_max_abs_hz": max_abs,
            "residual_peak_to_peak_hz": float(np.ptp(residual)),
            "residual_rms_hz": float(np.sqrt(np.mean(residual ** 2))),
            "residual_mean_hz": float(np.mean(residual)),
            "dot_with_constant": dot_constant,
            "dot_with_x": dot_x,
            "pearson_correlation": pearson,
            "cosine_similarity": cosine,
            "rms_shape_difference": float(np.sqrt(np.mean(difference ** 2))),
            "max_abs_shape_difference": float(np.max(np.abs(difference))),
        })
        raw_by_tau[tau] = raw
        fit_by_tau[tau] = fitted
        for i in range(SYMBOL_COUNT):
            shapes.append({
                "tau_seconds": tau,
                "symbol_index": int(i),
                "symbol_center_time_seconds": float(center_time[i]),
                "x": float(x[i]),
                "raw_hz": float(raw[i]),
                "constant_linear_fit_hz": float(fitted[i]),
                "residual_hz": float(residual[i]),
                "normalized_thermal_residual": float(normalized[i]),
                "normalized_quadratic_residual": float(q_norm[i]),
            })
    assert len(metrics) == 6 and len(shapes) == 6 * SYMBOL_COUNT
    return metrics, shapes, raw_by_tau, fit_by_tau, center_time, q_norm


def render(metrics: list[dict[str, float]], shapes: list[dict[str, float]],
           raw_by_tau: dict[int, np.ndarray], fit_by_tau: dict[int, np.ndarray],
           time_seconds: np.ndarray, q_norm: np.ndarray) -> None:
    colors = plt.get_cmap("viridis")(np.linspace(0.1, 0.88, len(TAUS_SECONDS)))
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), sharex=True, sharey=True,
                             constrained_layout=True)
    for ax, tau, color in zip(axes.flat, TAUS_SECONDS, colors, strict=True):
        ax.plot(time_seconds, raw_by_tau[tau], color=color, linewidth=1.8, label="Raw")
        ax.plot(time_seconds, fit_by_tau[tau], color="#3c4650", linestyle="--",
                linewidth=1.4, label="Constant + linear fit")
        ax.set_title(f"τ = {tau} s")
        ax.set_xlim(0, FRAME_DURATION_S)
        ax.set_ylim(-0.05, 1.05)
        ax.grid(alpha=0.18)
    axes[0, 0].legend(frameon=False, fontsize=8, loc="lower right")
    for ax in axes[1]:
        ax.set_xlabel("Symbol-center time from frame start (s)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Frequency offset (Hz)")
    fig.suptitle("First-order settling shape and decoder-representable fit; K = 1 Hz")
    fig.savefig(RAW_FIGURE, dpi=220, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.8, 5.1), constrained_layout=True)
    for tau, color in zip(TAUS_SECONDS, colors, strict=True):
        values = np.array([row["normalized_thermal_residual"] for row in shapes
                           if row["tau_seconds"] == tau])
        ax.plot(time_seconds, values, color=color, linewidth=1.7, label=f"τ = {tau} s")
    ax.axhline(0, color="#777777", linewidth=0.9)
    ax.set(xlabel="Symbol-center time from frame start (s)",
           ylabel="Residual / max |residual|",
           title="Orthogonal thermal residual shapes",
           xlim=(0, FRAME_DURATION_S), ylim=(-1.05, 1.05))
    ax.grid(alpha=0.18)
    ax.legend(frameon=False, ncol=2)
    fig.savefig(RESIDUAL_FIGURE, dpi=220, bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(12, 7), sharex=True, sharey=True,
                             constrained_layout=True)
    for ax, tau, color in zip(axes.flat, TAUS_SECONDS, colors, strict=True):
        values = np.array([row["normalized_thermal_residual"] for row in shapes
                           if row["tau_seconds"] == tau])
        ax.plot(time_seconds, values, color=color, linewidth=1.7, label="Thermal residual")
        ax.plot(time_seconds, q_norm, color="#3c4650", linestyle="--", linewidth=1.4,
                label="Orthogonal quadratic")
        row = next(row for row in metrics if row["tau_seconds"] == tau)
        ax.set_title(f"τ = {tau} s; r = {row['pearson_correlation']:.3f}")
        ax.set_xlim(0, FRAME_DURATION_S)
        ax.set_ylim(-1.05, 1.05)
        ax.grid(alpha=0.18)
    axes[0, 0].legend(frameon=False, fontsize=8)
    for ax in axes[1]:
        ax.set_xlabel("Symbol-center time from frame start (s)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Normalized residual")
    fig.suptitle("Thermal and validated orthogonal quadratic residual shapes")
    fig.savefig(COMPARISON_FIGURE, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    targets = (METRICS_CSV, SHAPES_CSV, RAW_FIGURE, RESIDUAL_FIGURE, COMPARISON_FIGURE)
    for target in targets:
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {target}")
    metrics, shapes, raw, fitted, time_seconds, q_norm = compute()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with METRICS_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=METRIC_FIELDS)
        writer.writeheader()
        writer.writerows(metrics)
    with SHAPES_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHAPE_FIELDS)
        writer.writeheader()
        writer.writerows(shapes)
    render(metrics, shapes, raw, fitted, time_seconds, q_norm)
    with METRICS_CSV.open(newline="") as handle:
        assert len(list(csv.DictReader(handle))) == len(TAUS_SECONDS)
    with SHAPES_CSV.open(newline="") as handle:
        assert len(list(csv.DictReader(handle))) == len(TAUS_SECONDS) * SYMBOL_COUNT
    assert all(path.stat().st_size > 10000 for path in
               (RAW_FIGURE, RESIDUAL_FIGURE, COMPARISON_FIGURE))
    print("THERMAL_PREFLIGHT_SPEC")
    print(f"symbol_count={SYMBOL_COUNT}")
    print(f"sample_rate_hz={SAMPLE_RATE_HZ}")
    print(f"samples_per_symbol={SAMPLES_PER_SYMBOL}")
    print(f"symbol_duration_seconds={SYMBOL_DURATION_S:.12g}")
    print("time_seconds=(symbol_index+0.5)*symbol_duration_seconds")
    print("x=(symbol_index-81)/81")
    print("f_raw(t)=1 Hz*(1-exp(-t/tau))")
    print(f"tau_seconds={list(TAUS_SECONDS)}")
    print("fit_basis=[1,x]")
    print("ORTHOGONALITY_CHECK")
    print("tau_seconds,dot_with_constant,dot_with_x,pass")
    for row in metrics:
        print(f"{row['tau_seconds']},{row['dot_with_constant']:.12g},"
              f"{row['dot_with_x']:.12g},"
              f"{abs(row['dot_with_constant']) < 1e-12 and abs(row['dot_with_x']) < 1e-12}")
    print("THERMAL_METRICS")
    thermal_fields = METRIC_FIELDS[:11]
    thermal_writer = csv.DictWriter(sys.stdout, fieldnames=thermal_fields,
                                    extrasaction="ignore", lineterminator="\n")
    thermal_writer.writeheader()
    thermal_writer.writerows(metrics)
    print("SHAPE_COMPARISON")
    comparison_fields = ("tau_seconds", *METRIC_FIELDS[11:])
    comparison_writer = csv.DictWriter(sys.stdout, fieldnames=comparison_fields,
                                       extrasaction="ignore", lineterminator="\n")
    comparison_writer.writeheader()
    comparison_writer.writerows(metrics)
    print("OUTPUT_PATHS")
    for path in targets:
        print(path)


if __name__ == "__main__":
    main()
