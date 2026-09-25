# Final core results

- AWGN SNR50: -31.5195 dB (piecewise-linear interpolation of measured SNR points).
- Linear D50 (Hz; refined grid, signed drift retained):

| SNR (dB) | Positive drift | Negative drift |
|---:|---:|---:|
| -29.5 | not bracketed | not bracketed |
| -30 | 0.6981 | 0.7105 |
| -30.5 | 0.4831 | 0.4886 |
| -31 | 0.2985 | 0.3313 |
| -31.5 | 0.0000 | 0.0000 |

- Quadratic A50 (Hz; pilot grid):

| SNR (dB) | A50 (Hz) |
|---:|---:|
| -29.5 | 0.5776 |
| -30 | 0.4408 |
| -30.5 | 0.3110 |
| -31 | 0.2026 |

- Balanced interaction bDA: 10.155478; cluster-robust SE: 0.838943; cluster-bootstrap 95% interval: [8.537717, 11.945403] (1,000 successful fits).

| Model | AIC | BIC | Brier score |
|:---|---:|---:|---:|
| M0 | 3534.398 | 3559.153 | 0.160689 |
| M1 | 3405.319 | 3436.263 | 0.153797 |

The controlled quadratic residual is orthogonal to the constant and linear basis within numerical precision (dot products -1.710e-14 and 4.441e-16 at A_res = 1 Hz).
