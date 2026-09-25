#!/usr/bin/env python3
"""Create final-core figures and metrics from existing WSPR result files only."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import numpy as np
import pandas as pd
from scipy.special import expit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from impairments.frequency import wspr_symbol_quadratic_residual_trajectory
from analyze_interaction_model import fit_binomial

FIGURE_DIR = ROOT / "results/figures/final_core"
ANALYSIS_DIR = ROOT / "results/analysis/final_core_results"
SOURCES = {
    "awgn": ROOT / "results/csv/awgn_baseline_summary.csv",
    "awgn_thresholds": ROOT / "results/csv/awgn_baseline_thresholds.json",
    "linear_coarse": ROOT / "results/csv/linear_drift_map/linear_drift_map_summary.csv",
    "linear_refined": ROOT / "results/csv/linear_drift_boundary/linear_drift_boundary_summary.csv",
    "quadratic": ROOT / "results/csv/quadratic_residual_pilot/quadratic_residual_pilot_summary.csv",
    "balanced_trials": ROOT / "results/csv/balanced_interaction_confirm/balanced_interaction_confirm_trials.csv",
    "balanced_summary": ROOT / "results/csv/balanced_interaction_confirm/balanced_interaction_confirm_summary.csv",
    "balanced_coefficients": ROOT / "results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_coefficients.csv",
    "balanced_bootstrap": ROOT / "results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_bootstrap_bDA.csv",
    "balanced_models": ROOT / "results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_model_comparison.csv",
}
FIGURES = (
    "awgn_decode_probability.png",
    "linear_drift_heatmap.png",
    "linear_drift_boundary.png",
    "quadratic_residual_heatmap.png",
    "quadratic_residual_boundary.png",
    "balanced_interaction.png",
    "interaction_model_check.png",
)
METRICS_CSV = ANALYSIS_DIR / "core_metrics.csv"
SUMMARY_MD = ANALYSIS_DIR / "results_summary.md"
METRIC_FIELDS = ("metric", "snr_db", "value", "lower", "upper", "units", "source")
COLORS = {"positive": "#1769aa", "negative": "#c05a36", "D0": "#1769aa", "D05": "#c05a36"}

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "figure.titlesize": 13,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "savefig.dpi": 220,
})


def read_csv(key: str) -> pd.DataFrame:
    path = SOURCES[key]
    if not path.is_file():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def save_figure(fig: plt.Figure, filename: str) -> None:
    fig.savefig(FIGURE_DIR / filename, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def crossing(frame: pd.DataFrame, x_column: str, target: float = 0.5) -> float | None:
    rows = frame.sort_values(x_column)
    xs = rows[x_column].to_numpy(dtype=float)
    ps = rows["p_decode"].to_numpy(dtype=float)
    for x, p in zip(xs, ps, strict=True):
        if np.isclose(p, target, rtol=0, atol=1e-12):
            return float(x)
    for index in range(len(xs) - 1):
        if (ps[index] - target) * (ps[index + 1] - target) < 0:
            fraction = (target - ps[index]) / (ps[index + 1] - ps[index])
            return float(xs[index] + fraction * (xs[index + 1] - xs[index]))
    return None


def metric(name: str, snr: float | None, value: float, units: str, source: str,
           lower: float | None = None, upper: float | None = None) -> dict[str, object]:
    return {
        "metric": name, "snr_db": "" if snr is None else snr, "value": value,
        "lower": "" if lower is None else lower,
        "upper": "" if upper is None else upper,
        "units": units, "source": source,
    }


def validate_probability_summary(frame: pd.DataFrame, group_fields: list[str]) -> None:
    assert not frame.duplicated(group_fields).any()
    assert frame["p_decode"].between(0, 1).all()
    assert np.allclose(frame["p_decode"], frame["successes"] / frame["n"], rtol=0, atol=1e-12)


def awgn_figure(awgn: pd.DataFrame, thresholds: dict[str, object]) -> list[dict[str, object]]:
    assert {"snr_db_2500hz", "n", "successes", "p_decode", "ci_low", "ci_high"} <= set(awgn)
    validate_probability_summary(awgn, ["snr_db_2500hz"])
    awgn = awgn.sort_values("snr_db_2500hz")
    snr50 = crossing(awgn.rename(columns={"snr_db_2500hz": "snr_db"}), "snr_db")
    assert snr50 is not None
    assert np.isclose(snr50, thresholds["snr_50_db"], atol=1e-12)
    x = awgn["snr_db_2500hz"].to_numpy()
    p = awgn["p_decode"].to_numpy()
    err = np.vstack((np.maximum(0, p - awgn["ci_low"].to_numpy()),
                     np.maximum(0, awgn["ci_high"].to_numpy() - p)))
    fig, ax = plt.subplots(figsize=(8.2, 5.2), constrained_layout=True)
    ax.errorbar(x, p, yerr=err, fmt="o-", color="#1769aa", ecolor="#7192b4",
                capsize=3, linewidth=1.8, markersize=5, label="Observed; Wilson 95% CI")
    ax.axhline(0.5, color="#777777", linewidth=1, linestyle=":")
    ax.axvline(snr50, color="#c05a36", linewidth=1.5, linestyle="--",
               label=f"SNR50 = {snr50:.2f} dB")
    ax.set(xlabel="Injected SNR (dB, 2500 Hz reference bandwidth)",
           ylabel="Decode probability", title="AWGN-only WSPR-2 decoding",
           ylim=(-0.025, 1.05), xlim=(min(x) - 0.4, max(x) + 0.4))
    ax.set_yticks(np.linspace(0, 1, 6))
    ax.grid(alpha=0.2)
    ax.legend(loc="lower right", frameon=False)
    save_figure(fig, FIGURES[0])
    return [metric("AWGN_SNR50", None, snr50, "dB", str(SOURCES["awgn_thresholds"].relative_to(ROOT)))]


def signed_heatmap(ax: plt.Axes, frame: pd.DataFrame, sign: int, title: str,
                   norm: Normalize) -> None:
    selected = frame.loc[(frame["drift_hz"] >= 0) if sign > 0 else (frame["drift_hz"] <= 0)].copy()
    selected["abs_drift_hz"] = selected["drift_hz"].abs()
    snrs = sorted(selected["snr_db"].unique())
    drifts = sorted(selected["abs_drift_hz"].unique())
    table = selected.pivot(index="snr_db", columns="abs_drift_hz", values="p_decode")
    assert table.shape == (len(snrs), len(drifts)) and table.notna().all().all()
    values = table.loc[snrs, drifts].to_numpy()
    image = ax.imshow(values, origin="lower", aspect="auto", cmap="viridis", norm=norm)
    ax.set_xticks(np.arange(len(drifts)), [f"{value:g}" for value in drifts])
    ax.set_yticks(np.arange(len(snrs)), [f"{value:g}" for value in snrs])
    ax.set(xlabel="|Linear drift| (Hz)", ylabel="SNR (dB)", title=title)
    for i in range(len(snrs)):
        for j in range(len(drifts)):
            value = values[i, j]
            ax.text(j, i, f"{value:.2f}", ha="center", va="center",
                    fontsize=7, color="white" if value < 0.55 else "#17212b")
    return image


def linear_heatmap(coarse: pd.DataFrame, refined: pd.DataFrame) -> None:
    norm = Normalize(0, 1)
    fig, axes = plt.subplots(2, 2, figsize=(11, 9), constrained_layout=True)
    image = None
    for row, (label, frame) in enumerate((("Coarse grid", coarse), ("Refined grid", refined))):
        for column, (sign, sign_label) in enumerate(((1, "positive"), (-1, "negative"))):
            image = signed_heatmap(axes[row, column], frame, sign,
                                   f"{label}: {sign_label} drift", norm)
    fig.colorbar(image, ax=axes, label="Observed decode probability", fraction=0.025, pad=0.02)
    fig.suptitle("Linear drift: signed observations (no sign averaging)")
    save_figure(fig, FIGURES[1])


def linear_boundary(refined: pd.DataFrame) -> list[dict[str, object]]:
    fig, ax = plt.subplots(figsize=(7.4, 5.0), constrained_layout=True)
    records = []
    for sign, label in ((1, "positive"), (-1, "negative")):
        selected = refined.loc[(refined["drift_hz"] >= 0) if sign > 0 else
                               (refined["drift_hz"] <= 0)].copy()
        selected["abs_drift_hz"] = selected["drift_hz"].abs()
        points = []
        for snr, group in selected.groupby("snr_db"):
            value = crossing(group, "abs_drift_hz")
            if value is not None:
                points.append((float(snr), value))
                records.append(metric(f"linear_D50_{label}", float(snr), value, "Hz",
                                      str(SOURCES["linear_refined"].relative_to(ROOT))))
        if points:
            points.sort()
            ax.plot([p[0] for p in points], [p[1] for p in points], "o-",
                    color=COLORS[label], linewidth=1.7, label=f"{label.capitalize()} drift")
    ax.set(xlabel="SNR (dB)", ylabel="Estimated |drift| at P_decode = 0.5 (Hz)",
           title="Linear-drift D50 within the refined grid", ylim=(-0.03, 1.03))
    ax.grid(alpha=0.2)
    ax.legend(frameon=False)
    save_figure(fig, FIGURES[2])
    return records


def quadratic_heatmap(quadratic: pd.DataFrame) -> None:
    snrs = sorted(quadratic["snr_db"].unique())
    amplitudes = sorted(quadratic["A_res_hz"].unique())
    table = quadratic.pivot(index="snr_db", columns="A_res_hz", values="p_decode")
    assert table.shape == (len(snrs), len(amplitudes)) and table.notna().all().all()
    values = table.loc[snrs, amplitudes].to_numpy()
    fig, ax = plt.subplots(figsize=(9, 4.6), constrained_layout=True)
    image = ax.imshow(values, origin="lower", aspect="auto", cmap="viridis", vmin=0, vmax=1)
    ax.set_xticks(np.arange(len(amplitudes)), [f"{value:g}" for value in amplitudes])
    ax.set_yticks(np.arange(len(snrs)), [f"{value:g}" for value in snrs])
    ax.set(xlabel="Quadratic residual amplitude A_res (Hz)", ylabel="SNR (dB)",
           title="Orthogonal quadratic residual: observed decoding")
    for i in range(len(snrs)):
        for j in range(len(amplitudes)):
            value = values[i, j]
            ax.text(j, i, f"{value:.2f}", ha="center", va="center",
                    fontsize=8, color="white" if value < 0.55 else "#17212b")
    fig.colorbar(image, ax=ax, label="Observed decode probability")
    save_figure(fig, FIGURES[3])


def quadratic_boundary(quadratic: pd.DataFrame) -> list[dict[str, object]]:
    records = []
    points = []
    for snr, group in quadratic.groupby("snr_db"):
        value = crossing(group, "A_res_hz")
        if value is not None:
            points.append((float(snr), value))
            records.append(metric("quadratic_A50", float(snr), value, "Hz",
                                  str(SOURCES["quadratic"].relative_to(ROOT))))
    points.sort()
    fig, ax = plt.subplots(figsize=(7.4, 5.0), constrained_layout=True)
    ax.plot([p[0] for p in points], [p[1] for p in points], "o-",
            color="#1769aa", linewidth=1.8)
    ax.set(xlabel="SNR (dB)", ylabel="Estimated A_res at P_decode = 0.5 (Hz)",
           title="Quadratic-residual A50 within the pilot grid", ylim=(0, 1.02))
    ax.grid(alpha=0.2)
    save_figure(fig, FIGURES[4])
    return records


def balanced_figure(balanced: pd.DataFrame) -> None:
    snrs = sorted(balanced["snr_db"].unique(), reverse=True)
    fig, axes = plt.subplots(1, len(snrs), figsize=(12.5, 4.4),
                             sharex=True, sharey=True, constrained_layout=True)
    for ax, snr in zip(axes, snrs, strict=True):
        for drift, label, color in ((0.0, "D = 0 Hz", COLORS["D0"]),
                                    (0.5, "D = 0.5 Hz", COLORS["D05"])):
            group = balanced.loc[(balanced["snr_db"] == snr) &
                                 (balanced["linear_drift_hz"] == drift)].sort_values("A_res_hz")
            ax.plot(group["A_res_hz"], group["p_decode"], "o-",
                    color=color, linewidth=1.8, label=label)
        ax.set(title=f"SNR {snr:g} dB", xticks=[0, 0.25, 0.5], ylim=(-0.03, 1.03))
        ax.grid(alpha=0.2)
        ax.set_xlabel("A_res (Hz)")
    axes[0].set_ylabel("Observed decode probability")
    axes[-1].legend(frameon=False, loc="upper right")
    fig.suptitle("Balanced linear × quadratic interaction: observed data")
    save_figure(fig, FIGURES[5])


def model_check(trials: pd.DataFrame, balanced: pd.DataFrame,
                coefficients: pd.DataFrame, models: pd.DataFrame) -> None:
    assert len(trials) == 3600 and len(balanced) == 18
    assert set(trials["decoded_success"].unique()) <= {0, 1}
    assert trials.groupby(["snr_db", "linear_drift_hz", "A_res_hz"]).size().eq(200).all()
    snr = trials["snr_db"].to_numpy(dtype=float) + 30.5
    drift = trials["linear_drift_hz"].to_numpy(dtype=float)
    amp = trials["A_res_hz"].to_numpy(dtype=float)
    x0 = np.column_stack((np.ones(len(trials)), snr, drift, amp))
    x1 = np.column_stack((x0, drift * amp))
    y = trials["decoded_success"].to_numpy(dtype=float)
    cells = balanced[["snr_db", "linear_drift_hz", "A_res_hz", "p_decode"]].copy()
    cell_snr = cells["snr_db"].to_numpy(dtype=float) + 30.5
    cell_drift = cells["linear_drift_hz"].to_numpy(dtype=float)
    cell_amp = cells["A_res_hz"].to_numpy(dtype=float)
    cx0 = np.column_stack((np.ones(len(cells)), cell_snr, cell_drift, cell_amp))
    cx1 = np.column_stack((cx0, cell_drift * cell_amp))
    predictions = {}
    for model, x, cx in (("M0", x0, cx0), ("M1", x1, cx1)):
        beta, _, ll, _ = fit_binomial(x, y, np.ones(len(y)))
        stored_ll = float(models.loc[models["model"] == model, "log_likelihood"].iloc[0])
        assert np.isclose(ll, stored_ll, atol=1e-7)
        if model == "M1":
            stored = coefficients.set_index("term").loc[
                ["intercept", "snr_c", "linear_drift_hz", "A_res_hz", "D_times_A"],
                "coefficient",
            ].to_numpy(dtype=float)
            assert np.allclose(beta, stored, atol=1e-8)
        predictions[model] = expit(cx @ beta)
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.8), sharex=True, sharey=True,
                             constrained_layout=True)
    colors = {-30.0: "#1769aa", -30.5: "#518a52", -31.0: "#c05a36"}
    for ax, label in zip(axes, ("M0", "M1"), strict=True):
        for snr_value, group in cells.groupby("snr_db", sort=False):
            indices = group.index.to_numpy()
            ax.scatter(group["p_decode"], predictions[label][indices],
                       label=f"{snr_value:g} dB", color=colors[snr_value],
                       s=50, alpha=0.9, edgecolor="white", linewidth=0.4)
        ax.plot([0, 1], [0, 1], ":", color="#555555", linewidth=1)
        ax.set(xlabel="Observed P_decode", title=label, xlim=(-0.03, 1.03), ylim=(-0.03, 1.03))
        ax.grid(alpha=0.15)
    axes[0].set_ylabel("Predicted P_decode")
    axes[1].legend(title="SNR", frameon=False, loc="upper left")
    fig.suptitle("Balanced factorial data: observed vs fitted probability")
    save_figure(fig, FIGURES[6])


def orthogonality() -> tuple[float, float]:
    trajectory = np.asarray(wspr_symbol_quadratic_residual_trajectory(162, 256, 1.0))
    symbols = trajectory.reshape(162, 256)[:, 0]
    x = (np.arange(162) - 81.0) / 81.0
    dot_constant = float(np.dot(symbols, np.ones_like(x)))
    dot_linear = float(np.dot(symbols, x))
    assert abs(dot_constant) < 1e-12 and abs(dot_linear) < 1e-12
    return dot_constant, dot_linear


def main() -> None:
    for path in SOURCES.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    for path in [*(FIGURE_DIR / name for name in FIGURES), METRICS_CSV, SUMMARY_MD]:
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
    awgn = read_csv("awgn")
    coarse = read_csv("linear_coarse")
    refined = read_csv("linear_refined")
    quadratic = read_csv("quadratic")
    trials = read_csv("balanced_trials")
    balanced = read_csv("balanced_summary")
    coefficients = read_csv("balanced_coefficients")
    bootstrap = read_csv("balanced_bootstrap")
    models = read_csv("balanced_models")
    thresholds = json.loads(SOURCES["awgn_thresholds"].read_text())
    validate_probability_summary(coarse, ["snr_db", "drift_hz"])
    validate_probability_summary(refined, ["snr_db", "drift_hz"])
    validate_probability_summary(quadratic, ["snr_db", "A_res_hz"])
    validate_probability_summary(balanced, ["snr_db", "linear_drift_hz", "A_res_hz"])
    assert len(coarse) == 45 and len(refined) == 45 and len(quadratic) == 28
    assert len(bootstrap) == 1000 and (bootstrap["status"] == "success").all()
    assert len(trials) == 3600 and len(balanced) == 18
    dot_constant, dot_linear = orthogonality()
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    metrics = awgn_figure(awgn, thresholds)
    linear_heatmap(coarse, refined)
    linear_metrics = linear_boundary(refined)
    metrics.extend(linear_metrics)
    quadratic_heatmap(quadratic)
    quadratic_metrics = quadratic_boundary(quadratic)
    metrics.extend(quadratic_metrics)
    balanced_figure(balanced)
    model_check(trials, balanced, coefficients, models)
    interaction = coefficients.loc[coefficients["term"] == "D_times_A"].iloc[0]
    bda = float(interaction["coefficient"])
    robust_se = float(interaction["cluster_robust_SE"])
    retained = bootstrap["bDA"].to_numpy(dtype=float)
    ci_low, ci_high = np.percentile(retained, [2.5, 97.5])
    coefficient_source = str(SOURCES["balanced_coefficients"].relative_to(ROOT))
    metrics.extend([
        metric("balanced_bDA", None, bda, "log-odds per Hz²", coefficient_source,
               float(ci_low), float(ci_high)),
        metric("balanced_bDA_cluster_robust_SE", None, robust_se,
               "log-odds per Hz²", coefficient_source),
        metric("quadratic_dot_constant", None, dot_constant, "Hz",
               "src/impairments/frequency.py:wspr_symbol_quadratic_residual_trajectory"),
        metric("quadratic_dot_linear", None, dot_linear, "Hz",
               "src/impairments/frequency.py:wspr_symbol_quadratic_residual_trajectory"),
    ])
    for model in ("M0", "M1"):
        row = models.loc[models["model"] == model].iloc[0]
        for field, units in (("AIC", "unitless"), ("BIC", "unitless"),
                             ("Brier_score", "probability squared")):
            metrics.append(metric(f"{model}_{field}", None, float(row[field]), units,
                                  str(SOURCES["balanced_models"].relative_to(ROOT))))
    with METRICS_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=METRIC_FIELDS)
        writer.writeheader()
        writer.writerows(metrics)
    lines = [
        "# Final core results",
        "",
        f"- AWGN SNR50: {thresholds['snr_50_db']:.4f} dB "
        "(piecewise-linear interpolation of measured SNR points).",
        "- Linear D50 (Hz; refined grid, signed drift retained):",
        "",
        "| SNR (dB) | Positive drift | Negative drift |",
        "|---:|---:|---:|",
    ]
    for snr in sorted(refined["snr_db"].unique(), reverse=True):
        positive = next((row["value"] for row in linear_metrics
                         if row["metric"] == "linear_D50_positive" and row["snr_db"] == snr), None)
        negative = next((row["value"] for row in linear_metrics
                         if row["metric"] == "linear_D50_negative" and row["snr_db"] == snr), None)
        lines.append(f"| {snr:g} | {positive:.4f} | {negative:.4f} |" if
                     positive is not None and negative is not None else
                     f"| {snr:g} | {'not bracketed' if positive is None else f'{positive:.4f}'} | "
                     f"{'not bracketed' if negative is None else f'{negative:.4f}'} |")
    lines.extend([
        "",
        "- Quadratic A50 (Hz; pilot grid):",
        "",
        "| SNR (dB) | A50 (Hz) |",
        "|---:|---:|",
    ])
    for row in sorted(quadratic_metrics, key=lambda value: value["snr_db"], reverse=True):
        lines.append(f"| {row['snr_db']:g} | {row['value']:.4f} |")
    lines.extend([
        "",
        f"- Balanced interaction bDA: {bda:.6f}; cluster-robust SE: {robust_se:.6f}; "
        f"cluster-bootstrap 95% interval: [{ci_low:.6f}, {ci_high:.6f}] "
        "(1,000 successful fits).",
        "",
        "| Model | AIC | BIC | Brier score |",
        "|:---|---:|---:|---:|",
    ])
    for model in ("M0", "M1"):
        row = models.loc[models["model"] == model].iloc[0]
        lines.append(f"| {model} | {row['AIC']:.3f} | {row['BIC']:.3f} | "
                     f"{row['Brier_score']:.6f} |")
    lines.extend([
        "",
        "The controlled quadratic residual is orthogonal to the constant and linear "
        "basis within numerical precision "
        f"(dot products {dot_constant:.3e} and {dot_linear:.3e} at A_res = 1 Hz).",
        "",
    ])
    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")
    assert len(list(csv.DictReader(METRICS_CSV.open(newline="")))) == len(metrics)
    assert all((FIGURE_DIR / name).stat().st_size > 10000 for name in FIGURES)
    print("FIGURES_CREATED")
    for name in FIGURES:
        print(FIGURE_DIR / name)
    print("CORE_METRICS")
    writer = csv.DictWriter(sys.stdout, fieldnames=METRIC_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(metrics)
    print("SUMMARY_PATH")
    print(SUMMARY_MD)
    print("OUTPUT_PATHS")
    print(METRICS_CSV)
    print(SUMMARY_MD)
    for name in FIGURES:
        print(FIGURE_DIR / name)


if __name__ == "__main__":
    main()
