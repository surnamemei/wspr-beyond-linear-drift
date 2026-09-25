#!/usr/bin/env python3
"""Run amplitude-matched thermal residual trials and compare existing quadratic data."""

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analysis.metrics import wilson_interval
from impairments.frequency import (
    apply_frequency_error, embed_active_trajectory,
    wspr_symbol_quadratic_residual_trajectory,
)
from impairments.noise import add_awgn
from thermal_preflight import thermal_symbol_projection
from wspr.encoder import encode_type1
from wspr.waveform import (
    SAMPLE_RATE_HZ, SAMPLES_PER_SYMBOL, SYMBOL_COUNT,
    generate_complex_baseband, write_c2,
)

TAU_GRID_SECONDS = (30, 60, 120)
TARGET_RESIDUAL_AMPLITUDES_HZ = (0.25, 0.5)
SNR_GRID = (-30.0, -30.5, -31.0)
N_PER_CONDITION = 100
TOTAL_THERMAL_CONDITIONS = 18
TOTAL_TRIALS = 1800
BASE_SEED = 2026100200
WORKERS = min(4, os.cpu_count() or 1)
MESSAGE = "K1ABC FN42 33"
OUTPUT_DIR = ROOT / "results/csv/thermal_amplitude_match"
ANALYSIS_DIR = ROOT / "results/analysis/thermal_amplitude_match"
TRIAL_CSV = OUTPUT_DIR / "thermal_amplitude_match_trials.csv"
SUMMARY_CSV = OUTPUT_DIR / "thermal_amplitude_match_summary.csv"
COMPARISON_CSV = ANALYSIS_DIR / "thermal_vs_quadratic_comparison.csv"
QUADRATIC_SUMMARY_CSV = (
    ROOT / "results/csv/quadratic_residual_pilot/quadratic_residual_pilot_summary.csv"
)

PREFLIGHT_FIELDS = (
    "tau_seconds", "target_A_res_hz", "g_tau", "K_required_hz",
    "actual_A_res_hz", "residual_rms_hz", "correlation_with_quadratic",
    "cosine_similarity_with_quadratic",
)
TRIAL_FIELDS = (
    "snr_db", "tau_seconds", "target_A_res_hz", "K_required_hz",
    "actual_A_res_hz", "trial_index", "seed", "decoded_success",
    "decoded_message", "reported_snr", "reported_drift",
    "reported_frequency", "runtime_seconds",
)
SUMMARY_FIELDS = (
    "snr_db", "tau_seconds", "target_A_res_hz", "K_required_hz",
    "actual_A_res_hz", "n", "successes", "p_decode", "Wilson95_low",
    "Wilson95_high", "mean_runtime_seconds",
)
COMPARISON_FIELDS = (
    "snr_db", "tau_seconds", "target_A_res_hz", "thermal_p_decode",
    "quadratic_p_decode", "difference", "thermal_Wilson95_low",
    "thermal_Wilson95_high", "quadratic_Wilson95_low",
    "quadratic_Wilson95_high", "shape_correlation",
    "residual_rms_hz",
)

_CLEAN_WAVEFORM = None
_IMPAIRED_CACHE: dict[tuple[int, float], object] = {}


def validate_specification() -> None:
    assert len(TAU_GRID_SECONDS) == 3
    assert len(TARGET_RESIDUAL_AMPLITUDES_HZ) == 2
    assert len(SNR_GRID) == 3
    assert N_PER_CONDITION == 100
    assert len(TAU_GRID_SECONDS) * len(TARGET_RESIDUAL_AMPLITUDES_HZ) * len(SNR_GRID) == TOTAL_THERMAL_CONDITIONS == 18
    assert TOTAL_THERMAL_CONDITIONS * N_PER_CONDITION == TOTAL_TRIALS == 1800
    assert SYMBOL_COUNT == 162 and SAMPLES_PER_SYMBOL == 256 and SAMPLE_RATE_HZ == 375


