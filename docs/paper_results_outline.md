# Proposed Results Structure

This is an outline of existing results, not a new analysis. Numerical entries refer to the specified production WSJT-X 3.0.2 `wsprd`, WSPR-2 waveform, AWGN convention, grids, and seeds. The [research checkpoint](research_checkpoint.md) records the earlier scope and limitations; the later [oscillator preflight](../results/analysis/oscillator_physics_preflight/) and [physical decoder sweep](../results/csv/physical_oscillator_decoder/) add synthetic Allan-targeted families. Proposed composites or plots are labeled as such and have not been generated here.

## R1. Decoder and AWGN validation

- Establish the chain: official WSJT-X 3.0.2 reference, independent Python encoder matching **162/162** official channel symbols, clean Python C2 decoding `K1ABC FN42 33` with the unmodified production decoder ([reference](wspr-reference.md), [generator validation](python-generator-validation.md)).
- State the [calibrated 2500 Hz SNR convention](awgn-calibration.md) for 375 Hz complex C2 samples. In the [1,550-trial AWGN baseline](awgn-baseline-results.md), piecewise interpolation of sampled probabilities gives SNR90 **−30.286 dB**, SNR50 **−31.519 dB**, SNR10 **−32.729 dB**. For 1,201 successful decodes with reported SNR, `reported − injected` has mean **+0.111 dB** and median **0.0 dB** ([saved thresholds](../results/csv/awgn_baseline_thresholds.json)).
- What it establishes: an end-to-end production-decoder baseline under the tested generated waveform and AWGN convention. It does not establish behavior for other decoders or propagation channels.
- Recommended artifact: existing [AWGN decode-probability figure](../results/figures/final_core/awgn_decode_probability.png); a compact threshold-and-offset table from the saved thresholds JSON.

## R2. First-order linear-drift robustness

- Define the **decoder-representable** trajectory as `Δf_i=(D/2)(i−81)/81`, held constant for each of 256 samples/symbol ([source analysis](decoder-source.md), [implementation](../src/impairments/frequency.py)). Noiseless strict controls decoded at drift `0, ±1, ±2, ±3, ±4` Hz, one trial each; −20 dB controls decoded **20/20** at each of those nine values ([strict-control CSVs](../results/csv/stages/)). At −31 dB, strict controls recorded **141/200** at 0 Hz, **8/200** at +2 Hz, and **7/200** at −2 Hz.
- Present the [coarse 2D map](../results/csv/linear_drift_map/linear_drift_map_matrix.csv) and [200-trial/cell refined map](../results/csv/linear_drift_boundary/linear_drift_boundary_matrix.csv). The coarse map has `P_decode=0.91` at both ±2 Hz and −28 dB, versus 0.02/+2 and 0.03/−2 at −31 dB. Retain signed results; do not silently average positive and negative drift.
- Signed, grid-interpolated D50 (Hz): at −30.0 dB, **+0.6981/−0.7105**; −30.5 dB, **+0.4831/−0.4886**; −31.0 dB, **+0.2985/−0.3313** ([core metrics](../results/analysis/final_core_results/core_metrics.csv)). At −29.5 dB neither direction is bracketed; at −31.5 dB the recorded D50 is 0 at the observed zero-drift boundary. Do not extrapolate.
- Framing: these are production-decoder robustness measurements *inside* its constant-plus-linear model class, not fundamental waveform limits.
- Recommended artifacts: existing [linear-drift heatmap](../results/figures/final_core/linear_drift_heatmap.png) and [D50 boundary](../results/figures/final_core/linear_drift_boundary.png), possibly assembled as two panels.

## R3. Beyond-first-order residual curvature

