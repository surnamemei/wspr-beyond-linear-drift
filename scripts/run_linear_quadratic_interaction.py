#!/usr/bin/env python3
"""Execute the fixed-linear-drift and quadratic-residual interaction grid."""

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analysis.metrics import wilson_interval
from impairments.frequency import (
    apply_frequency_error,
    embed_active_trajectory,
    wsprd_linear_drift_trajectory,
    wspr_symbol_quadratic_residual_trajectory,
)
from impairments.noise import add_awgn
from wspr.encoder import encode_type1
from wspr.waveform import generate_complex_baseband, write_c2

LINEAR_DRIFT_HZ = 0.5
SNR_GRID = (-29.5, -30.0, -30.5, -31.0)
A_RES_GRID_HZ = (0.0, 0.125, 0.25, 0.375, 0.5)
N_PER_CONDITION = 100
EXPECTED_CONDITIONS = 20
EXPECTED_TOTAL_TRIALS = 2000
BASE_SEED = 2026092800
WORKERS = min(4, os.cpu_count() or 1)
MESSAGE = "K1ABC FN42 33"
WSPRD_VERSION = (
    "official WSJT-X 3.0.2; binary SHA256 "
    "9e3c2fc14f63c4b4c4e9fcc33b386cd22daf8fe76ce724c5e37f07875e9a3dd9"
)
OUTPUT_DIR = ROOT / "results" / "csv" / "linear_quadratic_interaction"
TRIAL_CSV = OUTPUT_DIR / "linear_quadratic_interaction_trials.csv"
SUMMARY_CSV = OUTPUT_DIR / "linear_quadratic_interaction_summary.csv"
MATRIX_CSV = OUTPUT_DIR / "linear_quadratic_interaction_matrix.csv"

TRIAL_FIELDS = (
    "snr_db", "linear_drift_hz", "A_res_hz", "trial_index", "seed",
    "decoded_success", "decoded_message", "reported_snr", "reported_drift",
    "reported_frequency", "runtime_seconds", "decoder_exit_status",
    "wsprd_version", "decoder_stdout", "decoder_stderr",
)
SUMMARY_FIELDS = (
    "snr_db", "linear_drift_hz", "A_res_hz", "n", "successes",
    "p_decode", "Wilson95_low", "Wilson95_high", "mean_runtime_seconds",
)

_CLEAN_WAVEFORM = None
_IMPAIRED_CACHE: dict[float, object] = {}


def initialize_worker() -> None:
    global _CLEAN_WAVEFORM, _IMPAIRED_CACHE
    _CLEAN_WAVEFORM = generate_complex_baseband(encode_type1(MESSAGE).channel_symbols)
    _IMPAIRED_CACHE = {}


