# Verified references and claim mapping

The corresponding BibTeX entries are in [references.bib](references.bib). **VERIFIED** means metadata and claim support were checked against an official page, publisher record, or author-hosted original. The official user guide is a living, undated page; no publication year was invented. **REMOVE** denotes an earlier citation topic not used in the manuscript.

## WSPR / WSJT-X

| Status / key | Verified source and metadata | Exact manuscript claim supported |
| --- | --- | --- |
| VERIFIED `wsjtx302` | WSJT Development Group, *WSJT-X 3.0.2*, official [release and source archive](https://github.com/WSJTX/wsjtx/releases/tag/v3.0.2), June 2026. The official [downloads page](https://wsjtx.github.io/wsjtx/downloads.html) lists the June 2026 GA release. | Production decoder and matching official source/reference implementation; Sections I, II-A/B, III-A. Installed hashes are separately recorded in the repository. |
| VERIFIED `wsjtxguide` | WSJT Development Group, [*WSJT-X User Guide*](https://wsjtx.github.io/wsjtx/guide-full.html), official living guide, undated. | WSPR protocol and 2500-Hz SNR context, plus FST4/FST4W background; I, II-C. Not the source of this repository's exact AWGN arithmetic. |
| VERIFIED `taylor2010` | Joe Taylor and Bruce Walker, [“WSPRing Around the World”](https://wsjt.sourceforge.io/WSPR_QST_Nov_2010.pdf), *QST*, November 2010, author-hosted article. | Original WSPR beacon purpose, narrow four-tone signal, symbol/protocol context, and qualitative frequency-stability concern; I. Not evidence for 3.0.2 decoder boundaries. |

## WSPR spectral width / oscillator stability

| Status / key | Verified source and metadata | Exact manuscript claim supported |
| --- | --- | --- |
| VERIFIED `johnson2026` | R. Barry Johnson and Gene Marcus, [“How Narrow is Narrow Enough? An Investigation of WSPR-2 Spectral Width”](https://www.researchgate.net/publication/400563668_How_Narrow_is_Narrow_Enough_An_Investigation_of_WSPR-2_Spectral_Width), *The LongPath*, vol. 50, no. 1, pp. 10–12, January 2026. Author-uploaded copy; club technical publication, not identified as peer reviewed. | Prior transmitter spectral-width measurements and reference-stability/frequency-generation discussion; I. Not evidence for decoder probability. |
| VERIFIED `taylor2010` | Original WSPR article above. | General narrow-signal and frequency-stability context. |
| REMOVE | An exact external stability requirement for this decoder or specific TCXO/OCXO/GPSDO. | No such requirement is inferred; VII retains the limitation. |

## WSPR/FST4 Doppler and spectral spread

| Status / key | Verified source and metadata | Exact manuscript claim supported |
| --- | --- | --- |
| VERIFIED `griffiths2023` | Gwyn Griffiths, [“Identifying 14 MHz Propagation Modes Using FST4W SNR and Spectral Spread”](https://hamsci.org/publications/2023/identifying-14-mhz-propagation-modes-using-fst4w-snr-and-spectral-spread), *HamSCI Workshop 2023*, Scranton, PA, March 2023; organizer lists no DOI. | Prior FST4W use of spectral spread and SNR to study propagation modes; I. Not a WSPR-2 decoder robustness measurement. |
| VERIFIED `wsjtxguide` | Official guide above, FST4/FST4W sections. | Distinguishes frequency instability and Doppler spread as operational concerns; I. No FST4W tolerance is transferred to WSPR-2. |
| REMOVE | A quantitative WSPR-2 Doppler-tolerance claim. | No Doppler impairment was run. |

## Allan deviation / power-law frequency-noise models

| Status / key | Verified source and metadata | Exact manuscript claim supported |
| --- | --- | --- |
| VERIFIED `riley2008` | W. J. Riley, [*Handbook of Frequency Stability Analysis*](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication1065.pdf), NIST Special Publication 1065, July 2008, DOI [10.6028/NIST.SP.1065](https://doi.org/10.6028/NIST.SP.1065). The PDF title page gives one author; a duplicate-author catalog entry was not copied. | Allan-deviation definitions and qualitative white/flicker/random-walk FM slopes; I, V-C. Not traceable calibration of the synthetic generator. |
| REMOVE | Traceable calibration to a measured oscillator. | The saved processes have ensemble Allan targets and finite cadence only. |

## Propagation sensing / HamSCI

| Status / key | Verified source and metadata | Exact manuscript claim supported |
| --- | --- | --- |
| VERIFIED `frissell2019` | N. A. Frissell *et al.*, [“High-Frequency Communications Response to Solar Activity in September 2017 as Observed by Amateur Radio Networks”](https://doi.org/10.1029/2018SW002008), *Space Weather*, vol. 17, no. 1, pp. 118–132, 2019, DOI 10.1029/2018SW002008; publisher lists nine authors. | WSPRNet and other amateur-radio reports used to study HF propagation response to solar activity; I. No such field data are analyzed here. |
| VERIFIED `taylor2010` | Original WSPR article above. | WSPRnet propagation-reporting purpose; I. |
| REMOVE | This manuscript validates propagation-sensing accuracy in field data. | The results use generated C2 signals and AWGN. |

Numerical results remain tied to saved CSV/report provenance in [claim_audit.md](claim_audit.md), not to external references.
