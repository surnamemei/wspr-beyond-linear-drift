#!/usr/bin/env python3
"""Decode projected random-walk FM and score frozen deterministic-family models."""

from __future__ import annotations

import csv
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import hashlib
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from analysis.metrics import wilson_interval
from impairments.frequency import apply_frequency_error, embed_active_trajectory
from impairments.noise import add_awgn
from wspr.encoder import encode_type1
from wspr.waveform import SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT, generate_complex_baseband, write_c2
from random_walk_preflight import metrics_for

SIGMA_STEP_GRID_HZ = (0.01, 0.02, 0.04, 0.08)
SNR_GRID_DB = (-30.0, -30.5, -31.0)
N_PER_CONDITION = 200
TOTAL_CONDITIONS = 12
TOTAL_TRIALS = 2400
TRAJECTORY_SEED_BASE = 2026100500
NOISE_SEED_BASE = 2026100600
BOOTSTRAP_SEED = 2026100700
BOOTSTRAP_REPLICATES = 2000
WORKERS = min(4, os.cpu_count() or 1)
MESSAGE = "K1ABC FN42 33"
DECODER_SCRIPT = ROOT / "scripts/wsprd.sh"
DETERMINISTIC_TRIALS = ROOT / "results/analysis/residual_descriptor_analysis/descriptor_joined_trials.csv"
COEFFICIENTS_CSV = ROOT / "results/analysis/residual_descriptor_analysis/model_coefficients.csv"
RAW_DIR = ROOT / "results/csv/random_walk_decoder"
ANALYSIS_DIR = ROOT / "results/analysis/random_walk_external_validation"
TRIAL_CSV = RAW_DIR / "random_walk_decoder_trials.csv"
SUMMARY_CSV = RAW_DIR / "random_walk_decoder_summary.csv"
MANIFEST_CSV = ANALYSIS_DIR / "random_walk_trajectory_manifest.csv"
PREDICTIONS_CSV = ANALYSIS_DIR / "random_walk_predictions.csv"
MODEL_PERFORMANCE_CSV = ANALYSIS_DIR / "random_walk_model_performance.csv"
PER_SIGMA_CSV = ANALYSIS_DIR / "random_walk_per_sigma_performance.csv"
BOOTSTRAP_CSV = ANALYSIS_DIR / "random_walk_bootstrap.csv"
CALIBRATION_CSV = ANALYSIS_DIR / "random_walk_calibration_bins.csv"
REPORT_TXT = ANALYSIS_DIR / "random_walk_external_validation_report.txt"
DESCRIPTOR_FIELDS = (
    "max_abs_frequency_hz", "frequency_rms_hz", "frequency_peak_to_peak_hz",
    "max_abs_phase_rad", "phase_rms_rad", "phase_peak_to_peak_rad", "final_phase_rad",
    "fitted_constant_hz", "fitted_linear_coefficient",
)
TRIAL_FIELDS = (
    "snr_db", "sigma_step_hz", "trial_index", "trajectory_seed", "noise_seed",
    "decoded_success", "decoded_message", "reported_snr", "reported_drift",
    "reported_frequency", *DESCRIPTOR_FIELDS, "runtime_seconds",
)
SUMMARY_FIELDS = (
    "snr_db", "sigma_step_hz", "n", "successes", "p_decode",
    "Wilson95_low", "Wilson95_high", "mean_runtime_seconds",
)
MODEL_TERMS = {
    "AMP": ("intercept", "snr_c", "max_abs_frequency_hz"),
    "PHASE": ("intercept", "snr_c", "max_abs_frequency_hz", "max_abs_phase_rad"),
    "RMS": ("intercept", "snr_c", "max_abs_frequency_hz", "frequency_rms_hz"),
}
SAVED_MODEL_NAMES = {"AMP": "M_amp", "PHASE": "M_phase", "RMS": "M_rms"}
_CLEAN_WAVEFORM = None
_X = (np.arange(SYMBOL_COUNT) - 81.0) / 81.0
_BASIS = np.column_stack((np.ones_like(_X), _X))


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_specification() -> None:
    assert len(SIGMA_STEP_GRID_HZ) == 4
    assert len(SNR_GRID_DB) == 3
    assert N_PER_CONDITION == 200
    assert len(SIGMA_STEP_GRID_HZ) * len(SNR_GRID_DB) == TOTAL_CONDITIONS == 12
    assert TOTAL_CONDITIONS * N_PER_CONDITION == TOTAL_TRIALS == 2400
    assert (SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT) == (375, 256, 162)
    assert DECODER_SCRIPT.is_file() and (ROOT / ".cache/runtime/usr/bin/wsprd").is_file()


