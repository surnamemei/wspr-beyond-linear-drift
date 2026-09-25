#!/usr/bin/env python3
"""Decode projected, Allan-calibrated oscillator FM; score a frozen RMS model."""

from __future__ import annotations

import ast
import csv
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
from wspr.waveform import (
    SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT, SYMBOL_DURATION_S,
    generate_complex_baseband, write_c2,
)
from oscillator_physics_preflight import (
    NOISE_TYPES, SEED_BASE as PREFLIGHT_SEED_BASE, base_process,
    allan_variance, phase_descriptors, slope_check,
)

CARRIER_FREQUENCY_HZ = (10e6, 14e6, 28e6)
TARGET_SIGMA_Y_1S = (1e-9, 3e-9, 1e-8)
SNR_GRID_DB = (-30.5, -31.0)
N_PER_CONDITION = 100
TOTAL_CONDITIONS = 54
TOTAL_TRIALS = 5400
OSCILLATOR_SEED_BASE = 2026102000
NOISE_SEED_BASE = 2026101100
WORKERS = min(4, os.cpu_count() or 1)
MESSAGE = "K1ABC FN42 33"
DECODER_SCRIPT = ROOT / "scripts/wsprd.sh"
RMS_MODEL_SOURCE = ROOT / "results/analysis/roughness_descriptor/roughness_model_comparison.csv"
PREFLIGHT_DIR = ROOT / "results/analysis/oscillator_physics_preflight"
RAW_DIR = ROOT / "results/csv/physical_oscillator_decoder"
ANALYSIS_DIR = ROOT / "results/analysis/physical_oscillator_decoder"
TRIAL_CSV = RAW_DIR / "physical_oscillator_decoder_trials.csv"
SUMMARY_CSV = RAW_DIR / "physical_oscillator_decoder_summary.csv"
PREDICTIONS_CSV = ANALYSIS_DIR / "physical_oscillator_predictions.csv"
PERFORMANCE_CSV = ANALYSIS_DIR / "physical_oscillator_model_performance.csv"
SCALING_CSV = ANALYSIS_DIR / "physical_oscillator_scaling_audit.csv"
REPORT_TXT = ANALYSIS_DIR / "physical_oscillator_decoder_report.txt"

TRIAL_FIELDS = (
    "noise_family", "carrier_frequency_hz", "target_sigma_y_1s", "realized_sigma_y_1s",
    "snr_db", "trial_index", "oscillator_seed", "noise_seed", "decoded_success",
    "decoded_message", "reported_snr", "reported_drift", "reported_frequency",
    "raw_frequency_rms_hz", "raw_max_abs_frequency_hz", "residual_frequency_rms_hz",
    "residual_max_abs_frequency_hz", "residual_peak_to_peak_hz",
    "max_abs_phase_rad", "phase_rms_rad", "phase_peak_to_peak_rad",
    "fitted_constant_hz", "fitted_linear_coefficient", "dot_with_constant",
    "dot_with_x", "runtime_seconds",
)
SUMMARY_FIELDS = (
    "noise_family", "carrier_frequency_hz", "target_sigma_y_1s", "snr_db",
    "n", "successes", "p_decode", "Wilson95_low", "Wilson95_high",
    "median_realized_sigma_y_1s", "median_residual_frequency_rms_hz",
    "median_residual_max_abs_frequency_hz", "median_max_abs_phase_rad",
    "mean_runtime_seconds",
)
DESCRIPTOR_FIELDS = (
    "realized_sigma_y_1s", "raw_frequency_rms_hz", "raw_max_abs_frequency_hz",
    "residual_frequency_rms_hz", "residual_max_abs_frequency_hz",
    "residual_peak_to_peak_hz", "max_abs_phase_rad", "phase_rms_rad",
    "phase_peak_to_peak_rad", "fitted_constant_hz", "fitted_linear_coefficient",
    "dot_with_constant", "dot_with_x",
)
_CLEAN_WAVEFORM = None
_X = (np.arange(SYMBOL_COUNT) - 81.0) / 81.0
_BASIS = np.column_stack((np.ones_like(_X), _X))
_CENTER_TIMES = (np.arange(SYMBOL_COUNT) + 0.5) * SYMBOL_DURATION_S
_SAMPLED_INDEX = np.floor(_CENTER_TIMES).astype(int)
_N_SECONDS = int(_SAMPLED_INDEX.max()) + 2


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_preflight() -> tuple[dict[str, float], list[dict[str, object]]]:
    required = (
        PREFLIGHT_DIR / "oscillator_preflight_trajectory_metrics.csv",
        PREFLIGHT_DIR / "oscillator_preflight_summary.csv",
        PREFLIGHT_DIR / "oscillator_allan_deviation.csv",
    )
    assert all(path.is_file() for path in required)
    with required[0].open(newline="") as source:
        assert sum(1 for _ in source) - 1 == 30000
    blocks = {}
    for family_index, family in enumerate(NOISE_TYPES):
        blocks[family] = np.stack([
            base_process(family, PREFLIGHT_SEED_BASE + family_index * 100000 + j, _N_SECONDS)
            for j in range(500)
        ])
    slope_rows, _ = slope_check(blocks, _SAMPLED_INDEX, _BASIS)
    calibrations = {str(row["noise_type"]): float(row["base_adev_at_1s"]) for row in slope_rows}
    assert set(calibrations) == set(NOISE_TYPES)
    return calibrations, slope_rows


