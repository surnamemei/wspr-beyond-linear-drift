from pathlib import Path

p = Path("src/impairments/frequency.py")
s = p.read_text()
needle = '''    return tuple(
        float(total_drift_hz) * (index / (sample_count - 1) - 0.5)
        for index in range(sample_count)
    )


def quadratic_residual_trajectory'''
insert = '''    return tuple(
        float(total_drift_hz) * (index / (sample_count - 1) - 0.5)
        for index in range(sample_count)
    )


def wsprd_linear_drift_trajectory(
    symbol_count: int, samples_per_symbol: int, drift_parameter_hz: float
) -> tuple[float, ...]:
    """Reproduce the production wsprd symbolwise linear-drift definition.

    For symbol index ``i``, wsprd searches
    ``(drift/2) * (i - symbol_count/2) / (symbol_count/2)`` hertz relative
    to its center-frequency estimate. Thus for 162 symbols the actual
    first-to-last change is ``161/162 * drift``. Frequency is constant within
    each symbol while accumulated phase stays continuous at the boundaries.
    """

    if symbol_count <= 0 or samples_per_symbol <= 0 or not math.isfinite(drift_parameter_hz):
        raise ValueError("symbol sizes must be positive and drift finite")
    midpoint = symbol_count / 2.0
    values: list[float] = []
    for index in range(symbol_count):
        frequency = (float(drift_parameter_hz) / 2.0) * (index - midpoint) / midpoint
        values.extend((frequency,) * samples_per_symbol)
    return tuple(values)


def quadratic_residual_trajectory'''
assert needle in s
p.write_text(s.replace(needle, insert))

p = Path("tests/test_frequency.py")
s = p.read_text().replace(
    "    quadratic_residual_trajectory,\n)",
    "    quadratic_residual_trajectory,\n    wsprd_linear_drift_trajectory,\n)",
)
needle = "    def test_quadratic_residual_normalization_and_orthogonality(self):\n"
insert = '''    def test_wsprd_linear_definition_is_reproduced_exactly(self):
        trajectory = wsprd_linear_drift_trajectory(4, 3, 8.0)
        self.assertEqual(trajectory, (-4.0,) * 3 + (-2.0,) * 3 + (0.0,) * 3 + (2.0,) * 3)
        output = apply_frequency_error((1 + 0j,) * 12, trajectory, 100.0)
        for index in range(11):
            step = cmath.phase(output[index + 1] * output[index].conjugate())
            self.assertAlmostEqual(step, math.tau * trajectory[index] / 100.0, places=12)

    def test_quadratic_residual_normalization_and_orthogonality(self):
'''
assert needle in s
p.write_text(s.replace(needle, insert))

p = Path("experiments/02_frequency_model_mismatch.py")
s = p.read_text().replace(
    "    quadratic_residual_trajectory,\n)",
    "    quadratic_residual_trajectory,\n    wsprd_linear_drift_trajectory,\n)",
)
old = '''    if kind == "linear":
        return linear_drift_trajectory(count, value)
'''
new = '''    if kind == "linear":
        if count != 162 * 256:
            raise ValueError("wsprd linear control requires the 162x256 active frame")
        return wsprd_linear_drift_trajectory(162, 256, value)
'''
assert old in s
p.write_text(s.replace(old, new))
