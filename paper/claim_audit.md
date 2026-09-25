# Claim and source audit

Scope: [main manuscript](main.md), [Tables I–V](tables/), and [Fig. 7](figures/fig7_physical_oscillator_decode.png). This audit uses saved repository artifacts only. No decoder or Monte Carlo trial was run for paper preparation, and no raw CSV was edited. The CSV-handling check kept raw observations separate from derived presentation tables and preserved source units and denominators.

## Numerical claims checked

| Manuscript/table claim | Saved source checked | Audit outcome |
| --- | --- | --- |
| 162 symbols; 256 samples/symbol; 375-Hz C2 rate; 110.592-s active frame; exact `K1ABC FN42 33` clean decode and 162/162 symbol match | [Reference record](../docs/wspr-reference.md), [generator validation](../docs/python-generator-validation.md) | Matches documented reference and validation. |
| 2500-Hz injected SNR convention; `P_n=P_s(375/2500)10^(−SNR/10)`; 8.239-dB exact bandwidth conversion | [AWGN calibration](../docs/awgn-calibration.md) | Formula and units match. |
| AWGN SNR90/50/10 −30.286/−31.519/−32.729 dB; reported-minus-injected mean +0.111 dB, median 0.0 dB; 1,201 reported successful decodes | [Threshold JSON](../results/csv/awgn_baseline_thresholds.json) | Matches rounded stored values; thresholds are explicitly interpolations. |
| Strict drift control grid and 20/20 at −20 dB; −31-dB 141/200, 8/200, 7/200 | [Strict-control stage outputs](../results/csv/stages/) and [results outline](../docs/paper_results_outline.md) | Matches saved summaries; noiseless cells explicitly identified as one trial each. |
| Exact drift `(D/2)(i−81)/81`; source-inspected decoder form | [Frequency impairment implementation](../src/impairments/frequency.py), [decoder source notes](../docs/decoder-source.md) | Same symbol-index convention; endpoint qualification retained. |
| Signed D50 +0.6981/−0.7105, +0.4831/−0.4886, +0.2985/−0.3313 Hz | [Core metrics CSV](../results/analysis/final_core_results/core_metrics.csv), [refined summary](../results/csv/linear_drift_boundary/linear_drift_boundary_summary.csv) | Magnitudes match stored core metrics; negative branch sign restored for presentation. |
| No −29.5-dB linear D50; zero-drift-only boundary at −31.5 dB | [Final core summary](../results/analysis/final_core_results/results_summary.md), [core metrics](../results/analysis/final_core_results/core_metrics.csv) | No outside-grid extrapolation. |
| Quadratic A50 0.5776/0.4408/0.3110/0.2026 Hz; dot products −1.710×10⁻¹⁴ and 4.441×10⁻¹⁶ at 1 Hz | [Core metrics](../results/analysis/final_core_results/core_metrics.csv), [quadratic implementation](../src/impairments/frequency.py) | Matches rounded stored values; residual is not called a physical oscillator. |
| Balanced design 18 × 200 = 3,600; `b_DA=10.1555`; SE 0.9125/0.8389; bootstrap [8.5377,11.9454]; M0/M1 AIC, BIC, Brier | [Coefficient CSV](../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_coefficients.csv), [model comparison](../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_model_comparison.csv), [bootstrap](../results/analysis/balanced_interaction_confirm/balanced_interaction_confirm_bootstrap_bDA.csv) | Matches rounded values; claim limited to fitted log-odds and in-sample scores. |
| Thermal `g_τ` 0.322981/0.141356/0.048772; correlations to negative quadratic 0.956853/0.988241/0.996991 | [Thermal preflight metrics](../results/analysis/thermal_preflight/thermal_preflight_metrics.csv) | Positive-basis correlations in source are negative; sign reversal explicitly stated for the negative basis. |
| Thermal 0.5-Hz cells at −30 dB 0.68/0.50/0.46; signed quadratic +0.35/−0.36 | [Signed-control comparison](../results/analysis/signed_quadratic_control/thermal_vs_signed_quadratic.csv) | Matches saved comparison; no equivalence claim. |
| Random-walk preflight RMS medians and 12 decoder-cell probabilities | [Preflight distribution](../results/analysis/random_walk_preflight/random_walk_distribution_summary.csv), [decoder summary](../results/csv/random_walk_decoder/random_walk_decoder_summary.csv) | Decoder probabilities checked in σ-step order; each decoder cell has 200 trials. |
| Smooth-family AMP/PHASE/RMS Brier and log loss, 3,000 held-out trials | [LOFO overall](../results/analysis/leave_one_shape_out/leave_one_shape_out_overall.csv), [report](../results/analysis/leave_one_shape_out/leave_one_shape_out_report.txt) | Matches stored scores and paired difference/CI. |
| Random-walk external AMP/PHASE/RMS Brier and log loss, 2,400 trials | [External model performance](../results/analysis/random_walk_external_validation/random_walk_model_performance.csv) | Matches stored scores; separate holdout set identified. |
| RMS support extrapolation 1,467/2,400; family-diagnostic AIC/BIC/Brier | [RMS audit](../results/analysis/rms_universality/), [diagnostic comparison](../results/analysis/rms_universality/rms_family_effect_comparison.csv) | Matches saved support count and scores; family model identified as diagnostic only. |
| White/flicker/random-walk raw and projected Allan slopes, 500 trajectories per preflight cell, ±0.18 slope tolerance | [Oscillator preflight](../results/analysis/oscillator_physics_preflight/), [physical sweep report](../results/analysis/physical_oscillator_decoder/physical_oscillator_decoder_report.txt) | Rounded slopes match report; no traceable-metrology assertion. |
| Physical grid 3 families × 3 carriers × 3 targets × 2 SNR × 100 = 5,400; six Table IV cell values; frozen RMS Brier/log loss 0.143960/0.441462 | [54-row summary](../results/csv/physical_oscillator_decoder/physical_oscillator_decoder_summary.csv), [model performance](../results/analysis/physical_oscillator_decoder/physical_oscillator_model_performance.csv), [execution report](../results/analysis/physical_oscillator_decoder/physical_oscillator_decoder_report.txt) | Values match source after rounding. Fig. 7 builder asserts 54 unique conditions, 100 trials/cell, and proportion arithmetic. |

