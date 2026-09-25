# WSPR-2 frequency-instability research checkpoint

This checkpoint records the repository's saved results and current research interfaces as inspected on 2026-09-25. It does not add decoder trials or alter raw results. Numerical claims below apply to the tested production WSJT-X 3.0.2 `wsprd` configuration and grids.

## 1. Research question

How does practical WSPR-2 decoding robustness change when received frequency trajectories depart from the decoder-representable constant + first-order linear drift model, especially near the weak-signal threshold?

## 2. Validated infrastructure

- The unmodified production `wsprd` executable is identified as WSJT-X 3.0.2 by package provenance and SHA-256; its matching source and the official `wsprsim` reference are documented in [environment.md](../environment.md) and [wspr-reference.md](wspr-reference.md).
- The official clean C2 signal decoded as `K1ABC FN42 33`. The independent Python encoder matched all 162 official channel symbols, and its generated C2 decoded to the same message with production `wsprd` ([Python generator validation](python-generator-validation.md)).
- WSPR C2 samples use 375 Hz, 256 samples/symbol and a 2500 Hz SNR reference. The AWGN power convention and official-simulator cross-check are documented in [AWGN calibration](awgn-calibration.md); the 1,550-trial AWGN-only baseline is in [AWGN baseline results](awgn-baseline-results.md).
- The current frequency-experiment CLI uses explicit `--no-noise`: `snr_db=None` is propagated with a boolean `no_noise`, AWGN is bypassed, and the CSV SNR field is blank. No `-999`, `inf`, or `-inf` noiseless SNR sentinel appears in this active path. Noisy runs require finite `--snrs` ([runner](../experiments/02_frequency_model_mismatch.py)). This is distinct from the official reference simulator's own clean-generation convention.
- `wsprd_linear_drift_trajectory(162, 256, drift_hz)` reproduces the decoder's symbolwise `(drift/2)(i-81)/81` frequency trajectory ([decoder source analysis](decoder-source.md), [implementation](../src/impairments/frequency.py)). The strict controls and subsequent sweep scripts call this exact implementation.
- Experiment scripts record deterministic seeds and assert trial counts, condition counts, per-condition uniqueness and, where specified, matched seed sets. These are protocol safeguards, not evidence of independence between paired trials.

## 3. Phase status

| Phase | Purpose | Status | Key artifact/result | Notes |
| --- | --- | --- | --- | --- |
| 0A | Pin production decoder and environment | PASS | [environment.md](../environment.md) | WSJT-X 3.0.2 binary/source provenance and hashes recorded. |
| 0B | Official WSPR clean reference | PASS | [wspr-reference.md](wspr-reference.md) | Official C2 produced one exact-message production decode. |
| 1B | Independent Python generator | PASS | [python-generator-validation.md](python-generator-validation.md) | 162/162 symbols match; Python C2 decoded. |
| 2A AWGN baseline | Calibrate noise and measure clean-signal threshold | PASS | [AWGN baseline](awgn-baseline-results.md) | 1,550 trials; measured SNR curve and interpolated thresholds. |
| 2B linear drift | Exact drift controls and two robustness maps | CONFIRMED | [Strict controls](../results/csv/stages/), [coarse](../results/csv/linear_drift_map/), [refined](../results/csv/linear_drift_boundary/) | Confirmation is limited to tested drift/SNR grids and decoder. |
| 2C orthogonal quadratic residual | Probe beyond-first-order model mismatch | EXPLORATORY | [Quadratic pilot](../results/csv/quadratic_residual_pilot/) | Synthetic basis projected off constant and linear terms; not a physical oscillator model. |
| Linear × quadratic interaction | Balanced factorial confirmation | CONFIRMED | [Trials](../results/csv/balanced_interaction_confirm/), [model analysis](../results/analysis/balanced_interaction_confirm/) | 3,600 trials; interaction applies to the specified logit model and grid. |
| Thermal transient bridge | Project settling shapes and compare amplitude-matched decoding | EXPLORATORY | [Preflight](../results/analysis/thermal_preflight/), [trials](../results/csv/thermal_amplitude_match/) | Time constants are shape probes, not measured oscillator parameters. |
| Signed quadratic control | Compare positive/negative basis with matched seeds | EXPLORATORY | [Trials](../results/csv/signed_quadratic_control/), [comparison](../results/analysis/signed_quadratic_control/) | Sign and shape effects remain limited to the tested conditions. |
| Residual descriptor analysis | Frequency/phase descriptors and cross-shape prediction | EXPLORATORY | [Descriptors](../results/analysis/residual_descriptor_analysis/), [leave-one-shape-out](../results/analysis/leave_one_shape_out/) | Smooth deterministic families only in the first leave-one-family-out evaluation. |
| Random-walk external validation | Project stochastic FM and test prior predictors | EXPLORATORY | [Preflight](../results/analysis/random_walk_preflight/), [decoder trials](../results/csv/random_walk_decoder/), [external predictions](../results/analysis/random_walk_external_validation/) | Stochastic shape probe, not Allan-deviation/PSD calibrated. |
| RMS universality audit | Check support, calibration, bias and family effect | EXPLORATORY | [RMS audit](../results/analysis/rms_universality/) | Includes interpolation/extrapolation split and a diagnostic family-effect fit. |

