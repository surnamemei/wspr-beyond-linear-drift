# Engineering extension: fixed-grid drift retries

## Source-level motivation

WSJT-X 3.0.2 searches drift during its first two passes but fixes the third-pass coarse drift range to zero, where it tries block sizes 1, 2 and 3 and an additional bit-metric mode. The source comment gives reduced frequency-estimator variance as the reason. Candidate selection, synchronization, de-duplication and thresholds precede the final-pass retry. Existing block demodulation, timing jitter, Fano decoding, message checks and subtraction remain in place.

B2 scores the fixed grid `0, +0.5, -0.5, +1.0, -1.0 Hz` at the accepted candidate's estimated frequency and time, ranks hypotheses by the received-data sync score, and tries the ordered hypotheses until the sequential decoder succeeds. B3 first runs the original zero-drift attempt and, if it fails, retries `+0.5, -0.5, +1.0, -1.0 Hz` in that order. Successful decoder output proceeds through the original unpacking and validation; if validation suppresses it, the retry loop is not resumed. No true drift, transmitted symbols, message identity or outcome labels are supplied to a practical receiver. These are fixed-search baselines, not a novel adaptive algorithm.

## Screening evidence

The selected Gate 2B pilot used one message, two SNRs, four drift values and 25 paired seeds per SNR. B2 and B3 reproduced the restricted D-only oracle's 73 recovered A0 failures without an observed loss, over 200 inputs. The oracle substituted the true drift for the first already-accepted candidate on the third pass; it did not insert a missing candidate. Its result is neither deployable performance nor a universal upper bound.

Gate 2C used two new Type-1 messages, SNRs −30.5 and −31.0 dB, and decoder-aligned drift values 0, +0.5, −0.5, +0.75 and −1.5 Hz. Forty independent noise seeds per message/SNR were each reused across the five drifts, producing 800 signal-bearing files. Another 200 independent pure-noise files and 80 dual-signal files completed the 1,080-input screening. The full run used 12,960 invocations, including production, B2 and B3 with natural, generous-instrumented and two finite work-budget settings. Each receiver saw the same input files.

For `W1AW FN31 37` at −31 dB and −0.5 Hz, natural A0 decoded 6/40, while B2 and B3 decoded 28/40; the paired difference is 0.55 with a conservative exploratory 95% interval [0.260, 0.726]. For `VK3ABC QF22 30` at −31 dB, +0.75 Hz improved from 4/40 to 26/40, while −1.5 Hz improved from 2/40 to 4/40. In the first example the CPU median/p95 were 0.450/0.500 seconds for A0, 0.383/1.943 for B2 and 0.958/1.915 for B3. Timing used four workers and is not a randomized speed benchmark.

A common 100-million-Fano-iteration cap yielded 6/40, 22/40 and 6/40 for A0, B2 and B3 in that −0.5 Hz cell. A 40-million cap yielded 5/40, 12/40 and 5/40. A fixed cap reduces costly tails but can discard correct decodes; per-call Fano limits and additional coarse, sync and demodulation counters also matter. Equal Fano iterations do not imply equal total CPU work.

All tested combinations produced 0/200 detections in the pure-noise set. The Wilson 95% upper bound is approximately 1.9% for the mixture of the two noise settings; this is not evidence of a negligible false-alarm rate. In one dual-signal nonzero-drift condition at −30.5 dB, A0 recovered the two messages in 5/20 and 3/20 frames; B2 and B3 recovered them in 15/20 and 6/20. Subtraction was enabled in all arms; a subtraction-disabled control was not run. Full per-cell probabilities, intervals, costs and outcomes are in [the summary tables](../results/engineering_extension/MANIFEST.md).

## Descriptor-model reconciliation

For the historical smooth-family and random-walk evaluations, the saved labels correspond to these predictor sets, all with an intercept: AMP = SNR + peak residual frequency; PHASE = SNR + peak + phase excursion; Table 5 RMS = SNR + peak + RMS. The separate physical-sweep RMS fit used SNR + RMS. Table 5's published numbers were reproduced for the actual models, but its label “SNR plus RMS” misdescribes the fitted Table 5 models. A retrospective true SNR-plus-RMS reanalysis and SNR-only baseline were computed from the saved splits; they do not provide new independent inference. The original smooth-family bootstrap split shared seeds across shape clusters, so its uncertainty requires reanalysis preserving the shared-noise structure. No new manuscript was prepared.

## Scope

This is exploratory synthetic-data engineering evidence. The 254 pooled recoveries are not independent noise experiments, and 95% per-cell intervals were not adjusted across all conditions. The rejected manuscript is not a validated publication. No real-IQ, measured oscillator trace, hardware demonstration, formal AWGN generator equivalence, or new adaptive method was established.