def trajectory(sigma: float, trajectory_seed: int) -> tuple[dict[str, float], np.ndarray]:
    increments = np.random.default_rng(trajectory_seed).normal(0.0, sigma, SYMBOL_COUNT - 1)
    raw = np.concatenate(([0.0], np.cumsum(increments)))
    descriptors, residual = metrics_for(raw, _BASIS, _X)
    assert raw[0] == 0.0 and residual.shape == (SYMBOL_COUNT,)
    assert abs(descriptors["dot_with_constant"]) < 1e-10
    assert abs(descriptors["dot_with_x"]) < 1e-10
    return descriptors, residual


def build_manifest() -> pd.DataFrame:
    rows = []
    for sigma_index, sigma in enumerate(SIGMA_STEP_GRID_HZ):
        for trial_index in range(N_PER_CONDITION):
            seed = TRAJECTORY_SEED_BASE + sigma_index * 100000 + trial_index
            descriptors, _ = trajectory(sigma, seed)
            rows.append({"sigma_step_hz": sigma, "trial_index": trial_index,
                         "trajectory_seed": seed, **descriptors})
    manifest = pd.DataFrame(rows)
    assert len(manifest) == 800
    assert not manifest[["sigma_step_hz", "trial_index"]].duplicated().any()
    assert manifest["trajectory_seed"].is_unique
    assert np.isfinite(manifest[[*DESCRIPTOR_FIELDS, "dot_with_constant", "dot_with_x"]]).all().all()
    return manifest


def initialize_worker() -> None:
    global _CLEAN_WAVEFORM
    _CLEAN_WAVEFORM = generate_complex_baseband(encode_type1(MESSAGE).channel_symbols)
    assert _CLEAN_WAVEFORM.signal_sample_count == SYMBOL_COUNT * SAMPLES_PER_SYMBOL


def parse_decoder_output(stdout: str) -> tuple[bool, str, str, str, str]:
    messages = []
    exact = None
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) == 8 and re.fullmatch(r"[0-9]{4}", fields[0]):
            messages.append(" ".join(fields[5:8]))
            if fields[5:8] == MESSAGE.split():
                exact = fields
    if exact is None:
        return False, " | ".join(messages), "", "", ""
    return True, MESSAGE, exact[1], exact[4], exact[3]


def run_trial(task: tuple[float, float, int, int, int]) -> dict[str, object]:
    snr, sigma, trial_index, trajectory_seed, noise_seed = task
    started = time.perf_counter()
    if _CLEAN_WAVEFORM is None:
        raise RuntimeError("worker waveform not initialized")
    descriptors, residual = trajectory(sigma, trajectory_seed)
    active = np.repeat(residual, SAMPLES_PER_SYMBOL)
    full = embed_active_trajectory(
        len(_CLEAN_WAVEFORM.samples), _CLEAN_WAVEFORM.frame_start_sample,
        tuple(float(value) for value in active),
    )
    impaired_samples = apply_frequency_error(
        _CLEAN_WAVEFORM.samples, full, _CLEAN_WAVEFORM.sample_rate_hz
    )
    impaired = replace(_CLEAN_WAVEFORM, samples=impaired_samples)
    noisy = add_awgn(impaired.samples, snr, random.Random(noise_seed), signal_power=1.0)
    waveform = replace(impaired, samples=noisy)
    with tempfile.TemporaryDirectory(prefix="wspr-random-walk-") as directory:
        work = Path(directory)
        filename = "260925_0000.c2"
        write_c2(work / filename, waveform)
        process = subprocess.run(
            ["bash", str(DECODER_SCRIPT), "-H", "-a", str(work), filename],
            cwd=work, text=True, capture_output=True, check=False,
        )
    if process.returncode != 0:
        raise RuntimeError(
            f"wsprd failed: snr={snr}, sigma={sigma}, trial={trial_index}, "
            f"trajectory_seed={trajectory_seed}, noise_seed={noise_seed}: {process.stderr}"
        )
    success, message, reported_snr, reported_drift, reported_frequency = parse_decoder_output(process.stdout)
    return {
        "snr_db": snr, "sigma_step_hz": sigma, "trial_index": trial_index,
        "trajectory_seed": trajectory_seed, "noise_seed": noise_seed,
        "decoded_success": int(success), "decoded_message": message,
        "reported_snr": reported_snr, "reported_drift": reported_drift,
        "reported_frequency": reported_frequency,
        **{name: descriptors[name] for name in DESCRIPTOR_FIELDS},
        "runtime_seconds": time.perf_counter() - started,
    }


