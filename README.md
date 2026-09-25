# WSPR-2 robustness to nonstationary frequency error

This independent research project asks how often a practical WSPR-2 decoder correctly recovers a known message when the received instantaneous frequency departs from a constant-frequency plus linear-drift trajectory. The Phase-1 outcome is the fraction of correctly decoded frames in repeated trials, not a synchronization proxy.

The project uses software-generated signals and the unmodified production `wsprd` executable from official WSJT-X. No RF hardware is needed. **Phase 0B has passed:** matching official wsprsim generated a clean C2 signal that production wsprd decoded as K1ABC FN42 33. No custom waveform or Monte Carlo result exists yet.

## Phase-1 gates

1. Verify WSPR-2 parameters and encoding against authoritative sources.
2. Generate a Type-1 message and confirm that a clean WAV decodes correctly with the actual `wsprd`. This is a hard gate.
3. Calibrate AWGN to WSPR's 2500 Hz reference bandwidth and establish a plausible decode-probability curve versus SNR.
4. Validate constant CFO and first-order linear drift as receiver controls.
5. Test a controlled quadratic trajectory using residual frequency excursion after removal of its best constant-plus-linear fit. Measure actual decode probability versus SNR and residual excursion, with binomial confidence intervals.
6. Assess GO or NO-GO/REVISE from reproducibility, SNR dependence, controls, and checks against implementation artifacts. Quadratic drift is a model-mismatch probe, not a physical oscillator model.

Every eventual trial will record its seed, message, impairment and SNR parameters, decoder command/version, decoded output, success, timing, and software provenance in raw CSV. Figures will be generated from those files.

## Decoder setup

In Ubuntu 24.04 WSL or compatible x86_64 Linux, from the repository root:

```bash
bash scripts/setup_wsprd.sh
bash scripts/wsprd.sh -h
```

`-h` prints usage and exits with status 1 because upstream `wsprd` does not recognize it. The setup script extracts the official WSJT-X 3.0.2 Linux package into Git-ignored `.cache/`, without patching the decoder. See [environment.md](environment.md) for provenance and [docs/decoder-source.md](docs/decoder-source.md) for its drift model.

The clean official reference and 162-symbol oracle are documented in [docs/wspr-reference.md](docs/wspr-reference.md). Recheck them with bash scripts/validate_official_reference.sh in Ubuntu WSL. The next work item is source-checked Python encoder and waveform construction, using this reference as the oracle.