def verify_matched_noise() -> None:
    seed = NOISE_SEED_BASE
    zeros = (0j,) * 12
    shifted = (1 + 2j,) * 12
    noise_a = add_awgn(zeros, SNR_GRID_DB[0], random.Random(seed), signal_power=1.0)
    noise_b = add_awgn(shifted, SNR_GRID_DB[0], random.Random(seed), signal_power=1.0)
    assert all(abs((b - s) - a) < 1e-12 for a, b, s in zip(noise_a, noise_b, shifted))
    # Same seed and active signal power reproduce the same additive noise stream.


def validate_specification() -> None:
    assert len(NOISE_TYPES) == 3
    assert len(CARRIER_FREQUENCY_HZ) == 3
    assert len(TARGET_SIGMA_Y_1S) == 3
    assert len(SNR_GRID_DB) == 2
    assert N_PER_CONDITION == 100
    assert len(NOISE_TYPES) * len(CARRIER_FREQUENCY_HZ) * len(TARGET_SIGMA_Y_1S) * len(SNR_GRID_DB) == TOTAL_CONDITIONS == 54
    assert TOTAL_CONDITIONS * N_PER_CONDITION == TOTAL_TRIALS == 5400
    assert (SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT) == (375, 256, 162)
    assert DECODER_SCRIPT.is_file() and (ROOT / ".cache/runtime/usr/bin/wsprd").is_file()
    assert RMS_MODEL_SOURCE.is_file()
    assert not RAW_DIR.exists() and not ANALYSIS_DIR.exists(), "Refusing to overwrite prior physical sweep outputs"


def oscillator_seed(family_index: int, carrier_index: int, stability_index: int, trial_index: int) -> int:
    return (OSCILLATOR_SEED_BASE + family_index * 1_000_000 + carrier_index * 100_000
            + stability_index * 10_000 + trial_index)


def noise_seed(snr_index: int, trial_index: int) -> int:
    return NOISE_SEED_BASE + snr_index * 10_000 + trial_index


def tasks(calibrations: dict[str, float]) -> list[tuple[object, ...]]:
    return [
        (family, carrier, stability, snr, trial_index,
         oscillator_seed(family_index, carrier_index, stability_index, trial_index),
         noise_seed(snr_index, trial_index), calibrations[family])
        for family_index, family in enumerate(NOISE_TYPES)
        for carrier_index, carrier in enumerate(CARRIER_FREQUENCY_HZ)
        for stability_index, stability in enumerate(TARGET_SIGMA_Y_1S)
        for trial_index in range(N_PER_CONDITION)
        for snr_index, snr in enumerate(SNR_GRID_DB)
    ]


