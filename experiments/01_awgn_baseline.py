#!/usr/bin/env python3
"""Run actual wsprd decode trials for the AWGN-only WSPR baseline."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from dataclasses import replace
import json
import os
from pathlib import Path
import platform
import random
import re
import subprocess
import tempfile
import time

from analysis.metrics import wilson_interval
from impairments.noise import add_awgn
from wspr.encoder import encode_type1
from wspr.waveform import generate_complex_baseband, write_c2


MESSAGE = "K1ABC FN42 33"
WSPRD_VERSION = "official WSJT-X 3.0.2; binary SHA256 9e3c2fc14f63c4b4c4e9fcc33b386cd22daf8fe76ce724c5e37f07875e9a3dd9"
COARSE_SNRS = (-20.0, -24.0, -26.0, -28.0, -30.0, -32.0, -34.0)
FULL_PLAN = {
    -24.0: 50,
    -25.0: 50,
    -26.0: 100,
    -27.0: 200,
    -28.0: 200,
    -29.0: 200,
    -30.0: 200,
    -31.0: 200,
    -32.0: 200,
    -33.0: 100,
    -34.0: 50,
}

_CLEAN_WAVEFORM = None
_ROOT = None


def initialize_worker(root: str) -> None:
    global _CLEAN_WAVEFORM, _ROOT
    _ROOT = Path(root)
    symbols = encode_type1(MESSAGE).channel_symbols
    _CLEAN_WAVEFORM = generate_complex_baseband(symbols)


def parse_decoder_output(stdout: str) -> tuple[bool, str, str, str, str]:
    messages = []
    exact_row = None
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) == 8 and re.fullmatch(r"[0-9]{4}", fields[0]):
            messages.append(" ".join(fields[5:8]))
            if fields[5:8] == MESSAGE.split():
                exact_row = fields
    if exact_row is None:
        return False, " | ".join(messages), "", "", ""
    return True, MESSAGE, exact_row[1], exact_row[3], exact_row[4]


def run_trial(task: tuple[int, float, int, int]) -> dict[str, object]:
    condition_index, snr_db, trial_in_condition, seed = task
    if _CLEAN_WAVEFORM is None or _ROOT is None:
        raise RuntimeError("Worker was not initialized")
    start = time.perf_counter()
    noisy_samples = add_awgn(_CLEAN_WAVEFORM.samples, snr_db, random.Random(seed), signal_power=1.0)
    noisy_waveform = replace(_CLEAN_WAVEFORM, samples=noisy_samples)
    with tempfile.TemporaryDirectory(prefix="wspr-awgn-") as directory:
        work = Path(directory)
        filename = "260924_0002.c2"
        write_c2(work / filename, noisy_waveform)
        command = [
            "bash",
            str(_ROOT / "scripts/wsprd.sh"),
            "-H",
            "-a",
            str(work),
            filename,
        ]
        process = subprocess.run(command, cwd=work, text=True, capture_output=True, check=False)
    success, decoded_message, reported_snr, reported_frequency, reported_drift = parse_decoder_output(
        process.stdout
    )
    return {
        "experiment": "awgn_baseline",
        "trial_id": condition_index * 1_000_000 + trial_in_condition,
        "seed": seed,
        "message": MESSAGE,
        "snr_db_2500hz": snr_db,
        "decoded_success": int(success),
        "decoded_message": decoded_message,
        "reported_snr": reported_snr,
        "reported_frequency": reported_frequency,
        "reported_drift": reported_drift,
        "decoder_exit_status": process.returncode,
        "runtime_seconds": time.perf_counter() - start,
        "signal_file_or_identifier": f"generated:snr={snr_db:g},seed={seed}",
        "wsprd_version": WSPRD_VERSION,
        "decoder_stdout": process.stdout.strip(),
        "decoder_stderr": process.stderr.strip(),
    }


def git_commit(root: Path) -> str:
    process = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False
    )
    return process.stdout.strip() if process.returncode == 0 else "uncommitted-no-HEAD"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true", help="10 trials on the seven-point coarse grid")
    mode.add_argument("--full", action="store_true", help="documented adaptive full plan")
    parser.add_argument("--snrs", nargs="+", type=float, help="custom SNR grid")
    parser.add_argument("--trials", type=int, help="trials per point for a custom grid")
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--base-seed", type=int, default=2026092400)
    parser.add_argument("--output-prefix")
    return parser.parse_args()


def experiment_plan(args: argparse.Namespace) -> tuple[dict[float, int], str]:
    if args.snrs:
        if not args.trials or args.trials <= 0:
            raise ValueError("--trials must be positive with --snrs")
        return {snr: args.trials for snr in args.snrs}, args.output_prefix or "awgn_baseline_custom"
    if args.full:
        return dict(FULL_PLAN), args.output_prefix or "awgn_baseline"
    return {snr: 10 for snr in COARSE_SNRS}, args.output_prefix or "awgn_baseline_quick"


def main() -> int:
    args = parse_arguments()
    plan, prefix = experiment_plan(args)
    root = Path(__file__).resolve().parents[1]
    output_dir = root / "results/csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    tasks = []
    for condition_index, (snr, count) in enumerate(sorted(plan.items(), reverse=True)):
        for trial in range(count):
            seed = args.base_seed + condition_index * 100_000 + trial
            tasks.append((condition_index, snr, trial, seed))

    started = time.perf_counter()
    rows = []
    with ProcessPoolExecutor(
        max_workers=args.workers, initializer=initialize_worker, initargs=(str(root),)
    ) as executor:
        futures = [executor.submit(run_trial, task) for task in tasks]
        for completed, future in enumerate(as_completed(futures), start=1):
            rows.append(future.result())
            if completed % 10 == 0 or completed == len(futures):
                print(f"completed {completed}/{len(futures)}", flush=True)
    rows.sort(key=lambda row: (-float(row["snr_db_2500hz"]), int(row["trial_id"])))

    trial_path = output_dir / f"{prefix}_trials.csv"
    with trial_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summaries = []
    for snr in sorted(plan, reverse=True):
        selected = [row for row in rows if float(row["snr_db_2500hz"]) == snr]
        successes = sum(int(row["decoded_success"]) for row in selected)
        low, high = wilson_interval(successes, len(selected))
        reported = [
            float(row["reported_snr"])
            for row in selected
            if row["reported_snr"] != "" and int(row["decoded_success"])
        ]
        differences = [value - snr for value in reported]
        differences_sorted = sorted(differences)
        median_difference = ""
        if differences_sorted:
            middle = len(differences_sorted) // 2
            median_difference = (
                differences_sorted[middle]
                if len(differences_sorted) % 2
                else (differences_sorted[middle - 1] + differences_sorted[middle]) / 2.0
            )
        summaries.append(
            {
                "snr_db_2500hz": snr,
                "n": len(selected),
                "successes": successes,
                "p_decode": successes / len(selected),
                "ci_low": low,
                "ci_high": high,
                "reported_snr_count": len(reported),
                "mean_reported_minus_injected_db": (
                    sum(differences) / len(differences) if differences else ""
                ),
                "median_reported_minus_injected_db": median_difference,
                "mean_runtime_seconds": sum(float(row["runtime_seconds"]) for row in selected)
                / len(selected),
            }
        )
    summary_path = output_dir / f"{prefix}_summary.csv"
    with summary_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0].keys()))
        writer.writeheader()
        writer.writerows(summaries)

    metadata = {
        "experiment": "awgn_baseline",
        "mode": "full" if args.full else "quick" if not args.snrs else "custom",
        "message": MESSAGE,
        "snr_plan": plan,
        "base_seed": args.base_seed,
        "seed_policy": "base_seed + descending-condition-index*100000 + zero-based-trial-index",
        "workers": args.workers,
        "python_version": platform.python_version(),
        "wsprd_version": WSPRD_VERSION,
        "git_commit": git_commit(root),
        "decoder_options": ["-H"],
        "trial_csv": str(trial_path),
        "summary_csv": str(summary_path),
        "wall_runtime_seconds": time.perf_counter() - started,
    }
    (output_dir / f"{prefix}_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")

    print("SNR(dB)    N  decoded  P_decode       Wilson 95% CI")
    for row in summaries:
        print(
            f"{float(row['snr_db_2500hz']):7.1f} {int(row['n']):4d} "
            f"{int(row['successes']):8d} {float(row['p_decode']):9.3f} "
            f"[{float(row['ci_low']):.3f}, {float(row['ci_high']):.3f}]"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"AWGN experiment failed: {error}")
        raise SystemExit(1)