- Construct the controlled basis from `x_i=(i−81)/81`, `q=x²`, `X=[1,x]`, `q_perp=q−X lstsq(X,q)`, then normalize by `max|q_perp|` and scale by `A_res` ([implementation](../src/impairments/frequency.py)). At `A_res=1 Hz`, saved dot products with constant and `x` are **−1.710×10⁻¹⁴** and **4.441×10⁻¹⁶ Hz**, respectively ([core summary](../results/analysis/final_core_results/results_summary.md)).
- In the [100-trial/cell pilot](../results/csv/quadratic_residual_pilot/quadratic_residual_pilot_matrix.csv), grid-interpolated A50 is **0.5776, 0.4408, 0.3110, 0.2026 Hz** at −29.5, −30.0, −30.5, −31.0 dB. Show only interpolations bracketed by tested amplitudes.
- Framing: a controlled constant-plus-linear-orthogonal **model-mismatch basis**, not a physical oscillator model or a decoder-independent limit.
- Recommended artifacts: existing [quadratic heatmap](../results/figures/final_core/quadratic_residual_heatmap.png) and [A50 boundary](../results/figures/final_core/quadratic_residual_boundary.png), possibly assembled as two panels.

## R4. Joint first-order and beyond-first-order effects

- Present the [balanced factorial](../results/csv/balanced_interaction_confirm/): SNR `−30.0, −30.5, −31.0` dB; `D=0, +0.5 Hz`; `A_res=0, 0.25, 0.5 Hz`; 200 trials per cell; 3,600 total. Within each SNR, all six `D×A` conditions share the same 200 noise seeds.
- The fitted D×A logit coefficient is `bDA=10.1555 log-odds/Hz²`, ordinary SE 0.9125, cluster-robust SE **0.8389**, and 1,000-fit cluster-bootstrap 95% interval **[8.5377, 11.9454]** ([coefficients](../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_coefficients.csv), [bootstrap](../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_bootstrap_bDA.csv)). [M0/M1 comparison](../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_model_comparison.csv): AIC **3534.398/3405.319**, BIC **3559.153/3436.263**, Brier **0.160689/0.153797**.
- Describe only non-additivity on this fitted log-odds scale, within its grid. Do not infer a decoder mechanism.
- Recommended artifacts: existing [balanced-interaction figure](../results/figures/final_core/balanced_interaction.png); compact coefficient/model-comparison table.

## R5. Thermal-transient bridge

- Define the shape probe `f_raw(t)=K(1−exp(−t/τ))` at WSPR symbol centers, then remove its best `[1,x]` fit ([thermal preflight](../results/analysis/thermal_preflight/thermal_preflight_metrics.csv)). For `K=1 Hz`, `g_τ=max|r|` is **0.322981, 0.141356, 0.048772 Hz** at τ **30, 60, 120 s**. Correlations with the **negative** quadratic basis are **+0.956853, +0.988241, +0.996991** (the stored correlations with the positive basis have opposite sign).
- Describe [amplitude-matched thermal decoding](../results/csv/thermal_amplitude_match/) and the [signed-quadratic control](../results/csv/signed_quadratic_control/). For example, at −30 dB and `|A|=0.5 Hz`, observed thermal `P_decode` is **0.68/0.50/0.46** for τ 30/60/120 s, versus **0.35/+quadratic** and **0.36/−quadratic** in the matched-seed signed control ([comparison](../results/analysis/signed_quadratic_control/thermal_vs_signed_quadratic.csv)). Do not equate similar correlation with equivalent decoder behavior.
- Framing: slower tested thermal shapes approach the negative-quadratic shape *after projection*. The τ values and K scales are not measured oscillator parameters.
- Recommended artifacts: existing [normalized thermal-vs-quadratic shape figure](../results/analysis/thermal_preflight/thermal_vs_quadratic.png); compact amplitude-matched comparison table from saved CSVs. A comparison plot would be **proposed**, not existing.

## R6. Cross-trajectory severity descriptors