def trajectory(family: str, carrier: float, target_sigma: float, seed: int,
               calibration: float) -> tuple[dict[str, float], np.ndarray]:
    fractional = base_process(family, seed, _N_SECONDS)
    realized = math.sqrt(float(allan_variance(fractional, 1))) * target_sigma / calibration
    raw = carrier * (target_sigma / calibration) * fractional[_SAMPLED_INDEX]
    beta = np.linalg.lstsq(_BASIS, raw, rcond=None)[0]
    residual = raw - _BASIS @ beta
    dot_one = float(np.dot(residual, _BASIS[:, 0]))
    dot_x = float(np.dot(residual, _X))
    if abs(dot_one) >= 1e-10 or abs(dot_x) >= 1e-10:
        raise AssertionError(f"Orthogonality failed: seed={seed} dot_one={dot_one} dot_x={dot_x}")
    max_phase, rms_phase = phase_descriptors(residual)
    phase_edges = np.concatenate(([0.0], np.cumsum(residual * (2 * np.pi * SYMBOL_DURATION_S))))
    descriptors = {
        "realized_sigma_y_1s": realized,
        "raw_frequency_rms_hz": float(np.sqrt(np.mean(raw**2))),
        "raw_max_abs_frequency_hz": float(np.max(np.abs(raw))),
        "residual_frequency_rms_hz": float(np.sqrt(np.mean(residual**2))),
        "residual_max_abs_frequency_hz": float(np.max(np.abs(residual))),
        "residual_peak_to_peak_hz": float(np.ptp(residual)),
        "max_abs_phase_rad": max_phase, "phase_rms_rad": rms_phase,
        "phase_peak_to_peak_rad": float(np.ptp(phase_edges)),
        "fitted_constant_hz": float(beta[0]),
        "fitted_linear_coefficient": float(beta[1]),
        "dot_with_constant": dot_one, "dot_with_x": dot_x,
    }
    assert np.isfinite(list(descriptors.values())).all()
    return descriptors, residual


def initialize_worker() -> None:
    global _CLEAN_WAVEFORM
    _CLEAN_WAVEFORM = generate_complex_baseband(encode_type1(MESSAGE).channel_symbols)
    assert _CLEAN_WAVEFORM.signal_sample_count == SYMBOL_COUNT * SAMPLES_PER_SYMBOL


def parse_decoder_output(stdout: str) -> tuple[int, str, str, str, str]:
    messages = []
    exact = None
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) == 8 and re.fullmatch(r"[0-9]{4}", fields[0]):
            messages.append(" ".join(fields[5:8]))
            if fields[5:8] == MESSAGE.split():
                exact = fields
    if exact is None:
        return 0, " | ".join(messages), "", "", ""
    return 1, MESSAGE, exact[1], exact[4], exact[3]


def run_trial(task: tuple[object, ...]) -> dict[str, object]:
    family, carrier, stability, snr, trial_index, oscillator_seed_value, noise_seed_value, calibration = task
    started = time.perf_counter()
    if _CLEAN_WAVEFORM is None:
        raise RuntimeError("Worker waveform is not initialized")
    descriptors, residual = trajectory(family, carrier, stability, oscillator_seed_value, calibration)
    active = np.repeat(residual, SAMPLES_PER_SYMBOL)
    full = embed_active_trajectory(
        len(_CLEAN_WAVEFORM.samples), _CLEAN_WAVEFORM.frame_start_sample,
        tuple(float(value) for value in active),
    )
    impaired = replace(_CLEAN_WAVEFORM, samples=apply_frequency_error(
        _CLEAN_WAVEFORM.samples, full, _CLEAN_WAVEFORM.sample_rate_hz,
    ))
    noisy = replace(impaired, samples=add_awgn(
        impaired.samples, snr, random.Random(noise_seed_value), signal_power=1.0,
    ))
    with tempfile.TemporaryDirectory(prefix="wspr-physical-oscillator-") as directory:
        work = Path(directory)
        filename = "260925_0000.c2"
        write_c2(work / filename, noisy)
        process = subprocess.run(
            ["bash", str(DECODER_SCRIPT), "-H", "-a", str(work), filename],
            cwd=work, text=True, capture_output=True, check=False,
        )
    if process.returncode != 0:
        raise RuntimeError(
            f"wsprd exit {process.returncode}: {family} carrier={carrier} sigma={stability} "
            f"SNR={snr} trial={trial_index}: {process.stderr}"
        )
    success, message, reported_snr, reported_drift, reported_frequency = parse_decoder_output(process.stdout)
    return {
        "noise_family": family, "carrier_frequency_hz": carrier,
        "target_sigma_y_1s": stability, "realized_sigma_y_1s": descriptors["realized_sigma_y_1s"],
        "snr_db": snr, "trial_index": trial_index,
        "oscillator_seed": oscillator_seed_value, "noise_seed": noise_seed_value,
        "decoded_success": success, "decoded_message": message,
        "reported_snr": reported_snr, "reported_drift": reported_drift,
        "reported_frequency": reported_frequency,
        **{name: descriptors[name] for name in DESCRIPTOR_FIELDS if name != "realized_sigma_y_1s"},
        "runtime_seconds": time.perf_counter() - started,
    }


