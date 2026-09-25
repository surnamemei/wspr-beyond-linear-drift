# Phase 2A: AWGN-only decode baseline

**Status: PASS.** The experiment used the unmodified production `wsprd` from official WSJT-X 3.0.2 for every trial. No frequency error, drift, phase noise, fading, interference, or other impairment was applied.

The complete Phase 1B validation passed immediately before both the coarse and full runs. The official 162-symbol oracle and clean reference artifacts were not changed.

## Calibration

The derivation and official `wsprsim` cross-check are in [awgn-calibration.md](awgn-calibration.md). For active signal power `Ps`, complex C2 sample rate `Fs = 375 Hz`, and WSPR reference bandwidth `Bref = 2500 Hz`, the implemented complex noise power is

```text
E[|n|²] = Ps × (Fs/Bref) × 10^(-SNR_2500_dB/10)
         = Ps × (375/2500) × 10^(-SNR_2500_dB/10).
```

Each independent real and imaginary Gaussian component has variance `E[|n|²]/2`. The official WSJT-X 3.0.2 simulator expresses the same conversion as a rounded `+8.2 dB` adjustment from 2500 Hz to 375 Hz. Direct measurements at -20, -25, and -30 dB agreed with the exact-bandwidth interpretation within 0.07 dB.

## Procedure

The initial 10-trial coarse grid was `[-20, -24, -26, -28, -30, -32, -34]` dB. It located the transition between -30 and -32 dB. The full run used deterministic independent seeds, four worker processes, and an isolated temporary directory for every decoder invocation. The full grid and allocations were:

| Injected SNR (dB) | N | Correct decodes | P_decode | Wilson 95% CI |
| ---: | ---: | ---: | ---: | ---: |
| -24 | 50 | 50 | 1.000 | [0.929, 1.000] |
| -25 | 50 | 50 | 1.000 | [0.929, 1.000] |
| -26 | 100 | 100 | 1.000 | [0.963, 1.000] |
| -27 | 200 | 200 | 1.000 | [0.981, 1.000] |
| -28 | 200 | 200 | 1.000 | [0.981, 1.000] |
| -29 | 200 | 200 | 1.000 | [0.981, 1.000] |
| -30 | 200 | 196 | 0.980 | [0.950, 0.992] |
| -31 | 200 | 140 | 0.700 | [0.633, 0.759] |
| -32 | 200 | 63 | 0.315 | [0.255, 0.382] |
| -33 | 100 | 2 | 0.020 | [0.006, 0.070] |
| -34 | 50 | 0 | 0.000 | [0.000, 0.071] |

Every success required the exact message `K1ABC FN42 33`; synchronization or arbitrary output was not counted. All 1,550 decoder processes exited with status 0.

Piecewise linear interpolation between adjacent measured points gives:

- `SNR_90 = -30.286 dB`;
- `SNR_50 = -31.519 dB`; and
- `SNR_10 = -32.729 dB`.

These interpolations describe the sampled curve and are not fitted decoder models.

## Decoder-reported SNR check

There were 1,201 successful decodes with a reported SNR. Across them, `reported − injected` had mean `+0.111 dB` and median `0.0 dB`. Per-point mean offsets ranged from -0.04 dB through +0.40 dB across points with substantial successful samples; the two rare successes at -33 dB each reported 1 dB higher. Stdout reports integer SNR, so this behavior shows no unexplained calibration offset.

## Plausibility and runtime

The official [WSJT-X User Guide](https://wsjtx.github.io/wsjtx/guide-full.html) describes WSPR as effective down to approximately -31 dB in a 2500 Hz bandwidth. This experiment found `P_decode = 0.70` at -31 dB and an interpolated 50% point of -31.52 dB using WSJT-X 3.0.2 `wsprd`, which is broadly consistent. The source's own candidate-search comment associates its weak-signal region with approximately -33.3 dB in the same reference bandwidth, also consistent with the observed low-probability tail.

The full run took 61.47 seconds wall time with four workers. The summed per-trial runtime was 244.38 seconds; mean was 0.158 seconds and median 0.063 seconds. The host used Python 3.12.3. The repository has no commit at present, so metadata records `uncommitted-no-HEAD`.

## Artifacts and reproduction

- Trial-level data: `results/csv/awgn_baseline_trials.csv`
- Aggregated data: `results/csv/awgn_baseline_summary.csv`
- Configuration/runtime metadata: `results/csv/awgn_baseline_metadata.json`
- Interpolation and SNR-offset metadata: `results/csv/awgn_baseline_thresholds.json`
- Official simulator calibration measurements: `results/calibration/official_wsprsim_snr_oracle.csv`
- Figure generated from CSV: `results/figures/awgn_decode_probability.png`

Quick debugging run:

```bash
bash scripts/run_awgn_baseline.sh --quick
```

Complete experiment and figure:

```bash
bash scripts/reproduce_phase2a.sh
```

The full command reruns all clean-generator validation tests before launching decoder trials. The seed policy and exact decoder version/hash are stored with the results.

No anomaly remains that would put the AWGN calibration on hold. This result authorizes considering the next research phase, but this phase does not implement or test any frequency impairment.