- Define the compared scalars after projection: peak absolute residual frequency (AMP), maximum residual phase excursion (PHASE), and residual-frequency RMS (RMS). Distinguish the first [five-family smooth-shape holdouts](../results/analysis/leave_one_shape_out/) from the later [random-walk external test](../results/analysis/random_walk_external_validation/).
- Smooth-family leave-one-family-out (3,000 predictions, once per trial): AMP/PHASE/RMS Brier **0.173669/0.167685/0.168073** and log loss **0.522790/0.505995/0.507057** ([overall table](../results/analysis/leave_one_shape_out/leave_one_shape_out_overall.csv)). Paired AMP-minus-PHASE Brier difference **+0.005984**, cluster-bootstrap 95% interval **[+0.003534,+0.008470]** ([report](../results/analysis/leave_one_shape_out/leave_one_shape_out_report.txt)).
- Held-out random-walk (2,400 trials): AMP/PHASE/RMS Brier **0.147956/0.161398/0.145333** and log loss **0.466755/0.501690/0.457456** ([external table](../results/analysis/random_walk_external_validation/random_walk_model_performance.csv)). PHASE improves over AMP for the tested smooth deterministic families but not for random-walk FM; RMS has the lowest Brier and log loss among these three frozen models on random walk.
- Qualify the RMS candidate with the [six-family support audit](../results/analysis/rms_universality/): **1,467/2,400** random-walk holdouts fell outside deterministic-family training RMS support. The all-data family-effect fit is diagnostic, not an external predictor; M_RMS versus M_RMS+family AIC **5177.862/5178.173**, BIC **5197.644/5230.926**, Brier **0.156575/0.156226** ([diagnostic comparison](../results/analysis/rms_universality/rms_family_effect_comparison.csv)). Do not call RMS universal.
- Recommended artifact: a descriptor comparison table using the two saved performance CSVs. An observed-versus-predicted or calibration figure for these descriptor models is **not currently present**; [saved predictions](../results/analysis/leave_one_shape_out/leave_one_shape_out_predictions.csv) and [calibration bins](../results/analysis/random_walk_external_validation/random_walk_calibration_bins.csv) could support a later, separately labeled figure.

## R7. Stochastic random-walk FM

- The [random-walk preflight](../results/analysis/random_walk_preflight/) used `σ_step=0.005, 0.01, 0.02, 0.04, 0.08 Hz` and 1,000 trajectories per level. Median projected frequency RMS increases **0.01510, 0.02993, 0.06002, 0.12067, 0.23888 Hz** across that grid ([distribution summary](../results/analysis/random_walk_preflight/random_walk_distribution_summary.csv)).
- Decoder trials used σ_step **0.01, 0.02, 0.04, 0.08 Hz**, 200 per SNR×σ cell. At −30.0 dB, `P_decode` is **0.935, 0.945, 0.815, 0.345**; at −30.5 dB, **0.885, 0.795, 0.675, 0.175**; at −31.0 dB, **0.745, 0.620, 0.355, 0.035** ([decoder summary](../results/csv/random_walk_decoder/random_walk_decoder_summary.csv)). The frozen RMS model's external Brier/log loss is **0.145333/0.457456**.
- Framing: a stochastic shape probe. This σ_step grid is not calibrated to measured Allan deviation or frequency-noise PSD.
- Recommended artifacts: a random-walk `P_decode` matrix **proposed from** the saved decoder summary; existing [descriptor-scaling figure](../results/analysis/random_walk_preflight/random_walk_descriptor_scaling.png).

## R8. Allan-deviation-calibrated oscillator families

