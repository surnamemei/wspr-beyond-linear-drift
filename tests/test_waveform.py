import cmath
import math
from pathlib import Path
import struct
import tempfile
import unittest

from wspr.encoder import encode_type1
from wspr.waveform import (
    FRAME_DURATION_S,
    SAMPLE_RATE_HZ,
    SAMPLES_PER_SYMBOL,
    SYMBOL_DURATION_S,
    TONE_SPACING_HZ,
    generate_complex_baseband,
    tone_frequency_hz,
    write_c2,
)


class WaveformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.symbols = encode_type1("K1ABC FN42 33").channel_symbols
        cls.waveform = generate_complex_baseband(cls.symbols)

    def test_duration_and_sample_layout(self):
        self.assertEqual(self.waveform.sample_rate_hz, 375)
        self.assertEqual(self.waveform.frame_start_sample, 375)
        self.assertEqual(self.waveform.signal_sample_count, 162 * 256)
        self.assertEqual(len(self.waveform.samples), 45_000)
        self.assertAlmostEqual(SYMBOL_DURATION_S, 256 / 375, places=15)
        self.assertAlmostEqual(FRAME_DURATION_S, 110.592, places=12)
        self.assertAlmostEqual(self.waveform.frame_duration_s, 110.592, places=12)
        self.assertAlmostEqual(self.waveform.container_duration_s, 120.0, places=12)

    def test_tone_spacing_from_generated_sample_phase(self):
        measured = []
        start = self.waveform.frame_start_sample
        samples = self.waveform.samples
        for symbol_index, symbol in enumerate(self.symbols):
            index = start + symbol_index * SAMPLES_PER_SYMBOL + 100
            phase_step = cmath.phase(samples[index + 1] / samples[index])
            measured_frequency = phase_step * SAMPLE_RATE_HZ / math.tau
            expected_frequency = tone_frequency_hz(symbol)
            self.assertAlmostEqual(measured_frequency, expected_frequency, places=11)
            measured.append(measured_frequency)
        occupied = sorted(set(round(value, 12) for value in measured))
        self.assertEqual(len(occupied), 4)
        for lower, upper in zip(occupied, occupied[1:]):
            self.assertAlmostEqual(upper - lower, TONE_SPACING_HZ, places=11)

    def test_phase_is_continuous_at_every_symbol_boundary(self):
        start = self.waveform.frame_start_sample
        samples = self.waveform.samples
        for symbol_index in range(161):
            next_start = start + (symbol_index + 1) * SAMPLES_PER_SYMBOL
            observed_step = cmath.phase(samples[next_start] / samples[next_start - 1])
            expected_step = math.tau * tone_frequency_hz(self.symbols[symbol_index]) / SAMPLE_RATE_HZ
            self.assertAlmostEqual(observed_step, expected_step, places=11)

    def test_active_amplitude_is_constant_and_padding_is_zero(self):
        start = self.waveform.frame_start_sample
        stop = start + self.waveform.signal_sample_count
        self.assertTrue(all(sample == 0j for sample in self.waveform.samples[:start]))
        self.assertTrue(all(sample == 0j for sample in self.waveform.samples[stop:]))
        self.assertTrue(
            all(abs(abs(sample) - 1.0) < 2e-15 for sample in self.waveform.samples[start:stop])
        )

    def test_output_is_deterministic(self):
        duplicate = generate_complex_baseband(self.symbols)
        self.assertEqual(duplicate, self.waveform)

    def test_c2_header_layout_and_size(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "260924_0001.c2"
            write_c2(output, self.waveform)
            data = output.read_bytes()
        self.assertEqual(len(data), 26 + 45_000 * 8)
        name, mode, dial_frequency = struct.unpack_from("<14sid", data)
        self.assertEqual(name, b"260924_0001.c2")
        self.assertEqual(mode, 2)
        self.assertAlmostEqual(dial_frequency, 10.1387, places=12)


if __name__ == "__main__":
    unittest.main()
