#!/usr/bin/env python3
"""Run the balanced linear/quadratic interaction confirmation experiment."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import math
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import norm

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
from analyze_interaction_model import fit_binomial, clustered_covariance

SNR_GRID = (-30.0, -30.5, -31.0)
LINEAR_DRIFT_GRID_HZ = (0.0, 0.5)
A_RES_GRID_HZ = (0.0, 0.25, 0.5)
N_PER_CONDITION = 200
TOTAL_CONDITIONS = 18
TOTAL_TRIALS = 3600
BASE_SEED = 2026093000
BOOTSTRAP_SEED = 2026100100
BOOTSTRAP_REPLICATES = 1000
WORKERS = min(4, os.cpu_count() or 1)
MESSAGE = "K1ABC FN42 33"
OUTPUT_DIR = ROOT / "results/csv/balanced_interaction_confirm"
ANALYSIS_DIR = ROOT / "results/analysis/balanced_interaction_confirm"
TRIAL_CSV = OUTPUT_DIR / "balanced_interaction_confirm_trials.csv"
SUMMARY_CSV = OUTPUT_DIR / "balanced_interaction_confirm_summary.csv"
MATRIX_CSV = OUTPUT_DIR / "balanced_interaction_confirm_matrix.csv"
COEFFICIENT_CSV = ANALYSIS_DIR / "balanced_interaction_confirm_coefficients.csv"
BOOTSTRAP_CSV = ANALYSIS_DIR / "balanced_interaction_confirm_bootstrap_bDA.csv"
MODEL_CSV = ANALYSIS_DIR / "balanced_interaction_confirm_model_comparison.csv"

TRIAL_FIELDS = (
    "snr_db", "linear_drift_hz", "A_res_hz", "trial_index", "seed",
    "decoded_success", "decoded_message", "reported_snr", "reported_drift",
    "reported_frequency", "runtime_seconds",
)
SUMMARY_FIELDS = (
    "snr_db", "linear_drift_hz", "A_res_hz", "n", "successes",
    "p_decode", "Wilson95_low", "Wilson95_high", "mean_runtime_seconds",
)
TERMS = ("intercept", "snr_c", "linear_drift_hz", "A_res_hz", "D_times_A")

_CLEAN_WAVEFORM = None
_IMPAIRED_CACHE: dict[tuple[float, float], object] = {}


def initialize_worker() -> None:
    global _CLEAN_WAVEFORM, _IMPAIRED_CACHE
    _CLEAN_WAVEFORM = generate_complex_baseband(encode_type1(MESSAGE).channel_symbols)
    _IMPAIRED_CACHE = {}


def impaired_waveform(drift_hz: float, amplitude_hz: float):
    key = (drift_hz, amplitude_hz)
    if key in _IMPAIRED_CACHE:
        return _IMPAIRED_CACHE[key]
    if _CLEAN_WAVEFORM is None or _CLEAN_WAVEFORM.signal_sample_count != 162 * 256:
        raise RuntimeError("worker requires a 162x256 clean WSPR frame")
    linear = wsprd_linear_drift_trajectory(162, 256, drift_hz)
    quadratic = wspr_symbol_quadratic_residual_trajectory(162, 256, amplitude_hz)
    active = tuple(a + b for a, b in zip(linear, quadratic, strict=True))
    full = embed_active_trajectory(
        len(_CLEAN_WAVEFORM.samples), _CLEAN_WAVEFORM.frame_start_sample, active
    )
    samples = apply_frequency_error(
        _CLEAN_WAVEFORM.samples, full, _CLEAN_WAVEFORM.sample_rate_hz
    )
    waveform = replace(_CLEAN_WAVEFORM, samples=samples)
    _IMPAIRED_CACHE[key] = waveform
    return waveform


def parse_decoder_output(stdout: str) -> tuple[bool, str, str, str, str]:
    messages: list[str] = []
    exact_row = None
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) == 8 and re.fullmatch(r"[0-9]{4}", fields[0]):
            messages.append(" ".join(fields[5:8]))
            if fields[5:8] == MESSAGE.split():
                exact_row = fields
    if exact_row is None:
        return False, " | ".join(messages), "", "", ""
    return True, MESSAGE, exact_row[1], exact_row[4], exact_row[3]


def run_trial(task: tuple[float, float, float, int, int]) -> dict[str, object]:
    snr_db, drift_hz, amplitude_hz, trial_index, seed = task
    started = time.perf_counter()
    clean = impaired_waveform(drift_hz, amplitude_hz)
    noisy = add_awgn(clean.samples, snr_db, random.Random(seed), signal_power=1.0)
    waveform = replace(clean, samples=noisy)
    with tempfile.TemporaryDirectory(prefix="wspr-balanced-interaction-") as directory:
        work = Path(directory)
        filename = "260925_0000.c2"
        write_c2(work / filename, waveform)
        process = subprocess.run(
            ["bash", str(ROOT / "scripts/wsprd.sh"), "-H", "-a", str(work), filename],
            cwd=work, text=True, capture_output=True, check=False,
        )
    if process.returncode != 0:
        raise RuntimeError(
            f"wsprd failed for SNR={snr_db}, D={drift_hz}, A={amplitude_hz}, "
            f"trial={trial_index}, seed={seed}: {process.stderr.strip()}"
        )
    success, message, reported_snr, reported_drift, reported_frequency = (
        parse_decoder_output(process.stdout)
    )
    return {
        "snr_db": snr_db, "linear_drift_hz": drift_hz, "A_res_hz": amplitude_hz,
        "trial_index": trial_index, "seed": seed, "decoded_success": int(success),
        "decoded_message": message, "reported_snr": reported_snr,
        "reported_drift": reported_drift, "reported_frequency": reported_frequency,
        "runtime_seconds": time.perf_counter() - started,
    }


def validate_specification() -> None:
    assert len(SNR_GRID) == 3
    assert len(LINEAR_DRIFT_GRID_HZ) == 2
    assert len(A_RES_GRID_HZ) == 3
    assert N_PER_CONDITION == 200
    assert len(SNR_GRID) * len(LINEAR_DRIFT_GRID_HZ) * len(A_RES_GRID_HZ) == TOTAL_CONDITIONS == 18
    assert TOTAL_CONDITIONS * N_PER_CONDITION == TOTAL_TRIALS == 3600


def build_tasks() -> list[tuple[float, float, float, int, int]]:
    return [
        (snr, drift, amplitude, index, BASE_SEED + snr_index * 10_000 + index)
        for snr_index, snr in enumerate(SNR_GRID)
        for drift in LINEAR_DRIFT_GRID_HZ
        for amplitude in A_RES_GRID_HZ
        for index in range(N_PER_CONDITION)
    ]


def validate_trials(rows: list[dict[str, str]]) -> None:
    assert len(rows) == TOTAL_TRIALS
    grouped: dict[tuple[float, float, float], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        assert row["decoded_success"] in {"0", "1"}
        key = (float(row["snr_db"]), float(row["linear_drift_hz"]), float(row["A_res_hz"]))
        assert key[0] in SNR_GRID and key[1] in LINEAR_DRIFT_GRID_HZ and key[2] in A_RES_GRID_HZ
        grouped[key].append(row)
    assert len(grouped) == TOTAL_CONDITIONS
    for selected in grouped.values():
        assert len(selected) == N_PER_CONDITION
        assert len({int(row["seed"]) for row in selected}) == N_PER_CONDITION
        assert {int(row["trial_index"]) for row in selected} == set(range(N_PER_CONDITION))
    for snr_index, snr in enumerate(SNR_GRID):
        expected_seeds = {BASE_SEED + snr_index * 10_000 + index for index in range(N_PER_CONDITION)}
        for drift in LINEAR_DRIFT_GRID_HZ:
            for amplitude in A_RES_GRID_HZ:
                assert {int(row["seed"]) for row in grouped[(snr, drift, amplitude)]} == expected_seeds


def make_summaries(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple[float, float, float], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(float(row["snr_db"]), float(row["linear_drift_hz"]), float(row["A_res_hz"]))].append(row)
    summaries = []
    for snr in SNR_GRID:
        for drift in LINEAR_DRIFT_GRID_HZ:
            for amplitude in A_RES_GRID_HZ:
                selected = grouped[(snr, drift, amplitude)]
                successes = sum(int(row["decoded_success"]) for row in selected)
                low, high = wilson_interval(successes, N_PER_CONDITION)
                summaries.append({
                    "snr_db": snr, "linear_drift_hz": drift, "A_res_hz": amplitude,
                    "n": len(selected), "successes": successes,
                    "p_decode": successes / N_PER_CONDITION,
                    "Wilson95_low": low, "Wilson95_high": high,
                    "mean_runtime_seconds": sum(float(row["runtime_seconds"]) for row in selected) / len(selected),
                })
    return summaries


def write_summaries(summaries: list[dict[str, object]]) -> None:
    assert len(summaries) == TOTAL_CONDITIONS
    for row in summaries:
        assert row["n"] == N_PER_CONDITION
        assert row["p_decode"] == row["successes"] / N_PER_CONDITION
    with SUMMARY_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summaries)
    with SUMMARY_CSV.open(newline="") as handle:
        actual = list(csv.DictReader(handle))
    assert len(actual) == TOTAL_CONDITIONS
    assert all(float(row["p_decode"]) == int(row["successes"]) / N_PER_CONDITION for row in actual)
    probabilities = {
        (float(row["snr_db"]), float(row["linear_drift_hz"]), float(row["A_res_hz"])): row["p_decode"]
        for row in summaries
    }
    columns = [f"{amplitude:g}" for amplitude in A_RES_GRID_HZ]
    with MATRIX_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["snr_db", "linear_drift_hz", *columns])
        writer.writeheader()
        for snr in SNR_GRID:
            for drift in LINEAR_DRIFT_GRID_HZ:
                row = {"snr_db": snr, "linear_drift_hz": drift}
                for amplitude, column in zip(A_RES_GRID_HZ, columns, strict=True):
                    row[column] = probabilities[(snr, drift, amplitude)]
                writer.writerow(row)


def design(frame: pd.DataFrame, interaction: bool) -> np.ndarray:
    snr = frame["snr_db"].to_numpy(dtype=float) + 30.5
    drift = frame["linear_drift_hz"].to_numpy(dtype=float)
    amplitude = frame["A_res_hz"].to_numpy(dtype=float)
    columns = [np.ones(len(frame)), snr, drift, amplitude]
    if interaction:
        columns.append(drift * amplitude)
    return np.column_stack(columns)


def analyze() -> tuple[dict[str, object], list[dict[str, object]]]:
    frame = pd.read_csv(TRIAL_CSV)
    assert len(frame) == TOTAL_TRIALS
    y = frame["decoded_success"].to_numpy(dtype=float)
    totals = np.ones(len(frame))
    x0, x1 = design(frame, False), design(frame, True)
    model_results = []
    fits = {}
    for label, x in (("M0", x0), ("M1", x1)):
        beta, inverse_info, ll, iterations = fit_binomial(x, y, totals)
        probabilities = expit(x @ beta)
        fits[label] = (beta, inverse_info, probabilities)
        model_results.append({
            "model": label, "log_likelihood": ll,
            "AIC": -2 * ll + 2 * x.shape[1],
            "BIC": -2 * ll + x.shape[1] * math.log(len(y)),
            "Brier_score": float(np.mean((y - probabilities) ** 2)),
            "iterations": iterations,
        })
    beta, inverse_info, probabilities = fits["M1"]
    cluster_ids = frame["snr_db"].map(lambda value: f"{value:g}") + "|" + frame["seed"].astype(str)
    clusters, cluster_codes = np.unique(cluster_ids.to_numpy(), return_inverse=True)
    assert len(clusters) == len(SNR_GRID) * N_PER_CONDITION
    robust_covariance = clustered_covariance(
        x1, y, probabilities, cluster_codes, len(clusters), inverse_info
    )
    ordinary_se = np.sqrt(np.diag(inverse_info))
    robust_se = np.sqrt(np.diag(robust_covariance))
    coefficient_rows = [
        {"model": "M1", "term": term, "coefficient": float(beta[index]),
         "ordinary_SE": float(ordinary_se[index]), "cluster_robust_SE": float(robust_se[index])}
        for index, term in enumerate(TERMS)
    ]
    with COEFFICIENT_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=coefficient_rows[0].keys())
        writer.writeheader()
        writer.writerows(coefficient_rows)
    with MODEL_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=model_results[0].keys())
        writer.writeheader()
        writer.writerows(model_results)

    cell_frame = pd.DataFrame(
        [(snr, drift, amplitude)
         for snr in SNR_GRID for drift in LINEAR_DRIFT_GRID_HZ for amplitude in A_RES_GRID_HZ],
        columns=["snr_db", "linear_drift_hz", "A_res_hz"],
    )
    cells = pd.MultiIndex.from_frame(cell_frame)
    row_cells = pd.MultiIndex.from_frame(frame[["snr_db", "linear_drift_hz", "A_res_hz"]])
    cell_codes = cells.get_indexer(row_cells)
    assert np.all(cell_codes >= 0)
    counts = np.zeros((len(clusters), len(cells)), dtype=np.int32)
    successes = np.zeros_like(counts)
    np.add.at(counts, (cluster_codes, cell_codes), 1)
    np.add.at(successes, (cluster_codes, cell_codes), y.astype(np.int32))
    cell_design = design(cell_frame, True)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    bootstrap_rows = []
    for index in range(BOOTSTRAP_REPLICATES):
        drawn = rng.integers(0, len(clusters), size=len(clusters))
        multiplicity = np.bincount(drawn, minlength=len(clusters))
        count = multiplicity @ counts
        success = multiplicity @ successes
        mask = count > 0
        try:
            boot_beta, _, _, iterations = fit_binomial(
                cell_design[mask], success[mask], count[mask], initial=beta
            )
            bootstrap_rows.append({
                "replicate": index + 1, "bDA": float(boot_beta[4]),
                "status": "success", "iterations": iterations, "error": "",
            })
        except (RuntimeError, np.linalg.LinAlgError, FloatingPointError) as error:
            bootstrap_rows.append({
                "replicate": index + 1, "bDA": "",
                "status": "failed", "iterations": "", "error": str(error),
            })
    with BOOTSTRAP_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=bootstrap_rows[0].keys())
        writer.writeheader()
        writer.writerows(bootstrap_rows)
    retained = np.array(
        [row["bDA"] for row in bootstrap_rows if row["status"] == "success"], dtype=float
    )
    if not len(retained):
        raise RuntimeError("no successful bootstrap fits")
    interaction = {
        "bDA": float(beta[4]),
        "ordinary_SE": float(ordinary_se[4]),
        "cluster_robust_SE": float(robust_se[4]),
        "cluster_robust_p": float(2 * norm.sf(abs(beta[4] / robust_se[4]))),
        "bootstrap_median": float(np.median(retained)),
        "bootstrap_2.5th_percentile": float(np.percentile(retained, 2.5)),
        "bootstrap_97.5th_percentile": float(np.percentile(retained, 97.5)),
        "successful_bootstrap_fits": len(retained),
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
    }
    return interaction, model_results


def main() -> int:
    validate_specification()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    output_paths = (
        TRIAL_CSV, SUMMARY_CSV, MATRIX_CSV, COEFFICIENT_CSV, BOOTSTRAP_CSV, MODEL_CSV
    )
    for path in output_paths:
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
    tasks = build_tasks()
    assert len(tasks) == TOTAL_TRIALS
    started = time.perf_counter()
    progress: Counter[tuple[float, float, float]] = Counter()
    with TRIAL_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRIAL_FIELDS)
        writer.writeheader()
        handle.flush()
        with ProcessPoolExecutor(max_workers=WORKERS, initializer=initialize_worker) as executor:
            futures = [executor.submit(run_trial, task) for task in tasks]
            for future in as_completed(futures):
                row = future.result()
                writer.writerow(row)
                handle.flush()
                key = (float(row["snr_db"]), float(row["linear_drift_hz"]), float(row["A_res_hz"]))
                progress[key] += 1
                if progress[key] == 1 or progress[key] % 50 == 0:
                    print(
                        f"[SNR {key[0]:.1f} | D {key[1]:+.2f} | A {key[2]:.2f} | "
                        f"{progress[key]}/{N_PER_CONDITION}]",
                        file=sys.stderr, flush=True,
                    )
    with TRIAL_CSV.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    validate_trials(rows)
    summaries = make_summaries(rows)
    write_summaries(summaries)
    interaction, models = analyze()
    runtime = time.perf_counter() - started
    print("EXPERIMENT_SPEC")
    print(f"SNR_GRID={list(SNR_GRID)}")
    print(f"LINEAR_DRIFT_GRID_HZ={list(LINEAR_DRIFT_GRID_HZ)}")
    print(f"A_RES_GRID_HZ={list(A_RES_GRID_HZ)}")
    print(f"N_PER_CONDITION={N_PER_CONDITION}")
    print(f"SEED_RULE={BASE_SEED} + snr_index*10000 + trial_index; matched across all D/A within SNR")
    print("TRAJECTORY=wsprd_linear_drift_trajectory(162,256,D) + wspr_symbol_quadratic_residual_trajectory(162,256,A)")
    print("MODELS=M0: intercept+snr_c+D+A; M1: M0+D*A; snr_c=snr_db+30.5")
    print(f"BOOTSTRAP_REPLICATES={BOOTSTRAP_REPLICATES}; BOOTSTRAP_SEED={BOOTSTRAP_SEED}")
    print("TOTAL_TRIALS")
    print(TOTAL_TRIALS)
    print("TOTAL_CONDITIONS")
    print(TOTAL_CONDITIONS)
    print("RUNTIME")
    print(f"{runtime:.6f} seconds")
    print("SUMMARY_TABLE")
    summary_writer = csv.DictWriter(sys.stdout, fieldnames=SUMMARY_FIELDS, lineterminator="\n")
    summary_writer.writeheader()
    summary_writer.writerows(summaries)
    print("CSV_INTEGRITY_CHECK")
    print("PASS")
    print("INTERACTION_CONFIRMATION")
    for key, value in interaction.items():
        print(f"{key}={value}")
    print("MODEL_COMPARISON")
    model_writer = csv.DictWriter(sys.stdout, fieldnames=models[0].keys(), lineterminator="\n")
    model_writer.writeheader()
    model_writer.writerows(models)
    print("OUTPUT_PATHS")
    for path in output_paths:
        print(path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, RuntimeError, ValueError) as error:
        print(f"balanced interaction confirmation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
