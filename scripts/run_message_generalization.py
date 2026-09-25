#!/usr/bin/env python3
"""Three-condition, matched-seed Type-1 message generalization check."""

from __future__ import annotations

import csv
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
import os
import random
import re
import subprocess
import sys
import tempfile
import time

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, xlogy
from scipy.stats import chi2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from analysis.metrics import wilson_interval
from impairments.frequency import (
    apply_frequency_error, embed_active_trajectory,
    wsprd_linear_drift_trajectory, wspr_symbol_quadratic_residual_trajectory,
)
from impairments.noise import add_awgn
from wspr.encoder import encode_type1
from wspr.waveform import generate_complex_baseband, write_c2

MESSAGES = (
    "K1ABC FN42 33", "W9XYZ EN52 20", "N0CAL DM79 37",
    "G4AAA IO91 10", "M0BEE JO02 30", "VK2ZZ QF56 23",
    "JA1QRS PM95 17", "F5ABC JN18 40",
)
CONDITIONS = (
    ("awgn", -31.5, 0.0, 0.0),
    ("linear_drift", -30.5, 0.5, 0.0),
    ("quadratic_residual", -30.5, 0.0, 0.3125),
)
N = 100
BASE_SEED = 2026102000
TOTAL = 3 * 8 * N
WORKERS = min(4, os.cpu_count() or 1)
CSV_DIR = ROOT / "results/csv/message_generalization"
ANALYSIS_DIR = ROOT / "results/analysis/message_generalization"
TRIAL_PATH = CSV_DIR / "message_generalization_trials.csv"
SUMMARY_PATH = CSV_DIR / "message_generalization_summary.csv"
MANIFEST_PATH = ANALYSIS_DIR / "message_manifest.csv"
MODEL_PATH = ANALYSIS_DIR / "message_effect_model.csv"
PAIR_PATH = ANALYSIS_DIR / "message_pairwise_summary.csv"
REPORT_PATH = ANALYSIS_DIR / "message_generalization_report.txt"
TRIAL_FIELDS = (
    "message", "callsign", "grid", "power", "condition", "snr_db",
    "linear_drift_hz", "quadratic_residual_hz", "trial_index", "noise_seed",
    "decoded_success", "decoded_message", "reported_snr", "reported_drift",
    "runtime_seconds",
)

_WAVEFORMS = {}


def parse_decode(stdout: str, expected: str):
    other = []
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) == 8 and re.fullmatch(r"[0-9]{4}", fields[0]):
            message = " ".join(fields[5:8])
            if message == expected:
                return 1, message, fields[1], fields[4]
            other.append(message)
    return 0, " | ".join(other), "", ""


def decode(waveform, expected: str):
    with tempfile.TemporaryDirectory(prefix="wspr-message-generalization-") as directory:
        work = Path(directory)
        filename = "260925_0000.c2"
        write_c2(work / filename, waveform)
        process = subprocess.run(
            ["bash", str(ROOT / "scripts/wsprd.sh"), "-H", "-a", str(work), filename],
            cwd=work, text=True, capture_output=True, check=False,
        )
    if process.returncode:
        raise RuntimeError(f"wsprd exit={process.returncode}; stdout={process.stdout!r}; stderr={process.stderr!r}")
    return parse_decode(process.stdout, expected)


def initialize_worker():
    global _WAVEFORMS
    _WAVEFORMS = {}
    for message in MESSAGES:
        clean = generate_complex_baseband(encode_type1(message).channel_symbols)
        for condition, _, drift, amplitude in CONDITIONS:
            if drift == amplitude == 0:
                _WAVEFORMS[(message, condition)] = clean
                continue
            active = (
                wsprd_linear_drift_trajectory(162, 256, drift)
                if drift else wspr_symbol_quadratic_residual_trajectory(162, 256, amplitude)
            )
            full = embed_active_trajectory(len(clean.samples), clean.frame_start_sample, active)
            samples = apply_frequency_error(clean.samples, full, clean.sample_rate_hz)
            _WAVEFORMS[(message, condition)] = replace(clean, samples=samples)


def run_trial(task):
    condition, snr, drift, amplitude, message, index, seed = task
    started = time.perf_counter()
    impaired = _WAVEFORMS[(message, condition)]
    noisy = add_awgn(impaired.samples, snr, random.Random(seed), signal_power=1.0)
    success, decoded, reported_snr, reported_drift = decode(
        replace(impaired, samples=noisy), message
    )
    callsign, grid, power = message.split()
    return dict(
        message=message, callsign=callsign, grid=grid, power=power,
        condition=condition, snr_db=snr, linear_drift_hz=drift,
        quadratic_residual_hz=amplitude, trial_index=index, noise_seed=seed,
        decoded_success=success, decoded_message=decoded,
        reported_snr=reported_snr, reported_drift=reported_drift,
        runtime_seconds=time.perf_counter() - started,
    )