def validate_trials() -> pd.DataFrame:
    frame = pd.read_csv(TRIAL_CSV)
    assert len(frame) == TOTAL_TRIALS
    keys = ["noise_family", "carrier_frequency_hz", "target_sigma_y_1s", "snr_db"]
    assert len(frame.groupby(keys)) == TOTAL_CONDITIONS
    assert frame.groupby(keys).size().eq(N_PER_CONDITION).all()
    assert frame.groupby(keys)["oscillator_seed"].nunique().eq(N_PER_CONDITION).all()
    assert frame.groupby(keys)["noise_seed"].nunique().eq(N_PER_CONDITION).all()
    assert not frame[keys + ["trial_index"]].duplicated().any()
    assert frame.decoded_success.isin((0, 1)).all()
    assert np.isfinite(frame[list(DESCRIPTOR_FIELDS) + ["runtime_seconds"]]).all().all()
    assert (frame.runtime_seconds >= 0).all()
    assert frame.dot_with_constant.abs().max() < 1e-10
    assert frame.dot_with_x.abs().max() < 1e-10
    paired_keys = ["noise_family", "carrier_frequency_hz", "target_sigma_y_1s", "trial_index"]
    assert frame.groupby(paired_keys).size().eq(2).all()
    assert frame.groupby(paired_keys)["oscillator_seed"].nunique().eq(1).all()
    assert frame.groupby(paired_keys)[list(DESCRIPTOR_FIELDS)].nunique().eq(1).all().all()
    assert frame.groupby(["snr_db", "trial_index"])["noise_seed"].nunique().eq(1).all()
    for snr_index, snr in enumerate(SNR_GRID_DB):
        expected = {noise_seed(snr_index, trial) for trial in range(N_PER_CONDITION)}
        assert all(set(group.noise_seed) == expected for _, group in frame[frame.snr_db == snr].groupby(keys))
    return frame


