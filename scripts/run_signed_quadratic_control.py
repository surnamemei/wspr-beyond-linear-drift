#!/usr/bin/env python3
"""Run signed orthogonal-quadratic controls with thermal-matched noise seeds."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analysis.metrics import wilson_interval
from impairments.frequency import (
    apply_frequency_error, embed_active_trajectory,
    wspr_symbol_quadratic_residual_trajectory,
)
from impairments.noise import add_awgn
from wspr.encoder import encode_type1
from wspr.waveform import generate_complex_baseband, write_c2

A_RES_GRID_HZ = (0.25, -0.25, 0.5, -0.5)
ABS_A_GRID_HZ = (0.25, 0.5)
SNR_GRID = (-30.0, -30.5, -31.0)
N_PER_CONDITION = 100
TOTAL_TRIALS = 1200
TOTAL_CONDITIONS = 12
BASE_SEED = 2026100200
WORKERS = min(4, os.cpu_count() or 1)
MESSAGE = "K1ABC FN42 33"
OUTPUT_DIR = ROOT / "results/csv/signed_quadratic_control"
ANALYSIS_DIR = ROOT / "results/analysis/signed_quadratic_control"
TRIAL_CSV = OUTPUT_DIR / "signed_quadratic_control_trials.csv"
SUMMARY_CSV = OUTPUT_DIR / "signed_quadratic_control_summary.csv"
COMPARISON_CSV = ANALYSIS_DIR / "thermal_vs_signed_quadratic.csv"
THERMAL_TRIAL_CSV = ROOT / "results/csv/thermal_amplitude_match/thermal_amplitude_match_trials.csv"
THERMAL_SUMMARY_CSV = ROOT / "results/csv/thermal_amplitude_match/thermal_amplitude_match_summary.csv"
THERMAL_COMPARISON_CSV = ROOT / "results/analysis/thermal_amplitude_match/thermal_vs_quadratic_comparison.csv"

TRIAL_FIELDS = (
    "snr_db", "signed_A_res_hz", "abs_A_res_hz", "trial_index", "seed",
    "decoded_success", "decoded_message", "reported_snr", "reported_drift",
    "reported_frequency", "runtime_seconds",
)
SUMMARY_FIELDS = (
    "snr_db", "signed_A_res_hz", "n", "successes", "p_decode",
    "Wilson95_low", "Wilson95_high",
)
PAIRED_FIELDS = (
    "snr_db", "abs_A_res_hz", "both_decode", "positive_only",
    "negative_only", "neither",
)
COMPARISON_FIELDS = (
    "snr_db", "tau_seconds", "abs_A_res_hz", "thermal_p_decode",
    "positive_quadratic_p_decode", "negative_quadratic_p_decode",
    "thermal_minus_positive", "thermal_minus_negative",
    "thermal_shape_correlation_with_positive_quadratic",
)

_CLEAN_WAVEFORM = None
_IMPAIRED_CACHE: dict[float, object] = {}
_QUADRATIC_BASIS: np.ndarray | None = None


def validate_specification() -> None:
    assert A_RES_GRID_HZ == (0.25, -0.25, 0.5, -0.5)
    assert SNR_GRID == (-30.0, -30.5, -31.0)
    assert N_PER_CONDITION == 100
    assert len(A_RES_GRID_HZ) * len(SNR_GRID) == TOTAL_CONDITIONS == 12
    assert TOTAL_CONDITIONS * N_PER_CONDITION == TOTAL_TRIALS == 1200


def validated_basis() -> np.ndarray:
    basis = np.asarray(
        wspr_symbol_quadratic_residual_trajectory(162, 256, 1.0), dtype=float
    )
    assert basis.shape == (162 * 256,)
    assert np.isclose(np.max(np.abs(basis)), 1.0, rtol=0, atol=1e-14)
    for absolute_amplitude in ABS_A_GRID_HZ:
        positive = absolute_amplitude * basis
        negative = -absolute_amplitude * basis
        validated_positive = np.asarray(
            wspr_symbol_quadratic_residual_trajectory(162, 256, absolute_amplitude),
            dtype=float,
        )
        assert np.array_equal(positive, validated_positive)
        assert np.array_equal(negative, -positive)
        assert np.isclose(np.max(np.abs(negative)), absolute_amplitude,
                          rtol=0, atol=1e-14)
    return basis


def initialize_worker() -> None:
    global _CLEAN_WAVEFORM, _IMPAIRED_CACHE, _QUADRATIC_BASIS
    _CLEAN_WAVEFORM = generate_complex_baseband(encode_type1(MESSAGE).channel_symbols)
    _IMPAIRED_CACHE = {}
    _QUADRATIC_BASIS = validated_basis()


def impaired_waveform(signed_amplitude_hz: float):
    if signed_amplitude_hz in _IMPAIRED_CACHE:
        return _IMPAIRED_CACHE[signed_amplitude_hz]
    if _CLEAN_WAVEFORM is None or _CLEAN_WAVEFORM.signal_sample_count != 162 * 256:
        raise RuntimeError("worker requires a 162x256 clean WSPR frame")
    if _QUADRATIC_BASIS is None:
        raise RuntimeError("worker requires validated quadratic basis")
    active = tuple(float(value) for value in signed_amplitude_hz * _QUADRATIC_BASIS)
    full = embed_active_trajectory(
        len(_CLEAN_WAVEFORM.samples), _CLEAN_WAVEFORM.frame_start_sample, active
    )
    samples = apply_frequency_error(
        _CLEAN_WAVEFORM.samples, full, _CLEAN_WAVEFORM.sample_rate_hz
    )
    waveform = replace(_CLEAN_WAVEFORM, samples=samples)
    _IMPAIRED_CACHE[signed_amplitude_hz] = waveform
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


def run_trial(task: tuple[float, float, int, int]) -> dict[str, object]:
    snr_db, signed_amplitude_hz, trial_index, seed = task
    started = time.perf_counter()
    clean = impaired_waveform(signed_amplitude_hz)
    noisy = add_awgn(clean.samples, snr_db, random.Random(seed), signal_power=1.0)
    waveform = replace(clean, samples=noisy)
    with tempfile.TemporaryDirectory(prefix="wspr-signed-quadratic-") as directory:
        work = Path(directory)
        filename = "260925_0000.c2"
        write_c2(work / filename, waveform)
        process = subprocess.run(
            ["bash", str(ROOT / "scripts/wsprd.sh"), "-H", "-a", str(work), filename],
            cwd=work, text=True, capture_output=True, check=False,
        )
    if process.returncode != 0:
        raise RuntimeError(
            f"wsprd failed for SNR={snr_db}, signed_A={signed_amplitude_hz}, "
            f"trial={trial_index}, seed={seed}: {process.stderr.strip()}"
        )
    success, message, reported_snr, reported_drift, reported_frequency = (
        parse_decoder_output(process.stdout)
    )
    return {
        "snr_db": snr_db, "signed_A_res_hz": signed_amplitude_hz,
        "abs_A_res_hz": abs(signed_amplitude_hz), "trial_index": trial_index,
        "seed": seed, "decoded_success": int(success),
        "decoded_message": message, "reported_snr": reported_snr,
        "reported_drift": reported_drift, "reported_frequency": reported_frequency,
        "runtime_seconds": time.perf_counter() - started,
    }


def build_tasks() -> list[tuple[float, float, int, int]]:
    return [
        (snr_db, amplitude, trial_index, BASE_SEED + snr_index * 10_000 + trial_index)
        for snr_index, snr_db in enumerate(SNR_GRID)
        for amplitude in A_RES_GRID_HZ
        for trial_index in range(N_PER_CONDITION)
    ]


def validate_trials(rows: list[dict[str, str]]) -> dict[tuple[float, float], list[dict[str, str]]]:
    assert len(rows) == TOTAL_TRIALS
    grouped: dict[tuple[float, float], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        assert row["decoded_success"] in {"0", "1"}
        snr = float(row["snr_db"])
        amplitude = float(row["signed_A_res_hz"])
        assert snr in SNR_GRID and amplitude in A_RES_GRID_HZ
        assert float(row["abs_A_res_hz"]) == abs(amplitude)
        grouped[(snr, amplitude)].append(row)
    assert len(grouped) == TOTAL_CONDITIONS
    for selected in grouped.values():
        assert len(selected) == N_PER_CONDITION
        assert len({int(row["seed"]) for row in selected}) == N_PER_CONDITION
        assert {int(row["trial_index"]) for row in selected} == set(range(N_PER_CONDITION))
    for snr_index, snr in enumerate(SNR_GRID):
        expected = {BASE_SEED + snr_index * 10_000 + index
                    for index in range(N_PER_CONDITION)}
        for amplitude in A_RES_GRID_HZ:
            assert {int(row["seed"]) for row in grouped[(snr, amplitude)]} == expected
    return grouped


def make_summaries(grouped: dict[tuple[float, float], list[dict[str, str]]]) -> list[dict[str, object]]:
    rows = []
    for snr in SNR_GRID:
        for amplitude in A_RES_GRID_HZ:
            selected = grouped[(snr, amplitude)]
            successes = sum(int(row["decoded_success"]) for row in selected)
            low, high = wilson_interval(successes, N_PER_CONDITION)
            rows.append({
                "snr_db": snr, "signed_A_res_hz": amplitude,
                "n": len(selected), "successes": successes,
                "p_decode": successes / N_PER_CONDITION,
                "Wilson95_low": low, "Wilson95_high": high,
            })
    assert len(rows) == TOTAL_CONDITIONS
    assert all(row["p_decode"] == row["successes"] / N_PER_CONDITION for row in rows)
    return rows


def paired_sign_counts(grouped: dict[tuple[float, float], list[dict[str, str]]]) -> list[dict[str, object]]:
    rows = []
    for snr in SNR_GRID:
        for absolute_amplitude in ABS_A_GRID_HZ:
            positive = {int(row["seed"]): int(row["decoded_success"])
                        for row in grouped[(snr, absolute_amplitude)]}
            negative = {int(row["seed"]): int(row["decoded_success"])
                        for row in grouped[(snr, -absolute_amplitude)]}
            assert positive.keys() == negative.keys()
            both = sum(positive[seed] == 1 and negative[seed] == 1 for seed in positive)
            positive_only = sum(positive[seed] == 1 and negative[seed] == 0 for seed in positive)
            negative_only = sum(positive[seed] == 0 and negative[seed] == 1 for seed in positive)
            neither = sum(positive[seed] == 0 and negative[seed] == 0 for seed in positive)
            assert both + positive_only + negative_only + neither == N_PER_CONDITION
            rows.append({
                "snr_db": snr, "abs_A_res_hz": absolute_amplitude,
                "both_decode": both, "positive_only": positive_only,
                "negative_only": negative_only, "neither": neither,
            })
    assert len(rows) == len(SNR_GRID) * len(ABS_A_GRID_HZ)
    return rows


def compare_thermal(summaries: list[dict[str, object]]) -> list[dict[str, object]]:
    with THERMAL_TRIAL_CSV.open(newline="") as handle:
        thermal_trials = list(csv.DictReader(handle))
    with THERMAL_SUMMARY_CSV.open(newline="") as handle:
        thermal_summary = list(csv.DictReader(handle))
    with THERMAL_COMPARISON_CSV.open(newline="") as handle:
        old_comparison = list(csv.DictReader(handle))
    assert len(thermal_trials) == 1800 and len(thermal_summary) == 18
    assert len(old_comparison) == 18
    thermal_seeds: dict[float, set[int]] = defaultdict(set)
    for row in thermal_trials:
        thermal_seeds[float(row["snr_db"])].add(int(row["seed"]))
    for snr_index, snr in enumerate(SNR_GRID):
        expected = {BASE_SEED + snr_index * 10_000 + index
                    for index in range(N_PER_CONDITION)}
        assert thermal_seeds[snr] == expected
    thermal_lookup = {
        (float(row["snr_db"]), int(row["tau_seconds"]), float(row["target_A_res_hz"])): row
        for row in thermal_summary
    }
    shape_lookup = {
        (float(row["snr_db"]), int(row["tau_seconds"]), float(row["target_A_res_hz"])):
        float(row["shape_correlation"])
        for row in old_comparison
    }
    quadratic_lookup = {
        (float(row["snr_db"]), float(row["signed_A_res_hz"])): row
        for row in summaries
    }
    assert len(thermal_lookup) == 18 and len(shape_lookup) == 18
    rows = []
    for snr in SNR_GRID:
        for tau in (30, 60, 120):
            for absolute_amplitude in ABS_A_GRID_HZ:
                thermal = thermal_lookup[(snr, tau, absolute_amplitude)]
                correlation = shape_lookup[(snr, tau, absolute_amplitude)]
                assert correlation < 0
                thermal_p = float(thermal["p_decode"])
                positive_p = float(quadratic_lookup[(snr, absolute_amplitude)]["p_decode"])
                negative_p = float(quadratic_lookup[(snr, -absolute_amplitude)]["p_decode"])
                rows.append({
                    "snr_db": snr, "tau_seconds": tau,
                    "abs_A_res_hz": absolute_amplitude,
                    "thermal_p_decode": thermal_p,
                    "positive_quadratic_p_decode": positive_p,
                    "negative_quadratic_p_decode": negative_p,
                    "thermal_minus_positive": thermal_p - positive_p,
                    "thermal_minus_negative": thermal_p - negative_p,
                    "thermal_shape_correlation_with_positive_quadratic": correlation,
                })
    assert len(rows) == 18
    return rows


def print_table(fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
    validate_specification()
    validated_basis()
    for source in (THERMAL_TRIAL_CSV, THERMAL_SUMMARY_CSV, THERMAL_COMPARISON_CSV):
        if not source.is_file():
            raise FileNotFoundError(source)
    for output in (TRIAL_CSV, SUMMARY_CSV, COMPARISON_CSV):
        if output.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {output}")
    tasks = build_tasks()
    assert len(tasks) == TOTAL_TRIALS
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    progress: Counter[tuple[float, float]] = Counter()
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
                key = (float(row["snr_db"]), float(row["signed_A_res_hz"]))
                progress[key] += 1
                if progress[key] == 1 or progress[key] % 25 == 0:
                    print(
                        f"[SNR {key[0]:.1f} | signed A {key[1]:+.2f} | "
                        f"{progress[key]}/{N_PER_CONDITION}]",
                        file=sys.stderr, flush=True,
                    )
    with TRIAL_CSV.open(newline="") as handle:
        trials = list(csv.DictReader(handle))
    grouped = validate_trials(trials)
    summaries = make_summaries(grouped)
    with SUMMARY_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summaries)
    with SUMMARY_CSV.open(newline="") as handle:
        stored_summaries = list(csv.DictReader(handle))
    assert len(stored_summaries) == TOTAL_CONDITIONS
    assert all(float(row["p_decode"]) == int(row["successes"]) / N_PER_CONDITION
               for row in stored_summaries)
    paired = paired_sign_counts(grouped)
    comparison = compare_thermal(summaries)
    with COMPARISON_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMPARISON_FIELDS)
        writer.writeheader()
        writer.writerows(comparison)
    with COMPARISON_CSV.open(newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 18
    print("EXPERIMENT_SPEC")
    print(f"A_RES_GRID_HZ={list(A_RES_GRID_HZ)}")
    print(f"SNR_GRID={list(SNR_GRID)}")
    print(f"N_PER_CONDITION={N_PER_CONDITION}")
    print(f"SEED_RULE={BASE_SEED} + snr_index*10000 + trial_index")
    print("TRAJECTORY=signed_A_res_hz * wspr_symbol_quadratic_residual_trajectory(162,256,1.0)")
    print("TOTAL_TRIALS")
    print(TOTAL_TRIALS)
    print("SIGNED_QUADRATIC_SUMMARY")
    print_table(SUMMARY_FIELDS, summaries)
    print("PAIRED_SIGN_COMPARISON")
    print_table(PAIRED_FIELDS, paired)
    print("THERMAL_VS_SIGNED_QUADRATIC")
    print_table(COMPARISON_FIELDS, comparison)
    print("CSV_INTEGRITY_CHECK")
    print("PASS")
    print("OUTPUT_PATHS")
    for path in (TRIAL_CSV, SUMMARY_CSV, COMPARISON_CSV):
        print(path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, RuntimeError, ValueError) as error:
        print(f"signed quadratic control failed: {error}", file=sys.stderr)
        raise SystemExit(1)
