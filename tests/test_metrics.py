import unittest

from analysis.metrics import wilson_interval


class WilsonIntervalTests(unittest.TestCase):
    def test_known_boundary_cases(self):
        low, high = wilson_interval(0, 10)
        self.assertAlmostEqual(low, 0.0, places=15)
        self.assertAlmostEqual(high, 0.2775327998628892, places=12)
        low, high = wilson_interval(10, 10)
        self.assertAlmostEqual(low, 0.7224672001371106, places=12)
        self.assertAlmostEqual(high, 1.0, places=15)

    def test_symmetric_half_success_interval(self):
        low, high = wilson_interval(50, 100)
        self.assertAlmostEqual(low, 1.0 - high, places=14)
        self.assertLess(low, 0.5)
        self.assertGreater(high, 0.5)

    def test_invalid_counts_are_rejected(self):
        for successes, trials in ((0, 0), (-1, 10), (11, 10)):
            with self.subTest(successes=successes, trials=trials), self.assertRaises(ValueError):
                wilson_interval(successes, trials)


if __name__ == "__main__":
    unittest.main()