def tasks() -> list[tuple[float, float, int, int, int]]:
    return [
        (snr, sigma, trial_index,
         TRAJECTORY_SEED_BASE + sigma_index * 100000 + trial_index,
         NOISE_SEED_BASE + snr_index * 10000 + trial_index)
        for snr_index, snr in enumerate(SNR_GRID_DB)
        for sigma_index, sigma in enumerate(SIGMA_STEP_GRID_HZ)
        for trial_index in range(N_PER_CONDITION)
    ]


def read_and_validate_trials(manifest: pd.DataFrame) -> pd.DataFrame:
    frame = pd.read_csv(TRIAL_CSV)
    assert len(frame) == TOTAL_TRIALS
    assert not frame[["snr_db", "sigma_step_hz", "trial_index"]].duplicated().any()
    assert frame["decoded_success"].isin((0, 1)).all()
    assert frame.groupby(["snr_db", "sigma_step_hz"]).size().eq(N_PER_CONDITION).all()
    assert frame.groupby(["snr_db", "sigma_step_hz"])["trajectory_seed"].nunique().eq(200).all()
    assert frame.groupby(["snr_db", "sigma_step_hz"])["noise_seed"].nunique().eq(200).all()
    assert frame.groupby(["sigma_step_hz", "trial_index"])["trajectory_seed"].nunique().eq(1).all()
    assert frame.groupby(["sigma_step_hz", "trial_index"])[list(DESCRIPTOR_FIELDS)].nunique().eq(1).all().all()
    assert frame.groupby(["snr_db", "trial_index"])["noise_seed"].nunique().eq(1).all()
    assert len(frame.groupby(["snr_db", "sigma_step_hz"])) == TOTAL_CONDITIONS
    assert np.isfinite(frame[list(DESCRIPTOR_FIELDS) + ["runtime_seconds"]]).all().all()
    assert (frame["runtime_seconds"] >= 0).all()
    expected = frame.merge(manifest, on=["sigma_step_hz", "trial_index", "trajectory_seed"],
                           how="left", validate="many_to_one", suffixes=("", "_manifest"))
    assert len(expected) == TOTAL_TRIALS
    for name in DESCRIPTOR_FIELDS:
        assert np.allclose(expected[name], expected[f"{name}_manifest"], rtol=0, atol=1e-12)
    for snr_index, snr in enumerate(SNR_GRID_DB):
        expected_noise = {NOISE_SEED_BASE + snr_index * 10000 + index for index in range(200)}
        for sigma in SIGMA_STEP_GRID_HZ:
            selected = frame[(frame.snr_db == snr) & (frame.sigma_step_hz == sigma)]
            assert set(selected.noise_seed) == expected_noise
    return frame


