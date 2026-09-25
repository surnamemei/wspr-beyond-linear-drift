# Table V — Held-out descriptor-model scores

| Evaluation | Trial count | Metric | AMP | PHASE | RMS |
| --- | ---: | --- | ---: | ---: | ---: |
| Smooth-family leave-one-family-out | 3,000 | Brier | 0.173669 | 0.167685 | 0.168073 |
| Smooth-family leave-one-family-out | 3,000 | Log loss | 0.522790 | 0.505995 | 0.507057 |
| External symbol-rate random walk | 2,400 | Brier | 0.147956 | 0.161398 | 0.145333 |
| External symbol-rate random walk | 2,400 | Log loss | 0.466755 | 0.501690 | 0.457456 |

AMP uses peak absolute projected frequency; PHASE adds maximum absolute projected phase to AMP; RMS here denotes the separately tested SNR-plus-residual-RMS model. These comparisons are on identical held-out trials within each evaluation, but the two evaluations have different trajectory sets. Sources: [smooth holdout](../../results/analysis/leave_one_shape_out/leave_one_shape_out_overall.csv) and [random-walk external validation](../../results/analysis/random_walk_external_validation/random_walk_model_performance.csv).