## 4. Core measured results

### AWGN baseline

Piecewise-linear interpolation of adjacent observed decode probabilities gives SNR90 **-30.286 dB**, SNR50 **-31.519 dB**, and SNR10 **-32.729 dB**. Among 1,201 successful decodes with reported SNR, decoder-reported minus injected SNR had mean **+0.111 dB** and median **0.0 dB**. These are from [threshold metadata](../results/csv/awgn_baseline_thresholds.json) and [trial data](../results/csv/awgn_baseline_trials.csv), not fitted universal thresholds.

### Exact linear drift

The [coarse map](../results/csv/linear_drift_map/linear_drift_map_matrix.csv) used 100 trials per cell: at -28 dB, `P_decode` at ±2 Hz was 0.91/0.91; at -30 dB, drift 0 was 0.98 and ±2 Hz was 0.25/0.33; at -31 dB, drift 0 was 0.79 and ±2 Hz was 0.02/0.03. The [refined map](../results/csv/linear_drift_boundary/linear_drift_boundary_matrix.csv) used 200 trials per cell over -29.5 to -31.5 dB and signed drift up to ±1 Hz.

The saved [D50 interpolation](../results/analysis/final_core_results/core_metrics.csv), in Hz, retains drift sign:

| SNR (dB) | Positive D50 | Negative D50 |
| ---: | ---: | ---: |
| -29.5 | Not bracketed | Not bracketed |
| -30.0 | 0.6981 | 0.7105 |
| -30.5 | 0.4831 | 0.4886 |
| -31.0 | 0.2985 | 0.3313 |
| -31.5 | 0.0000 | 0.0000 |

At -31.5 dB, `P_decode=0.5` at zero drift, so the tabulated D50 is the observed grid endpoint, not an inferred positive tolerance. No D50 is extrapolated at -29.5 dB.

### Orthogonal quadratic residual

The [pilot matrix](../results/csv/quadratic_residual_pilot/quadratic_residual_pilot_matrix.csv) used 100 trials per cell. Its saved [A50 interpolation](../results/analysis/final_core_results/core_metrics.csv) is **0.5776, 0.4408, 0.3110, 0.2026 Hz** at SNR **-29.5, -30.0, -30.5, -31.0 dB**, respectively. The basis is formed by projecting `x²` off `[1,x]`, with `x=(i-81)/81`; at 1 Hz amplitude the stored numerical dot products with constant and `x` were -1.710e-14 and 4.441e-16 Hz ([core summary](../results/analysis/final_core_results/results_summary.md)).

### Balanced linear × quadratic interaction

In the 3,600-trial balanced dataset, the specified M1 logit interaction coefficient `bDA` is **10.1555 log-odds/Hz²**, with cluster-robust SE **0.8389** and 1,000-fit cluster-bootstrap 95% interval **[8.5377, 11.9454]** ([coefficients](../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_coefficients.csv), [bootstrap](../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_bootstrap_bDA.csv)).

| Model | AIC | BIC | Brier |
| --- | ---: | ---: | ---: |
| M0, no D×A term | 3534.398 | 3559.153 | 0.160689 |
| M1, with D×A term | 3405.319 | 3436.263 | 0.153797 |

Source: [model comparison](../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_model_comparison.csv).

### Thermal preflight and amplitude matching

