import cmath
import math
import unittest

from impairments.frequency import (
    apply_frequency_error,
    constant_cfo_trajectory,
    linear_drift_trajectory,
    quadratic_residual_trajectory,
    wsprd_linear_drift_trajectory,
)


class FrequencyImpairmentTests(unittest.TestCase):
    def test_zero_impairment_returns_original(self):
        samples = (1 + 2j, -3j, 0j, 2 - 1j)
        self.assertEqual(apply_frequency_error(samples, (0.0,) * 4, 10.0), samples)

    def test_constant_cfo_has_expected_positive_phase_slope(self):
        output = apply_frequency_error((1 + 0j,) * 8, constant_cfo_trajectory(8, 2.0), 10.0)
        for index, sample in enumerate(output):
            self.assertAlmostEqual(cmath.phase(sample / cmath.exp(1j * math.tau * 2 * index / 10)), 0.0, places=12)

    def test_linear_drift_has_quadratic_accumulated_phase(self):
        fs = 20.0
        trajectory = linear_drift_trajectory(9, 4.0)
        output = apply_frequency_error((1 + 0j,) * 9, trajectory, fs)
        phase = 0.0
        for index, sample in enumerate(output):
            self.assertAlmostEqual(abs(sample - cmath.exp(1j * phase)), 0.0, places=12)
            phase += math.tau * trajectory[index] / fs
        increments = [trajectory[i + 1] - trajectory[i] for i in range(8)]
        self.assertTrue(all(abs(value - increments[0]) < 1e-15 for value in increments))

    def test_phase_is_continuous_and_output_deterministic(self):
        trajectory = linear_drift_trajectory(101, 7.0)
        first = apply_frequency_error((1 + 0j,) * 101, trajectory, 375.0)
        second = apply_frequency_error((1 + 0j,) * 101, trajectory, 375.0)
        self.assertEqual(first, second)
        steps = [cmath.phase(first[i + 1] * first[i].conjugate()) for i in range(100)]
        expected = [math.tau * trajectory[i] / 375.0 for i in range(100)]
        for actual, target in zip(steps, expected):
            self.assertAlmostEqual(actual, target, places=12)

    def test_wsprd_linear_definition_is_reproduced_exactly(self):
        trajectory = wsprd_linear_drift_trajectory(4, 3, 8.0)
        self.assertEqual(trajectory, (-4.0,) * 3 + (-2.0,) * 3 + (0.0,) * 3 + (2.0,) * 3)
        output = apply_frequency_error((1 + 0j,) * 12, trajectory, 100.0)
        for index in range(11):
            step = cmath.phase(output[index + 1] * output[index].conjugate())
            self.assertAlmostEqual(step, math.tau * trajectory[index] / 100.0, places=12)

    def test_quadratic_residual_normalization_and_orthogonality(self):
        count = 1001
        requested = 0.75
        residual = quadratic_residual_trajectory(count, requested)
        x = [index - (count - 1) / 2 for index in range(count)]
        self.assertAlmostEqual(max(abs(value) for value in residual), requested, places=12)
        self.assertAlmostEqual(sum(residual), 0.0, places=10)
        self.assertAlmostEqual(sum(xi * yi for xi, yi in zip(x, residual)), 0.0, places=7)


if __name__ == "__main__":
    unittest.main()
