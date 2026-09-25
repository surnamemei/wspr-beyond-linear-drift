#!/usr/bin/env python3
"""Analyze saved thermal and signed-quadratic outcomes without decoder runs."""

from __future__ import annotations

import csv
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import binomtest, norm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from impairments.frequency import wspr_symbol_quadratic_residual_trajectory
from wspr.waveform import SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT
from thermal_preflight import thermal_symbol_projection
from analyze_interaction_model import fit_binomial, clustered_covariance

SNR_GRID = (-30.0, -30.5, -31.0)
TAU_GRID = (30, 60, 120)
AMPLITUDES = (0.25, 0.5)
SIGNED_AMPLITUDES = (0.25, -0.25, 0.5, -0.5)
OUTPUT_DIR = ROOT / "results/analysis/residual_descriptor_analysis"
DESCRIPTORS_CSV = OUTPUT_DIR / "trajectory_descriptors.csv"
JOINED_CSV = OUTPUT_DIR / "descriptor_joined_trials.csv"
PAIRED_CSV = OUTPUT_DIR / "paired_thermal_vs_negative_quadratic.csv"
MODELS_CSV = OUTPUT_DIR / "model_comparison.csv"
COEFFICIENTS_CSV = OUTPUT_DIR / "model_coefficients.csv"
SOURCE_PATHS = {
    "quadratic_trials": ROOT / "results/csv/signed_quadratic_control/signed_quadratic_control_trials.csv",
    "quadratic_summary": ROOT / "results/csv/signed_quadratic_control/signed_quadratic_control_summary.csv",
    "thermal_trials": ROOT / "results/csv/thermal_amplitude_match/thermal_amplitude_match_trials.csv",
    "thermal_summary": ROOT / "results/csv/thermal_amplitude_match/thermal_amplitude_match_summary.csv",
    "thermal_shapes": ROOT / "results/analysis/thermal_preflight/thermal_residual_shapes.csv",
}
DESCRIPTOR_FIELDS = (
    "trajectory_id", "family", "tau_seconds", "signed_A_res_hz",
    "max_abs_frequency_hz", "frequency_rms_hz", "frequency_peak_to_peak_hz",
    "max_abs_phase_rad", "phase_rms_rad", "final_phase_rad",
    "phase_peak_to_peak_rad", "correlation_with_negative_quadratic",
    "cosine_similarity_with_negative_quadratic", "RMS_shape_difference",
    "max_shape_difference",
)
PAIRED_FIELDS = (
    "snr_db", "tau_seconds", "abs_A_res_hz", "both_decode",
    "thermal_only", "negative_quadratic_only", "neither",
    "paired_difference", "exact_mcnemar_p",
)
MODEL_FIELDS = (
    "model", "n_trials", "n_clusters", "log_likelihood",
    "AIC", "BIC", "Brier_score",
)
COEFFICIENT_FIELDS = (
    "model", "term", "coefficient", "ordinary_SE",
    "cluster_robust_SE", "cluster_robust_z", "cluster_robust_p",
)
MODEL_TERMS = {
    "M_amp": ("intercept", "snr_c", "max_abs_frequency_hz"),
    "M_rms": ("intercept", "snr_c", "max_abs_frequency_hz", "frequency_rms_hz"),
    "M_phase": ("intercept", "snr_c", "max_abs_frequency_hz", "max_abs_phase_rad"),
    "M_full": ("intercept", "snr_c", "max_abs_frequency_hz",
               "frequency_rms_hz", "max_abs_phase_rad"),
}


def trajectory_id(family: str, amplitude: float, tau: int | None = None) -> str:
    if family == "quadratic":
        return f"quadratic_{amplitude:+.2f}"
    assert tau is not None
    return f"thermal_tau{tau}_A{amplitude:.2f}"


def load_sources() -> dict[str, pd.DataFrame]:
    for path in SOURCE_PATHS.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    frames = {key: pd.read_csv(path) for key, path in SOURCE_PATHS.items()}
    assert len(frames["quadratic_trials"]) == 1200
    assert len(frames["thermal_trials"]) == 1800
    assert len(frames["quadratic_summary"]) == 12
    assert len(frames["thermal_summary"]) == 18
    assert len(frames["thermal_shapes"]) == 6 * SYMBOL_COUNT
    return frames