## Final production cross-check

The seven external bibliography entries were checked against the official release and guide, an author-hosted WSPR article, an author-uploaded technical article, the HamSCI workshop listing, the NIST report, and the journal DOI record. Each key used by the LaTeX manuscript exists in both identical BibTeX files; [references_notes.md](references_notes.md) maps each citation to the supported statement and marks excluded claim types as REMOVE. The living WSJT-X User Guide has no invented publication date. External sources support protocol and related-work context, not the repository's measured decoder probabilities.

After the Introduction and LaTeX conversion, the principal numeric claims above were rechecked against saved artifacts. In particular, AWGN SNR50 is $-31.5194805$ dB in the threshold/core-metrics files; the positive signed D50 sequence at $-30/-30.5/-31$ dB is $0.6981132/0.4831081/0.2985075$ Hz (the corresponding negative branch is printed with a negative sign in the paper); the balanced interaction CSV gives $b_{DA}=10.1554779$, ordinary SE $0.9124621$, and cluster SE $0.8389427$; and the physical-sweep model-performance CSV gives Brier $0.1439602721$ and log loss $0.4414623867$ over 5,400 rows. The 54-cell source summary remains the sole data input to Fig. 7, with the builder checking 100 trials/cell and proportion arithmetic. No result source was edited.

Fully compiled LaTeX audit: pdfTeX and BibTeX through latexmk produced a nine-page IEEEtran PDF. The seven figure environments, five table environments, and seven BibTeX entries render. The final log contains no undefined citation or reference, no missing graphic, and no overfull horizontal box. Two overfull vertical-box warnings remain (73.40004 pt and 5.5157 pt); the rendered paired-figure pages need final venue-proof review. The body continues onto page 9 before references, so a no-cut [reduction plan](page_reduction_notes.md) records possible supplementary moves.

## Risky-wording search

Searched both `main.md` and `latex/main.tex` case-insensitively for `novel`, `first`, `prove`, `proves`, `fundamental`, `universal`, `guarantee`, `hardware validated`, and `real oscillator`.

| Occurrence | Decision |
| --- | --- |
| “First-Order” / “first-order” in title and section headings | Retained: a mathematical order of the decoder-aligned drift model, not a novelty or priority claim. |
| “performance guarantee” in Section VII | Retained only in the explicit negation “No ... guarantee is derived”; it prevents an engineering overclaim. |
| Other listed terms | No occurrence in either manuscript form at final static audit. |

## Claims softened or excluded

- Decoder behavior is limited to production WSJT-X 3.0.2 `wsprd`; no decoder-independent boundary is claimed.
- The quadratic residual is called a controlled orthogonal mismatch basis, not an oscillator model.
- Thermal τ values and random-walk step levels are labeled shape probes, not measured hardware constants.
- Synthetic Allan-family calibration is described as an ensemble 1-s target with qualitative slope checks, not traceable metrology.
- The 10/14/28-MHz parameter scales fractional frequency to hertz; the manuscript does not suggest separate RF hardware or band-dependent propagation was tested.
- Interaction inference is limited to fitted log-odds non-additivity; no acquisition mechanism is inferred.
- Held-out smooth-shape and external random-walk scores are not pooled or treated as a broad transfer guarantee.
- Residual RMS is a tested scalar candidate with family/support limitations, not a trajectory-independent rule.
- Hardware validation, Doppler/spread validation, measured oscillator performance, and publication-priority language are absent.

## Remaining production tasks

- Resolve or explicitly accept the two vertical overflow warnings after venue-format proofing; check small Fig. 2/4/6 labels at print size. The bibliography and cross-references are resolved.
- Supply the author/byline metadata when it is available; the LaTeX source does not invent names or affiliations.
- Figures 2, 3, and 6 remain paired source panels, not missing data. Their final scale should be checked in the compiled proof; see [figure_audit.md](figure_audit.md).
