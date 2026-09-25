import math
import random
import statistics
import unittest

from impairments.noise import add_awgn, complex_noise_power_for_wspr_snr


class NoiseCalibrationTests(unittest.TestCase):
    SAMPLE_COUNT = 100_000
    CLEAN = (1.0 + 0.0j,) * SAMPLE_COUNT

    def test_fixed_seed_is_deterministic_and_input_is_unchanged(self):
        original = self.CLEAN
        first = add_awgn(original, -20.0, random.Random(12345))
        second = add_awgn(original, -20.0, random.Random(12345))
        self.assertEqual(first, second)
        self.assertIs(original, self.CLEAN)
        self.assertTrue(all(sample == 1.0 + 0.0j for sample in original))

    def test_noise_is_zero_mean_and_circular(self):
        noisy = add_awgn(self.CLEAN, -20.0, random.Random(20260924))
        noise = [sample - 1.0 for sample in noisy]
        real = [sample.real for sample in noise]
        imag = [sample.imag for sample in noise]
        real_variance = statistics.pvariance(real)
        imag_variance = statistics.pvariance(imag)
        target_component_variance = complex_noise_power_for_wspr_snr(1.0, -20.0) / 2.0
        self.assertLess(abs(statistics.fmean(real)), 0.02)
        self.assertLess(abs(statistics.fmean(imag)), 0.02)
        self.assertAlmostEqual(real_variance / target_component_variance, 1.0, delta=0.02)
        self.assertAlmostEqual(imag_variance / target_component_variance, 1.0, delta=0.02)
        self.assertAlmostEqual(real_variance / imag_variance, 1.0, delta=0.03)

    def test_measured_complex_noise_power_matches_target(self):
        requested_snr = -27.0
        noisy = add_awgn(self.CLEAN, requested_snr, random.Random(91))
        measured = math.fsum(abs(sample - 1.0) ** 2 for sample in noisy) / len(noisy)
        target = complex_noise_power_for_wspr_snr(1.0, requested_snr)
        self.assertAlmostEqual(measured / target, 1.0, delta=0.015)

    def test_ten_db_lower_snr_requires_ten_times_noise_power(self):
        easier = complex_noise_power_for_wspr_snr(1.0, -20.0)
        harder = complex_noise_power_for_wspr_snr(1.0, -30.0)
        self.assertAlmostEqual(harder / easier, 10.0, places=12)


if __name__ == "__main__":
    unittest.main()
