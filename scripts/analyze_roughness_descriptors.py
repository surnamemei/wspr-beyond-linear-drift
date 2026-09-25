#!/usr/bin/env python3
"""Analysis-only morphology and cross-family prediction from saved trials."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from impairments.frequency import wspr_symbol_quadratic_residual_trajectory
from wspr.waveform import SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT
from thermal_preflight import thermal_symbol_projection
from run_random_walk_external_validation import trajectory as regenerate_random_walk
from analyze_interaction_model import fit_binomial, clustered_covariance

DETERMINISTIC_TRIALS = ROOT / "results/analysis/residual_descriptor_analysis/descriptor_joined_trials.csv"
DETERMINISTIC_DESCRIPTORS = ROOT / "results/analysis/residual_descriptor_analysis/trajectory_descriptors.csv"
THERMAL_SUMMARY = ROOT / "results/csv/thermal_amplitude_match/thermal_amplitude_match_summary.csv"
RANDOM_WALK_TRIALS = ROOT / "results/csv/random_walk_decoder/random_walk_decoder_trials.csv"
RANDOM_WALK_MANIFEST = ROOT / "results/analysis/random_walk_external_validation/random_walk_trajectory_manifest.csv"
SOURCES = (DETERMINISTIC_TRIALS, DETERMINISTIC_DESCRIPTORS, THERMAL_SUMMARY,
           RANDOM_WALK_TRIALS, RANDOM_WALK_MANIFEST)
OUTPUT_DIR = ROOT / "results/analysis/roughness_descriptor"
OUTPUTS = {
    "trials": OUTPUT_DIR / "roughness_trial_table.csv",
    "family": OUTPUT_DIR / "roughness_family_summary.csv",
    "correlation": OUTPUT_DIR / "roughness_correlation_matrix.csv",
    "models": OUTPUT_DIR / "roughness_model_comparison.csv",
    "cv": OUTPUT_DIR / "roughness_leave_one_family_out.csv",
    "predictions": OUTPUT_DIR / "roughness_predictions.csv",
    "bootstrap": OUTPUT_DIR / "roughness_bootstrap.csv",
    "report": OUTPUT_DIR / "roughness_analysis_report.txt",
}
FAMILIES = (
    "quadratic_positive", "quadratic_negative", "thermal_tau30",
    "thermal_tau60", "thermal_tau120", "random_walk",
)
SNRS = {-30.0, -30.5, -31.0}
DESCRIPTORS = (
    "max_abs_frequency_hz", "frequency_rms_hz", "max_abs_phase_rad", "phase_rms_rad",
    "first_difference_rms_hz", "total_variation_hz", "second_difference_rms_hz",
    "normalized_first_difference_rms", "normalized_second_difference_rms",
)
AUDIT_DESCRIPTORS = (
    "frequency_rms_hz", "first_difference_rms_hz", "total_variation_hz",
    "second_difference_rms_hz", "max_abs_phase_rad",
)
MODEL_TERMS = {
    "M_RMS": ("snr_c", "frequency_rms_hz"),
    "M_RMS_D1": ("snr_c", "frequency_rms_hz", "first_difference_rms_hz"),
    "M_RMS_TV": ("snr_c", "frequency_rms_hz", "total_variation_hz"),
    "M_RMS_D2": ("snr_c", "frequency_rms_hz", "second_difference_rms_hz"),
    "M_RMS_PHASE": ("snr_c", "frequency_rms_hz", "max_abs_phase_rad"),
    "M_RMS_D1_PHASE": ("snr_c", "frequency_rms_hz", "first_difference_rms_hz", "max_abs_phase_rad"),
}
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 2026100800


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def symbol_descriptors(residual: np.ndarray) -> dict[str, float]:
    assert residual.shape == (SYMBOL_COUNT,)
    x = (np.arange(SYMBOL_COUNT) - 81.0) / 81.0
    assert abs(float(np.sum(residual))) < 1e-10
    assert abs(float(np.dot(residual, x))) < 1e-10
    difference_1 = np.diff(residual)
    difference_2 = np.diff(residual, n=2)
    frequency_rms = float(np.sqrt(np.mean(residual ** 2)))
    phase_step = (2 * np.pi / SAMPLE_RATE_HZ) * np.repeat(residual, SAMPLES_PER_SYMBOL)
    phase_at_samples = np.concatenate(([0.0], np.cumsum(phase_step)))[:-1]
    first_rms = float(np.sqrt(np.mean(difference_1 ** 2)))
    second_rms = float(np.sqrt(np.mean(difference_2 ** 2)))
    return {
        "max_abs_frequency_hz": float(np.max(np.abs(residual))),
        "frequency_rms_hz": frequency_rms,
        "max_abs_phase_rad": float(np.max(np.abs(phase_at_samples))),
        "phase_rms_rad": float(np.sqrt(np.mean(phase_at_samples ** 2))),
        "first_difference_rms_hz": first_rms,
        "total_variation_hz": float(np.sum(np.abs(difference_1))),
        "second_difference_rms_hz": second_rms,
        "normalized_first_difference_rms": first_rms / frequency_rms if frequency_rms else 0.0,
        "normalized_second_difference_rms": second_rms / frequency_rms if frequency_rms else 0.0,
    }


def deterministic_family(row: pd.Series) -> str:
    if row.family == "quadratic":
        return "quadratic_positive" if row.signed_A_res_hz > 0 else "quadratic_negative"
    assert row.family == "thermal"
    return f"thermal_tau{int(row.tau_seconds)}"


def build_deterministic() -> pd.DataFrame:
    trials = pd.read_csv(DETERMINISTIC_TRIALS)
    stored_descriptors = pd.read_csv(DETERMINISTIC_DESCRIPTORS)
    thermal = pd.read_csv(THERMAL_SUMMARY)
    assert len(trials) == 3000 and len(stored_descriptors) == 10
    assert stored_descriptors.trajectory_id.is_unique
    assert set(trials.snr_db) == SNRS
    assert trials.decoded_success.isin((0, 1)).all()
    assert not trials[["trajectory_id", "snr_db", "seed"]].duplicated().any()
    thermal_scale = thermal.groupby(["tau_seconds", "target_A_res_hz"])["K_required_hz"]
    assert thermal_scale.nunique().eq(1).all()
    scale_lookup = thermal_scale.first().to_dict()
    basis = np.asarray(wspr_symbol_quadratic_residual_trajectory(162, 256, 1.0))
    basis = basis.reshape(SYMBOL_COUNT, SAMPLES_PER_SYMBOL)[:, 0]
    rows = []
    for stored in stored_descriptors.itertuples(index=False):
        if stored.family == "quadratic":
            residual = float(stored.signed_A_res_hz) * basis
        else:
            tau = int(stored.tau_seconds)
            amplitude = float(stored.max_abs_frequency_hz)
            candidate = [(key, scale) for key, scale in scale_lookup.items()
                         if key[0] == tau and np.isclose(key[1], amplitude, rtol=0, atol=1e-12)]
            assert len(candidate) == 1
            _, _, _, _, residual = thermal_symbol_projection(tau, float(candidate[0][1]))
        measured = symbol_descriptors(np.asarray(residual, dtype=float))
        for name in ("max_abs_frequency_hz", "frequency_rms_hz", "max_abs_phase_rad", "phase_rms_rad"):
            assert np.isclose(measured[name], getattr(stored, name), rtol=0, atol=1e-9), (stored.trajectory_id, name)
        rows.append({"trajectory_id": stored.trajectory_id, **measured})
    trajectory_table = pd.DataFrame(rows)
    joined = trials.merge(trajectory_table, on="trajectory_id", how="left",
                          validate="many_to_one", suffixes=("_stored", ""))
    assert len(joined) == 3000
    for name in ("max_abs_frequency_hz", "frequency_rms_hz", "max_abs_phase_rad", "phase_rms_rad"):
        assert np.allclose(joined[name], joined[f"{name}_stored"], atol=1e-9, rtol=0)
        del joined[f"{name}_stored"]
    joined["trajectory_family"] = joined.apply(deterministic_family, axis=1)
    joined["trajectory_identity"] = joined.trajectory_id
    joined["source_dataset"] = "deterministic"
    joined["noise_seed"] = joined.seed
    joined["trajectory_seed"] = pd.NA
    return joined


def build_random_walk() -> pd.DataFrame:
    trials = pd.read_csv(RANDOM_WALK_TRIALS)
    manifest = pd.read_csv(RANDOM_WALK_MANIFEST)
    assert len(trials) == 2400 and len(manifest) == 800
    assert manifest.trajectory_seed.is_unique
    assert trials.groupby("trajectory_seed").size().eq(3).all()
    assert set(trials.snr_db) == SNRS
    assert trials.decoded_success.isin((0, 1)).all()
    rows = []
    for item in manifest.itertuples(index=False):
        stored, residual = regenerate_random_walk(float(item.sigma_step_hz), int(item.trajectory_seed))
        measured = symbol_descriptors(residual)
        for name in ("max_abs_frequency_hz", "frequency_rms_hz", "max_abs_phase_rad", "phase_rms_rad"):
            assert np.isclose(measured[name], getattr(item, name), rtol=0, atol=1e-9)
            assert np.isclose(stored[name], getattr(item, name), rtol=0, atol=1e-9)
        rows.append({"trajectory_seed": int(item.trajectory_seed), **measured})
    shape_table = pd.DataFrame(rows)
    joined = trials.merge(shape_table, on="trajectory_seed", how="left",
                          validate="many_to_one", suffixes=("_stored", ""))
    assert len(joined) == 2400
    for name in ("max_abs_frequency_hz", "frequency_rms_hz", "max_abs_phase_rad", "phase_rms_rad"):
        assert np.allclose(joined[name], joined[f"{name}_stored"], atol=1e-9, rtol=0)
        del joined[f"{name}_stored"]
    joined["trajectory_family"] = "random_walk"
    joined["trajectory_id"] = joined.trajectory_seed.map(lambda seed: f"random_walk_{seed}")
    joined["trajectory_identity"] = joined.trajectory_id
    joined["source_dataset"] = "random_walk"
    joined["seed"] = joined.noise_seed
    return joined


def unified_trials() -> pd.DataFrame:
    deterministic = build_deterministic()
    random_walk = build_random_walk()
    fields = ["source_dataset", "trajectory_family", "trajectory_id", "trajectory_identity",
              "snr_db", "seed", "trajectory_seed", "noise_seed", "trial_index",
              "decoded_success", *DESCRIPTORS]
    unified = pd.concat((deterministic[fields], random_walk[fields]), ignore_index=True)
    unified["snr_c"] = unified.snr_db + 30.5
    assert len(unified) == 5400
    assert set(unified.trajectory_family) == set(FAMILIES)
    assert set(unified.snr_db) == SNRS
    assert unified.decoded_success.isin((0, 1)).all()
    assert not unified[["trajectory_id", "snr_db", "seed"]].duplicated().any()
    assert np.isfinite(unified[list(DESCRIPTORS)]).all().all()
    assert unified.groupby("trajectory_identity").size().sum() == len(unified)
    assert unified.trajectory_identity.nunique() == 810
    return unified


def descriptor_audit(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for family in FAMILIES:
        selected = frame.loc[frame.trajectory_family == family]
        for name in AUDIT_DESCRIPTORS:
            values = selected[name].to_numpy(dtype=float)
            rows.append({"trajectory_family": family, "n_trials": len(selected),
                         "descriptor": name, "median": float(np.median(values)),
                         "p25": float(np.percentile(values, 25)),
                         "p75": float(np.percentile(values, 75)),
                         "iqr": float(np.subtract(*np.percentile(values, [75, 25])))})
    summary = pd.DataFrame(rows)
    correlations = frame[list(DESCRIPTORS)].corr()
    correlations.index.name = "descriptor"
    assert len(summary) == 30 and correlations.shape == (9, 9)
    return summary, correlations


def design(frame: pd.DataFrame, model: str) -> np.ndarray:
    return np.column_stack([np.ones(len(frame)),
                            *(frame[name].to_numpy(dtype=float) for name in MODEL_TERMS[model])])


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    safe = np.clip(p, 1e-15, 1 - 1e-15)
    return float(-np.mean(y * np.log(safe) + (1 - y) * np.log1p(-safe)))


def stable_logistic_mle(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fit the same unpenalized logit after rescaling training columns."""
    scales = np.ones(x.shape[1])
    scales[1:] = np.std(x[:, 1:], axis=0)
    assert np.isfinite(scales).all() and (scales > 0).all()
    scaled = x / scales

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        eta = scaled @ beta
        p = expit(eta)
        value = float(np.sum(np.logaddexp(0.0, eta) - y * eta))
        gradient = scaled.T @ (p - y)
        return value, gradient

    result = minimize(objective, np.zeros(x.shape[1]), jac=True,
                      method="L-BFGS-B", options={"maxiter": 10000, "ftol": 1e-14,
                                                   "gtol": 1e-9, "maxls": 100})
    gradient_max = float(np.max(np.abs(objective(result.x)[1])))
    if not result.success and gradient_max >= 1e-5:
        raise RuntimeError(f"logistic MLE did not converge: {result.message}; gradient={gradient_max}")
    beta = result.x / scales
    assert np.isfinite(beta).all()
    return beta