- Reuse the [synthetic white, flicker, and random-walk FM preflight](../scripts/oscillator_physics_preflight.py). Expected Allan slopes are −0.5, 0, +0.5; measured **raw** slopes are **−0.5026, −0.0279, +0.4387**, and **projected** slopes are **−0.4344, +0.0116, +0.4367**, within the configured ±0.18 slope tolerance ([saved decoder report](../results/analysis/physical_oscillator_decoder/physical_oscillator_decoder_report.txt)). The preflight used 500 trajectories per family×carrier×stability cell.
- Present the [production-decoder sweep](../results/csv/physical_oscillator_decoder/): carriers **10/14/28 MHz**, target `σ_y(1 s)=1×10⁻⁹, 3×10⁻⁹, 1×10⁻⁸`, SNR **−30.5/−31.0 dB**, 100 trials in each of **54** cells. Each raw fractional-frequency process is calibrated to an ensemble 1-second Allan target, converted by `Δf=f_c y`, sampled at validated symbol centers, and projected off `[1,x]` before applying the residual. The same oscillator seed is reused across the two SNR values; AWGN seeds are matched across physical cells at a given SNR and trial index ([execution report](../results/analysis/physical_oscillator_decoder/physical_oscillator_decoder_report.txt)).
- Same fractional target, different families: at **10 MHz**, `σ_y(1 s)=1×10⁻⁸`, and **−31 dB**, median residual RMS is **0.09746/0.15570/0.34478 Hz** for white/flicker/random-walk FM; observed `P_decode` is **0.53/0.22/0.01**, each based on 100 trials ([scaling audit](../results/analysis/physical_oscillator_decoder/physical_oscillator_scaling_audit.csv), [decoder summary](../results/csv/physical_oscillator_decoder/physical_oscillator_decoder_summary.csv)).
- Carrier comparison: for random-walk FM at `σ_y(1 s)=3×10⁻⁹` and **−31 dB**, 10/14/28 MHz median residual RMS is **0.11282/0.14218/0.27776 Hz**, with observed `P_decode` **0.43/0.27/0.02**. These are Monte Carlo cell estimates, not hardware specifications.
- The [frozen RMS-model external score](../results/analysis/physical_oscillator_decoder/physical_oscillator_model_performance.csv) on all 5,400 new trials is Brier **0.143960** and log loss **0.441462**; no physical-sweep outcomes were used for refitting.
- Framing: the synthetic generators reproduced the expected qualitative Allan slopes within the configured preflight tolerance. Do not claim traceable metrology calibration or measured oscillator performance.
- Recommended artifacts: existing [Allan-deviation curves](../results/analysis/oscillator_physics_preflight/allan_deviation_by_noise_type.png); existing [RMS-vs-carrier](../results/analysis/oscillator_physics_preflight/residual_rms_vs_carrier.png) and [RMS-vs-stability](../results/analysis/oscillator_physics_preflight/residual_rms_vs_stability.png); a physical-decoder grouped result or heatmap is **proposed from** the 54-row summary and does not yet exist.

## R9. Engineering interpretation

Organize the existing measurements as `fractional stability → absolute frequency deviation in Hz → removal of decoder-representable constant + linear terms → residual-frequency severity → production-decoder P_decode`. At equal target fractional stability, the saved carrier scaling audit shows larger median residual Hz at higher carrier frequency. Family-specific residual severity differs at the same target Allan level. Across the tested weak-signal grids, fewer residual excursions remain tolerable as SNR falls. State these as observed trends under the simulated conditions; do not derive an untested oscillator procurement threshold or new numerical requirement.

## R10. Limitations

- The outcome includes implementation-specific production-`wsprd` search and acquisition behavior; there is no oracle receiver or decoder-independent limit.
- No hardware measurement, measured oscillator trace, or Doppler/nonstationary propagation validation is present. Synthetic power-law processes have finite cadence, bandwidth/low-frequency cutoff, and ensemble Allan-target calibration; they are not traceable metrology references.
- Grids and Monte Carlo cell sizes are finite. Wilson intervals, matched seeds, and interpolation bounds must accompany claims. Some earlier deterministic-family shape comparisons reuse only a few fixed shapes; trajectory-cluster bootstrap intervals with very small cluster counts can be unstable.
- Residual descriptors are calculated after `[1,x]` projection. Peak frequency, phase excursion, and RMS do not specify an entire trajectory. RMS remains a candidate scalar descriptor with family-dependent errors and out-of-support predictions, not a universal law.