For `K=1 Hz`, the projected residual's `g_tau=max|r|` is **0.322981, 0.141356, 0.048772 Hz** at τ **30, 60, 120 s**. Correlation of each normalized residual with the *positive* orthogonal quadratic basis is **-0.956853, -0.988241, -0.996991**, respectively ([preflight metrics](../results/analysis/thermal_preflight/thermal_preflight_metrics.csv)). The [amplitude-matched trials](../results/csv/thermal_amplitude_match/) and [signed control](../results/csv/signed_quadratic_control/) separate target magnitude from curvature sign; they do not establish physical parameter values.

### Random-walk preflight and decoder outcomes

The [preflight](../results/analysis/random_walk_preflight/) generated 1,000 projected trajectories at each σ_step = **0.005, 0.01, 0.02, 0.04, 0.08 Hz**. Saved median residual frequency RMS and maximum absolute phase are:

| σ_step (Hz) | Median frequency RMS (Hz) | Median max phase (rad) |
| ---: | ---: | ---: |
| 0.005 | 0.01510 | 1.9370 |
| 0.01 | 0.02993 | 3.8978 |
| 0.02 | 0.06002 | 7.8153 |
| 0.04 | 0.12067 | 15.5861 |
| 0.08 | 0.23888 | 31.1397 |

The [decoder summary](../results/csv/random_walk_decoder/random_walk_decoder_summary.csv) has 200 trials per SNR×σ cell. Entries are `P_decode` for σ = 0.01, 0.02, 0.04, 0.08 Hz:

| SNR (dB) | 0.01 | 0.02 | 0.04 | 0.08 |
| ---: | ---: | ---: | ---: | ---: |
| -30.0 | 0.935 | 0.945 | 0.815 | 0.345 |
| -30.5 | 0.885 | 0.795 | 0.675 | 0.175 |
| -31.0 | 0.745 | 0.620 | 0.355 | 0.035 |

### Descriptor-model checks

The [smooth-family leave-one-family-out analysis](../results/analysis/leave_one_shape_out/leave_one_shape_out_overall.csv) predicted each of 3,000 quadratic/thermal trials once: aggregate Brier **0.173669 (AMP)**, **0.167685 (PHASE)**, **0.168073 (RMS)**. The paired AMP-minus-PHASE Brier difference was **+0.005984**, cluster-bootstrap 95% interval **[+0.003534,+0.008470]** ([report](../results/analysis/leave_one_shape_out/leave_one_shape_out_report.txt)).

On 2,400 held-out random-walk trials, [external-model performance](../results/analysis/random_walk_external_validation/random_walk_model_performance.csv) was:

| Model | Brier | Log loss |
| --- | ---: | ---: |
| AMP | 0.147956 | 0.466755 |
| PHASE | 0.161398 | 0.501690 |
| RMS | 0.145333 | 0.457456 |

The [six-family RMS audit](../results/analysis/rms_universality/rms_leave_one_family_performance.csv) used 5,400 rows. Held-out Brier was **0.15396** (quadratic positive), **0.17055** (quadratic negative), **0.18847** (thermal τ30), **0.16758** (τ60), **0.15684** (τ120), and **0.14501** (random walk). For random walk, only **933/2,400** held-out rows were inside the training RMS support; **1,467** were outside. The diagnostic all-data [family-effect comparison](../results/analysis/rms_universality/rms_family_effect_comparison.csv) gave M_RMS AIC/BIC/Brier **5177.862/5197.644/0.156575**, versus M_RMS+family **5178.173/5230.926/0.156226**. Its family terms are diagnostic, not a deployable cross-family predictor. At -31 dB, held-out random-walk mean observed-minus-predicted probability was **-0.0524**, trajectory-cluster bootstrap 95% interval **[-0.0804,-0.0248]** ([bias table](../results/analysis/rms_universality/rms_family_bias.csv)).

## 5. Claims currently supported by the data

- Within the tested grid, exact first-order drift has an SNR-dependent decode-probability boundary; signed D50 estimates are reported only where bracketed.
- The projected quadratic residual is orthogonal to the tested constant-plus-linear basis within numerical precision, and its tested nonzero amplitudes reduced decode probability near threshold relative to zero amplitude.
- Within the balanced grid and specified logit model, the nonzero D×A coefficient and bootstrap interval indicate non-additivity on the fitted log-odds scale.
- The tested τ30/60/120 thermal residual shapes become progressively more correlated with the negative quadratic basis after projection. Equal peak frequency amplitude alone did not collapse all observed cross-shape decode rates.
- Maximum phase excursion improved held-out Brier prediction over peak frequency amplitude among the five smooth deterministic families, but performed worse than both AMP and RMS on the held-out random-walk trials.
- Residual-frequency RMS had the lowest Brier of the three externally tested scalar descriptor models on random walk; it remains a candidate cross-family severity descriptor, not a universal law. The held-out family biases and support limits show remaining family-dependent error near threshold.