def validate_trial_pairing(frames: dict[str, pd.DataFrame]) -> None:
    for key, condition_fields, expected_conditions in (
        ("quadratic_trials", ["snr_db", "signed_A_res_hz"], 12),
        ("thermal_trials", ["snr_db", "tau_seconds", "target_A_res_hz"], 18),
    ):
        frame = frames[key]
        assert frame["decoded_success"].isin((0, 1)).all()
        groups = frame.groupby(condition_fields)
        assert len(groups) == expected_conditions
        assert groups.size().eq(100).all()
        assert groups["seed"].nunique().eq(100).all()
        assert groups["trial_index"].nunique().eq(100).all()
    for snr_index, snr in enumerate(SNR_GRID):
        expected = {2026100200 + snr_index * 10000 + index for index in range(100)}
        for key in ("quadratic_trials", "thermal_trials"):
            selected = frames[key].loc[frames[key]["snr_db"] == snr]
            assert set(selected["seed"].astype(int)) == expected
    assert sorted(frames["quadratic_trials"]["snr_db"].unique().tolist()) == sorted(SNR_GRID)
    assert sorted(frames["thermal_trials"]["snr_db"].unique().tolist()) == sorted(SNR_GRID)


def descriptor(symbol_frequency: np.ndarray, negative_basis: np.ndarray,
               family: str, amplitude: float, tau: int | None = None) -> dict[str, object]:
    assert symbol_frequency.shape == (SYMBOL_COUNT,)
    frequency = np.repeat(symbol_frequency, SAMPLES_PER_SYMBOL)
    assert len(frequency) == SYMBOL_COUNT * SAMPLES_PER_SYMBOL
    sample_phase_step = 2 * np.pi * frequency / SAMPLE_RATE_HZ
    phase_edges = np.concatenate(([0.0], np.cumsum(sample_phase_step)))
    # Output sample n uses the phase at the start of its sample interval.
    phase_at_samples = phase_edges[:-1]
    normalized = symbol_frequency / np.max(np.abs(symbol_frequency))
    difference = normalized - negative_basis
    correlation = float(np.corrcoef(normalized, negative_basis)[0, 1])
    cosine = float(np.dot(normalized, negative_basis) /
                   (np.linalg.norm(normalized) * np.linalg.norm(negative_basis)))
    return {
        "trajectory_id": trajectory_id(family, amplitude, tau),
        "family": family,
        "tau_seconds": "" if tau is None else tau,
        "signed_A_res_hz": amplitude if family == "quadratic" else "",
        "max_abs_frequency_hz": float(np.max(np.abs(frequency))),
        "frequency_rms_hz": float(np.sqrt(np.mean(frequency ** 2))),
        "frequency_peak_to_peak_hz": float(np.ptp(frequency)),
        "max_abs_phase_rad": float(np.max(np.abs(phase_at_samples))),
        "phase_rms_rad": float(np.sqrt(np.mean(phase_at_samples ** 2))),
        "final_phase_rad": float(phase_edges[-1]),
        "phase_peak_to_peak_rad": float(np.ptp(phase_edges)),
        "correlation_with_negative_quadratic": correlation,
        "cosine_similarity_with_negative_quadratic": cosine,
        "RMS_shape_difference": float(np.sqrt(np.mean(difference ** 2))),
        "max_shape_difference": float(np.max(np.abs(difference))),
    }