def gate_messages():
    rows = []
    for message in MESSAGES:
        encoded = encode_type1(message)
        assert len(encoded.channel_symbols) == 162
        assert set(encoded.channel_symbols) <= {0, 1, 2, 3}
        waveform = generate_complex_baseband(encoded.channel_symbols)
        assert waveform.signal_sample_count == 162 * 256
        success, decoded, _, _ = decode(waveform, message)
        print(f"CLEAN_GATE {message}: {success}, decoded={decoded}", file=sys.stderr, flush=True)
        if not success or decoded != message:
            raise RuntimeError(f"clean decode gate failed: {message}, decoded={decoded}")
        call, grid, power = message.split()
        rows.append(dict(message=message, callsign=call, grid=grid, power=power,
                         symbol_count=162, clean_decode_success=1,
                         clean_decoded_message=decoded))
    return rows


def fit_logit(X, y, seeds):
    def objective(beta):
        eta = X @ beta
        return float(np.logaddexp(0, eta).sum() - y @ eta)
    def gradient(beta):
        return X.T @ (expit(X @ beta) - y)
    fitted = minimize(objective, np.zeros(X.shape[1]), jac=gradient, method="BFGS",
                      options={"gtol": 1e-8, "maxiter": 1000})
    beta = fitted.x
    p = expit(X @ beta)
    H = (X.T * (p * (1 - p))) @ X
    bread = np.linalg.pinv(H)
    scores = X * (y - p)[:, None]
    cluster_scores = np.array([scores[seeds == seed].sum(axis=0)
                               for seed in np.unique(seeds)])
    meat = cluster_scores.T @ cluster_scores
    G = len(cluster_scores)
    correction = G / (G - 1) * (len(y) - 1) / (len(y) - X.shape[1])
    cluster_cov = correction * bread @ meat @ bread
    return dict(beta=beta, cluster_cov=cluster_cov,
                ordinary_se=np.sqrt(np.maximum(0, np.diag(bread))),
                cluster_se=np.sqrt(np.maximum(0, np.diag(cluster_cov))),
                log_likelihood=-objective(beta), converged=bool(fitted.success or
                np.linalg.norm(gradient(beta)) < 1e-5),
                min_probability=float(p.min()), max_probability=float(p.max()))