def impaired_waveform(amplitude_hz: float):
    if amplitude_hz in _IMPAIRED_CACHE:
        return _IMPAIRED_CACHE[amplitude_hz]
    if _CLEAN_WAVEFORM is None or _CLEAN_WAVEFORM.signal_sample_count != 162 * 256:
        raise RuntimeError("worker requires a 162x256 clean WSPR frame")
    linear = wsprd_linear_drift_trajectory(162, 256, LINEAR_DRIFT_HZ)
    quadratic = wspr_symbol_quadratic_residual_trajectory(162, 256, amplitude_hz)
    active = tuple(a + b for a, b in zip(linear, quadratic, strict=True))
    full = embed_active_trajectory(
        len(_CLEAN_WAVEFORM.samples), _CLEAN_WAVEFORM.frame_start_sample, active
    )
    samples = apply_frequency_error(
        _CLEAN_WAVEFORM.samples, full, _CLEAN_WAVEFORM.sample_rate_hz
    )
    waveform = replace(_CLEAN_WAVEFORM, samples=samples)
    _IMPAIRED_CACHE[amplitude_hz] = waveform
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
    snr_db, amplitude_hz, trial_index, seed = task
    started = time.perf_counter()
    clean = impaired_waveform(amplitude_hz)
    noisy = add_awgn(clean.samples, snr_db, random.Random(seed), signal_power=1.0)
    waveform = replace(clean, samples=noisy)
    with tempfile.TemporaryDirectory(prefix="wspr-linear-quadratic-") as directory:
        work = Path(directory)
        filename = "260925_0000.c2"
        write_c2(work / filename, waveform)
        process = subprocess.run(
            ["bash", str(ROOT / "scripts" / "wsprd.sh"), "-H", "-a", str(work), filename],
            cwd=work, text=True, capture_output=True, check=False,
        )
    if process.returncode != 0:
        raise RuntimeError(
            f"wsprd failed for SNR={snr_db}, A_res={amplitude_hz}, "
            f"trial={trial_index}, seed={seed}: {process.stderr.strip()}"
        )
    success, message, reported_snr, reported_drift, reported_frequency = (
        parse_decoder_output(process.stdout)
    )
    return {
        "snr_db": snr_db,
        "linear_drift_hz": LINEAR_DRIFT_HZ,
        "A_res_hz": amplitude_hz,
        "trial_index": trial_index,
        "seed": seed,
        "decoded_success": int(success),
        "decoded_message": message,
        "reported_snr": reported_snr,
        "reported_drift": reported_drift,
        "reported_frequency": reported_frequency,
        "runtime_seconds": time.perf_counter() - started,
        "decoder_exit_status": process.returncode,
        "wsprd_version": WSPRD_VERSION,
        "decoder_stdout": process.stdout.strip(),
        "decoder_stderr": process.stderr.strip(),
    }


def validate_specification() -> None:
    assert LINEAR_DRIFT_HZ == 0.5
    assert len(SNR_GRID) == 4
    assert len(A_RES_GRID_HZ) == 5
    assert N_PER_CONDITION == 100
    assert len(SNR_GRID) * len(A_RES_GRID_HZ) * N_PER_CONDITION == EXPECTED_TOTAL_TRIALS == 2000


def build_tasks() -> list[tuple[float, float, int, int]]:
    return [
        (snr_db, amplitude_hz, trial_index, BASE_SEED + snr_index * 10_000 + trial_index)
        for snr_index, snr_db in enumerate(SNR_GRID)
        for amplitude_hz in A_RES_GRID_HZ
        for trial_index in range(N_PER_CONDITION)
    ]


def validate_trials(rows: list[dict[str, str]]) -> None:
    assert len(rows) == EXPECTED_TOTAL_TRIALS
    grouped: dict[tuple[float, float, float], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        assert row["decoded_success"] in {"0", "1"}
        assert float(row["linear_drift_hz"]) == LINEAR_DRIFT_HZ
        grouped[
            (float(row["snr_db"]), float(row["linear_drift_hz"]), float(row["A_res_hz"]))
        ].append(row)
    assert len(grouped) == EXPECTED_CONDITIONS
    for condition_rows in grouped.values():
        assert len(condition_rows) == N_PER_CONDITION
        assert len({int(row["seed"]) for row in condition_rows}) == N_PER_CONDITION
        assert len({int(row["trial_index"]) for row in condition_rows}) == N_PER_CONDITION
    for snr_db in SNR_GRID:
        seed_sets = [
            {int(row["seed"]) for row in grouped[(snr_db, LINEAR_DRIFT_HZ, amplitude_hz)]}
            for amplitude_hz in A_RES_GRID_HZ
        ]
        assert all(seed_set == seed_sets[0] for seed_set in seed_sets[1:])


def make_summaries(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple[float, float], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(float(row["snr_db"]), float(row["A_res_hz"]))].append(row)
    summaries = []
    for snr_db in SNR_GRID:
        for amplitude_hz in A_RES_GRID_HZ:
            selected = grouped[(snr_db, amplitude_hz)]
            successes = sum(int(row["decoded_success"]) for row in selected)
            low, high = wilson_interval(successes, N_PER_CONDITION)
            summaries.append({
                "snr_db": snr_db,
                "linear_drift_hz": LINEAR_DRIFT_HZ,
                "A_res_hz": amplitude_hz,
                "n": len(selected),
                "successes": successes,
                "p_decode": successes / N_PER_CONDITION,
                "Wilson95_low": low,
                "Wilson95_high": high,
                "mean_runtime_seconds": sum(float(row["runtime_seconds"]) for row in selected) / len(selected),
            })
    return summaries


def validate_summaries(rows: list[dict[str, str]]) -> None:
    assert len(rows) == EXPECTED_CONDITIONS
    for row in rows:
        assert int(row["n"]) == N_PER_CONDITION
        assert float(row["linear_drift_hz"]) == LINEAR_DRIFT_HZ
        assert math.isclose(
            float(row["p_decode"]), int(row["successes"]) / N_PER_CONDITION,
            rel_tol=0.0, abs_tol=0.0,
        )


def write_matrix(summaries: list[dict[str, object]]) -> None:
    probabilities = {
        (float(row["snr_db"]), float(row["A_res_hz"])): row["p_decode"]
        for row in summaries
    }
    columns = [f"{amplitude_hz:g}" for amplitude_hz in A_RES_GRID_HZ]
    with MATRIX_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["snr_db", *columns])
        writer.writeheader()
        for snr_db in SNR_GRID:
            row = {"snr_db": snr_db}
            for amplitude_hz, column in zip(A_RES_GRID_HZ, columns):
                row[column] = probabilities[(snr_db, amplitude_hz)]
            writer.writerow(row)