def preflight() -> list[dict[str, float]]:
    quadratic = np.asarray(
        wspr_symbol_quadratic_residual_trajectory(162, 256, 1.0),
        dtype=float,
    ).reshape(162, 256)[:, 0]
    rows = []
    for tau in TAU_GRID_SECONDS:
        _, x, _, _, unit_residual = thermal_symbol_projection(tau, 1.0)
        g_tau = float(np.max(np.abs(unit_residual)))
        assert math.isfinite(g_tau) and g_tau > 0
        for target in TARGET_RESIDUAL_AMPLITUDES_HZ:
            required_k = target / g_tau
            _, x_regenerated, _, _, residual = thermal_symbol_projection(tau, required_k)
            assert np.array_equal(x, x_regenerated)
            actual = float(np.max(np.abs(residual)))
            assert math.isclose(actual, target, rel_tol=0, abs_tol=1e-12), (
                tau, target, actual
            )
            assert abs(float(np.dot(residual, np.ones_like(x)))) < 1e-11
            assert abs(float(np.dot(residual, x))) < 1e-11
            correlation = float(np.corrcoef(residual, quadratic)[0, 1])
            cosine = float(np.dot(residual, quadratic) /
                           (np.linalg.norm(residual) * np.linalg.norm(quadratic)))
            rows.append({
                "tau_seconds": tau, "target_A_res_hz": target, "g_tau": g_tau,
                "K_required_hz": required_k, "actual_A_res_hz": actual,
                "residual_rms_hz": float(np.sqrt(np.mean(residual ** 2))),
                "correlation_with_quadratic": correlation,
                "cosine_similarity_with_quadratic": cosine,
            })
    assert len(rows) == len(TAU_GRID_SECONDS) * len(TARGET_RESIDUAL_AMPLITUDES_HZ)
    return rows


def initialize_worker() -> None:
    global _CLEAN_WAVEFORM, _IMPAIRED_CACHE
    _CLEAN_WAVEFORM = generate_complex_baseband(encode_type1(MESSAGE).channel_symbols)
    _IMPAIRED_CACHE = {}


def impaired_waveform(tau: int, target: float, required_k: float):
    key = (tau, target)
    if key in _IMPAIRED_CACHE:
        return _IMPAIRED_CACHE[key]
    if _CLEAN_WAVEFORM is None or _CLEAN_WAVEFORM.signal_sample_count != 162 * 256:
        raise RuntimeError("worker requires a 162x256 clean WSPR frame")
    _, _, _, _, residual = thermal_symbol_projection(tau, required_k)
    assert math.isclose(float(np.max(np.abs(residual))), target, rel_tol=0, abs_tol=1e-12)
    active = tuple(float(value) for value in np.repeat(residual, SAMPLES_PER_SYMBOL))
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


def run_trial(task: tuple[float, int, float, float, float, int, int]) -> dict[str, object]:
    snr, tau, target, required_k, actual, trial_index, seed = task
    started = time.perf_counter()
    clean = impaired_waveform(tau, target, required_k)
    noisy = add_awgn(clean.samples, snr, random.Random(seed), signal_power=1.0)
    waveform = replace(clean, samples=noisy)
    with tempfile.TemporaryDirectory(prefix="wspr-thermal-match-") as directory:
        work = Path(directory)
        filename = "260925_0000.c2"
        write_c2(work / filename, waveform)
        process = subprocess.run(
            ["bash", str(ROOT / "scripts/wsprd.sh"), "-H", "-a", str(work), filename],
            cwd=work, text=True, capture_output=True, check=False,
        )
    if process.returncode != 0:
        raise RuntimeError(
            f"wsprd failed: SNR={snr}, tau={tau}, A={target}, "
            f"trial={trial_index}, seed={seed}: {process.stderr.strip()}"
        )
    success, message, reported_snr, reported_drift, reported_frequency = (
        parse_decoder_output(process.stdout)
    )
    return {
        "snr_db": snr, "tau_seconds": tau, "target_A_res_hz": target,
        "K_required_hz": required_k, "actual_A_res_hz": actual,
        "trial_index": trial_index, "seed": seed, "decoded_success": int(success),
        "decoded_message": message, "reported_snr": reported_snr,
        "reported_drift": reported_drift, "reported_frequency": reported_frequency,
        "runtime_seconds": time.perf_counter() - started,
    }