def fit_models(frame: pd.DataFrame) -> pd.DataFrame:
    y = frame.decoded_success.to_numpy(dtype=float)
    clusters, codes = np.unique(frame.trajectory_identity.to_numpy(), return_inverse=True)
    rows = []
    for model, terms in MODEL_TERMS.items():
        x = design(frame, model)
        assert np.linalg.matrix_rank(x) == x.shape[1]
        beta, inverse_information, ll, _ = fit_binomial(x, y, np.ones(len(frame)))
        p = expit(x @ beta)
        covariance = clustered_covariance(x, y, p, codes, len(clusters), inverse_information)
        robust_se = np.sqrt(np.diag(covariance))
        assert np.isfinite(beta).all() and np.isfinite(robust_se).all()
        names = ("intercept", *terms)
        rows.append({
            "model": model, "n_rows": len(frame), "n_parameters": len(names),
            "n_trajectory_clusters": len(clusters), "log_likelihood": ll,
            "AIC": -2 * ll + 2 * len(names),
            "BIC": -2 * ll + len(names) * np.log(len(frame)),
            "Brier_score": float(np.mean((y - p) ** 2)), "log_loss": float(-ll / len(frame)),
            "coefficients": json.dumps(dict(zip(names, map(float, beta)))),
            "trajectory_cluster_robust_SE": json.dumps(dict(zip(names, map(float, robust_se)))),
        })
    return pd.DataFrame(rows)


