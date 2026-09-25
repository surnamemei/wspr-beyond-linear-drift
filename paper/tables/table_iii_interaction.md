# Table III — Balanced linear × quadratic interaction

| M1 interaction coefficient | Estimate | Ordinary SE | Cluster-robust SE | Cluster-bootstrap 95% interval |
| --- | ---: | ---: | ---: | --- |
| D × A, log-odds/Hz² | 10.1555 | 0.9125 | 0.8389 | [8.5377, 11.9454] |

| Model | Log-likelihood | AIC | BIC | Brier score |
| --- | ---: | ---: | ---: | ---: |
| M0: additive SNR + D + A | −1763.199 | 3534.398 | 3559.153 | 0.160689 |
| M1: M0 + D × A | −1697.660 | 3405.319 | 3436.263 | 0.153797 |

The balanced design has 18 cells and 200 trials/cell, with matched noise seeds within each SNR. M0/M1 are in-sample fitted-model comparisons, not external predictive scores. Sources: [coefficient CSV](../../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_coefficients.csv), [model comparison CSV](../../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_model_comparison.csv), [bootstrap results](../../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_bootstrap_bDA.csv).
