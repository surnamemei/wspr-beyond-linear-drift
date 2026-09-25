# AWGN calibration for 375 Hz WSPR C2 samples

This calibration applies to the Phase 2A AWGN-only experiment. It is derived from the matching official WSJT-X 3.0.2 source and from noise-bandwidth dimensions before any decode-probability sweep.

## Source evidence

In `lib/wsprd/wsprsim.c`, lines 191–193, the official simulator states that SNR in 375 Hz is 8.2 dB higher than SNR in 2500 Hz, then computes its signal amplitude as

```text
A = sqrt(2) × 10^((SNR_2500 + 8.2)/20).
```

It adds independent unit-variance real and imaginary Gaussian samples, so its complex noise power is `E[|n|²] = 1 + 1 = 2`. Therefore its active signal power is `A²`, and its sample-domain power ratio is

```text
A² / 2 = 10^((SNR_2500 + 8.2)/10).
```

The exact bandwidth conversion is

```text
10 log10(2500/375) = 8.239087409 dB.
```

The official 8.2 dB constant is this value rounded to one decimal place.

The decoder independently returns to the 2500 Hz convention. In `lib/wsprd/wsprd.c`, lines 1047–1092, `wsprd` estimates a spectral noise percentile, forms a candidate peak-to-noise estimate in the WSPR bandwidth, and subtracts `26.3` dB for WSPR-2. Its comment relates an approximately -7 dB threshold in WSPR bandwidth to `-7 - 26.3 = -33.3 dB` in 2500 Hz. The decoder-reported SNR is an estimator and is quantized to integer dB in normal stdout; it is an independent check rather than an exact per-trial oracle.

## Dimensional derivation

Let:

- `Ps` be active complex-signal power, `E[|s|²]`;
- `N0` be complex noise power spectral density in power/Hz;
- `Fs = 375 Hz` be the complex C2 sample rate and represented noise bandwidth;
- `Bref = 2500 Hz` be the WSPR reporting reference bandwidth; and
- `Pn` be complex sample noise power, `E[|n|²]`.

White complex baseband noise sampled at `Fs` contains

```text
Pn = N0 × Fs.
```

WSPR's reference SNR is

```text
SNR_2500_linear = Ps / (N0 × Bref).
```

Eliminating `N0` gives the implemented calibration equation:

```text
Pn = Ps × (Fs/Bref) × 10^(-SNR_2500_dB/10)
   = Ps × (375/2500) × 10^(-SNR_2500_dB/10).
```

Equivalently,

```text
10 log10(Ps/Pn) = SNR_2500_dB + 10 log10(2500/375)
                = SNR_2500_dB + 8.239087409 dB.
```

For circular complex Gaussian noise `n = nI + j nQ`, the components are independent and

```text
Var(nI) = Var(nQ) = Pn/2.
```

The clean Python WSPR frame has unit active power. Exact-zero timing padding is excluded when measuring `Ps`; noise is then added to every C2 sample, including padding. For example, at -20 dB referenced to 2500 Hz, `Pn = 15` and each component variance is `7.5`.

This is why directly setting `20 log10(signal_rms/noise_rms)` to the requested WSPR SNR would be wrong by 8.239 dB in the 375 Hz C2 representation.

## Official simulator cross-check

`scripts/calibrate_awgn_oracle.py` generated official `wsprsim` C2 files at -20, -25, and -30 dB. For each file it subtracted the appropriately scaled official clean signal and measured the residual complex noise. Results are saved in `results/calibration/official_wsprsim_snr_oracle.csv`.

| Requested (dB) | Measured complex noise power | SNR inferred with exact 2500/375 ratio (dB) |
| ---: | ---: | ---: |
| -20 | 2.00044 | -20.040 |
| -25 | 1.99322 | -25.024 |
| -30 | 2.01484 | -30.071 |

The official simulator deliberately keeps complex noise power near 2 and scales the signal. Our module keeps clean signal power at 1 and scales noise instead. These are equivalent under a decoder with no absolute-amplitude dependence. The small approximately -0.04 dB expected difference comes from the official rounded `8.2` dB constant versus the exact `8.239087409` dB bandwidth ratio; finite random samples explain the remaining variation.

## Implementation and validation

`src/impairments/noise.py` implements the exact bandwidth ratio, independent equal-variance Gaussian components, and caller-supplied `random.Random` state. It does not modify the input signal or contain any frequency impairment.

Statistical tests use 100,000 samples and verify deterministic seeded output, zero component means, circularity, target complex noise power, and the expected factor-of-ten noise change for a 10 dB SNR change. The tolerances are based on sampling variation and do not assert exact random arrays.