## 6. Claims not yet supported

- No universal oscillator-instability law, and no claim that the quadratic residual is itself a physical oscillator model.
- No hardware validation or validation against real measured oscillator frequency traces.
- No Doppler validation or calibration of the random walk to measured oscillator Allan deviation or frequency-noise PSD.
- No claim that frequency RMS is universal, that the results apply to every WSPR decoder, or that they cover every WSPR propagation condition. Decoder findings concern the tested production WSJT-X 3.0.2 `wsprd`.

## 7. Important methodological caveats

- Search/acquisition behavior is implementation-specific. The decoded-message probability is not a decoder-independent property of the waveform.
- Deterministic-family trials reuse a small number of fixed shapes over many AWGN draws; each family×SNR cell in the RMS audit has only two trajectory clusters. Trajectory-cluster bootstrap intervals for such cells can be unstable or misleading.
- Paired comparisons must preserve the matched noise-seed design. Repeated seeds across conditions are intentional and must not be treated as independent observations.
- D50/A50 interpolation is confined to observed brackets. The -31.5 dB zero-drift D50 is a boundary point; the -29.5 dB linear D50 is not estimated.
- A low Brier score in a near-certain or near-impossible decoding regime is not by itself a measure of greater robustness. Compare predictors on the same held-out trials and inspect calibration and support.
- All residual descriptors concern trajectories *after* projection off the decoder-representable constant and linear components. In the RMS audit, 1,467/2,400 held-out random-walk trials required RMS extrapolation beyond deterministic-family training support.

## 8. Current best working model

The current simplest tested cross-family candidate is `P_decode ≈ f(SNR, residual_frequency_RMS)`, with morphology-dependent residual error near threshold. This is a working summary of the tested models, not a universal relationship.

## 9. Next research priorities

A. Literature re-audit against the now-specific contribution.
B. Measured or physically calibrated oscillator instability.
C. Real WSPR sample sanity check, if samples are available.
D. Doppler and nonstationary propagation extension.
E. Decoder-mechanism analysis or an oracle receiver, only if needed.

## 10. Artifact index

- [Raw decoder results](../results/csv/): AWGN baseline; strict controls in `stages/`; linear drift coarse/refined; quadratic pilot; balanced interaction; thermal amplitude match; signed quadratic; random-walk decoder.
- [Derived analyses](../results/analysis/): final core metrics; balanced interaction; thermal preflight and comparison; signed-quadratic comparison; residual descriptors; leave-one-shape-out; random-walk preflight/external validation; RMS universality; roughness diagnostic.
- [Final core figures](../results/figures/final_core/): AWGN, linear drift, quadratic residual and interaction plots currently present.
- Main experiment scripts: [AWGN baseline](../scripts/run_awgn_baseline.sh), [strict linear controls](../scripts/run_linear_validation_strict.py), [coarse drift](../scripts/run_linear_drift_map.py), [refined drift](../scripts/run_linear_drift_boundary.py), [quadratic pilot](../scripts/run_quadratic_residual_pilot.py), [balanced interaction](../scripts/run_balanced_interaction_confirm.py), [thermal preflight](../scripts/thermal_preflight.py), [signed control](../scripts/run_signed_quadratic_control.py), and [random-walk external validation](../scripts/run_random_walk_external_validation.py).
- Main analysis scripts: [core consolidation](../scripts/consolidate_final_core.py), [descriptors](../scripts/analyze_residual_descriptors.py), [leave-one-shape-out](../scripts/analyze_leave_one_shape_out.py), [RMS audit](../scripts/analyze_rms_universality.py), and [roughness diagnostic](../scripts/analyze_roughness_descriptors.py).

## 11. Reproducibility rules

- Never place expected results in a result file; report **NOT RUN** for an experiment that was not executed.
- Use the pinned production decoder for any `P_decode` claim, and record its provenance, invocation and exact trial seeds.
- Preserve raw CSVs. Put derived analyses in separate paths and retain source-file references.
- Assert trial totals, condition counts, seed uniqueness, matched-seed equality where designed, and summary arithmetic. Stop on an integrity failure.
- Do not silently change a trajectory definition, SNR calibration, decoder configuration, grid, seed rule or success criterion between comparisons.