def leave_one_family_out(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    y = frame.decoded_success.to_numpy(dtype=float)
    predicted = {model: np.full(len(frame), np.nan) for model in MODEL_TERMS}
    logits = {model: np.full(len(frame), np.nan) for model in MODEL_TERMS}
    assigned = np.zeros(len(frame), dtype=int)
    rows = []
    for family in FAMILIES:
        test_mask = (frame.trajectory_family == family).to_numpy()
        train_mask = ~test_mask
        train, test = frame.loc[train_mask], frame.loc[test_mask]
        assert family not in set(train.trajectory_family)
        assert set(test.trajectory_family) == {family}
        assert set(train.trajectory_family) == set(FAMILIES) - {family}
        assert set(train.trajectory_identity).isdisjoint(set(test.trajectory_identity))
        assigned[test_mask] += 1
        for model in MODEL_TERMS:
            beta = stable_logistic_mle(design(train, model), y[train_mask])
            eta = design(test, model) @ beta
            p = expit(eta)
            predicted[model][test_mask] = p
            logits[model][test_mask] = eta
            rows.append({"held_out_family": family, "model": model,
                         "training_rows": len(train), "test_rows": len(test),
                         "brier_score": float(np.mean((y[test_mask] - p) ** 2)),
                         "log_loss": float(np.mean(np.logaddexp(0.0, eta) - y[test_mask] * eta))})
    assert np.all(assigned == 1)
    assert all(np.isfinite(values).all() for values in predicted.values())
    assert all(np.isfinite(values).all() for values in logits.values())
    out = frame.copy()
    for model, values in predicted.items():
        out[f"p_{model}"] = values
        out[f"brier_{model}"] = (y - values) ** 2
        out[f"log_loss_{model}"] = np.logaddexp(0.0, logits[model]) - y * logits[model]
    cv = pd.DataFrame(rows)
    assert len(cv) == len(FAMILIES) * len(MODEL_TERMS)
    assert cv.groupby("model").test_rows.sum().eq(len(frame)).all()
    return cv, out


def bootstrap(predictions: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, tuple[float, float, float, float]]]:
    frame = predictions.copy()
    frame["paired_difference"] = frame.brier_M_RMS - frame.brier_M_RMS_D1
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    replicate_rows = []
    results = {}
    for scope, selected in (("all", frame), ("random_walk", frame[frame.trajectory_family == "random_walk"])):
        clusters = selected.groupby("trajectory_identity").paired_difference.agg(["sum", "count"])
        assert len(clusters) == (810 if scope == "all" else 800)
        sums = clusters["sum"].to_numpy()
        counts = clusters["count"].to_numpy()
        for replicate in range(1, BOOTSTRAP_REPLICATES + 1):
            drawn = rng.integers(0, len(clusters), size=len(clusters))
            replicate_rows.append({"scope": scope, "replicate": replicate,
                                   "mean_brier_M_RMS_minus_M_RMS_D1":
                                   float(sums[drawn].sum() / counts[drawn].sum())})
        values = np.array([row["mean_brier_M_RMS_minus_M_RMS_D1"]
                           for row in replicate_rows[-BOOTSTRAP_REPLICATES:]])
        low, high = np.percentile(values, [2.5, 97.5])
        results[scope] = (float(selected.paired_difference.mean()),
                          float(low), float(high), float(np.mean(values > 0)))
    output = pd.DataFrame(replicate_rows)
    assert len(output) == BOOTSTRAP_REPLICATES * 2
    return output, results


