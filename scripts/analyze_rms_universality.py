#!/usr/bin/env python3
"""Analysis-only RMS support, held-out calibration, and family-bias audit."""

from __future__ import annotations

import hashlib
from itertools import combinations
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/analysis/roughness_descriptor/roughness_trial_table.csv"
PRIOR_CV = ROOT / "results/analysis/roughness_descriptor/roughness_predictions.csv"
OUTPUT_DIR = ROOT / "results/analysis/rms_universality"
OUTPUTS = {
    "support": OUTPUT_DIR / "rms_support_by_family.csv",
    "predictions": OUTPUT_DIR / "rms_leave_one_family_predictions.csv",
    "performance": OUTPUT_DIR / "rms_leave_one_family_performance.csv",
    "calibration": OUTPUT_DIR / "rms_calibration.csv",
    "bias": OUTPUT_DIR / "rms_family_bias.csv",
    "bootstrap": OUTPUT_DIR / "rms_family_bias_bootstrap.csv",
    "family_effect": OUTPUT_DIR / "rms_family_effect_comparison.csv",
    "report": OUTPUT_DIR / "rms_universality_report.txt",
}
FAMILIES = (
    "quadratic_positive", "quadratic_negative", "thermal_tau30",
    "thermal_tau60", "thermal_tau120", "random_walk",
)
SNRS = (-30.0, -30.5, -31.0)
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 2026100900


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_trials() -> pd.DataFrame:
    frame = pd.read_csv(SOURCE)
    frame = frame.loc[frame.snr_db.isin(SNRS)].copy().reset_index(drop=True)
    assert len(frame) == 5400
    assert set(frame.trajectory_family) == set(FAMILIES)
    assert set(frame.snr_db) == set(SNRS)
    assert frame.decoded_success.isin((0, 1)).all()
    assert frame.trajectory_identity.nunique() == 810
    assert not frame[["trajectory_id", "snr_db", "seed"]].duplicated().any()
    assert np.isfinite(frame.frequency_rms_hz).all()
    assert (frame.frequency_rms_hz >= 0).all()
    return frame


