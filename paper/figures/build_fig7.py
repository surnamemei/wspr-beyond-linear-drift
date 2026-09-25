"""Render Fig. 7 from the saved physical-oscillator summary; no decoder work."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "results/csv/physical_oscillator_decoder/physical_oscillator_decoder_summary.csv"
OUTPUT = Path(__file__).resolve().parent / "fig7_physical_oscillator_decode.png"
PDF_OUTPUT = OUTPUT.with_suffix(".pdf")


def main() -> None:
    with SOURCE.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 54
    families = ("white_FM", "flicker_FM", "random_walk_FM")
    carriers = (10_000_000.0, 14_000_000.0, 28_000_000.0)
    snrs = (-30.5, -31.0)
    targets = (1e-9, 3e-9, 1e-8)
    assert len({(r["noise_family"], float(r["carrier_frequency_hz"]),
                 float(r["target_sigma_y_1s"]), float(r["snr_db"])) for r in rows}) == 54

    palette = {"white_FM": "#147d88", "flicker_FM": "#d48120", "random_walk_FM": "#774eaa"}
    labels = {"white_FM": "White FM", "flicker_FM": "Flicker FM", "random_walk_FM": "Random-walk FM"}
    data = {(r["noise_family"], float(r["carrier_frequency_hz"]),
             float(r["target_sigma_y_1s"]), float(r["snr_db"])): r for r in rows}
    # IEEE two-column figure width. Reserve the top strip for the shared legend.
    plt.rcParams.update({"font.size": 8, "axes.titlesize": 8.5,
                         "axes.labelsize": 8, "xtick.labelsize": 7.5,
                         "ytick.labelsize": 7.5})
    fig, axes = plt.subplots(3, 2, figsize=(7.1, 7.2), sharex=True, sharey=True)
    fig.subplots_adjust(left=0.105, right=0.985, bottom=0.09, top=0.88,
                        wspace=0.12, hspace=0.26)
    for i, carrier in enumerate(carriers):
        for j, snr in enumerate(snrs):
            ax = axes[i, j]
            for family in families:
                group = [data[(family, carrier, target, snr)] for target in targets]
                y = [float(r["p_decode"]) for r in group]
                lower = [float(r["Wilson95_low"]) for r in group]
                upper = [float(r["Wilson95_high"]) for r in group]
                assert all(int(r["n"]) == 100 for r in group)
                assert all(abs(float(r["successes"]) / 100 - p) < 1e-12 for r, p in zip(group, y))
                ax.errorbar(targets, y, yerr=[[max(0.0, p - lo) for p, lo in zip(y, lower)],
                                               [max(0.0, hi - p) for p, hi in zip(y, upper)]],
                            marker="o", markersize=4.5, linewidth=1.6, capsize=2.5,
                            color=palette[family], label=labels[family])
            ax.set_xscale("log")
            ax.set_xticks(targets, [r"$10^{-9}$", r"$3\times10^{-9}$", r"$10^{-8}$"])
            ax.set_ylim(-0.055, 1.055)
            ax.grid(alpha=0.25)
            ax.set_title(f"{int(carrier / 1e6)} MHz  |  SNR {snr:g} dB")
    handles = [Line2D([0], [0], color=palette[f], marker="o", lw=1.6, label=labels[f]) for f in families]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.545, 0.98),
               ncol=3, frameon=False, fontsize=8)
    fig.supylabel(r"Observed $P_{\mathrm{decode}}$", x=0.015, fontsize=8)
    fig.supxlabel(r"Target $\sigma_y(1\,\mathrm{s})$", y=0.025, fontsize=8)
    fig.savefig(OUTPUT, dpi=400)
    fig.savefig(PDF_OUTPUT)
    plt.close(fig)
    print(OUTPUT)
    print(PDF_OUTPUT)


if __name__ == "__main__":
    main()
