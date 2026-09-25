"""Signal impairment models used by controlled WSPR experiments."""

from .noise import add_awgn, complex_noise_power_for_wspr_snr

__all__ = ["add_awgn", "complex_noise_power_for_wspr_snr"]
