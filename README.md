# WSPR-2 frequency instability and fixed-grid decoder study

This repository studies how software-generated WSPR-2 signals behave under frequency drift and other time-varying frequency impairments. The original investigation used the production WSJT-X 3.0.2 `wsprd` decoder to measure AWGN performance, linear and nonlinear drift responses, and synthetic oscillator models. The submitted IEEE Access manuscript was rejected; it is a historical working document, not a published or journal-validated result.

A subsequent engineering investigation examined why decoder-aligned linear drift can still cause substantial losses. In the production decoder, the third pass fixes the drift search to zero before trying several block demodulation settings. The extension tests fixed drift hypotheses for an already accepted third-pass candidate. **B2** orders the hypotheses by the received-data synchronization score; **B3** first tries zero drift and then follows a fixed fallback order. Both are receiver-side engineering modifications, not new adaptive drift estimators.

## Engineering findings

- Official `wsprsim` and the Python generator showed no material decode-rate discrepancy in a 900-versus-900 AWGN screening. Formal equivalence was not established; the historical interpolated −31.519 dB SNR50 was not independently confirmed to that precision.
- The Table 5 model labeled RMS in the rejected manuscript actually used SNR, peak residual frequency **and** RMS. Its numerical scores reproduce for that fitted model, not for a standalone SNR-plus-RMS model. A true SNR-plus-RMS model was subsequently evaluated; see the [descriptor audit](docs/ENGINEERING_EXTENSION.md#descriptor-model-reconciliation).
- A restricted truth-parameter diagnostic identified a recoverable final-pass gap. It used transmitter truth and is not a practical receiver. On its selected 200-input subset, B2 and B3 recovered the same 73 baseline failures recovered by the restricted D-only oracle, with no observed loss of baseline correct decodes.
- On an independent synthetic screening of 1,080 inputs and 12,960 invocations, B2 and B3 had identical exact-success outcomes on 800 signal inputs and each recovered 254 A0 failures with no observed A0-success loss. Drift conditions share noise realizations, so those 254 recoveries are not 254 independent noise experiments. Search order, work budget and CPU-time tails materially affected performance.
- In 200 pure-noise frames, each tested arm and budget produced zero detections. This small sample does not establish a negligible false-alarm rate. The results are synthetic; real-IQ and hardware validation were not performed.

The engineering implementation is **kept**. A novel adaptive decoder is **on hold**, and a publishable new algorithm is **not supported by these results alone**. Read the [engineering extension](docs/ENGINEERING_EXTENSION.md), [research status](docs/RESEARCH_STATUS.md), and [complete result summaries](results/engineering_extension/MANIFEST.md) for conditions, uncertainties and limitations.

## Build and reproduce

The fixed-grid source patches and budget instrumentation are in [decoder_extension/](decoder_extension/README.md). A hash-pinned build script applies them to the separately obtained official WSJT-X 3.0.2 source archive in a disposable build directory. A deterministic clean example and Parser V2 are supplied. The [reproducibility guide](docs/REPRODUCIBILITY.md) explains the optional, much longer frozen screening workflow and the limits of public raw-data availability.

Existing research code remains under `src/`, `experiments/`, `scripts/`, `tests/`, and `results/`. Historical files in `paper/` retain the rejected manuscript and earlier working drafts. Do not interpret their labels or claims without the corrections above.

## Archival and licensing

The [existing Zenodo archive](https://doi.org/10.5281/zenodo.22961777) refers to an earlier software/data release; it does not contain this later engineering extension, and no new DOI or release is claimed. Raw Gate 0A–2C C2 archives and decoder logs are not uploaded here; [result provenance](docs/RESULT_PROVENANCE.md) distinguishes local archival paths from public artifacts.

Project-authored code remains under the repository [MIT license](LICENSE), and result data under [CC BY 4.0](LICENSE-DATA). WSJT-X-derived decoder patches and their diagnostic modifications are GPL-covered; see [license details](decoder_extension/LICENSE_INFO.md). This work is not an official WSJT-X distribution or endorsement.