def analyze(rows):
    summary, models, pairs, report_lines = [], [], [], []
    for condition, snr, drift, amplitude in CONDITIONS:
        selected = [r for r in rows if r["condition"] == condition]
        y = np.array([int(r["decoded_success"]) for r in selected], dtype=float)
        seeds = np.array([int(r["noise_seed"]) for r in selected])
        m_index = np.array([MESSAGES.index(r["message"]) for r in selected])
        X0 = np.ones((len(selected), 1))
        X1 = np.column_stack((X0, *[(m_index == i).astype(float) for i in range(1, 8)]))
        f0, f1 = fit_logit(X0, y, seeds), fit_logit(X1, y, seeds)
        probs = []
        by_message = {}
        for message in MESSAGES:
            subset = [r for r in selected if r["message"] == message]
            by_message[message] = {int(r["noise_seed"]): int(r["decoded_success"])
                                   for r in subset}
            successes = sum(by_message[message].values())
            low, high = wilson_interval(successes, N)
            prob = successes / N
            probs.append(prob)
            summary.append(dict(message=message, condition=condition, n=N,
                                successes=successes, p_decode=prob,
                                Wilson95_low=low, Wilson95_high=high))
        mean = float(np.mean(probs))
        spread = max(probs) - min(probs)
        sd = float(np.std(probs, ddof=1))
        likelihood_ratio = 2 * (f1["log_likelihood"] - f0["log_likelihood"])
        cluster_wald = float(
            f1["beta"][1:] @ np.linalg.pinv(f1["cluster_cov"][1:, 1:]) @ f1["beta"][1:]
        )
        models.append(dict(condition=condition, model="M0_intercept",
                           log_likelihood=f0["log_likelihood"], parameters=1,
                           converged=f0["converged"], lr_vs_M0="", df="",
                           p_chi2="", cluster_wald_chi2="", cluster_wald_p="",
                           message_effect_range=spread,
                           message_effect_sd=sd, across_message_mean=mean,
                           max_abs_deviation_from_mean=max(abs(p-mean) for p in probs),
                           within_descriptive_delta_0_10=int(all(abs(p-mean) <= .10 for p in probs)),
                           term_order="intercept",
                           coefficients_by_term=str(f0["beta"].tolist()),
                           ordinary_se_by_term=str(f0["ordinary_se"].tolist()),
                           cluster_se_by_term=str(f0["cluster_se"].tolist()),
                           ordinary_se_intercept=f0["ordinary_se"][0],
                           cluster_se_intercept=f0["cluster_se"][0]))
        models.append(dict(condition=condition, model="M1_categorical_message",
                           log_likelihood=f1["log_likelihood"], parameters=8,
                           converged=f1["converged"], lr_vs_M0=likelihood_ratio,
                           df=7, p_chi2=chi2.sf(likelihood_ratio, 7),
                           cluster_wald_chi2=cluster_wald,
                           cluster_wald_p=chi2.sf(cluster_wald, 7),
                           message_effect_range=spread, message_effect_sd=sd,
                           across_message_mean=mean,
                           max_abs_deviation_from_mean=max(abs(p-mean) for p in probs),
                           within_descriptive_delta_0_10=int(all(abs(p-mean) <= .10 for p in probs)),
                           term_order="intercept;" + ";".join(f"{message}_vs_{MESSAGES[0]}" for message in MESSAGES[1:]),
                           coefficients_by_term=str(f1["beta"].tolist()),
                           ordinary_se_by_term=str(f1["ordinary_se"].tolist()),
                           cluster_se_by_term=str(f1["cluster_se"].tolist()),
                           ordinary_se_intercept=f1["ordinary_se"][0],
                           cluster_se_intercept=f1["cluster_se"][0]))
        for i, left in enumerate(MESSAGES):
            for right in MESSAGES[i+1:]:
                a, b = by_message[left], by_message[right]
                assert a.keys() == b.keys()
                both = sum(a[s] and b[s] for s in a)
                left_only = sum(a[s] and not b[s] for s in a)
                right_only = sum(not a[s] and b[s] for s in a)
                neither = sum(not a[s] and not b[s] for s in a)
                assert both + left_only + right_only + neither == N
                pairs.append(dict(condition=condition, message_a=left, message_b=right,
                                  both_decode=both, a_only=left_only, b_only=right_only,
                                  neither=neither, paired_difference=(left_only-right_only)/N))
        report_lines.append(
            f"{condition}: p_decode={dict(zip(MESSAGES, probs))}; range={spread:.3f}; "
            f"sample_sd={sd:.4f}; mean={mean:.4f}; max_abs_deviation={max(abs(p-mean) for p in probs):.4f}; "
            f"within_descriptive_delta_0_10={all(abs(p-mean)<=.10 for p in probs)}; "
            f"M0_loglik={f0['log_likelihood']:.6f}; M1_loglik={f1['log_likelihood']:.6f}; "
            f"LR={likelihood_ratio:.6f}; chi2_df7_p={chi2.sf(likelihood_ratio,7):.6g}; "
            f"cluster_robust_Wald_chi2_df7={cluster_wald:.6f}; "
            f"cluster_robust_Wald_p={chi2.sf(cluster_wald,7):.6g}; "
            f"M1_cluster_robust_se_by_term={f1['cluster_se'].tolist()}"
        )
    return summary, models, pairs, report_lines


