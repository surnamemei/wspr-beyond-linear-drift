"""Generate and characterize the independent Python WSPR reference signal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys

from wspr.encoder import encode_type1
from wspr.waveform import (
    FRAME_DURATION_S,
    SAMPLE_RATE_HZ,
    SAMPLES_PER_SYMBOL,
    TONE_SPACING_HZ,
    generate_complex_baseband,
    tone_frequency_hz,
    write_c2,
)


MESSAGE = "K1ABC FN42 33"
OUTPUT_NAME = "260924_0001.c2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_c2_samples(path: Path) -> tuple[complex, ...]:
    data = path.read_bytes()
    if len(data) != 26 + 45_000 * 8:
        raise ValueError(f"Unexpected C2 size for {path}: {len(data)}")
    values = struct.iter_unpack("<ff", memoryview(data)[26:])
    return tuple(complex(i_sample, -stored_q) for i_sample, stored_q in values)


def active_bounds(samples: tuple[complex, ...]) -> tuple[int, int]:
    active = [index for index, sample in enumerate(samples) if abs(sample) > 0.5]
    if not active:
        raise ValueError("Signal contains no active unit-amplitude samples")
    return active[0], active[-1] + 1


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    output_dir = root / "results" / "python-reference"
    output_dir.mkdir(parents=True, exist_ok=True)
    reference = json.loads((root / "tests/data/reference_symbols.json").read_text())

    encoded = encode_type1(MESSAGE)
    expected = tuple(reference["channel_symbols"])
    matching = sum(actual == official for actual, official in zip(encoded.channel_symbols, expected))
    if len(encoded.channel_symbols) != 162 or matching != 162:
        raise ValueError(f"Official symbol comparison failed: {matching}/162")

    waveform = generate_complex_baseband(encoded.channel_symbols)
    output_path = output_dir / OUTPUT_NAME
    write_c2(output_path, waveform)

    official_path = root / "results/reference/260924_0000.c2"
    official_samples = read_c2_samples(official_path)
    python_bounds = active_bounds(waveform.samples)
    official_bounds = active_bounds(official_samples)
    max_sample_difference = max(
        abs(python_sample - official_sample)
        for python_sample, official_sample in zip(waveform.samples, official_samples)
    )
    active = waveform.samples[python_bounds[0] : python_bounds[1]]
    tone_frequencies = [tone_frequency_hz(tone) for tone in range(4)]

    metadata = {
        "message": encoded.message,
        "matching_official_symbols": matching,
        "symbol_count": len(encoded.channel_symbols),
        "packed_message_hex": encoded.packed_bytes.hex(" ").upper(),
        "information_bit_count": len(encoded.information_bits),
        "terminated_bit_count": len(encoded.terminated_bits),
        "convolutional_bit_count": len(encoded.convolutional_bits),
        "interleaved_bit_count": len(encoded.interleaved_bits),
        "format": "WSJT-X C2: 14-byte name, int32 mode, float64 dial MHz, 45000 float32 I/-Q pairs",
        "internal_representation": "Python complex (positive Q), unit amplitude while active",
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "sample_count": len(waveform.samples),
        "container_duration_s": waveform.container_duration_s,
        "frame_start_sample": waveform.frame_start_sample,
        "frame_start_s": waveform.frame_start_sample / SAMPLE_RATE_HZ,
        "frame_sample_count": waveform.signal_sample_count,
        "frame_duration_s": FRAME_DURATION_S,
        "samples_per_symbol": SAMPLES_PER_SYMBOL,
        "tone_spacing_hz": TONE_SPACING_HZ,
        "tone_frequencies_hz": tone_frequencies,
        "active_amplitude_min": min(abs(sample) for sample in active),
        "active_amplitude_max": max(abs(sample) for sample in active),
        "python_active_bounds_samples": list(python_bounds),
        "official_active_bounds_samples": list(official_bounds),
        "max_complex_sample_difference_from_official_after_c2_float32": max_sample_difference,
        "official_c2_sha256": sha256(official_path),
        "python_c2_sha256": sha256(output_path),
        "output": str(output_path),
    }
    (output_dir / "generator_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (output_dir / "message.txt").write_text(encoded.message + "\n")
    print(f"Official channel-symbol match: {matching}/162")
    print(f"Generated {output_path}")
    print(f"C2: {len(waveform.samples)} complex samples at {SAMPLE_RATE_HZ} Hz")
    print(f"WSPR frame duration: {FRAME_DURATION_S:.3f} s")
    print(f"Official comparison max complex-sample difference: {max_sample_difference:.3g}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"Python reference generation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