def summarize(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for snr in SNR_GRID_DB:
        for sigma in SIGMA_STEP_GRID_HZ:
            selected = frame[(frame.snr_db == snr) & (frame.sigma_step_hz == sigma)]
            successes = int(selected.decoded_success.sum())
            low, high = wilson_interval(successes, N_PER_CONDITION)
            rows.append({"snr_db": snr, "sigma_step_hz": sigma, "n": len(selected),
                         "successes": successes, "p_decode": successes / N_PER_CONDITION,
                         "Wilson95_low": low, "Wilson95_high": high,
                         "mean_runtime_seconds": float(selected.runtime_seconds.mean())})
    summary = pd.DataFrame(rows, columns=SUMMARY_FIELDS)
    assert len(summary) == TOTAL_CONDITIONS
    assert np.allclose(summary.p_decode, summary.successes / N_PER_CONDITION, atol=0, rtol=0)
    return summary


def frozen_coefficients() -> dict[str, np.ndarray]:
    deterministic = pd.read_csv(DETERMINISTIC_TRIALS)
    assert len(deterministic) == 3000
    assert set(deterministic.snr_db) == set(SNR_GRID_DB)
    assert deterministic.decoded_success.isin((0, 1)).all()
    saved = pd.read_csv(COEFFICIENTS_CSV)
    coefficients = {}
    for model, terms in MODEL_TERMS.items():
        selected = saved[saved.model == SAVED_MODEL_NAMES[model]]
        assert list(selected.term) == list(terms)
        beta = selected.coefficient.to_numpy(dtype=float)
        assert len(beta) == len(terms) and np.isfinite(beta).all()
        coefficients[model] = beta
    return coefficients


def design(frame: pd.DataFrame, model: str) -> np.ndarray:
    sources = {"intercept": np.ones(len(frame)),
               "snr_c": frame.snr_db.to_numpy(dtype=float) + 30.5}
    for name in DESCRIPTOR_FIELDS:
        sources[name] = frame[name].to_numpy(dtype=float)
    return np.column_stack([sources[name] for name in MODEL_TERMS[model]])


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    safe = np.clip(p, 1e-15, 1 - 1e-15)
    return float(-np.mean(y * np.log(safe) + (1 - y) * np.log1p(-safe)))


def score(frame: pd.DataFrame, coefficients: dict[str, np.ndarray]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    predictions = frame.copy()
    y = predictions.decoded_success.to_numpy(dtype=float)
    for model in MODEL_TERMS:
        p = expit(design(predictions, model) @ coefficients[model])
        assert np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all()
        predictions[f"p_{model.lower()}"] = p
        predictions[f"brier_{model.lower()}"] = (y - p) ** 2
    performance_rows = []
    per_sigma_rows = []
    calibration_rows = []
    for model in MODEL_TERMS:
        label = model.lower()
        performance_rows.append({"model": model, "n": len(predictions),
                                 "brier_score": float(predictions[f"brier_{label}"].mean()),
                                 "log_loss": log_loss(y, predictions[f"p_{label}"].to_numpy())})
        for sigma in SIGMA_STEP_GRID_HZ:
            subset = predictions[predictions.sigma_step_hz == sigma]
            per_sigma_rows.append({"sigma_step_hz": sigma, "model": model,
                                   "n": len(subset),
                                   "brier_score": float(subset[f"brier_{label}"].mean()),
                                   "log_loss": log_loss(subset.decoded_success.to_numpy(dtype=float),
                                                        subset[f"p_{label}"].to_numpy(dtype=float))})
        bins = pd.qcut(predictions[f"p_{label}"], q=10, labels=False, duplicates="drop")
        for bin_index, selected in predictions.groupby(bins, sort=True):
            assert len(selected) >= 20
            calibration_rows.append({"model": model, "bin": int(bin_index) + 1,
                                     "n": len(selected),
                                     "mean_predicted_probability": float(selected[f"p_{label}"].mean()),
                                     "observed_decode_probability": float(selected.decoded_success.mean())})
    return predictions, pd.DataFrame(performance_rows), pd.DataFrame(per_sigma_rows), pd.DataFrame(calibration_rows)


def bootstrap(predictions: pd.DataFrame) -> pd.DataFrame:
    predictions = predictions.copy()
    predictions["paired_difference"] = predictions.brier_amp - predictions.brier_phase
    groups = predictions.groupby("trajectory_seed")["paired_difference"].agg(["sum", "count"])
    assert len(groups) == 800 and groups["count"].eq(3).all()
    sums = groups["sum"].to_numpy()
    counts = groups["count"].to_numpy()
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    rows = []
    for replicate in range(1, BOOTSTRAP_REPLICATES + 1):
        selected = rng.integers(0, len(groups), size=len(groups))
        rows.append({"replicate": replicate,
                     "mean_brier_amp_minus_phase": float(sums[selected].sum() / counts[selected].sum())})
    return pd.DataFrame(rows)


def main() -> None:
    validate_specification()
    all_outputs = (TRIAL_CSV, SUMMARY_CSV, MANIFEST_CSV, PREDICTIONS_CSV,
                   MODEL_PERFORMANCE_CSV, PER_SIGMA_CSV, BOOTSTRAP_CSV,
                   CALIBRATION_CSV, REPORT_TXT)
    if any(path.exists() for path in all_outputs):
        raise FileExistsError("Refusing to overwrite an existing random-walk output")
    source_hashes = {path: checksum(path) for path in (DETERMINISTIC_TRIALS, COEFFICIENTS_CSV)}
    coefficients = frozen_coefficients()
    manifest = build_manifest()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(MANIFEST_CSV, index=False, mode="x")
    assert len(pd.read_csv(MANIFEST_CSV)) == 800
    all_tasks = tasks()
    assert len(all_tasks) == TOTAL_TRIALS
    counts: dict[tuple[float, float], int] = defaultdict(int)
    with TRIAL_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRIAL_FIELDS)
        writer.writeheader()
        handle.flush()
        with ProcessPoolExecutor(max_workers=WORKERS, initializer=initialize_worker) as executor:
            futures = [executor.submit(run_trial, task) for task in all_tasks]
            for future in as_completed(futures):
                row = future.result()
                writer.writerow(row)
                handle.flush()
                condition = (row["snr_db"], row["sigma_step_hz"])
                counts[condition] += 1
                if counts[condition] in (1, N_PER_CONDITION) or counts[condition] % 50 == 0:
                    print(f"[SNR {condition[0]:.1f} | sigma {condition[1]:.3f} | "
                          f"{counts[condition]}/{N_PER_CONDITION}]", file=sys.stderr, flush=True)
    frame = read_and_validate_trials(manifest)
    summary = summarize(frame)
    summary.to_csv(SUMMARY_CSV, index=False, mode="x")
    assert len(pd.read_csv(SUMMARY_CSV)) == TOTAL_CONDITIONS
    predictions, performance, per_sigma, calibration = score(frame, coefficients)
    bootstrap_frame = bootstrap(predictions)
    predictions.to_csv(PREDICTIONS_CSV, index=False, mode="x")
    performance.to_csv(MODEL_PERFORMANCE_CSV, index=False, mode="x")
    per_sigma.to_csv(PER_SIGMA_CSV, index=False, mode="x")
    bootstrap_frame.to_csv(BOOTSTRAP_CSV, index=False, mode="x")
    calibration.to_csv(CALIBRATION_CSV, index=False, mode="x")
    assert len(pd.read_csv(PREDICTIONS_CSV)) == TOTAL_TRIALS
    assert len(pd.read_csv(BOOTSTRAP_CSV)) == BOOTSTRAP_REPLICATES
    assert all(checksum(path) == digest for path, digest in source_hashes.items())
    paired_mean = float((predictions.brier_amp - predictions.brier_phase).mean())
    ci_low, ci_high = np.percentile(bootstrap_frame.mean_brier_amp_minus_phase, [2.5, 97.5])
    fraction_positive = float((bootstrap_frame.mean_brier_amp_minus_phase > 0).mean())
    max_dot_constant = float(manifest.dot_with_constant.abs().max())
    max_dot_x = float(manifest.dot_with_x.abs().max())
    descriptor_range = pd.DataFrame([
        {"descriptor": name, "min": float(frame[name].min()), "max": float(frame[name].max())}
        for name in DESCRIPTOR_FIELDS
    ])
    lines = [
        "EXPERIMENT_SPEC",
        f"sigma_step_grid_hz={list(SIGMA_STEP_GRID_HZ)} snr_grid_db={list(SNR_GRID_DB)} n_per_condition={N_PER_CONDITION}",
        f"trajectory_seed={TRAJECTORY_SEED_BASE}+sigma_index*100000+trial_index noise_seed={NOISE_SEED_BASE}+snr_index*10000+trial_index",
        "residual_projection=least_squares([1,x],symbol_rate_random_walk); waveform=validated_WSPR; noise=calibrated_AWGN; decoder=production_wsprd",
        "TOTAL_TRIALS", str(TOTAL_TRIALS),
        "RANDOM_WALK_SUMMARY", summary.to_csv(index=False).strip(),
        "DESCRIPTOR_RANGE", descriptor_range.to_csv(index=False).strip(),
        "ORTHOGONALITY_CHECK",
        f"max_abs_dot_with_constant={max_dot_constant:.12g} max_abs_dot_with_x={max_dot_x:.12g} tolerance=1e-10",
        "EXTERNAL_MODEL_PERFORMANCE", performance.to_csv(index=False).strip(),
        "PER_SIGMA_PERFORMANCE", per_sigma.to_csv(index=False).strip(),
        "PAIRED_BRIER_DIFFERENCE", f"mean_brier_amp_minus_phase={paired_mean:.12g}",
        "BOOTSTRAP_RESULT",
        f"B={BOOTSTRAP_REPLICATES} rng_seed={BOOTSTRAP_SEED} trajectory_clusters=800 ci95_low={ci_low:.12g} ci95_high={ci_high:.12g} fraction_positive={fraction_positive:.12g}",
        "CSV_INTEGRITY_CHECK",
        "trial_rows=2400 conditions=12 rows_per_condition=200 unique_trajectory_seeds_per_condition=200 unique_noise_seeds_per_condition=200 matched_trajectory_descriptors_across_SNR=True matched_noise_seeds_across_sigma=True descriptors_finite=True deterministic_sources_unchanged=True",
        "OUTPUT_PATHS", *(str(path) for path in all_outputs),
    ]
    report = "\n".join(lines) + "\n"
    with REPORT_TXT.open("x", encoding="utf-8") as stream:
        stream.write(report)
    print(report, end="")


if __name__ == "__main__":
    main()
