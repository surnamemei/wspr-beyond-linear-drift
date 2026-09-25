# Phase 2B/2C frequency-control result: HOLD

## Gate outcome

Phase 2B/2C is **HOLD**. Constant CFO behaved consistently with the configured
frequency search. The linear-drift control did not remain close to the AWGN
baseline near threshold, even for a source-matched ±2 Hz/frame parameter well
inside the documented drift search. Per the phase brief, the quadratic
model-mismatch probe was not started.

All decode decisions used the unmodified official WSJT-X 3.0.2 `wsprd` binary.
The official clean reference, Python generator validation, and full unit suite
were rerun before the experiment.

## Exact production search definition

Matching source: `.cache/wsjtx-3.0.2/lib/wsprd/wsprd.c`.

- Default candidate-center filter: `fmin=-110`, `fmax=110` Hz. `-w` changes it
  to ±150 Hz. These experiments used the default and did not pass `-w`.
- Candidate spectrum grid: `df=375/256/2 = 0.732421875` Hz.
- Each candidate is searched over five coarse frequency bins (`if0-2` through
  `if0+2`). Frequency refinement then uses −0.50…+0.50 Hz in 0.25 Hz steps and
  −0.10…+0.10 Hz in 0.05 Hz steps.
- For symbol index `i=0..161`, the searched center is
  `f0 + (drift/2)*(i-81)/81`. Positive drift means increasing frequency. The
  parameter is nominal total Hz/frame; the first-to-last searched difference
  is `161/162` times that parameter.
- Passes 0 and 1 use single-symbol demodulation and search integer drift
  −4…+4 Hz/frame, followed by a one-step ±0.5 Hz refinement.
- Pass 2 uses multiple block sizes for weak-signal gain but sets `maxdrift=0`.
  When pass 0 has no decode, the three-pass loop skips pass 1 and proceeds to
  this zero-drift block pass.

The injected linear control reproduces the source expression exactly at each
symbol and accumulates phase continuously. A separate mathematical linear
trajectory test verifies the expected quadratic accumulated phase.

## Results and interpretation

The focused CFO confirmation used N=100 per cell. At −31 dB, P_decode was
0.68 at −100 Hz, 0.77 at 0 Hz, and 0.71 at +100 Hz, versus the stored AWGN
baseline 0.70 (N=200). At −29 dB the three probabilities were 1.00, 1.00, and
0.99. At ±150 Hz, outside the default candidate filter, the quick sweep yielded
0/20 at all three SNRs. This is a search-window limitation.

The focused linear confirmation used N=200 per cell:

| SNR (dB) | drift (Hz/frame) | decoded/N | P_decode | Wilson 95% CI | stored AWGN P_decode |
|---:|---:|---:|---:|---:|---:|
| -29 | -2 | 162/200 | 0.810 | 0.750–0.858 | 1.000 |
| -29 | 0 | 200/200 | 1.000 | 0.981–1.000 | 1.000 |
| -29 | +2 | 170/200 | 0.850 | 0.794–0.893 | 1.000 |
| -31 | -2 | 3/200 | 0.015 | 0.005–0.043 | 0.700 |
| -31 | 0 | 135/200 | 0.675 | 0.607–0.736 | 0.700 |
| -31 | +2 | 2/200 | 0.010 | 0.003–0.036 | 0.700 |
| -32 | -2 | 2/200 | 0.010 | 0.003–0.036 | 0.315 |
| -32 | 0 | 50/200 | 0.250 | 0.195–0.314 | 0.315 |
| -32 | +2 | 0/200 | 0.000 | 0.000–0.019 | 0.315 |

Successful drifted decodes report the expected sign and usually the injected
integer drift. Repeating the control with a continuous within-symbol linear
trajectory produced the same qualitative collapse. The evidence supports a
practical decoder/pass limitation: the near-threshold gain path does not search
drift. It does not establish a WSPR waveform/coherence limit.

Observed failures are classified as follows:

1. ±150 Hz CFO: search-window/configuration limitation.
2. Near-threshold ±2 Hz/frame control: practical decoder/model implementation
   limitation associated with pass selection.
3. Waveform/coherence limitation: not measured in this HOLD state.

No quadratic A_res sweep, heatmap, or A90/A50/A10 boundary exists. Reporting a
normalized A_res boundary in tone spacings would therefore be unsupported.

## Artifacts

- Raw trials: `results/csv/frequency_model_mismatch_trials.csv`
- Aggregate controls: `results/csv/frequency_controls_summary.csv`
- Metadata: `results/csv/frequency_model_mismatch_metadata.json`
- CFO figure: `results/figures/cfo_control.png`
- Linear-drift figure: `results/figures/linear_drift_control.png`

Reproduce with `bash scripts/reproduce_phase2bc.sh` in Ubuntu WSL.
