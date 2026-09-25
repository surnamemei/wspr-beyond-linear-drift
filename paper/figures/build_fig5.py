"""Paper layout of the validated thermal residual shapes; saved CSV only."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "results/analysis/thermal_preflight/thermal_residual_shapes.csv"
OUTPUT = Path(__file__).resolve().parent / "fig5_thermal_vs_negative_quadratic.png"
TAUS = (30, 60, 120)


def main() -> None:
    with SOURCE.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    fig, axes = plt.subplots(3, 1, figsize=(7.1, 5.7), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.105, right=0.985, bottom=0.10, top=0.87, hspace=0.28)
    for ax, tau in zip(axes, TAUS):
        group = sorted((row for row in rows if int(row["tau_seconds"]) == tau),
                       key=lambda row: int(row["symbol_index"]))
        assert len(group) == 162
        assert [int(row["symbol_index"]) for row in group] == list(range(162))
        x = [float(row["symbol_center_time_seconds"]) for row in group]
        thermal = [float(row["normalized_thermal_residual"]) for row in group]
        negative_quadratic = [-float(row["normalized_quadratic_residual"]) for row in group]
        ax.plot(x, thermal, color="#147d88", lw=1.8)
        ax.plot(x, negative_quadratic, color="#333333", ls="--", lw=1.5)
        ax.set_title(f"Thermal time constant {tau} s", fontsize=9)
        ax.set_ylim(-1.08, 1.08)
        ax.grid(alpha=0.22)
        ax.tick_params(labelsize=8)
    handles = [
        Line2D([0], [0], color="#147d88", lw=1.8, label="Projected thermal residual"),
        Line2D([0], [0], color="#333333", ls="--", lw=1.5,
               label="Negative orthogonal quadratic basis"),
    ]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.54, 0.98),
               ncol=2, frameon=False, fontsize=8)
    fig.supxlabel("Symbol-center time from frame start (s)", y=0.025, fontsize=8)
    fig.supylabel("Normalized residual frequency", x=0.015, fontsize=8)
    fig.savefig(OUTPUT, dpi=400)
    plt.close(fig)
    print(OUTPUT)


if __name__ == "__main__":
    main()