# Figure Plan

Seven main-text figure slots are proposed. A composite made from existing panels and any figure marked *proposed* would require separate figure production; this documentation task creates no figures.

| Figure | Working title | Source artifact | Main message | Placement |
| --- | --- | --- | --- | --- |
| F1 | AWGN baseline decode probability | Existing [AWGN figure](../results/figures/final_core/awgn_decode_probability.png) | Tested production baseline and interpolated thresholds | Main text |
| F2 | Signed linear-drift map and D50 | Existing [heatmap](../results/figures/final_core/linear_drift_heatmap.png) + [boundary](../results/figures/final_core/linear_drift_boundary.png); proposed composite | SNR-dependent drift tolerance within decoder model class | Main text |
| F3 | Orthogonal quadratic map and A50 | Existing [heatmap](../results/figures/final_core/quadratic_residual_heatmap.png) + [boundary](../results/figures/final_core/quadratic_residual_boundary.png); proposed composite | Controlled beyond-first-order boundary | Main text |
| F4 | Balanced D×A interaction | Existing [interaction figure](../results/figures/final_core/balanced_interaction.png) | Observed factorial curves by SNR | Main text |
| F5 | Projected thermal versus quadratic shapes | Existing [thermal comparison](../results/analysis/thermal_preflight/thermal_vs_quadratic.png) | Projected-shape relationship, without a hardware-τ claim | Main text |
| F6 | Allan slopes and residual-Hz scaling | Existing [Allan figure](../results/analysis/oscillator_physics_preflight/allan_deviation_by_noise_type.png), [carrier scaling](../results/analysis/oscillator_physics_preflight/residual_rms_vs_carrier.png); proposed composite | Validated qualitative slopes and carrier-dependent Hz scaling | Main text |
| F7 | Physical oscillator decoder response | [54-row decoder summary](../results/csv/physical_oscillator_decoder/physical_oscillator_decoder_summary.csv); figure proposed, **not yet generated** | Measured `P_decode` across family, carrier, stability, and SNR | Main text |
| S1 | Random-walk shape and outcome diagnostics | Existing [descriptor scaling](../results/analysis/random_walk_preflight/random_walk_descriptor_scaling.png); [decoder summary](../results/csv/random_walk_decoder/random_walk_decoder_summary.csv) for a proposed matrix | Stochastic probe detail | Supplementary |
| S2 | Descriptor prediction and calibration | [Smooth holdout predictions](../results/analysis/leave_one_shape_out/leave_one_shape_out_predictions.csv), [random-walk calibration bins](../results/analysis/random_walk_external_validation/random_walk_calibration_bins.csv); plot proposed, **not yet generated** | Prediction diagnostics and support | Supplementary |
| S3 | Interaction model check and other trajectory shapes | Existing [model check](../results/figures/final_core/interaction_model_check.png), [thermal residual shapes](../results/analysis/thermal_preflight/thermal_residual_shapes.png), [oscillator examples](../results/analysis/oscillator_physics_preflight/projected_example_trajectories.png) | Model and shape diagnostics | Supplementary |

# Table Plan

