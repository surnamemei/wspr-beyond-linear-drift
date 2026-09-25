#!/usr/bin/env python3
"""Analyze existing WSPR interaction trials; never invokes the decoder."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import chi2, norm


ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "linear_drift_boundary": ROOT / "results/csv/linear_drift_boundary/linear_drift_boundary_trials.csv",
    "quadratic_residual_pilot": ROOT / "results/csv/quadratic_residual_pilot/quadratic_residual_pilot_trials.csv",
    "linear_quadratic_interaction": ROOT / "results/csv/linear_quadratic_interaction/linear_quadratic_interaction_trials.csv",
}
OUTPUT = ROOT / "results/analysis/interaction_model"
FILES = {
    "combined": OUTPUT / "interaction_combined_trials.csv",
    "coefficients": OUTPUT / "interaction_model_coefficients.csv",
    "comparison": OUTPUT / "interaction_model_comparison.csv",
    "bootstrap": OUTPUT / "interaction_bootstrap_bDA.csv",
    "diagnostic": OUTPUT / "interaction_observed_vs_predicted.csv",
    "report": OUTPUT / "interaction_analysis_report.txt",
}
COMMON_SNRS = (-29.5, -30.0, -30.5, -31.0)
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = 2026092900
TERMS = {
    "M0": ("intercept", "snr_c", "abs_linear_drift_hz", "A_res_hz"),
    "M1": ("intercept", "snr_c", "abs_linear_drift_hz", "A_res_hz", "D_times_A"),
    "M2": (
        "intercept", "snr_c", "abs_linear_drift_hz", "A_res_hz", "D_times_A",
        "snr_c_times_D", "snr_c_times_A",
    ),
}


def load_sources() -> tuple[pd.DataFrame, list[dict[str, object]]]:
    frames = []
    audits = []
    for source, path in SOURCES.items():
        frame = pd.read_csv(path)
        required = {"snr_db", "seed", "decoded_success"}
        if source == "linear_drift_boundary":
            required.add("drift_hz")
        else:
            required.add("A_res_hz")
        if source == "linear_quadratic_interaction":
            required.add("linear_drift_hz")
        assert required <= set(frame.columns), (source, sorted(required - set(frame.columns)))
        invalid_success = int((~frame["decoded_success"].isin((0, 1))).sum())
        audit = {
            "source_dataset": source,
            "row_count": len(frame),
            "columns": list(frame.columns),
            "unique_snr_db": sorted(frame["snr_db"].dropna().unique().tolist()),
            "unique_drift_hz": sorted(
                (frame["drift_hz"] if source == "linear_drift_boundary"
                 else frame["linear_drift_hz"] if source == "linear_quadratic_interaction"
                 else pd.Series([0.0])).dropna().unique().tolist()
            ),
            "unique_A_res_hz": sorted(
                (frame["A_res_hz"] if source != "linear_drift_boundary"
                 else pd.Series([0.0])).dropna().unique().tolist()
            ),
            "unique_seed_count": int(frame["seed"].nunique(dropna=True)),
            "seed_min": int(frame["seed"].min()),
            "seed_max": int(frame["seed"].max()),
            "seeds_by_snr": {
                f"{snr:g}": {
                    "count": int(group["seed"].nunique()),
                    "min": int(group["seed"].min()),
                    "max": int(group["seed"].max()),
                }
                for snr, group in frame.groupby("snr_db", sort=True)
            },
            "duplicate_rows": int(frame.duplicated().sum()),
            "missing_values_by_column": {key: int(value) for key, value in frame.isna().sum().items()},
            "invalid_decoded_success": invalid_success,
        }
        audits.append(audit)
        if invalid_success:
            raise ValueError(f"invalid decoded_success in {source}: {invalid_success}")
        for column in ("snr_db", "seed", "decoded_success"):
            if frame[column].isna().any():
                raise ValueError(f"missing {column} in {source}")
        if source == "linear_drift_boundary":
            drift = frame["drift_hz"].abs()
            amplitude = pd.Series(0.0, index=frame.index)
        elif source == "quadratic_residual_pilot":
            drift = pd.Series(0.0, index=frame.index)
            amplitude = frame["A_res_hz"]
        else:
            drift = frame["linear_drift_hz"].abs()
            amplitude = frame["A_res_hz"]
        combined = pd.DataFrame({
            "source_dataset": source,
            "snr_db": frame["snr_db"].astype(float),
            "abs_linear_drift_hz": drift.astype(float),
            "A_res_hz": amplitude.astype(float),
            "decoded_success": frame["decoded_success"].astype(int),
            "seed": frame["seed"].astype(int),
            "trial_index": frame["trial_index"].astype(int),
        })
        if combined[["snr_db", "abs_linear_drift_hz", "A_res_hz"]].isna().any().any():
            raise ValueError(f"missing model predictor in {source}")
        combined["cluster_id"] = (
            combined["source_dataset"] + "|" + combined["snr_db"].map(lambda x: f"{x:g}")
            + "|" + combined["seed"].astype(str)
        )
        combined["snr_c"] = combined["snr_db"] + 30.25
        combined["in_primary_support"] = combined["snr_db"].isin(COMMON_SNRS)
        frames.append(combined)
    return pd.concat(frames, ignore_index=True), audits


def design(frame: pd.DataFrame, model: str) -> np.ndarray:
    snr = frame["snr_c"].to_numpy(dtype=float)
    drift = frame["abs_linear_drift_hz"].to_numpy(dtype=float)
    amplitude = frame["A_res_hz"].to_numpy(dtype=float)
    columns = [np.ones(len(frame)), snr, drift, amplitude]
    if model in ("M1", "M2"):
        columns.append(drift * amplitude)
    if model == "M2":
        columns.extend((snr * drift, snr * amplitude))
    return np.column_stack(columns)


def log_likelihood(beta: np.ndarray, x: np.ndarray, successes: np.ndarray,
                   totals: np.ndarray) -> float:
    eta = x @ beta
    return float(np.sum(successes * eta - totals * np.logaddexp(0.0, eta)))


def fit_binomial(x: np.ndarray, successes: np.ndarray, totals: np.ndarray,
                 initial: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, float, int]:
    """Newton MLE for independent Bernoulli rows or grouped binomial counts."""
    beta = np.zeros(x.shape[1]) if initial is None else initial.copy()
    for iteration in range(1, 101):
        p = expit(x @ beta)
        gradient = x.T @ (successes - totals * p)
        information = x.T @ ((totals * p * (1.0 - p))[:, None] * x)
        try:
            step = np.linalg.solve(information, gradient)
        except np.linalg.LinAlgError as error:
            raise RuntimeError("singular information matrix") from error
        current_ll = log_likelihood(beta, x, successes, totals)
        fraction = 1.0
        while fraction >= 2.0 ** -30:
            candidate = beta + fraction * step
            if np.max(np.abs(candidate)) < 100 and log_likelihood(candidate, x, successes, totals) >= current_ll - 1e-9:
                break
            fraction *= 0.5
        if fraction < 2.0 ** -30:
            raise RuntimeError("line search failed")
        beta = candidate
        if np.max(np.abs(fraction * step)) < 1e-10:
            break
    else:
        raise RuntimeError("maximum iterations reached")
    p = expit(x @ beta)
    information = x.T @ ((totals * p * (1.0 - p))[:, None] * x)
    inverse_information = np.linalg.inv(information)
    if not np.all(np.isfinite(beta)) or not np.all(np.isfinite(inverse_information)):
        raise RuntimeError("nonfinite fit")
    return beta, inverse_information, log_likelihood(beta, x, successes, totals), iteration


def clustered_covariance(x: np.ndarray, outcome: np.ndarray, probability: np.ndarray,
                         cluster_codes: np.ndarray, n_clusters: int,
                         inverse_information: np.ndarray) -> np.ndarray:
    scores = np.zeros((n_clusters, x.shape[1]))
    np.add.at(scores, cluster_codes, x * (outcome - probability)[:, None])
    correction = (n_clusters / (n_clusters - 1)) * ((len(outcome) - 1) / (len(outcome) - x.shape[1]))
    return correction * inverse_information @ (scores.T @ scores) @ inverse_information


def bootstrap_interaction(primary: pd.DataFrame, original_beta: np.ndarray,
                          cell_frame: pd.DataFrame) -> pd.DataFrame:
    clusters, cluster_codes = np.unique(primary["cluster_id"].to_numpy(), return_inverse=True)
    cells = pd.MultiIndex.from_frame(cell_frame[["snr_db", "abs_linear_drift_hz", "A_res_hz"]])
    row_cells = pd.MultiIndex.from_frame(primary[["snr_db", "abs_linear_drift_hz", "A_res_hz"]])
    cell_codes = cells.get_indexer(row_cells)
    assert np.all(cell_codes >= 0)
    counts = np.zeros((len(clusters), len(cells)), dtype=np.int32)
    successes = np.zeros_like(counts)
    np.add.at(counts, (cluster_codes, cell_codes), 1)
    np.add.at(successes, (cluster_codes, cell_codes), primary["decoded_success"].to_numpy(dtype=np.int32))
    x = design(cell_frame.assign(snr_c=cell_frame["snr_db"] + 30.25), "M1")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    records = []
    for index in range(BOOTSTRAP_REPLICATES):
        drawn = rng.integers(0, len(clusters), size=len(clusters))
        multiplicity = np.bincount(drawn, minlength=len(clusters))
        total = multiplicity @ counts
        success = multiplicity @ successes
        mask = total > 0
        try:
            beta, _, _, iterations = fit_binomial(
                x[mask], success[mask], total[mask], initial=original_beta
            )
            records.append({"replicate": index + 1, "bDA": beta[4], "status": "success", "iterations": iterations, "error": ""})
        except (RuntimeError, np.linalg.LinAlgError, FloatingPointError) as error:
            records.append({"replicate": index + 1, "bDA": np.nan, "status": "failed", "iterations": "", "error": str(error)})
    return pd.DataFrame(records)


def main() -> int:
    combined, audits = load_sources()
    primary = combined.loc[combined["in_primary_support"]].copy()
    assert sorted(primary["snr_db"].unique().tolist()) == list(sorted(COMMON_SNRS))
    assert primary["decoded_success"].isin((0, 1)).all()
    outcome = primary["decoded_success"].to_numpy(dtype=float)
    n_rows = len(primary)
    clusters, cluster_codes = np.unique(primary["cluster_id"].to_numpy(), return_inverse=True)
    model_results = {}
    coefficient_rows = []
    predictions = {}
    for model in ("M0", "M1", "M2"):
        x = design(primary, model)
        beta, inverse_info, ll, iterations = fit_binomial(x, outcome, np.ones(n_rows))
        predicted = expit(x @ beta)
        predictions[model] = predicted
        ordinary_se = np.sqrt(np.diag(inverse_info))
        robust_cov = clustered_covariance(x, outcome, predicted, cluster_codes, len(clusters), inverse_info)
        robust_se = np.sqrt(np.diag(robust_cov))
        brier = float(np.mean((outcome - predicted) ** 2))
        k = len(beta)
        model_results[model] = {
            "beta": beta, "ll": ll, "n_rows": n_rows, "n_parameters": k,
            "aic": -2 * ll + 2 * k, "bic": -2 * ll + k * np.log(n_rows),
            "brier": brier, "iterations": iterations,
        }
        for index, term in enumerate(TERMS[model]):
            z = beta[index] / ordinary_se[index]
            robust_z = beta[index] / robust_se[index]
            coefficient_rows.append({
                "model": model, "term": term, "coefficient": beta[index],
                "ordinary_se": ordinary_se[index], "ordinary_z": z,
                "ordinary_p": 2 * norm.sf(abs(z)),
                "cluster_robust_se": robust_se[index], "cluster_robust_z": robust_z,
                "cluster_robust_p": 2 * norm.sf(abs(robust_z)),
                "n_clusters": len(clusters),
            })
    coefficients = pd.DataFrame(coefficient_rows)
    comparison_rows = []
    for model in ("M0", "M1", "M2"):
        result = model_results[model]
        comparison_rows.append({
            "row_type": "model", "comparison": model, "n_rows": n_rows,
            "n_parameters": result["n_parameters"], "log_likelihood": result["ll"],
            "AIC": result["aic"], "BIC": result["bic"],
            "LR_statistic": np.nan, "LR_df": np.nan, "LR_p": np.nan,
            "method": "ordinary binomial logit maximum likelihood",
        })
    for smaller, larger in (("M0", "M1"), ("M1", "M2")):
        df = model_results[larger]["n_parameters"] - model_results[smaller]["n_parameters"]
        statistic = max(0.0, 2 * (model_results[larger]["ll"] - model_results[smaller]["ll"]))
        comparison_rows.append({
            "row_type": "likelihood_ratio", "comparison": f"{smaller} vs {larger}",
            "n_rows": n_rows, "n_parameters": np.nan, "log_likelihood": np.nan,
            "AIC": np.nan, "BIC": np.nan, "LR_statistic": statistic,
            "LR_df": df, "LR_p": chi2.sf(statistic, df),
            "method": "ordinary likelihood; matched-seed dependence not accounted for",
        })
    comparison = pd.DataFrame(comparison_rows)
    keys = ["snr_db", "abs_linear_drift_hz", "A_res_hz"]
    diagnostic_source = primary[keys + ["decoded_success"]].copy()
    for model in ("M0", "M1", "M2"):
        diagnostic_source[f"{model}_predicted_p"] = predictions[model]
    diagnostic = diagnostic_source.groupby(keys, as_index=False).agg(
        n=("decoded_success", "size"),
        observed_p_decode=("decoded_success", "mean"),
        M0_predicted_p=("M0_predicted_p", "mean"),
        M1_predicted_p=("M1_predicted_p", "mean"),
        M2_predicted_p=("M2_predicted_p", "mean"),
    )
    bootstrap = bootstrap_interaction(primary, model_results["M1"]["beta"], diagnostic[keys])
    valid_bda = bootstrap.loc[bootstrap["status"] == "success", "bDA"].to_numpy(dtype=float)
    if len(valid_bda) == 0:
        raise RuntimeError("no successful bootstrap fits")
    bootstrap_stats = {
        "B": BOOTSTRAP_REPLICATES,
        "rng_seed": BOOTSTRAP_SEED,
        "successful": len(valid_bda),
        "failed": BOOTSTRAP_REPLICATES - len(valid_bda),
        "median_bDA": float(np.median(valid_bda)),
        "percentile_2_5": float(np.percentile(valid_bda, 2.5)),
        "percentile_97_5": float(np.percentile(valid_bda, 97.5)),
        "failure_reasons": bootstrap.loc[bootstrap["status"] == "failed", "error"].value_counts().to_dict(),
    }
    if len(valid_bda) < 950:
        warnings.warn("more than 5% of bootstrap fits failed", RuntimeWarning)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for path in FILES.values():
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing analysis output: {path}")
    combined.to_csv(FILES["combined"], index=False)
    coefficients.to_csv(FILES["coefficients"], index=False)
    comparison.to_csv(FILES["comparison"], index=False)
    bootstrap.to_csv(FILES["bootstrap"], index=False)
    diagnostic.to_csv(FILES["diagnostic"], index=False)
    report_lines = [
        "DATA_AUDIT",
        *(json.dumps(audit, sort_keys=True) for audit in audits),
        f"combined_rows={len(combined)} primary_rows={n_rows} primary_snr_values={list(COMMON_SNRS)} primary_clusters={len(clusters)}",
        "MODEL_COEFFICIENTS",
        coefficients.to_csv(index=False).strip(),
        "CLUSTER_ROBUST_RESULTS",
        "method=analytic cluster sandwich; correction=G/(G-1)*(N-1)/(N-k); statsmodels_not_installed=1",
        coefficients[["model", "term", "coefficient", "cluster_robust_se", "cluster_robust_z", "cluster_robust_p", "n_clusters"]].to_csv(index=False).strip(),
        "BOOTSTRAP_BDA",
        json.dumps(bootstrap_stats, sort_keys=True),
        "MODEL_COMPARISON",
        comparison.to_csv(index=False).strip(),
        "BRIER_SCORES",
        *(f"{model}={model_results[model]['brier']:.17g}" for model in ("M0", "M1", "M2")),
        "OBSERVED_VS_PREDICTED",
        f"rows={len(diagnostic)} path={FILES['diagnostic']}",
        "METHOD",
        "cluster_id=source_dataset|snr_db|seed",
        "bootstrap=global cluster resampling with replacement; all rows per sampled cluster retained via equivalent grouped binomial counts",
        "likelihood_ratio=ordinary likelihood; matched-seed dependence not accounted for",
    ]
    FILES["report"].write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print("DATA_AUDIT")
    for audit in audits:
        print(json.dumps(audit, sort_keys=True))
    print(f"combined_rows={len(combined)} primary_rows={n_rows} primary_clusters={len(clusters)}")
    print("MODEL_COEFFICIENTS")
    print(coefficients[["model", "term", "coefficient", "ordinary_se", "ordinary_p"]].to_csv(index=False).strip())
    print("CLUSTER_ROBUST_RESULTS")
    print(coefficients[["model", "term", "cluster_robust_se", "cluster_robust_p", "n_clusters"]].to_csv(index=False).strip())
    print("BOOTSTRAP_BDA")
    print(json.dumps(bootstrap_stats, sort_keys=True))
    print("MODEL_COMPARISON")
    print(comparison.to_csv(index=False).strip())
    print("BRIER_SCORES")
    for model in ("M0", "M1", "M2"):
        print(f"{model}={model_results[model]['brier']:.17g}")
    print("OUTPUT_PATHS")
    for label, path in FILES.items():
        print(f"{label}={path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, RuntimeError, ValueError, np.linalg.LinAlgError) as error:
        print(f"interaction analysis failed: {error}", file=sys.stderr)
        raise SystemExit(1)
