# Table II — Grid-interpolated 50% decode boundaries

| Injected SNR (dB) | Positive D50 (Hz) | Negative D50 (Hz) | Quadratic A50 (Hz) |
| ---: | ---: | ---: | ---: |
| −29.5 | Not bracketed | Not bracketed | 0.5776 |
| −30.0 | +0.6981 | −0.7105 | 0.4408 |
| −30.5 | +0.4831 | −0.4886 | 0.3110 |
| −31.0 | +0.2985 | −0.3313 | 0.2026 |
| −31.5 | 0.0 (boundary) | 0.0 (boundary) | Not tested |

D50 is signed drift in the exact decoder-aligned linear trajectory. The negative D50 magnitudes in [core metrics](../../results/analysis/final_core_results/core_metrics.csv) are displayed here with their negative sign. The −31.5 dB value is a zero-drift observation at the boundary, not evidence of a positive tolerance. The −29.5 dB linear grid does not bracket 50%. A50 is the nonnegative scale of the orthogonal quadratic residual. Sources: [refined linear summary](../../results/csv/linear_drift_boundary/linear_drift_boundary_summary.csv), [quadratic pilot summary](../../results/csv/quadratic_residual_pilot/quadratic_residual_pilot_summary.csv), and [core metrics](../../results/analysis/final_core_results/core_metrics.csv).
