#!/usr/bin/env python3
"""Execute the fixed WSPR-2 linear-drift/SNR robustness map."""

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
)
from impairments.noise import add_awgn
from wspr.encoder import encode_type1
from wspr.waveform import generate_complex_baseband, write_c2


SNR_GRID = (-28.0, -29.0, -30.0, -31.0, -32.0)
DRIFT_GRID = (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 2.0, -2.0)
N_PER_CONDITION = 100
EXPECTED_CONDITIONS = 45
EXPECTED_TOTAL_TRIALS = 4500
BASE_SEED = 2026092500
WORKERS = min(4, os.cpu_count() or 1)
MESSAGE = "K1ABC FN42 33"
WSPRD_VERSION = (
    "official WSJT-X 3.0.2; binary SHA256 "
    "9e3c2fc14f63c4b4c4e9fcc33b386cd22daf8fe76ce724c5e37f07875e9a3dd9"
)
OUTPUT_DIR = ROOT / "results" / "csv" / "linear_drift_map"
TRIAL_CSV = OUTPUT_DIR / "linear_drift_map_trials.csv"
SUMMARY_CSV = OUTPUT_DIR / "linear_drift_map_summary.csv"
MATRIX_CSV = OUTPUT_DIR / "linear_drift_map_matrix.csv"

TRIAL_FIELDS = (
    "snr_db",
    "drift_hz",
    "trial_index",
    "seed",
    "decoded_success",
    "decoded_message",
    "reported_snr",
    "reported_drift",
    "reported_frequency",
    "runtime_seconds",
    "decoder_exit_status",
    "wsprd_version",
    "decoder_stdout",
    "decoder_stderr",
)
SUMMARY_FIELDS = (
    "snr_db",
    "drift_hz",
    "n",
    "successes",
    "p_decode",
    "Wilson95_low",
    "Wilson95_high",
    "mean_runtime_seconds",
)

_CLEAN_WAVEFORM = None
_IMPAIRED_CACHE: dict[float, object] = {}


def initialize_worker() -> None:
    global _CLEAN_WAVEFORM, _IMPAIRED_CACHE
    _CLEAN_WAVEFORM = generate_complex_baseband(encode_type1(MESSAGE).channel_symbols)
    _IMPAIRED_CACHE = {}


def impaired_waveform(drift_hz: float):
    if drift_hz in _IMPAIRED_CACHE:
        return _IMPAIRED_CACHE[drift_hz]
    if _CLEAN_WAVEFORM is None:
        raise RuntimeError("worker not initialized")
    if _CLEAN_WAVEFORM.signal_sample_count != 162 * 256:
        raise RuntimeError("exact wsprd linear drift requires a 162x256 active frame")
    active = wsprd_linear_drift_trajectory(162, 256, drift_hz)
    full = embed_active_trajectory(
        len(_CLEAN_WAVEFORM.samples), _CLEAN_WAVEFORM.frame_start_sample, active
    )
    samples = apply_frequency_error(
        _CLEAN_WAVEFORM.samples, full, _CLEAN_WAVEFORM.sample_rate_hz
    )
    waveform = replace(_CLEAN_WAVEFORM, samples=samples)
    _IMPAIRED_CACHE[drift_hz] = waveform
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
    snr_db, drift_hz, trial_index, seed = task
    start = time.perf_counter()
    clean = impaired_waveform(drift_hz)
    noisy_samples = add_awgn(
        clean.samples, snr_db, random.Random(seed), signal_power=1.0
    )
    waveform = replace(clean, samples=noisy_samples)
    with tempfile.TemporaryDirectory(prefix="wspr-linear-map-") as directory:
        work = Path(directory)
        filename = "260925_0000.c2"
        write_c2(work / filename, waveform)
        process = subprocess.run(
            ["bash", str(ROOT / "scripts" / "wsprd.sh"), "-H", "-a", str(work), filename],
            cwd=work,
            text=True,
            capture_output=True,
            check=False,
        )
    if process.returncode != 0:
        raise RuntimeError(
            f"wsprd failed for SNR={snr_db}, drift={drift_hz}, "
            f"trial={trial_index}, seed={seed}: {process.stderr.strip()}"
        )
    success, decoded_message, reported_snr, reported_drift, reported_frequency = (
        parse_decoder_output(process.stdout)
    )
    return {
        "snr_db": snr_db,
        "drift_hz": drift_hz,
        "trial_index": trial_index,
        "seed": seed,
        "decoded_success": int(success),
        "decoded_message": decoded_message,
        "reported_snr": reported_snr,
        "reported_drift": reported_drift,
        "reported_frequency": reported_frequency,
        "runtime_seconds": time.perf_counter() - start,
        "decoder_exit_status": process.returncode,
        "wsprd_version": WSPRD_VERSION,
        "decoder_stdout": process.stdout.strip(),
        "decoder_stderr": process.stderr.strip(),
    }


def validate_specification() -> None:
    assert len(SNR_GRID) == 5
    assert len(DRIFT_GRID) == 9
    assert N_PER_CONDITION == 100
    assert len(SNR_GRID) * len(DRIFT_GRID) * N_PER_CONDITION == EXPECTED_TOTAL_TRIALS