def build_tasks(preflight_rows: list[dict[str, float]]) -> list[tuple[float, int, float, float, float, int, int]]:
    parameters = {(int(row["tau_seconds"]), float(row["target_A_res_hz"])): row
                  for row in preflight_rows}
    return [
        (snr, tau, target,
         float(parameters[(tau, target)]["K_required_hz"]),
         float(parameters[(tau, target)]["actual_A_res_hz"]),
         index, BASE_SEED + snr_index * 10_000 + index)
        for snr_index, snr in enumerate(SNR_GRID)
        for tau in TAU_GRID_SECONDS
        for target in TARGET_RESIDUAL_AMPLITUDES_HZ
        for index in range(N_PER_CONDITION)
    ]


def validate_trials(rows: list[dict[str, str]]) -> None:
    assert len(rows) == TOTAL_TRIALS
    groups: dict[tuple[float, int, float], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        assert row["decoded_success"] in {"0", "1"}
        key = (float(row["snr_db"]), int(row["tau_seconds"]), float(row["target_A_res_hz"]))
        assert key[0] in SNR_GRID and key[1] in TAU_GRID_SECONDS
        assert key[2] in TARGET_RESIDUAL_AMPLITUDES_HZ
        assert math.isclose(float(row["actual_A_res_hz"]), key[2], rel_tol=0, abs_tol=1e-12)
        groups[key].append(row)
    assert len(groups) == TOTAL_THERMAL_CONDITIONS
    for selected in groups.values():
        assert len(selected) == N_PER_CONDITION
        assert len({int(row["seed"]) for row in selected}) == N_PER_CONDITION
        assert {int(row["trial_index"]) for row in selected} == set(range(N_PER_CONDITION))
        assert len({float(row["K_required_hz"]) for row in selected}) == 1
    for snr_index, snr in enumerate(SNR_GRID):
        expected = {BASE_SEED + snr_index * 10_000 + index
                    for index in range(N_PER_CONDITION)}
        for tau in TAU_GRID_SECONDS:
            for target in TARGET_RESIDUAL_AMPLITUDES_HZ:
                assert {int(row["seed"]) for row in groups[(snr, tau, target)]} == expected


def summarize(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    groups: dict[tuple[float, int, float], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(float(row["snr_db"]), int(row["tau_seconds"]),
                float(row["target_A_res_hz"]))].append(row)
    summaries = []
    for snr in SNR_GRID:
        for tau in TAU_GRID_SECONDS:
            for target in TARGET_RESIDUAL_AMPLITUDES_HZ:
                selected = groups[(snr, tau, target)]
                successes = sum(int(row["decoded_success"]) for row in selected)
                low, high = wilson_interval(successes, N_PER_CONDITION)
                summaries.append({
                    "snr_db": snr, "tau_seconds": tau, "target_A_res_hz": target,
                    "K_required_hz": float(selected[0]["K_required_hz"]),
                    "actual_A_res_hz": float(selected[0]["actual_A_res_hz"]),
                    "n": len(selected), "successes": successes,
                    "p_decode": successes / N_PER_CONDITION,
                    "Wilson95_low": low, "Wilson95_high": high,
                    "mean_runtime_seconds": sum(float(row["runtime_seconds"])
                                                for row in selected) / len(selected),
                })
    assert len(summaries) == TOTAL_THERMAL_CONDITIONS
    assert all(row["n"] == N_PER_CONDITION and
               row["p_decode"] == row["successes"] / N_PER_CONDITION
               for row in summaries)
    return summaries


def compare(summaries: list[dict[str, object]],
            preflight_rows: list[dict[str, float]]) -> list[dict[str, object]]:
    with QUADRATIC_SUMMARY_CSV.open(newline="") as handle:
        quadratic_rows = list(csv.DictReader(handle))
    quadratic = {
        (float(row["snr_db"]), float(row["A_res_hz"])): row
        for row in quadratic_rows
        if float(row["snr_db"]) in SNR_GRID and
        float(row["A_res_hz"]) in TARGET_RESIDUAL_AMPLITUDES_HZ
    }
    assert len(quadratic) == len(SNR_GRID) * len(TARGET_RESIDUAL_AMPLITUDES_HZ)
    assert all(int(row["n"]) == 100 and
               float(row["p_decode"]) == int(row["successes"]) / 100
               for row in quadratic.values())
    shape = {(int(row["tau_seconds"]), float(row["target_A_res_hz"])): row
             for row in preflight_rows}
    comparison = []
    for row in summaries:
        snr = float(row["snr_db"])
        tau = int(row["tau_seconds"])
        target = float(row["target_A_res_hz"])
        prior = quadratic[(snr, target)]
        thermal_p = float(row["p_decode"])
        quadratic_p = float(prior["p_decode"])
        comparison.append({
            "snr_db": snr, "tau_seconds": tau, "target_A_res_hz": target,
            "thermal_p_decode": thermal_p, "quadratic_p_decode": quadratic_p,
            "difference": thermal_p - quadratic_p,
            "thermal_Wilson95_low": row["Wilson95_low"],
            "thermal_Wilson95_high": row["Wilson95_high"],
            "quadratic_Wilson95_low": prior["Wilson95_low"],
            "quadratic_Wilson95_high": prior["Wilson95_high"],
            "shape_correlation": shape[(tau, target)]["correlation_with_quadratic"],
            "residual_rms_hz": shape[(tau, target)]["residual_rms_hz"],
        })
    assert len(comparison) == TOTAL_THERMAL_CONDITIONS
    return comparison


def print_table(fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=fields, extrasaction="ignore",
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
    validate_specification()
    for path in (TRIAL_CSV, SUMMARY_CSV, COMPARISON_CSV):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {path}")
    if not QUADRATIC_SUMMARY_CSV.is_file():
        raise FileNotFoundError(QUADRATIC_SUMMARY_CSV)
    started = time.perf_counter()
    preflight_rows = preflight()
    print("PREFLIGHT_TABLE")
    print_table(PREFLIGHT_FIELDS, preflight_rows)
    sys.stdout.flush()
    tasks = build_tasks(preflight_rows)
    assert len(tasks) == TOTAL_TRIALS
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    progress: Counter[tuple[float, int, float]] = Counter()
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
                key = (float(row["snr_db"]), int(row["tau_seconds"]),
                       float(row["target_A_res_hz"]))
                progress[key] += 1
                if progress[key] == 1 or progress[key] % 25 == 0:
                    print(f"[SNR {key[0]:.1f} | tau {key[1]} | A {key[2]:.2f} | "
                          f"{progress[key]}/{N_PER_CONDITION}]",
                          file=sys.stderr, flush=True)
    with TRIAL_CSV.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    validate_trials(rows)
    summaries = summarize(rows)
    with SUMMARY_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summaries)
    with SUMMARY_CSV.open(newline="") as handle:
        written_summaries = list(csv.DictReader(handle))
    assert len(written_summaries) == TOTAL_THERMAL_CONDITIONS
    assert all(float(row["p_decode"]) == int(row["successes"]) / N_PER_CONDITION
               for row in written_summaries)
    comparison = compare(summaries, preflight_rows)
    with COMPARISON_CSV.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMPARISON_FIELDS)
        writer.writeheader()
        writer.writerows(comparison)
    with COMPARISON_CSV.open(newline="") as handle:
        assert len(list(csv.DictReader(handle))) == TOTAL_THERMAL_CONDITIONS
    runtime = time.perf_counter() - started
    print("EXPERIMENT_SPEC")
    print(f"TAU_GRID_SECONDS={list(TAU_GRID_SECONDS)}")
    print(f"TARGET_RESIDUAL_AMPLITUDES_HZ={list(TARGET_RESIDUAL_AMPLITUDES_HZ)}")
    print(f"SNR_GRID={list(SNR_GRID)}")
    print(f"N_PER_CONDITION={N_PER_CONDITION}")
    print(f"TOTAL_THERMAL_CONDITIONS={TOTAL_THERMAL_CONDITIONS}")
    print(f"SEED_RULE={BASE_SEED} + snr_index*10000 + trial_index; matched across all six thermal conditions within SNR")
    print("TRAJECTORY=thermal_symbol_projection(tau,K_required), symbolwise residual only")
    print("TOTAL_TRIALS")
    print(TOTAL_TRIALS)
    print("RUNTIME")
    print(f"{runtime:.6f} seconds")
    print("THERMAL_SUMMARY")
    print_table(SUMMARY_FIELDS, summaries)
    print("THERMAL_VS_QUADRATIC_COMPARISON")
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
        print(f"thermal amplitude match failed: {error}", file=sys.stderr)
        raise SystemExit(1)
