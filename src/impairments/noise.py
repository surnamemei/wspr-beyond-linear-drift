"""Calibrated complex AWGN for WSPR's 2500 Hz SNR convention."""

from __future__ import annotations

import math
import random
from typing import Sequence

WSPR_REFERENCE_BANDWIDTH_HZ = 2500.0
C2_SAMPLE_RATE_HZ = 375.0


def active_signal_power(signal: Sequence[complex]) -> float:
    """Measure mean power over nonzero samples of a clean timed frame."""

    active_powers = [abs(sample) ** 2 for sample in signal if sample != 0j]
    if not active_powers:
        raise ValueError("Signal has no nonzero samples from which to measure power")
    return math.fsum(active_powers) / len(active_powers)


def complex_noise_power_for_wspr_snr(
    signal_power: float,
    wspr_snr_db: float,
    *,
    sample_rate_hz: float = C2_SAMPLE_RATE_HZ,
    reference_bandwidth_hz: float = WSPR_REFERENCE_BANDWIDTH_HZ,
) -> float:
    """Return E[|n|^2] needed for SNR referenced to 2500 Hz.

    For complex samples spanning ``sample_rate_hz``, noise power is N0*Fs.
    WSPR SNR is Ps/(N0*2500), hence

        Pn = Ps * (Fs/2500) * 10**(-SNR_2500/10).
    """

    if signal_power <= 0 or sample_rate_hz <= 0 or reference_bandwidth_hz <= 0:
        raise ValueError("Powers and bandwidths must be positive")
    return (
        signal_power
        * (sample_rate_hz / reference_bandwidth_hz)
        * 10.0 ** (-wspr_snr_db / 10.0)
    )


def add_awgn(
    signal: Sequence[complex],
    wspr_snr_db: float,
    rng: random.Random,
    *,
    signal_power: float | None = None,
) -> tuple[complex, ...]:
    """Add circular complex Gaussian noise without modifying ``signal``.

    ``rng`` is supplied by the caller so every trial has an explicit,
    reproducible seed. If signal power is omitted, it is measured over nonzero
    samples, which excludes the exact-zero timing padding in a clean WSPR C2.
    """

    if signal_power is None:
        signal_power = active_signal_power(signal)
    noise_power = complex_noise_power_for_wspr_snr(signal_power, wspr_snr_db)
    component_sigma = math.sqrt(noise_power / 2.0)
    return tuple(
        sample + complex(rng.gauss(0.0, component_sigma), rng.gauss(0.0, component_sigma))
        for sample in signal
    )