def build_tasks() -> list[tuple[float, float, int, int]]:
    tasks = []
    for snr_index, snr_db in enumerate(SNR_GRID):
        for drift_hz in DRIFT_GRID:
            for trial_index in range(N_PER_CONDITION):
                seed = BASE_SEED + snr_index * 10_000 + trial_index
                tasks.append((snr_db, drift_hz, trial_index, seed))
    return tasks


def validate_trial_rows(rows: list[dict[str, str]]) -> None:
    assert len(rows) == EXPECTED_TOTAL_TRIALS
    conditions: dict[tuple[float, float], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        assert row["decoded_success"] in {"0", "1"}
        conditions[(float(row["snr_db"]), float(row["drift_hz"]))].append(row)
    assert len(conditions) == EXPECTED_CONDITIONS
    for condition_rows in conditions.values():
        assert len(condition_rows) == N_PER_CONDITION
        assert len({int(row["seed"]) for row in condition_rows}) == N_PER_CONDITION
    for snr_db in SNR_GRID:
        seed_sets = [
            {int(row["seed"]) for row in conditions[(snr_db, drift_hz)]}
            for drift_hz in DRIFT_GRID
        ]
        assert all(seed_set == seed_sets[0] for seed_set in seed_sets[1:])


def create_summaries(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    by_condition: dict[tuple[float, float], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_condition[(float(row["snr_db"]), float(row["drift_hz"]))].append(row)
    summaries = []
    for snr_db in SNR_GRID:
        for drift_hz in DRIFT_GRID:
            selected = by_condition[(snr_db, drift_hz)]
            successes = sum(int(row["decoded_success"]) for row in selected)
            low, high = wilson_interval(successes, len(selected))
            summaries.append(
                {
                    "snr_db": snr_db,
                    "drift_hz": drift_hz,
                    "n": len(selected),
                    "successes": successes,
                    "p_decode": successes / N_PER_CONDITION,
                    "Wilson95_low": low,
                    "Wilson95_high": high,
                    "mean_runtime_seconds": sum(
                        float(row["runtime_seconds"]) for row in selected
                    )
                    / len(selected),
                }
            )
    return summaries


def validate_summaries(summaries: list[dict[str, str]]) -> None:
    assert len(summaries) == EXPECTED_CONDITIONS
    for row in summaries:
        assert int(row["n"]) == N_PER_CONDITION
        assert math.isclose(
            float(row["p_decode"]),
            int(row["successes"]) / N_PER_CONDITION,
            rel_tol=0.0,
            abs_tol=0.0,
        )


def write_matrix(summaries: list[dict[str, object]]) -> None:
    probabilities = {
        (float(row["snr_db"]), float(row["drift_hz"])): float(row["p_decode"])
        for row in summaries
    }
    drift_columns = [f"{drift_hz:+.1f}" for drift_hz in DRIFT_GRID]
    with MATRIX_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["snr_db", *drift_columns])
        writer.writeheader()
        for snr_db in SNR_GRID:
            row: dict[str, object] = {"snr_db": snr_db}
            for drift_hz, column in zip(DRIFT_GRID, drift_columns):
                row[column] = probabilities[(snr_db, drift_hz)]
            writer.writerow(row)


def main() -> int:
    validate_specification()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (TRIAL_CSV, SUMMARY_CSV, MATRIX_CSV):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")

    tasks = build_tasks()
    assert len(tasks) == EXPECTED_TOTAL_TRIALS
    condition_progress: Counter[tuple[float, float]] = Counter()
    started = time.perf_counter()

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
                key = (float(row["snr_db"]), float(row["drift_hz"]))
                condition_progress[key] += 1
                count = condition_progress[key]
                if count == 1 or count % 25 == 0:
                    print(
                        f"[SNR {key[0]:.0f} | drift {key[1]:+.1f} | "
                        f"{count}/{N_PER_CONDITION}]",
                        flush=True,
                    )

    with TRIAL_CSV.open(newline="") as handle:
        trial_rows = list(csv.DictReader(handle))
    validate_trial_rows(trial_rows)

    summaries = create_summaries(trial_rows)
    with SUMMARY_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summaries)
    with SUMMARY_CSV.open(newline="") as handle:
        summary_rows = list(csv.DictReader(handle))
    validate_summaries(summary_rows)
    write_matrix(summaries)

    runtime = time.perf_counter() - started
    print("EXPERIMENT_SPEC")
    print(f"SNR_GRID={list(SNR_GRID)}")
    print(f"DRIFT_GRID={list(DRIFT_GRID)}")
    print(f"N_PER_CONDITION={N_PER_CONDITION}")
    print(f"SEED_RULE={BASE_SEED} + snr_index*10000 + trial_index; reused across drift within SNR")
    print("TRAJECTORY=wsprd_linear_drift_trajectory(162, 256, drift_hz)")
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
        print(f"linear drift map failed: {error}", file=sys.stderr)
        raise SystemExit(1)