def support_audit(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    ranges = {}
    for family in FAMILIES:
        values = frame.loc[frame.trajectory_family == family, "frequency_rms_hz"].to_numpy()
        low, high = float(values.min()), float(values.max())
        ranges[family] = (low, high)
        rows.append({"row_type": "family_support", "family_a": family, "family_b": "",
                     "n_trials": len(values), "min_frequency_rms_hz": low,
                     "p05_frequency_rms_hz": float(np.percentile(values, 5)),
                     "median_frequency_rms_hz": float(np.median(values)),
                     "p95_frequency_rms_hz": float(np.percentile(values, 95)),
                     "max_frequency_rms_hz": high,
                     "overlap_min_hz": np.nan, "overlap_max_hz": np.nan,
                     "overlap_width_hz": np.nan})
    for first, second in combinations(FAMILIES, 2):
        low = max(ranges[first][0], ranges[second][0])
        high = min(ranges[first][1], ranges[second][1])
        overlaps = low <= high
        rows.append({"row_type": "pairwise_overlap", "family_a": first,
                     "family_b": second, "n_trials": np.nan,
                     "min_frequency_rms_hz": np.nan, "p05_frequency_rms_hz": np.nan,
                     "median_frequency_rms_hz": np.nan, "p95_frequency_rms_hz": np.nan,
                     "max_frequency_rms_hz": np.nan,
                     "overlap_min_hz": low if overlaps else np.nan,
                     "overlap_max_hz": high if overlaps else np.nan,
                     "overlap_width_hz": high - low if overlaps else 0.0})
    output = pd.DataFrame(rows)
    assert len(output) == 6 + 15
    return output


def design(frame: pd.DataFrame, *, family_effect: bool = False) -> np.ndarray:
    columns = [np.ones(len(frame)), frame.snr_db.to_numpy(dtype=float) + 30.5,
               frame.frequency_rms_hz.to_numpy(dtype=float)]
    if family_effect:
        columns.extend((frame.trajectory_family == family).to_numpy(dtype=float)
                       for family in FAMILIES[1:])
    return np.column_stack(columns)


def mle(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Unpenalized logistic MLE with training-only column scaling."""
    assert np.linalg.matrix_rank(x) == x.shape[1]
    scales = np.ones(x.shape[1])
    scales[1:] = np.std(x[:, 1:], axis=0)
    assert np.isfinite(scales).all() and (scales > 0).all()
    scaled = x / scales

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        eta = scaled @ beta
        value = float(np.sum(np.logaddexp(0.0, eta) - y * eta))
        gradient = scaled.T @ (expit(eta) - y)
        return value, gradient

    fitted = minimize(objective, np.zeros(x.shape[1]), jac=True,
                      method="L-BFGS-B", options={"maxiter": 10000, "ftol": 1e-14,
                                                   "gtol": 1e-9, "maxls": 100})
    gradient = float(np.max(np.abs(objective(fitted.x)[1])))
    if not fitted.success and gradient >= 1e-5:
        raise RuntimeError(f"RMS logistic MLE failed: {fitted.message}; gradient={gradient}")
    beta = fitted.x / scales
    assert np.isfinite(beta).all()
    return beta


def holdout_predictions(frame: pd.DataFrame) -> pd.DataFrame:
    predicted = np.full(len(frame), np.nan)
    logits = np.full(len(frame), np.nan)
    inside = np.zeros(len(frame), dtype=bool)
    support_min = np.full(len(frame), np.nan)
    support_max = np.full(len(frame), np.nan)
    assignments = np.zeros(len(frame), dtype=int)
    for family in FAMILIES:
        test_mask = (frame.trajectory_family == family).to_numpy()
        train = frame.loc[~test_mask]
        test = frame.loc[test_mask]
        assert family not in set(train.trajectory_family)
        assert set(test.trajectory_family) == {family}
        assert set(train.trajectory_identity).isdisjoint(set(test.trajectory_identity))
        low, high = float(train.frequency_rms_hz.min()), float(train.frequency_rms_hz.max())
        beta = mle(design(train), train.decoded_success.to_numpy(dtype=float))
        eta = design(test) @ beta
        p = expit(eta)
        observed_rms = test.frequency_rms_hz.to_numpy(dtype=float)
        predicted[test_mask] = p
        logits[test_mask] = eta
        inside[test_mask] = (observed_rms >= low) & (observed_rms <= high)
        support_min[test_mask] = low
        support_max[test_mask] = high
        assignments[test_mask] += 1
    assert np.all(assignments == 1)
    assert np.isfinite(predicted).all() and np.isfinite(logits).all()
    output = frame[["trajectory_family", "trajectory_id", "trajectory_identity",
                    "snr_db", "seed", "trajectory_seed", "noise_seed", "trial_index",
                    "frequency_rms_hz", "decoded_success"]].copy()
    output["predicted_probability"] = predicted
    output["inside_training_rms_support"] = inside
    output["training_rms_min_hz"] = support_min
    output["training_rms_max_hz"] = support_max
    output["support_region"] = np.where(inside, "inside",
                                        np.where(output.frequency_rms_hz < support_min, "below", "above"))
    y = output.decoded_success.to_numpy(dtype=float)
    output["brier_loss"] = (y - predicted) ** 2
    output["log_loss"] = np.logaddexp(0.0, logits) - y * logits
    output["residual_bias"] = y - predicted
    assert np.isfinite(output[["brier_loss", "log_loss", "residual_bias"]]).all().all()
    assert (output.inside_training_rms_support == (output.support_region == "inside")).all()
    return output


def performance(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for family in FAMILIES:
        selected = predictions[predictions.trajectory_family == family]
        for scope, subset in (
            ("all", selected),
            ("interpolation", selected[selected.inside_training_rms_support]),
            ("extrapolation", selected[~selected.inside_training_rms_support]),
        ):
            rows.append({"trajectory_family": family, "scope": scope,
                         "n_rows": len(subset),
                         "brier_score": float(subset.brier_loss.mean()) if len(subset) else np.nan,
                         "log_loss": float(subset.log_loss.mean()) if len(subset) else np.nan,
                         "below_support_rows": int((subset.support_region == "below").sum()),
                         "above_support_rows": int((subset.support_region == "above").sum())})
    output = pd.DataFrame(rows)
    assert len(output) == 18
    for family in FAMILIES:
        selected = output[output.trajectory_family == family].set_index("scope")
        assert selected.loc["all", "n_rows"] == (
            selected.loc["interpolation", "n_rows"] + selected.loc["extrapolation", "n_rows"]
        )
    return output


def calibration_fit(y: np.ndarray, p: np.ndarray) -> tuple[float, float, str]:
    if len(np.unique(y)) < 2 or len(np.unique(p)) < 2:
        return np.nan, np.nan, "unavailable_single_outcome_or_prediction"
    z = logit(np.clip(p, 1e-15, 1 - 1e-15))
    x = np.column_stack((np.ones(len(p)), z))
    try:
        beta = mle(x, y)
        if np.max(np.abs(beta)) >= 30:
            return np.nan, np.nan, "unavailable_boundary_fit"
        return float(beta[0]), float(beta[1]), "fitted"
    except (AssertionError, RuntimeError, ValueError, np.linalg.LinAlgError) as error:
        return np.nan, np.nan, f"unavailable_{type(error).__name__}"


def calibration(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for family in FAMILIES:
        family_rows = predictions[predictions.trajectory_family == family]
        for snr, selected in ((np.nan, family_rows),
                              *((float(value), family_rows[family_rows.snr_db == value]) for value in SNRS)):
            y = selected.decoded_success.to_numpy(dtype=float)
            p = selected.predicted_probability.to_numpy(dtype=float)
            intercept, slope, status = calibration_fit(y, p)
            common = {"trajectory_family": family, "snr_db": snr}
            rows.append({**common, "row_type": "summary", "bin_index": np.nan,
                         "n_rows": len(selected), "mean_predicted_probability": float(np.mean(p)),
                         "observed_decode_rate": float(np.mean(y)),
                         "calibration_intercept": intercept, "calibration_slope": slope,
                         "calibration_fit_status": status})
            q = min(5, len(np.unique(p)))
            while q > 1:
                labels = pd.qcut(selected.predicted_probability, q=q,
                                 labels=False, duplicates="drop")
                sizes = labels.value_counts()
                if len(sizes) > 0 and sizes.min() >= 20:
                    break
                q -= 1
            if q == 1:
                labels = pd.Series(np.zeros(len(selected), dtype=int), index=selected.index)
            for bin_index, subset in selected.groupby(labels, sort=True):
                assert len(subset) >= 20
                rows.append({**common, "row_type": "bin", "bin_index": int(bin_index) + 1,
                             "n_rows": len(subset),
                             "mean_predicted_probability": float(subset.predicted_probability.mean()),
                             "observed_decode_rate": float(subset.decoded_success.mean()),
                             "calibration_intercept": np.nan, "calibration_slope": np.nan,
                             "calibration_fit_status": ""})
    output = pd.DataFrame(rows)
    assert len(output[output.row_type == "summary"]) == 24
    for family in FAMILIES:
        selected = output[(output.trajectory_family == family) & (output.row_type == "bin")]
        assert selected[selected.snr_db.isna()].n_rows.sum() == len(predictions[predictions.trajectory_family == family])
        for snr in SNRS:
            assert selected[selected.snr_db == snr].n_rows.sum() == len(
                predictions[(predictions.trajectory_family == family) & (predictions.snr_db == snr)]
            )
    return output


def family_bias(predictions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    summary_rows = []
    bootstrap_rows = []
    for family in FAMILIES:
        for snr in SNRS:
            selected = predictions[(predictions.trajectory_family == family) &
                                   (predictions.snr_db == snr)]
            clusters = selected.groupby("trajectory_identity").residual_bias.agg(["sum", "count"])
            assert len(clusters) == (800 if family == "random_walk" else 2)
            sums = clusters["sum"].to_numpy(dtype=float)
            counts = clusters["count"].to_numpy(dtype=int)
            replicates = np.empty(BOOTSTRAP_REPLICATES)
            for index in range(BOOTSTRAP_REPLICATES):
                drawn = rng.integers(0, len(clusters), size=len(clusters))
                value = float(sums[drawn].sum() / counts[drawn].sum())
                replicates[index] = value
                bootstrap_rows.append({"trajectory_family": family, "snr_db": snr,
                                       "replicate": index + 1, "mean_residual_bias": value})
            low, high = np.percentile(replicates, [2.5, 97.5])
            summary_rows.append({"trajectory_family": family, "snr_db": snr,
                                 "n_rows": len(selected), "n_trajectory_clusters": len(clusters),
                                 "mean_residual_bias": float(selected.residual_bias.mean()),
                                 "bootstrap95_low": float(low), "bootstrap95_high": float(high)})
    summary = pd.DataFrame(summary_rows)
    bootstrap = pd.DataFrame(bootstrap_rows)
    assert len(summary) == 18 and len(bootstrap) == 18 * BOOTSTRAP_REPLICATES
    return summary, bootstrap


def family_effect_diagnostic(frame: pd.DataFrame) -> pd.DataFrame:
    y = frame.decoded_success.to_numpy(dtype=float)
    rows = []
    for name, include_family in (("M_RMS", False), ("M_RMS_family", True)):
        x = design(frame, family_effect=include_family)
        beta = mle(x, y)
        eta = x @ beta
        p = expit(eta)
        ll = float(np.sum(y * eta - np.logaddexp(0.0, eta)))
        k = x.shape[1]
        rows.append({"model": name, "diagnostic_only": include_family,
                     "n_rows": len(frame), "n_parameters": k,
                     "log_likelihood": ll, "AIC": -2 * ll + 2 * k,
                     "BIC": -2 * ll + k * np.log(len(frame)),
                     "Brier_score": float(np.mean((y - p) ** 2))})
    return pd.DataFrame(rows)


def main() -> None:
    assert not OUTPUT_DIR.exists(), f"Refusing to overwrite {OUTPUT_DIR}"
    original_hashes = {path: checksum(path) for path in (SOURCE, PRIOR_CV)}
    frame = load_trials()
    support = support_audit(frame)
    predictions = holdout_predictions(frame)
    previous = pd.read_csv(PRIOR_CV)
    assert len(previous) == len(predictions)
    keyed = predictions[["trajectory_id", "snr_db", "seed", "predicted_probability"]].merge(
        previous[["trajectory_id", "snr_db", "seed", "p_M_RMS"]],
        on=["trajectory_id", "snr_db", "seed"], validate="one_to_one")
    assert len(keyed) == len(predictions)
    assert np.allclose(keyed.predicted_probability, keyed.p_M_RMS, rtol=0, atol=1e-8)
    scores = performance(predictions)
    calibration_table = calibration(predictions)
    bias, bootstrap = family_bias(predictions)
    effect = family_effect_diagnostic(frame)
    assert all(checksum(path) == value for path, value in original_hashes.items())
    OUTPUT_DIR.mkdir(parents=True)
    support.to_csv(OUTPUTS["support"], index=False, mode="x")
    predictions.to_csv(OUTPUTS["predictions"], index=False, mode="x")
    scores.to_csv(OUTPUTS["performance"], index=False, mode="x")
    calibration_table.to_csv(OUTPUTS["calibration"], index=False, mode="x")
    bias.to_csv(OUTPUTS["bias"], index=False, mode="x")
    bootstrap.to_csv(OUTPUTS["bootstrap"], index=False, mode="x")
    effect.to_csv(OUTPUTS["family_effect"], index=False, mode="x")
    expected_rows = {"support": 21, "predictions": 5400, "performance": 18,
                     "bias": 18, "bootstrap": 36000, "family_effect": 2}
    for name, count in expected_rows.items():
        assert len(pd.read_csv(OUTPUTS[name])) == count
    summary_calibration = calibration_table[calibration_table.row_type == "summary"]
    lines = [
        "RMS_SUPPORT", support.to_csv(index=False).strip(),
        "LEAVE_ONE_FAMILY_OUT", scores[scores.scope == "all"].to_csv(index=False).strip(),
        "INTERPOLATION_VS_EXTRAPOLATION", scores.to_csv(index=False).strip(),
        "CALIBRATION", summary_calibration.to_csv(index=False).strip(),
        "probability_bin_rows_saved_in=rms_calibration.csv",
        "FAMILY_BIAS", bias.to_csv(index=False).strip(),
        "FAMILY_EFFECT_DIAGNOSTIC", effect.to_csv(index=False).strip(),
        "INTEGRITY_CHECK",
        "source_rows=5400 families=6 trajectory_identities=810 heldout_predictions=5400 predicted_once=True no_family_leakage=True prior_M_RMS_predictions_match=True source_hashes_unchanged=True",
        "OUTPUT_PATHS", *(str(path) for path in OUTPUTS.values()),
    ]
    report = "\n".join(lines) + "\n"
    with OUTPUTS["report"].open("x", encoding="utf-8") as stream:
        stream.write(report)
    print(report, end="")


if __name__ == "__main__":
    main()
