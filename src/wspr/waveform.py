"""Continuous-phase WSPR-2 complex baseband generation and C2 output."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import struct
from typing import Sequence

SAMPLE_RATE_HZ = 375
SAMPLES_PER_SYMBOL = 256
SYMBOL_COUNT = 162
TONE_SPACING_HZ = SAMPLE_RATE_HZ / SAMPLES_PER_SYMBOL
SYMBOL_DURATION_S = SAMPLES_PER_SYMBOL / SAMPLE_RATE_HZ
FRAME_DURATION_S = SYMBOL_COUNT * SYMBOL_DURATION_S
DEFAULT_START_DELAY_S = 1.0
DEFAULT_CONTAINER_DURATION_S = 120.0
DEFAULT_DIAL_FREQUENCY_MHZ = 10.1387


@dataclass(frozen=True)
class ComplexWaveform:
    """A complex baseband signal using positive-Q internal convention."""

    samples: tuple[complex, ...]
    sample_rate_hz: int
    frame_start_sample: int
    signal_sample_count: int
    center_frequency_hz: float

    @property
    def frame_duration_s(self) -> float:
        return self.signal_sample_count / self.sample_rate_hz

    @property
    def container_duration_s(self) -> float:
        return len(self.samples) / self.sample_rate_hz


def tone_frequency_hz(symbol: int, center_frequency_hz: float = 0.0) -> float:
    """Map tone number 0..3 to the official center-relative frequency."""

    if symbol not in (0, 1, 2, 3):
        raise ValueError(f"Invalid WSPR tone: {symbol}")
    return center_frequency_hz + (symbol - 1.5) * TONE_SPACING_HZ


def generate_complex_baseband(
    symbols: Sequence[int],
    *,
    center_frequency_hz: float = 0.0,
    start_delay_s: float = DEFAULT_START_DELAY_S,
    container_duration_s: float = DEFAULT_CONTAINER_DURATION_S,
    initial_phase_rad: float = 0.0,
) -> ComplexWaveform:
    """Generate a deterministic, continuous-phase WSPR-2 baseband frame.

    Frequency trajectory construction and phase accumulation are kept in one
    explicit loop. A later phase can add a separately computed frequency-error
    trajectory before accumulation without changing encoding or C2 handling.
    No impairment is applied here.
    """

    if len(symbols) != SYMBOL_COUNT:
        raise ValueError(f"Expected {SYMBOL_COUNT} symbols, got {len(symbols)}")
    if start_delay_s < 0 or container_duration_s <= 0:
        raise ValueError("Durations must be positive and start delay nonnegative")
    start_sample = round(start_delay_s * SAMPLE_RATE_HZ)
    total_samples = round(container_duration_s * SAMPLE_RATE_HZ)
    signal_samples = SYMBOL_COUNT * SAMPLES_PER_SYMBOL
    if start_sample + signal_samples > total_samples:
        raise ValueError("WSPR frame does not fit in the requested container")

    samples = [0j] * total_samples
    phase = float(initial_phase_rad)
    output_index = start_sample
    for symbol in symbols:
        frequency = tone_frequency_hz(int(symbol), center_frequency_hz)
        phase_step = math.tau * frequency / SAMPLE_RATE_HZ
        for _ in range(SAMPLES_PER_SYMBOL):
            samples[output_index] = complex(math.cos(phase), math.sin(phase))
            phase += phase_step
            output_index += 1
    return ComplexWaveform(
        samples=tuple(samples),
        sample_rate_hz=SAMPLE_RATE_HZ,
        frame_start_sample=start_sample,
        signal_sample_count=signal_samples,
        center_frequency_hz=center_frequency_hz,
    )


def write_c2(
    path: str | Path,
    waveform: ComplexWaveform,
    *,
    dial_frequency_mhz: float = DEFAULT_DIAL_FREQUENCY_MHZ,
) -> None:
    """Write the little-endian C2 layout used by WSJT-X 3.0.2 wsprd.

    The C2 convention stores ``I, -Q`` float32 pairs. The 14-byte embedded
    filename is required to be exact rather than silently truncated or padded.
    """

    output = Path(path)
    header_name = output.name.encode("ascii")
    if len(header_name) != 14:
        raise ValueError("C2 filename must be exactly 14 ASCII bytes, e.g. YYMMDD_HHMM.c2")
    if waveform.sample_rate_hz != SAMPLE_RATE_HZ or len(waveform.samples) != 45_000:
        raise ValueError("WSPR-2 C2 requires exactly 45,000 complex samples at 375 Hz")

    payload = bytearray(struct.pack("<14sid", header_name, 2, dial_frequency_mhz))
    for sample in waveform.samples:
        payload.extend(struct.pack("<ff", float(sample.real), float(-sample.imag)))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
