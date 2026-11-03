# Result provenance

The [engineering manifest](../results/engineering_extension/MANIFEST.md) identifies each public CSV, its local source table and its SHA-256. The raw Gate 0A–2C input archives and per-call logs are not included in this repository. Local archival paths are provided for maintainers who retain the original checkout; they are not public URLs or promises of access.

Gate 0A compares official and Python-generated inputs using the same production decoder. The official simulator's rounded bandwidth adjustment was accounted for. Its 900 official seeds were distinct PID-derived seeds; distinctness is not a proof of independence. Per-cell rates are screening results and formal equivalence was not tested.

Gate 1B and 1C distinguish the full truth-based candidate intervention from the last-pass first-accepted-candidate factorial intervention. Gate 2B fixed-grid and oracle data use a selected 200-input single-message subset. Gate 2C summaries derive from 1,080 held-out synthetic inputs and 12,960 invocation records, including 12,559 validated reused records and 401 calls completed after a controlled resumption. The earlier STOP records and the procedural deviation remain part of local provenance, not omitted evidence of a clean uninterrupted run.

Parser V2 corrected historical wrong-message counts; the published engineering tables use corrected records. The 200 noise-only frames cannot establish a near-zero false-alarm rate. Gate 2C seeds are paired across drift conditions, and all results are exploratory. The earlier Zenodo archive is not an archive of this extension.

## Signal-generator source identity

The following SHA-256 values were captured after the original Gate 2C input generation; they match the public source files, but do not prove the files were unchanged before capture.

| Public source | SHA-256 |
|---|---|
| `src/wspr/encoder.py` | `8b1ae823ae33a2c5f2d1be271baa0e23f874b2aa56c13c529d88c6c97174f737` |
| `src/wspr/waveform.py` | `0d299d269b0d159fc38876f1315033fa7da3801fade8761adbddf80ece4b20a5` |
| `src/impairments/frequency.py` | `2d2356745f82dc3f0b33c2824f6640d30b99116e844347ab8f00aa888b2aa0b5` |
| `src/impairments/noise.py` | `b8d09133ca9b08592b82d541191cfa562e5d3edaf005710a7c0f3a77b6d6369e` |