| Table | Contents | Exact source | Placement |
| --- | --- | --- | --- |
| T1 | AWGN SNR90/50/10 and decoder-reported minus injected SNR mean/median | [Threshold metadata](../results/csv/awgn_baseline_thresholds.json) | Main text |
| T2 | Signed D50 by SNR and quadratic A50 by SNR; mark unbracketed/boundary cases | [Core metrics](../results/analysis/final_core_results/core_metrics.csv) | Main text |
| T3 | Balanced interaction `bDA`, ordinary/cluster SE, bootstrap CI, M0/M1 AIC/BIC/Brier | [Coefficients](../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_coefficients.csv), [model comparison](../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_model_comparison.csv) | Main text |
| T4 | Representative physical cells with target/realized σᵧ, median residual RMS, `P_decode`, Wilson interval | [Physical summary](../results/csv/physical_oscillator_decoder/physical_oscillator_decoder_summary.csv), [scaling audit](../results/analysis/physical_oscillator_decoder/physical_oscillator_scaling_audit.csv) | Main text |
| T5 | AMP/PHASE/RMS smooth-holdout and random-walk external Brier/log loss | [Smooth holdout](../results/analysis/leave_one_shape_out/leave_one_shape_out_overall.csv), [random-walk external](../results/analysis/random_walk_external_validation/random_walk_model_performance.csv) | Main text or supplementary, subject to space |
| S-T1 | Full 54-cell physical summary and thermal/signed paired comparisons | [Physical CSV](../results/csv/physical_oscillator_decoder/physical_oscillator_decoder_summary.csv), [thermal/signed comparison](../results/analysis/signed_quadratic_control/thermal_vs_signed_quadratic.csv) | Supplementary |

# Result hierarchy

| Result | Classification | Basis for placement |
| --- | --- | --- |
| R1 production decoder, generator, AWGN | FOUNDATIONAL | Establishes the measured baseline and signal/noise provenance. |
| R2 exact linear drift | CORE | Directly measured decoder-representable robustness boundary. |
| R3 orthogonal quadratic | CORE | Controlled beyond-first-order comparison. |
| R4 balanced interaction | CONFIRMATORY | Balanced matched-seed test of the specified D×A logit term. |
| R5 thermal bridge and signed control | BRIDGE | Connects projected transient shape to synthetic curvature controls. |
| R6 cross-shape descriptors | CORE | Tests candidate severity summaries with held-out predictions. |
| R7 uncalibrated random-walk FM | EXPLORATORY | Stochastic shape probe and external check, without oscillator metrology. |
| R8 Allan-targeted synthetic FM and physical grid | CORE | Connects fractional Allan targets to Hz residuals and tested decoder outcomes. |
| R9 engineering chain | BRIDGE | Organizes already measured transformations and trends; adds no new requirements. |
| R10 limitations and extended diagnostics | SUPPLEMENTARY | Bounds the interpretation and houses detailed checks. |

# SAFE MAIN-TEXT CLAIMS

- The tested production-decoder AWGN baseline, exact first-order drift, and orthogonal quadratic probes have measured, SNR-dependent decode-probability curves within their stated grids.
- In the balanced factorial dataset, the D×A term is nonzero on the specified fitted log-odds scale; report its cluster-aware uncertainty and model comparison.
- The synthetic white/flicker/random-walk generators reproduce expected *qualitative* Allan-deviation slopes within the configured tolerance. In the tested physical grid, equal target fractional stability maps to different residual-Hz distributions and observed decoder probabilities across families and carriers.
- The frozen RMS candidate is evaluated externally on random-walk and Allan-targeted synthetic sweeps; report its Brier/log loss together with support and calibration limits.

# QUALIFIED / DISCUSSION-ONLY CLAIMS

- Projected slow thermal-settling shapes approach the negative-quadratic basis over tested τ values; no τ value is an observed hardware constant.
- Phase excursion improves held-out prediction for tested smooth deterministic families but not for the random-walk external set. RMS is the most robust of the tested scalar candidates in the cited random-walk comparison, with remaining family-specific error and extrapolation.
- Higher carrier frequencies increase absolute residual Hz at a common target fractional stability in the tested synthetic grid. This does not specify a universal stability requirement for a radio.

# CLAIMS TO AVOID

- A universal oscillator-instability law, a universal RMS predictor, or a decoder-independent WSPR tolerance.
- Physical realism of the quadratic residual; traceable metrology calibration of synthetic FM; measured TCXO/OCXO/GPSDO performance; hardware or real-trace validation.
- Doppler or nonstationary-propagation validation, a claim covering all WSPR decoders, or a claim covering all propagation conditions.
- A decoder mechanism inferred from fitted interactions or a numeric engineering requirement outside the simulated grid.
