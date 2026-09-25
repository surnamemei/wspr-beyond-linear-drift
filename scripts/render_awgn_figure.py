"""Render the AWGN baseline PNG and derived interpolation metadata from CSV."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import statistics
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def crossing(rows, target):
    for left, right in zip(rows, rows[1:]):
        if min(left["p"], right["p"]) <= target <= max(left["p"], right["p"]):
            if left["p"] == right["p"]:
                return (left["snr"] + right["snr"]) / 2.0
            fraction = (target - left["p"]) / (right["p"] - left["p"])
            return left["snr"] + fraction * (right["snr"] - left["snr"])
    return None


def main():
    root = Path(sys.argv[1]).resolve()
    with (root / "results/csv/awgn_baseline_summary.csv").open(newline="") as handle:
        rows = [
            {
                "snr": float(row["snr_db_2500hz"]),
                "n": int(row["n"]),
                "p": float(row["p_decode"]),
                "low": float(row["ci_low"]),
                "high": float(row["ci_high"]),
            }
            for row in csv.DictReader(handle)
        ]
    rows.sort(key=lambda row: row["snr"])
    with (root / "results/csv/awgn_baseline_trials.csv").open(newline="") as handle:
        differences = [
            float(row["reported_snr"]) - float(row["snr_db_2500hz"])
            for row in csv.DictReader(handle)
            if row["decoded_success"] == "1" and row["reported_snr"]
        ]

    x = [row["snr"] for row in rows]
    y = [row["p"] for row in rows]
    yerr = [
        [max(0.0, row["p"] - row["low"]) for row in rows],
        [max(0.0, row["high"] - row["p"]) for row in rows],
    ]
    figure, axis = plt.subplots(figsize=(8.2, 5.2))
    axis.errorbar(x, y, yerr=yerr, fmt="o-", color="#1769aa", ecolor="#4f83cc", capsize=4)
    axis.axhline(0.5, color="#777777", linestyle="--", linewidth=1)
    axis.set(
        xlabel="Injected WSPR SNR (dB, 2500 Hz reference bandwidth)",
        ylabel="Correct decode probability",
        title="WSJT-X 3.0.2 wsprd: AWGN-only WSPR-2 decode probability",
        ylim=(-0.03, 1.08),
        xlim=(min(x) - 0.5, max(x) + 0.5),
    )
    axis.grid(True, alpha=0.25)
    for row in rows:
        axis.annotate(f"N={row['n']}", (row["snr"], row["p"]), xytext=(0, 9),
                      textcoords="offset points", ha="center", fontsize=7)
    figure.tight_layout()
    figure_path = root / "results/figures/awgn_decode_probability.png"
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(figure_path, dpi=180)
    plt.close(figure)

    derived = {
        "method": "piecewise linear interpolation between adjacent measured SNR points",
        "snr_10_db": crossing(rows, 0.1),
        "snr_50_db": crossing(rows, 0.5),
        "snr_90_db": crossing(rows, 0.9),
        "successful_decodes_with_reported_snr": len(differences),
        "mean_reported_minus_injected_db": statistics.fmean(differences),
        "median_reported_minus_injected_db": statistics.median(differences),
    }
    derived_path = root / "results/csv/awgn_baseline_thresholds.json"
    derived_path.write_text(json.dumps(derived, indent=2) + "\n")
    print(figure_path)
    print(json.dumps(derived, indent=2))


if __name__ == "__main__":
    main()