def write_csv_exclusive(path, fields, records):
    with path.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def main():
    assert len(MESSAGES) == 8 and len(CONDITIONS) == 3 and N == 100 and TOTAL == 2400
    assert len(set(MESSAGES)) == 8
    outputs = (TRIAL_PATH, SUMMARY_PATH, MANIFEST_PATH, MODEL_PATH, PAIR_PATH, REPORT_PATH)
    for path in outputs:
        if path.exists():
            raise FileExistsError(f"refusing to overwrite: {path}")
    manifest = gate_messages()
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    write_csv_exclusive(MANIFEST_PATH, tuple(manifest[0]), manifest)
    tasks = [
        (condition, snr, drift, amplitude, message, index,
         BASE_SEED + condition_index * 10_000 + index)
        for condition_index, (condition, snr, drift, amplitude) in enumerate(CONDITIONS)
        for message in MESSAGES for index in range(N)
    ]
    assert len(tasks) == TOTAL
    started = time.perf_counter()
    progress = defaultdict(int)
    with TRIAL_PATH.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRIAL_FIELDS)
        writer.writeheader()
        handle.flush()
        with ProcessPoolExecutor(max_workers=WORKERS, initializer=initialize_worker) as pool:
            futures = [pool.submit(run_trial, task) for task in tasks]
            for future in as_completed(futures):
                row = future.result()
                writer.writerow(row)
                handle.flush()
                key = (row["condition"], row["message"])
                progress[key] += 1
                if progress[key] == 1 or progress[key] % 25 == 0:
                    print(f"[{key[0]} | {key[1]} | {progress[key]}/100]",
                          file=sys.stderr, flush=True)
    with TRIAL_PATH.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == TOTAL
    assert {r["decoded_success"] for r in rows} <= {"0", "1"}
    assert len({(r["condition"], r["message"], r["trial_index"]) for r in rows}) == TOTAL
    for cidx, (condition, _, _, _) in enumerate(CONDITIONS):
        expected = {BASE_SEED + cidx * 10_000 + i for i in range(N)}
        for message in MESSAGES:
            cell = [r for r in rows if r["condition"] == condition and r["message"] == message]
            assert len(cell) == N
            assert {int(r["noise_seed"]) for r in cell} == expected
            assert {int(r["trial_index"]) for r in cell} == set(range(N))
    summary, models, pairs, report_lines = analyze(rows)
    assert len(summary) == 24 and len(models) == 6 and len(pairs) == 84
    write_csv_exclusive(SUMMARY_PATH, tuple(summary[0]), summary)
    write_csv_exclusive(MODEL_PATH, tuple(models[0]), models)
    write_csv_exclusive(PAIR_PATH, tuple(pairs[0]), pairs)
    REPORT_PATH.write_text(
        "MESSAGE_GENERALIZATION\n"
        + f"messages={len(MESSAGES)}; conditions={len(CONDITIONS)}; trials={len(rows)}; "
        + f"seed_rule={BASE_SEED}+condition_index*10000+trial_index; "
        + "same seeds across all messages within condition\n"
        + "Descriptive +/-0.10 criterion is not a formal equivalence test.\n"
        + "M1 cluster-robust SE and joint Wald tests are sandwich estimates clustered by noise_seed; "
        + "LR p-values are conventional likelihood-ratio diagnostics, not clustered tests.\n"
        + "\n".join(report_lines) + "\n"
        + f"runtime_seconds={time.perf_counter()-started:.3f}\n"
        + "integrity=PASS\n",
        encoding="utf-8",
    )
    print("MESSAGE_GENERALIZATION_COMPLETE", len(rows), f"runtime={time.perf_counter()-started:.3f}s")


def reanalyze_existing_trials():
    """Refresh derived diagnostics without invoking wsprd or editing raw trials."""
    with TRIAL_PATH.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == TOTAL
    for cidx, (condition, _, _, _) in enumerate(CONDITIONS):
        expected = {BASE_SEED + cidx * 10_000 + i for i in range(N)}
        for message in MESSAGES:
            cell = [r for r in rows if r["condition"] == condition and r["message"] == message]
            assert len(cell) == N
            assert {int(r["noise_seed"]) for r in cell} == expected
    summary, models, pairs, report_lines = analyze(rows)
    assert len(summary) == 24 and len(models) == 6 and len(pairs) == 84
    for path, records in ((MODEL_PATH, models), (PAIR_PATH, pairs)):
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=tuple(records[0]))
            writer.writeheader()
            writer.writerows(records)
    old_report = REPORT_PATH.read_text(encoding="utf-8")
    runtime_line = next((line for line in old_report.splitlines()
                         if line.startswith("runtime_seconds=")), "runtime_seconds=unavailable")
    REPORT_PATH.write_text(
        "MESSAGE_GENERALIZATION\n"
        + f"messages={len(MESSAGES)}; conditions={len(CONDITIONS)}; trials={len(rows)}; "
        + f"seed_rule={BASE_SEED}+condition_index*10000+trial_index; "
        + "same seeds across all messages within condition\n"
        + "Descriptive +/-0.10 criterion is not a formal equivalence test.\n"
        + "M1 cluster-robust SE and joint Wald tests are sandwich estimates clustered by noise_seed; "
        + "LR p-values are conventional likelihood-ratio diagnostics, not clustered tests.\n"
        + "\n".join(report_lines) + "\n" + runtime_line + "\nintegrity=PASS\n",
        encoding="utf-8",
    )
    print("MESSAGE_GENERALIZATION_REANALYSIS_COMPLETE", len(rows))


if __name__ == "__main__":
    if sys.argv[1:] == ["--reanalyze"]:
        reanalyze_existing_trials()
    elif not sys.argv[1:]:
        raise SystemExit(main())
    else:
        raise SystemExit("usage: run_message_generalization.py [--reanalyze]")
