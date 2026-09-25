"""Measure official wsprsim noise against the source-derived SNR equation."""

from __future__ import annotations

import csv
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


def read_c2(path: Path) -> tuple[complex, ...]:
    data = path.read_bytes()
    return tuple(complex(i_value, -stored_q) for i_value, stored_q in struct.iter_unpack("<ff", data[26:]))


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    simulator = root / ".cache/wsjtx-3.0.2/lib/wsprd/wsprsim"
    clean = read_c2(root / "results/reference/260924_0000.c2")
    output = root / "results/calibration/official_wsprsim_snr_oracle.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for snr_db in (-20.0, -25.0, -30.0):
        # This is the literal amplitude equation in wsprsim.c lines 191-193.
        amplitude = math.sqrt(2.0) * 10.0 ** ((snr_db + 8.2) / 20.0)
        with tempfile.TemporaryDirectory(prefix="wsprsim-oracle-") as directory:
            filename = f"260924_{abs(int(snr_db)):04d}.c2"
            process = subprocess.run(
                [str(simulator), "-s", str(snr_db), "-o", filename, "K1ABC FN42 33"],
                cwd=directory,
                text=True,
                capture_output=True,
                check=False,
            )
            noisy = read_c2(Path(directory) / filename)
        if process.returncode != 1:
            raise RuntimeError(f"Unexpected wsprsim status {process.returncode}: {process.stderr}")
        residual = [observed - amplitude * reference for observed, reference in zip(noisy, clean)]
        noise_mean = sum(residual) / len(residual)
        noise_power = math.fsum(abs(value - noise_mean) ** 2 for value in residual) / len(residual)
        signal_power = amplitude * amplitude
        inferred_snr = 10.0 * math.log10(signal_power / noise_power) - 10.0 * math.log10(2500.0 / 375.0)
        rows.append(
            {
                "requested_snr_db_2500hz": snr_db,
                "official_signal_amplitude": amplitude,
                "official_signal_power": signal_power,
                "measured_complex_noise_power_375hz": noise_power,
                "measured_noise_psd_power_per_hz": noise_power / 375.0,
                "measured_noise_mean_real": noise_mean.real,
                "measured_noise_mean_imag": noise_mean.imag,
                "inferred_snr_db_2500hz_exact_bandwidth": inferred_snr,
                "error_db": inferred_snr - snr_db,
            }
        )
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(output)
    for row in rows:
        print(
            f"{row['requested_snr_db_2500hz']:5.1f} dB: "
            f"Pn={row['measured_complex_noise_power_375hz']:.5f}, "
            f"inferred={row['inferred_snr_db_2500hz_exact_bandwidth']:.3f} dB"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
