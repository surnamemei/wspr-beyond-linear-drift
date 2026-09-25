# WSPR-2 robustness under nonstationary frequency instability

[![Zenodo DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22957460.svg)](https://doi.org/10.5281/zenodo.22957460)

This repository contains a generated-signal study of WSPR-2 decoding with the unmodified production WSJT-X 3.0.2 `wsprd`. It includes the waveform generator, seeded experiment runners, trial-level results, derived analyses, and an IEEE-style working manuscript.

## Research question

How does practical WSPR-2 decoding robustness change when the received frequency trajectory departs from the constant-plus-first-order-linear-drift model used by production `wsprd`?

## Main results

- The independent Python generator matched all 162 official WSJT-X channel symbols and produced the expected clean decode.
- The AWGN-only, interpolated SNR50 was **−31.519 dB** in the 2500-Hz WSPR reference bandwidth.
- Signed linear-drift D50 estimates were **+0.6981/−0.7105 Hz** at −30.0 dB, **+0.4831/−0.4886 Hz** at −30.5 dB, and **+0.2985/−0.3313 Hz** at −31.0 dB.
- For the controlled orthogonal quadratic residual, A50 was **0.5776 Hz** at −29.5 dB, **0.4408 Hz** at −30.0 dB, **0.3110 Hz** at −30.5 dB, and **0.2026 Hz** at −31.0 dB.
- A saved decoder sweep also covers synthetic Allan-targeted white, flicker, and random-walk FM processes. Residual-frequency RMS was the most robust tested scalar cross-family severity descriptor in the reported comparisons, but it is not universal.

These are measured outcomes for the stated generated waveforms, grids, and decoder; see the [claim audit](paper/claim_audit.md) and [saved core metrics](results/analysis/final_core_results/core_metrics.csv) for provenance and qualifications.

## Manuscript

- [Compiled IEEE-style working draft](paper/latex/main.pdf)
- [LaTeX source](paper/latex/main.tex)

**Manuscript status:** working draft prepared in IEEE style; not yet peer reviewed. No journal publication or article DOI is claimed. The DOI badge identifies the separate archived software/data release.

## Repository structure

| Path | Contents |
| --- | --- |
| `src/` | WSPR encoding, waveform generation, impairments, and analysis primitives |
| `experiments/` | Core AWGN and frequency-mismatch experiment entry points |
| `scripts/` | Decoder setup, validation, experiment runners, and analyses |
| `tests/` | Generator, impairment, and metric tests |
| `docs/` | Validation, provenance, and research checkpoints |
| `results/csv/` | Preserved trial-level and condition-summary outputs |
| `results/analysis/` | Derived statistics, comparisons, and preflight descriptors |
| `results/figures/` | Data-derived figures |
| `paper/` | Manuscript, tables, references, figure assets, and audits |

## Reproduction

Use x86_64 Linux or Ubuntu 24.04 under WSL. The working research environment used Python **3.12.3**; install [requirements.txt](requirements.txt) into a Python 3.12 environment and activate it before running these commands. The setup downloads the official WSJT-X package separately and checks its hash.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
bash scripts/setup_wsprd.sh
bash scripts/validate_official_reference.sh
bash scripts/validate_python_generator.sh
pytest
```

The validation scripts write their documented reference outputs; inspect existing outputs before rerunning them. Long Monte Carlo jobs are **not** part of the basic setup. Their active runners include `scripts/run_linear_drift_map.py`, `scripts/run_linear_drift_boundary.py`, `scripts/run_quadratic_residual_pilot.py`, `scripts/run_balanced_interaction_confirm.py`, and `scripts/run_physical_oscillator_decoder.py`; see each runner and the associated saved output before launching a job.

## Decoder provenance

All reported decodes used production WSJT-X **3.0.2** `wsprd`, not a modified decoder. The pinned upstream package, executable, matching source archive, hashes, and launch procedure are recorded in [environment.md](environment.md). WSJT-X itself retains its upstream license and is downloaded separately.

## Data and results

Raw scientific trial CSVs remain in `results/csv/`; derived analyses are stored separately under `results/analysis/`. Figures and manuscript tables are derived presentation artifacts. Do not modify raw results in place or treat historical files in `archive/development/` as current experiment code.

## Limitations

Results are specific to production `wsprd` and software-generated signals. There is no RF hardware validation, measured oscillator trace, or Doppler/propagation validation. Thermal and random-walk probes are synthetic, and the Allan-targeted processes are not traceable metrology standards. Boundaries are interpolated within tested grids; the [manuscript](paper/latex/main.pdf) records further limitations.

## Citation

The versioned research software/data release is archived on [Zenodo (DOI: 10.5281/zenodo.22957460)](https://doi.org/10.5281/zenodo.22957460). Use this DOI when citing the archive. [CITATION.cff](CITATION.cff) identifies the archived release; it does not assign a DOI or publication status to the IEEE manuscript.

## License

Repository source code is [MIT-licensed](LICENSE). Result CSVs, figures, and manuscript-derived data products are under [CC BY 4.0 International](LICENSE-DATA). These licenses do not relicense third-party WSJT-X content; obtain WSJT-X separately under its original upstream terms.