def main() -> int:
    validate_specification()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (TRIAL_CSV, SUMMARY_CSV, MATRIX_CSV):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
    tasks = build_tasks()
    assert len(tasks) == EXPECTED_TOTAL_TRIALS
    started = time.perf_counter()
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
                key = (float(row["snr_db"]), float(row["A_res_hz"]))
                progress[key] += 1
                if progress[key] == 1 or progress[key] % 25 == 0:
                    print(
                        f"[SNR {key[0]:.1f} | A_res {key[1]:g} | {progress[key]}/{N_PER_CONDITION}]",
                        file=sys.stderr, flush=True,
                    )
    with TRIAL_CSV.open(newline="") as handle:
        trials = list(csv.DictReader(handle))
    validate_trials(trials)
    summaries = make_summaries(trials)
    with SUMMARY_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summaries)
    with SUMMARY_CSV.open(newline="") as handle:
        validate_summaries(list(csv.DictReader(handle)))
    write_matrix(summaries)
    runtime = time.perf_counter() - started
    print("EXPERIMENT_SPEC")
    print(f"LINEAR_DRIFT_HZ={LINEAR_DRIFT_HZ}")
    print(f"SNR_GRID={list(SNR_GRID)}")
    print(f"A_RES_GRID_HZ={list(A_RES_GRID_HZ)}")
    print(f"N_PER_CONDITION={N_PER_CONDITION}")
    print(f"SEED_RULE={BASE_SEED} + snr_index*10000 + trial_index; reused across amplitudes within SNR")
    print("TRAJECTORY=wsprd_linear_drift_trajectory(162,256,0.5) + wspr_symbol_quadratic_residual_trajectory(162,256,A_res_hz)")
    print("TOTAL_TRIALS")
    print(EXPECTED_TOTAL_TRIALS)
    print("TOTAL_CONDITIONS")
    print(EXPECTED_CONDITIONS)
    print("RUNTIME")
    print(f"{runtime:.6f} seconds")
    print("SUMMARY_TABLE")
    summary_writer = csv.DictWriter(sys.stdout, fieldnames=SUMMARY_FIELDS, lineterminator="\n")
    summary_writer.writeheader()
    summary_writer.writerows(summaries)
    print("CSV_INTEGRITY_CHECK")
    print("PASS")
    print("OUTPUT_PATHS")
    print(f"TRIAL_CSV={TRIAL_CSV}")
    print(f"SUMMARY_CSV={SUMMARY_CSV}")
    print(f"MATRIX_CSV={MATRIX_CSV}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, RuntimeError, ValueError) as error:
        print(f"linear quadratic interaction failed: {error}", file=sys.stderr)
        raise SystemExit(1)
