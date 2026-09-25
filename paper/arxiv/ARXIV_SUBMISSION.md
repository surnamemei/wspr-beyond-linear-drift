# arXiv v1 submission metadata

Title: Beyond First-Order Drift: Practical WSPR-2 Decoding Robustness under Nonstationary Frequency Instability

Author: Jinghang Mei

Affiliation: School of Electrical and Computer Engineering, The University of Sydney, Sydney, NSW, Australia

Primary category: eess.SP (Signal Processing)

Possible cross-list: cs.IT (Information Theory), subject to author and arXiv moderation review. Do not select eess.SY merely because oscillator dynamics appear in the manuscript.

Abstract (matches `main.tex`):

> Frequency error in a weak-signal transmission has components that a receiver may search explicitly and components outside its trajectory model. We measured this distinction for a generated WSPR-2 signal decoded by the unmodified production WSJT-X 3.0.2 \texttt{wsprd}. The independent waveform implementation matched all 162 reference channel symbols; complex additive white Gaussian noise (AWGN) was calibrated to the 2500-Hz WSPR SNR convention. The AWGN-only 50\% decode point was $-31.519$ dB by interpolation. Exact decoder-aligned linear drift, an orthogonal quadratic residual, thermal-settling shape probes, and stochastic frequency-modulation (FM) families were evaluated on saved, seeded trial grids. Signed linear-drift 50\% boundaries contracted from $+0.6981/-0.7105$ Hz at $-30.0$ dB to $+0.2985/-0.3313$ Hz at $-31.0$ dB. The corresponding orthogonal-quadratic 50\% amplitude decreased from $0.4408$ to $0.2026$ Hz. A balanced factorial fit measured a linear-drift $\times$ residual interaction coefficient of $10.1555$ log-odds/Hz$^2$ on its fitted scale. Among tested scalar trajectory descriptors, maximum phase excursion improved smooth-shape held-out scores, whereas residual-frequency RMS scored better on the separate held-out random-walk set. A further 5,400-trial sweep of synthetic Allan-targeted FM processes related fractional-frequency stability, carrier scaling, projected residuals, and decode outcomes. The results characterize this decoder and these generated waveforms and grids; no transmitter hardware, measured oscillator, or propagation impairment was tested.

Comments: 9 pages; 7 figure environments containing 10 figure assets; 5 tables; 7 references. Standalone PDF compiled from this directory.

Journal reference: leave blank (no publication claim).

DOI: leave blank (no DOI assigned).

Code and data: https://github.com/surnamemei/wspr-beyond-linear-drift

License: consider arXiv's CC BY 4.0 option after checking any intended venue's policy. This note is a recommendation, not a selected license.

Before submission:

- Confirmed corresponding email: jmei0175@uni.sydney.edu.au; the existing arXiv PDF intentionally omits email.
- Confirmed ORCID: https://orcid.org/0009-0007-2901-3285; the existing arXiv PDF does not display it.
- TODO: Review arXiv category and cross-list selection in the submission form.
- TODO: Review the irreversible license selection and intended venue policy.
- TODO: Check the final uploaded source preview against the locally compiled PDF.

Source package: `main.tex`, `references.bib`, `main.bbl`, and only the ten referenced figure assets under `figures/`. The local `main.pdf` is a proof copy, not required for source compilation.