def build_descriptors(frames: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    assert (SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT) == (375, 256, 162)
    basis_samples = np.asarray(
        wspr_symbol_quadratic_residual_trajectory(162, 256, 1.0), dtype=float
    ).reshape(162, 256)
    assert np.allclose(basis_samples, basis_samples[:, :1], rtol=0, atol=0)
    basis = basis_samples[:, 0]
    negative_basis = -basis
    assert np.isclose(np.max(np.abs(basis)), 1.0, atol=1e-14)
    rows = [
        descriptor(amplitude * basis, negative_basis, "quadratic", amplitude)
        for amplitude in SIGNED_AMPLITUDES
    ]
    stored = frames["thermal_shapes"]
    for tau in TAU_GRID:
        stored_tau = stored.loc[stored["tau_seconds"] == tau].sort_values("symbol_index")
        assert stored_tau["symbol_index"].tolist() == list(range(SYMBOL_COUNT))
        stored_normalized = stored_tau["normalized_thermal_residual"].to_numpy(dtype=float)
        for amplitude in AMPLITUDES:
            matching = frames["thermal_summary"].loc[
                (frames["thermal_summary"]["tau_seconds"] == tau) &
                (frames["thermal_summary"]["target_A_res_hz"] == amplitude)
            ]
            assert len(matching) == len(SNR_GRID)
            assert np.allclose(matching["K_required_hz"],
                               matching["K_required_hz"].iloc[0], atol=0, rtol=0)
            required_k = float(matching["K_required_hz"].iloc[0])
            _, _, _, _, residual = thermal_symbol_projection(tau, required_k)
            assert np.isclose(np.max(np.abs(residual)), amplitude, rtol=0, atol=1e-12)
            assert np.allclose(residual / np.max(np.abs(residual)),
                               stored_normalized, rtol=0, atol=1e-12)
            rows.append(descriptor(residual, negative_basis, "thermal", amplitude, tau))
    assert len(rows) == 10
    assert len({row["trajectory_id"] for row in rows}) == 10
    return rows


def join_trials(frames: dict[str, pd.DataFrame],
                descriptors: list[dict[str, object]]) -> pd.DataFrame:
    quadratic = frames["quadratic_trials"].copy()
    quadratic["trajectory_id"] = quadratic["signed_A_res_hz"].map(
        lambda value: trajectory_id("quadratic", float(value))
    )
    quadratic["family"] = "quadratic"
    thermal = frames["thermal_trials"].copy()
    thermal["trajectory_id"] = thermal.apply(
        lambda row: trajectory_id("thermal", float(row["target_A_res_hz"]),
                                  int(row["tau_seconds"])), axis=1
    )
    thermal["family"] = "thermal"
    columns = ("trajectory_id", "family", "snr_db", "trial_index", "seed",
               "decoded_success")
    joined = pd.concat((quadratic[list(columns)], thermal[list(columns)]),
                       ignore_index=True)
    descriptor_frame = pd.DataFrame(descriptors)
    joined = joined.merge(
        descriptor_frame.drop(columns=["family"]), on="trajectory_id",
        validate="many_to_one",
    )
    assert len(joined) == 3000 and not joined[["snr_db", "seed", "decoded_success"]].isna().any().any()
    assert joined.groupby(["snr_db", "trajectory_id"]).size().eq(100).all()
    assert len(joined.groupby(["snr_db", "trajectory_id"])) == 30
    assert joined.groupby(["snr_db", "seed"]).size().eq(10).all()
    assert len(joined.groupby(["snr_db", "seed"])) == 300
    return joined


def paired_comparisons(frames: dict[str, pd.DataFrame]) -> list[dict[str, object]]:
    thermal = frames["thermal_trials"]
    quadratic = frames["quadratic_trials"]
    rows = []
    for snr in SNR_GRID:
        for tau in TAU_GRID:
            for amplitude in AMPLITUDES:
                t = thermal.loc[(thermal["snr_db"] == snr) &
                                (thermal["tau_seconds"] == tau) &
                                (thermal["target_A_res_hz"] == amplitude)]
                q = quadratic.loc[(quadratic["snr_db"] == snr) &
                                  (quadratic["signed_A_res_hz"] == -amplitude)]
                t_by_seed = t.set_index("seed")["decoded_success"]
                q_by_seed = q.set_index("seed")["decoded_success"]
                assert len(t_by_seed) == len(q_by_seed) == 100
                assert t_by_seed.index.is_unique and q_by_seed.index.is_unique
                assert set(t_by_seed.index) == set(q_by_seed.index)
                paired = pd.DataFrame({"thermal": t_by_seed, "quadratic": q_by_seed})
                both = int(((paired["thermal"] == 1) & (paired["quadratic"] == 1)).sum())
                thermal_only = int(((paired["thermal"] == 1) & (paired["quadratic"] == 0)).sum())
                negative_only = int(((paired["thermal"] == 0) & (paired["quadratic"] == 1)).sum())
                neither = int(((paired["thermal"] == 0) & (paired["quadratic"] == 0)).sum())
                assert both + thermal_only + negative_only + neither == 100
                discordant = thermal_only + negative_only
                p_value = (float(binomtest(thermal_only, discordant, 0.5).pvalue)
                           if discordant else 1.0)
                rows.append({
                    "snr_db": snr, "tau_seconds": tau, "abs_A_res_hz": amplitude,
                    "both_decode": both, "thermal_only": thermal_only,
                    "negative_quadratic_only": negative_only, "neither": neither,
                    "paired_difference": (thermal_only - negative_only) / 100,
                    "exact_mcnemar_p": p_value,
                })
    assert len(rows) == 18
    return rows


def fit_models(joined: pd.DataFrame) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    snr_c = joined["snr_db"].to_numpy(dtype=float) + 30.5
    amplitude = joined["max_abs_frequency_hz"].to_numpy(dtype=float)
    rms = joined["frequency_rms_hz"].to_numpy(dtype=float)
    phase = joined["max_abs_phase_rad"].to_numpy(dtype=float)
    predictors = {
        "intercept": np.ones(len(joined)), "snr_c": snr_c,
        "max_abs_frequency_hz": amplitude, "frequency_rms_hz": rms,
        "max_abs_phase_rad": phase,
    }
    y = joined["decoded_success"].to_numpy(dtype=float)
    assert np.isin(y, (0, 1)).all()
    cluster_id = (joined["snr_db"].map(lambda value: f"{value:g}") + "|" +
                  joined["seed"].astype(str))
    clusters, cluster_codes = np.unique(cluster_id.to_numpy(), return_inverse=True)
    assert len(clusters) == 300
    model_rows = []
    coefficient_rows = []
    for model, terms in MODEL_TERMS.items():
        x = np.column_stack([predictors[term] for term in terms])
        assert np.linalg.matrix_rank(x) == len(terms), model
        beta, inverse_info, ll, _ = fit_binomial(x, y, np.ones(len(y)))
        probability = expit(x @ beta)
        ordinary_se = np.sqrt(np.diag(inverse_info))
        robust_covariance = clustered_covariance(
            x, y, probability, cluster_codes, len(clusters), inverse_info
        )
        robust_se = np.sqrt(np.diag(robust_covariance))
        assert np.isfinite(beta).all() and np.isfinite(robust_se).all()
        model_rows.append({
            "model": model, "n_trials": len(joined), "n_clusters": len(clusters),
            "log_likelihood": ll, "AIC": -2 * ll + 2 * len(terms),
            "BIC": -2 * ll + len(terms) * math.log(len(joined)),
            "Brier_score": float(np.mean((y - probability) ** 2)),
        })
        for index, term in enumerate(terms):
            z = float(beta[index] / robust_se[index])
            coefficient_rows.append({
                "model": model, "term": term, "coefficient": float(beta[index]),
                "ordinary_SE": float(ordinary_se[index]),
                "cluster_robust_SE": float(robust_se[index]),
                "cluster_robust_z": z,
                "cluster_robust_p": float(2 * norm.sf(abs(z))),
            })
    return model_rows, coefficient_rows


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def print_table(fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


def main() -> None:
    outputs = (DESCRIPTORS_CSV, JOINED_CSV, PAIRED_CSV, MODELS_CSV, COEFFICIENTS_CSV)
    for path in outputs:
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
    frames = load_sources()
    validate_trial_pairing(frames)
    descriptors = build_descriptors(frames)
    joined = join_trials(frames, descriptors)
    paired = paired_comparisons(frames)
    models, coefficients = fit_models(joined)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(DESCRIPTORS_CSV, DESCRIPTOR_FIELDS, descriptors)
    joined.to_csv(JOINED_CSV, index=False, mode="x")
    write_csv(PAIRED_CSV, PAIRED_FIELDS, paired)
    write_csv(MODELS_CSV, MODEL_FIELDS, models)
    write_csv(COEFFICIENTS_CSV, COEFFICIENT_FIELDS, coefficients)
    for path, count in ((DESCRIPTORS_CSV, 10), (JOINED_CSV, 3000),
                        (PAIRED_CSV, 18), (MODELS_CSV, 4)):
        with path.open(newline="") as handle:
            assert len(list(csv.DictReader(handle))) == count
    print("TRAJECTORY_DESCRIPTORS")
    print("phase_at_sample_n=2*pi*sum(frequency_samples_before_n)/375")
    print("final_phase=2*pi*sum(all_active_frequency_samples)/375")
    print_table(DESCRIPTOR_FIELDS, descriptors)
    print("PAIRED_THERMAL_VS_QUADRATIC")
    print_table(PAIRED_FIELDS, paired)
    print("MODEL_COMPARISON")
    print_table(MODEL_FIELDS, models)
    print("OUTPUT_PATHS")
    for path in outputs:
        print(path)


if __name__ == "__main__":
    main()
