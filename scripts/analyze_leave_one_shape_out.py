"""Leave-one-trajectory-family-out prediction from existing decoder outcomes only."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import expit, logit

from analyze_interaction_model import fit_binomial


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "results/analysis/residual_descriptor_analysis"
TRIAL_PATH = INPUT_DIR / "descriptor_joined_trials.csv"
DESCRIPTOR_PATH = INPUT_DIR / "trajectory_descriptors.csv"
OUTPUT_DIR = ROOT / "results/analysis/leave_one_shape_out"
FAMILIES = (
    "quadratic_positive", "quadratic_negative", "thermal_tau30",
    "thermal_tau60", "thermal_tau120",
)
SNRS = {-30.0, -30.5, -31.0}
MODELS = {
    "amp": ("snr_c", "max_abs_frequency_hz"),
    "phase": ("snr_c", "max_abs_frequency_hz", "max_abs_phase_rad"),
    "rms": ("snr_c", "max_abs_frequency_hz", "frequency_rms_hz"),
}
BOOTSTRAP_REPLICATES = 2000
BOOTSTRAP_SEED = 2026100300


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def family_for(row: pd.Series) -> str:
    if row["family"] == "quadratic":
        return "quadratic_positive" if float(row["signed_A_res_hz"]) > 0 else "quadratic_negative"
    if row["family"] == "thermal":
        return f"thermal_tau{int(row['tau_seconds'])}"
    raise ValueError(f"Unexpected trajectory source family: {row['family']}")


def design(frame: pd.DataFrame, model: str) -> np.ndarray:
    columns = [np.ones(len(frame))]
    columns.extend(frame[column].to_numpy(dtype=float) for column in MODELS[model])
    return np.column_stack(columns)


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    safe = np.clip(p, 1e-15, 1 - 1e-15)
    return float(-np.mean(y * np.log(safe) + (1 - y) * np.log1p(-safe)))


def calibration(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    safe = np.clip(p, 1e-15, 1 - 1e-15)
    x = np.column_stack((np.ones(len(y)), logit(safe)))
    try:
        beta, _, _, _ = fit_binomial(x, y, np.ones(len(y)))
        return float(beta[0]), float(beta[1])
    except (RuntimeError, np.linalg.LinAlgError, FloatingPointError):
        return np.nan, np.nan


def main() -> None:
    assert not OUTPUT_DIR.exists(), f"Refusing to overwrite {OUTPUT_DIR}"
    input_hashes = {path: sha256(path) for path in (TRIAL_PATH, DESCRIPTOR_PATH)}
    trials = pd.read_csv(TRIAL_PATH)
    descriptors = pd.read_csv(DESCRIPTOR_PATH)
    assert descriptors["trajectory_id"].is_unique
    assert len(descriptors) == 10
    trials = trials.loc[trials["snr_db"].isin(SNRS)].copy().reset_index(drop=True)
    assert len(trials) == 3000
    assert set(trials["snr_db"]) == SNRS
    assert trials["decoded_success"].isin((0, 1)).all()
    assert trials[["trajectory_id", "snr_db", "seed"]].duplicated().sum() == 0
    trials["trajectory_family"] = trials.apply(family_for, axis=1)
    assert set(trials["trajectory_family"]) == set(FAMILIES)
    assert trials.groupby("trajectory_family").size().eq(600).all()
    descriptor_columns = ("max_abs_frequency_hz", "frequency_rms_hz", "max_abs_phase_rad")
    joined = trials.merge(
        descriptors[["trajectory_id", *descriptor_columns]],
        on="trajectory_id", how="left", validate="many_to_one", suffixes=("", "_descriptor"),
    )
    assert len(joined) == len(trials)
    for column in descriptor_columns:
        assert np.allclose(joined[column], joined[f"{column}_descriptor"], rtol=0, atol=1e-12)
        del joined[f"{column}_descriptor"]
    assert joined[list(descriptor_columns)].notna().all().all()
    joined["snr_c"] = joined["snr_db"] + 30.5
    joined["cluster_id"] = (
        joined["family"].astype(str) + "|" + joined["trajectory_family"] + "|"
        + joined["snr_db"].map(lambda value: f"{value:.1f}") + "|"
        + joined["seed"].astype(str)
    )
    assert joined.groupby("cluster_id").size().eq(2).all()
    y = joined["decoded_success"].to_numpy(dtype=float)
    predictions = {model: np.full(len(joined), np.nan) for model in MODELS}
    assignment_count = np.zeros(len(joined), dtype=int)
    by_family_rows = []

    for family in FAMILIES:
        test_mask = (joined["trajectory_family"] == family).to_numpy()
        train_mask = ~test_mask
        train, test = joined.loc[train_mask], joined.loc[test_mask]
        assert family not in set(train["trajectory_family"])
        assert set(train["trajectory_family"]) == set(FAMILIES) - {family}
        assert set(test["trajectory_family"]) == {family}
        assert len(train) == 2400 and len(test) == 600
        assert not set(train.index).intersection(test.index)
        assignment_count[test_mask] += 1
        row = {"trajectory_family": family, "training_rows": len(train), "test_rows": len(test)}
        y_test = y[test_mask]
        for model in MODELS:
            beta, _, _, _ = fit_binomial(
                design(train, model), y[train_mask], np.ones(len(train))
            )
            p = expit(design(test, model) @ beta)
            predictions[model][test_mask] = p
            row[f"brier_{model}"] = float(np.mean((y_test - p) ** 2))
            row[f"log_loss_{model}"] = log_loss(y_test, p)
            intercept, slope = calibration(y_test, p)
            row[f"calibration_intercept_{model}"] = intercept
            row[f"calibration_slope_{model}"] = slope
        by_family_rows.append(row)

    assert np.all(assignment_count == 1)
    assert all(np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all() for p in predictions.values())
    for model, p in predictions.items():
        joined[f"p_{model}"] = p
        joined[f"brier_{model}"] = (y - p) ** 2

    overall_rows = [
        {"model": model.upper(), "test_rows": len(joined),
         "brier_score": float(joined[f"brier_{model}"].mean()),
         "log_loss": log_loss(y, predictions[model])}
        for model in MODELS
    ]
    joined["paired_brier_difference"] = joined["brier_amp"] - joined["brier_phase"]
    paired_mean = float(joined["paired_brier_difference"].mean())
    clusters = joined.groupby("cluster_id", sort=True)["paired_brier_difference"].agg(["sum", "count"])
    assert int(clusters["count"].sum()) == 3000
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    sums = clusters["sum"].to_numpy()
    counts = clusters["count"].to_numpy()
    bootstrap_rows = []
    for replicate in range(1, BOOTSTRAP_REPLICATES + 1):
        selected = rng.integers(0, len(clusters), size=len(clusters))
        bootstrap_rows.append({
            "replicate": replicate,
            "mean_brier_amp_minus_phase": float(sums[selected].sum() / counts[selected].sum()),
        })
    bootstrap = pd.DataFrame(bootstrap_rows)
    low, high = np.percentile(bootstrap["mean_brier_amp_minus_phase"], [2.5, 97.5])
    positive_fraction = float((bootstrap["mean_brier_amp_minus_phase"] > 0).mean())
    by_family = pd.DataFrame(by_family_rows)
    overall = pd.DataFrame(overall_rows)

    assert len(by_family) == 5 and by_family["test_rows"].sum() == 3000
    assert len(overall) == 3 and overall["test_rows"].eq(3000).all()
    assert len(bootstrap) == BOOTSTRAP_REPLICATES
    assert all(sha256(path) == original for path, original in input_hashes.items())

    OUTPUT_DIR.mkdir(parents=True)
    paths = {
        "predictions": OUTPUT_DIR / "leave_one_shape_out_predictions.csv",
        "by_family": OUTPUT_DIR / "leave_one_shape_out_by_family.csv",
        "overall": OUTPUT_DIR / "leave_one_shape_out_overall.csv",
        "bootstrap": OUTPUT_DIR / "leave_one_shape_out_bootstrap.csv",
        "report": OUTPUT_DIR / "leave_one_shape_out_report.txt",
    }
    prediction_columns = [
        "trajectory_family", "family", "trajectory_id", "snr_db", "seed", "trial_index",
        "cluster_id", "decoded_success", *descriptor_columns,
        "p_amp", "p_phase", "p_rms", "brier_amp", "brier_phase", "brier_rms",
    ]
    joined[prediction_columns].to_csv(paths["predictions"], index=False, mode="x")
    by_family.to_csv(paths["by_family"], index=False, mode="x")
    overall.to_csv(paths["overall"], index=False, mode="x")
    bootstrap.to_csv(paths["bootstrap"], index=False, mode="x")
    report = "\n".join([
        "CV_BY_FAMILY", by_family.to_string(index=False),
        "CV_OVERALL", overall.to_string(index=False),
        "PAIRED_BRIER_DIFFERENCE", f"mean_loss_amp_minus_phase={paired_mean:.12g}",
        "BOOTSTRAP_RESULT",
        f"B={BOOTSTRAP_REPLICATES} rng_seed={BOOTSTRAP_SEED} clusters={len(clusters)}",
        f"ci95_low={low:.12g} ci95_high={high:.12g} fraction_positive={positive_fraction:.12g}",
        "INTEGRITY_CHECK",
        f"input_rows=3000 predicted_once=3000 family_holdouts=5 clusters={len(clusters)} input_hashes_unchanged=True",
        "OUTPUT_PATHS", *(str(path) for path in paths.values()),
    ]) + "\n"
    with paths["report"].open("x", encoding="utf-8") as stream:
        stream.write(report)
    print(report, end="")


if __name__ == "__main__":
    main()
