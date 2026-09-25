#!/usr/bin/env python3
"""Combine Phase 2B control stages and render HOLD diagnostics."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from analysis.metrics import wilson_interval


STAGES = (
    "cfo_quick",
    "cfo_confirm",
    "linear_exact_check",
    "linear_confirm",
)
VALUE_COLUMNS = {"cfo": "cfo_hz", "linear": "linear_drift_parameter"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    stage_dir = root / "results/csv/stages"
    output_dir = root / "results/csv"
    figure_dir = root / "results/figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    metadata = []
    for stage in STAGES:
        rows.extend(read_csv(stage_dir / f"{stage}_trials.csv"))
        metadata.append(json.loads((stage_dir / f"{stage}_metadata.json").read_text()))
    rows.sort(
        key=lambda row: (
            row["impairment_type"],
            -float(row["snr_db"]),
            float(row[VALUE_COLUMNS[row["impairment_type"]]]),
            int(row["seed"]),
        )
    )
    trial_path = output_dir / "frequency_model_mismatch_trials.csv"
    with trial_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    baseline = {
        float(row["snr_db_2500hz"]): row
        for row in read_csv(output_dir / "awgn_baseline_summary.csv")
    }
    grouped: dict[tuple[str, float, float], list[dict[str, str]]] = {}
    for row in rows:
        kind = row["impairment_type"]
        value = float(row[VALUE_COLUMNS[kind]])
        key = (kind, float(row["snr_db"]), value)
        grouped.setdefault(key, []).append(row)

    summaries = []
    for (kind, snr, value), selected in sorted(grouped.items()):
        successes = sum(int(row["decoded_success"]) for row in selected)
        n = len(selected)
        low, high = wilson_interval(successes, n)
        base = baseline[snr]
        base_p = float(base["p_decode"])
        base_low = float(base["ci_low"])
        base_high = float(base["ci_high"])
        reported_drift = [
            float(row["reported_drift"])
            for row in selected
            if row["decoded_success"] == "1" and row["reported_drift"] != ""
        ]
        summaries.append(
            {
                "impairment_type": kind,
                "snr_db": snr,
                "value_hz": value,
                "inside_documented_search": int(abs(value) <= (110.0 if kind == "cfo" else 4.0)),
                "n": n,
                "successes": successes,
                "p_decode": successes / n,
                "ci_low": low,
                "ci_high": high,
                "awgn_baseline_n": int(base["n"]),
                "awgn_baseline_p_decode": base_p,
                "awgn_baseline_ci_low": base_low,
                "awgn_baseline_ci_high": base_high,
                "delta_p_decode": successes / n - base_p,
                "delta_conservative_low": low - base_high,
                "delta_conservative_high": high - base_low,
                "mean_reported_drift_on_success": (
                    sum(reported_drift) / len(reported_drift) if reported_drift else ""
                ),
            }
        )
    summary_path = output_dir / "frequency_controls_summary.csv"
    with summary_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    colors = {-29.0: "#1b9e77", -31.0: "#d95f02", -32.0: "#7570b3"}
    for kind, filename, xlabel in (
        ("cfo", "cfo_control.png", "Injected CFO (Hz)"),
        ("linear", "linear_drift_control.png", "Injected wsprd drift parameter (Hz/frame)"),
    ):
        fig, ax = plt.subplots(figsize=(9.5, 5.8), constrained_layout=True)
        for snr in (-29.0, -31.0, -32.0):
            points = [
                row for row in summaries
                if row["impairment_type"] == kind and float(row["snr_db"]) == snr
            ]
            if not points:
                continue
            points.sort(key=lambda row: float(row["value_hz"]))
            x = [float(row["value_hz"]) for row in points]
            y = [float(row["p_decode"]) for row in points]
            yerr = [
                [y[i] - float(points[i]["ci_low"]) for i in range(len(points))],
                [float(points[i]["ci_high"]) - y[i] for i in range(len(points))],
            ]
            ax.errorbar(x, y, yerr=yerr, marker="o", capsize=2.5, color=colors[snr], label=f"{snr:.0f} dB")
            base = baseline[snr]
            ax.axhline(float(base["p_decode"]), color=colors[snr], linestyle=":", alpha=0.55)
        if kind == "cfo":
            ax.axvspan(-110, 110, color="#777777", alpha=0.08, label="default search span")
        else:
            ax.axvspan(-4, 4, color="#777777", alpha=0.08, label="coarse drift search")
        ax.set(xlabel=xlabel, ylabel="Decode probability", ylim=(-0.03, 1.03))
        ax.grid(alpha=0.25)
        ax.legend(ncol=2)
        fig.savefig(figure_dir / filename, dpi=170)
        plt.close(fig)

    total_trials = len(rows)
    total_decoder_runtime = sum(float(row["runtime_seconds"]) for row in rows)
    wall_runtime = sum(float(item["wall_runtime_seconds"]) for item in metadata)
    result_metadata = {
        "phase": "2B/2C",
        "status": "HOLD",
        "hold_reason": "linear-drift control loses most decodes at +/-2 Hz/frame near threshold despite being inside the documented search; quadratic probe not started",
        "included_stages": list(STAGES),
        "total_trials": total_trials,
        "total_decoder_runtime_seconds": total_decoder_runtime,
        "summed_stage_wall_runtime_seconds": wall_runtime,
        "decoder_exit_errors": sum(int(row["decoder_exit_status"]) != 0 for row in rows),
        "unique_seeds": len({row["seed"] for row in rows}),
        "raw_trials": str(trial_path),
        "summary": str(summary_path),
        "quadratic_trials": 0,
        "tone_spacing_hz": 1.46484375,
    }
    (output_dir / "frequency_model_mismatch_metadata.json").write_text(
        json.dumps(result_metadata, indent=2) + "\n"
    )
    print(json.dumps(result_metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