def main() -> None:
    assert (SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT) == (375, 256, 162)
    if OUTPUT_DIR.exists():
        assert set(OUTPUT_DIR.iterdir()) == set(OUTPUTS.values()), "Refusing to overwrite unfamiliar output files"
    source_hashes = {path: checksum(path) for path in SOURCES}
    frame = unified_trials()
    family_summary, correlations = descriptor_audit(frame)
    model_comparison = fit_models(frame)
    cv, predictions = leave_one_family_out(frame)
    bootstrap_frame, bootstrap_results = bootstrap(predictions)
    assert all(checksum(path) == digest for path, digest in source_hashes.items())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUTS["trials"], index=False)
    family_summary.to_csv(OUTPUTS["family"], index=False)
    correlations.to_csv(OUTPUTS["correlation"])
    model_comparison.to_csv(OUTPUTS["models"], index=False)
    cv.to_csv(OUTPUTS["cv"], index=False)
    predictions.to_csv(OUTPUTS["predictions"], index=False)
    bootstrap_frame.to_csv(OUTPUTS["bootstrap"], index=False)
    assert len(pd.read_csv(OUTPUTS["trials"])) == 5400
    assert len(pd.read_csv(OUTPUTS["cv"])) == 36
    assert len(pd.read_csv(OUTPUTS["predictions"])) == 5400
    assert len(pd.read_csv(OUTPUTS["bootstrap"])) == 4000
    compact_models = model_comparison.drop(columns=["coefficients", "trajectory_cluster_robust_SE"])
    lines = [
        "DESCRIPTOR_AUDIT", family_summary.to_csv(index=False).strip(),
        "descriptor_correlation_matrix", correlations.to_csv().strip(),
        "MODEL_COMPARISON", compact_models.to_csv(index=False).strip(),
        "cluster_robust_coefficients_and_SE_saved_in=roughness_model_comparison.csv",
        "LEAVE_ONE_FAMILY_OUT", cv.to_csv(index=False).strip(),
        "RANDOM_WALK_HOLDOUT",
        cv[cv.held_out_family == "random_walk"].to_csv(index=False).strip(),
        "PAIRED_BRIER_IMPROVEMENT",
        f"all_mean={bootstrap_results['all'][0]:.12g} random_walk_mean={bootstrap_results['random_walk'][0]:.12g}",
        "BOOTSTRAP_RESULT",
        f"B={BOOTSTRAP_REPLICATES} rng_seed={BOOTSTRAP_SEED}",
        f"all_ci95=[{bootstrap_results['all'][1]:.12g},{bootstrap_results['all'][2]:.12g}] all_fraction_positive={bootstrap_results['all'][3]:.12g}",
        f"random_walk_ci95=[{bootstrap_results['random_walk'][1]:.12g},{bootstrap_results['random_walk'][2]:.12g}] random_walk_fraction_positive={bootstrap_results['random_walk'][3]:.12g}",
        "INTEGRITY_CHECK",
        "trial_rows=5400 families=6 trajectory_identities=810 all_trials_predicted_once=True train_test_family_leakage=False residual_projection_unchanged=True source_hashes_unchanged=True",
        "OUTPUT_PATHS", *(str(path) for path in OUTPUTS.values()),
    ]
    report = "\n".join(lines) + "\n"
    with OUTPUTS["report"].open("w", encoding="utf-8") as stream:
        stream.write(report)
    print(report, end="")


if __name__ == "__main__":
    main()