def summarize(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["noise_family", "carrier_frequency_hz", "target_sigma_y_1s", "snr_db"]
    for (family, carrier, stability, snr), group in frame.groupby(keys, sort=False):
        successes = int(group.decoded_success.sum())
        low, high = wilson_interval(successes, N_PER_CONDITION)
        rows.append({
            "noise_family": family, "carrier_frequency_hz": carrier,
            "target_sigma_y_1s": stability, "snr_db": snr,
            "n": len(group), "successes": successes,
            "p_decode": successes / N_PER_CONDITION,
            "Wilson95_low": low, "Wilson95_high": high,
            "median_realized_sigma_y_1s": float(group.realized_sigma_y_1s.median()),
            "median_residual_frequency_rms_hz": float(group.residual_frequency_rms_hz.median()),
            "median_residual_max_abs_frequency_hz": float(group.residual_max_abs_frequency_hz.median()),
            "median_max_abs_phase_rad": float(group.max_abs_phase_rad.median()),
            "mean_runtime_seconds": float(group.runtime_seconds.mean()),
        })
    result = pd.DataFrame(rows, columns=SUMMARY_FIELDS)
    assert len(result) == TOTAL_CONDITIONS
    assert np.array_equal(result.p_decode.to_numpy(), result.successes.to_numpy() / N_PER_CONDITION)
    return result


def scaling_audit(frame: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    physical = frame[frame.snr_db == SNR_GRID_DB[0]].copy()
    assert len(physical) == TOTAL_TRIALS // len(SNR_GRID_DB)
    rows = []
    for (family, carrier, stability), group in physical.groupby(
        ["noise_family", "carrier_frequency_hz", "target_sigma_y_1s"], sort=False
    ):
        rows.append({
            "noise_family": family, "carrier_frequency_hz": carrier,
            "target_sigma_y_1s": stability, "n_trajectories": len(group),
            "median_residual_frequency_rms_hz": float(group.residual_frequency_rms_hz.median()),
        })
    audit = pd.DataFrame(rows)
    assert len(audit) == len(NOISE_TYPES) * len(CARRIER_FREQUENCY_HZ) * len(TARGET_SIGMA_Y_1S)
    max_ratio_error = 0.0
    for family in NOISE_TYPES:
        subset = audit[audit.noise_family == family]
        for stability in TARGET_SIGMA_Y_1S:
            sequence = subset[subset.target_sigma_y_1s == stability].sort_values("carrier_frequency_hz")
            values = sequence.median_residual_frequency_rms_hz.to_numpy()
            assert np.diff(values).min() > 0
            ratios = values[1:] / values[:-1]
            expected = np.array(CARRIER_FREQUENCY_HZ[1:]) / np.array(CARRIER_FREQUENCY_HZ[:-1])
            max_ratio_error = max(max_ratio_error, float(np.max(np.abs(ratios / expected - 1))))
        for carrier in CARRIER_FREQUENCY_HZ:
            sequence = subset[subset.carrier_frequency_hz == carrier].sort_values("target_sigma_y_1s")
            values = sequence.median_residual_frequency_rms_hz.to_numpy()
            assert np.diff(values).min() > 0
            ratios = values[1:] / values[:-1]
            expected = np.array(TARGET_SIGMA_Y_1S[1:]) / np.array(TARGET_SIGMA_Y_1S[:-1])
            max_ratio_error = max(max_ratio_error, float(np.max(np.abs(ratios / expected - 1))))
    assert max_ratio_error < 0.30, f"Median scaling differs more than 30%: {max_ratio_error}"
    return audit, max_ratio_error


def frozen_rms_coefficients() -> tuple[dict[str, float], str]:
    saved = pd.read_csv(RMS_MODEL_SOURCE)
    row = saved.loc[saved.model == "M_RMS"]
    assert len(row) == 1 and int(row.iloc[0].n_rows) == 5400
    coefficients = ast.literal_eval(row.iloc[0].coefficients)
    assert set(coefficients) == {"intercept", "snr_c", "frequency_rms_hz"}
    assert np.isfinite(list(coefficients.values())).all()
    return coefficients, hash_file(RMS_MODEL_SOURCE)


def score_model(frame: pd.DataFrame, coefficients: dict[str, float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    eta = (coefficients["intercept"]
           + coefficients["snr_c"] * (frame.snr_db.to_numpy() + 30.5)
           + coefficients["frequency_rms_hz"] * frame.residual_frequency_rms_hz.to_numpy())
    y = frame.decoded_success.to_numpy()
    predictions = frame[["noise_family", "carrier_frequency_hz", "target_sigma_y_1s", "snr_db",
                         "trial_index", "oscillator_seed", "noise_seed", "realized_sigma_y_1s",
                         "residual_frequency_rms_hz", "decoded_success"]].copy()
    predictions["predicted_probability"] = expit(eta)
    predictions["brier_loss"] = (y - predictions.predicted_probability.to_numpy()) ** 2
    predictions["log_loss"] = np.logaddexp(0, eta) - y * eta
    assert len(predictions) == TOTAL_TRIALS and np.isfinite(predictions[["predicted_probability", "brier_loss", "log_loss"]]).all().all()
    rows = []
    for scope, column in (("overall", None), ("noise_family", "noise_family"),
                          ("carrier_frequency_hz", "carrier_frequency_hz"),
                          ("target_sigma_y_1s", "target_sigma_y_1s")):
        groups = [("all", predictions)] if column is None else predictions.groupby(column, sort=False)
        for value, group in groups:
            rows.append({"scope": scope, "value": value, "n": len(group),
                         "brier_score": float(group.brier_loss.mean()),
                         "log_loss": float(group.log_loss.mean())})
    return predictions, pd.DataFrame(rows)


def main() -> None:
    validate_specification()
    verify_matched_noise()
    calibrations, slopes = verify_preflight()
    coefficients, model_hash = frozen_rms_coefficients()
    task_list = tasks(calibrations)
    assert len(task_list) == TOTAL_TRIALS
    assert len({task[5] for task in task_list}) == TOTAL_TRIALS // 2
    assert {task[6] for task in task_list} == {
        noise_seed(snr_index, trial) for snr_index in range(len(SNR_GRID_DB))
        for trial in range(N_PER_CONDITION)
    }
    RAW_DIR.mkdir(parents=True)
    ANALYSIS_DIR.mkdir(parents=True)
    started = time.perf_counter()
    with TRIAL_CSV.open("x", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=TRIAL_FIELDS)
        writer.writeheader()
        with ProcessPoolExecutor(max_workers=WORKERS, initializer=initialize_worker) as pool:
            futures = [pool.submit(run_trial, task) for task in task_list]
            for completed, future in enumerate(as_completed(futures), 1):
                writer.writerow(future.result())
                target.flush()
                if completed % 100 == 0 or completed == TOTAL_TRIALS:
                    print(f"[{completed}/{TOTAL_TRIALS}]", file=sys.stderr, flush=True)

    trials = validate_trials()
    summary = summarize(trials)
    scaling, max_scaling_error = scaling_audit(trials)
    predictions, performance = score_model(trials, coefficients)
    summary.to_csv(SUMMARY_CSV, index=False)
    scaling.to_csv(SCALING_CSV, index=False)
    predictions.to_csv(PREDICTIONS_CSV, index=False)
    performance.to_csv(PERFORMANCE_CSV, index=False)
    assert len(pd.read_csv(SUMMARY_CSV)) == TOTAL_CONDITIONS
    assert len(pd.read_csv(PREDICTIONS_CSV)) == TOTAL_TRIALS
    assert len(pd.read_csv(SCALING_CSV)) == 27
    runtime = time.perf_counter() - started
    report = (
        "EXPERIMENT_SPEC\n"
        f"families={list(NOISE_TYPES)} carriers_hz={list(CARRIER_FREQUENCY_HZ)} "
        f"sigma_y_1s={list(TARGET_SIGMA_Y_1S)} snrs_db={list(SNR_GRID_DB)} "
        f"N={N_PER_CONDITION} conditions={TOTAL_CONDITIONS} workers={WORKERS}\n"
        f"generator=oscillator_physics_preflight.base_process; calibration=ensemble_ADEV_1s; "
        f"symbol_sampling=zero_order_hold_at_centers; decoder=production_wsprd; "
        f"runtime_seconds={runtime:.3f}\n"
        f"oscillator_seed={OSCILLATOR_SEED_BASE}+family_index*1000000+carrier_index*100000+"
        f"stability_index*10000+trial_index\n"
        f"noise_seed={NOISE_SEED_BASE}+snr_index*10000+trial_index\n"
        f"matched_noise_check=passed matched_trajectory_check=passed "
        f"model_source={RMS_MODEL_SOURCE} model_sha256={model_hash} model_coefficients={coefficients}\n"
        f"preflight_slopes={slopes}\n"
        "TOTAL_TRIALS\n5400\n"
        "PHYSICAL_DECODER_SUMMARY\n" + summary.to_csv(index=False)
        + "SCALING_AUDIT\n" + scaling.to_csv(index=False)
        + f"max_relative_median_scaling_ratio_error={max_scaling_error:.6g}\n"
        + "ORTHOGONALITY_CHECK\n"
        + f"max_abs_dot_constant={trials.dot_with_constant.abs().max():.6g} "
        f"max_abs_dot_x={trials.dot_with_x.abs().max():.6g} tolerance=1e-10\n"
        + "RMS_MODEL_EXTERNAL_PERFORMANCE\n" + performance.to_csv(index=False)
        + "CSV_INTEGRITY_CHECK\n"
        + "trial_rows=5400 conditions=54 rows_per_condition=100 unique_oscillator_seeds=100 "
        "unique_noise_seeds=100 summary_rows=54 paired_trajectory_descriptors=True "
        "matched_noise_seeds=True descriptors_finite=True\n"
        + "OUTPUT_PATHS\n" + "\n".join(str(path) for path in (
            TRIAL_CSV, SUMMARY_CSV, PREDICTIONS_CSV, PERFORMANCE_CSV, SCALING_CSV, REPORT_TXT
        )) + "\n"
    )
    REPORT_TXT.write_text(report)
    print(report, end="")


if __name__ == "__main__":
    main()
