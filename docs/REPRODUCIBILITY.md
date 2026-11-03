# Reproducibility and interpretation

## Small smoke test

Follow [the decoder build and smoke-test instructions](../decoder_extension/README.md). They build from the hash-pinned upstream source and generate one deterministic clean input locally. This is a functionality test, not a new performance study. The clean-source B2/B3 patches were verified against saved study outputs on 24 Gate 2B and eight Gate 2C off-grid inputs: 96 decoder runs with stdout, stderr, `ALL_WSPR.TXT` and `wspr_spots.txt` byte-identical to the corresponding saved outputs. The diagnostic budget patches were tested on eight saved inputs across three arms and three budget modes: 72 runs matched outputs and budget-event counters. These finite checks do not prove bit-for-bit equivalence for every possible input or environment.

## Frozen Gate 2C screening

The public, path-sanitized [screening protocol](../decoder_extension/screening_protocol.json) records the messages, SNRs, drift conditions, seed rules, noise convention, dual-signal settings and work budgets. Inputs use 45,000 complex samples at 375 Hz, stored as little-endian float32 I/−Q C2 data, with a 2,500 Hz reference bandwidth. One seed per message/SNR/trial was reused for five drift conditions. The 200 noise-only and 80 two-signal frames use separate seed ranges. See the protocol before attempting reproduction.

The 1,080 C2 inputs and 12,960 raw decoder outputs were not uploaded. The [local provenance manifest](../results/engineering_extension/MANIFEST.md) identifies their historical locations but these paths are not public download links. The input generator can recreate the fixed design in a **new** directory (about 389 MB):

```bash
python3 decoder_extension/generate_screening_inputs.py /tmp/wspr-gate2c-inputs
```

A signal, a noise-only frame and a dual-signal frame were regenerated in memory during the engineering update and each matched its saved C2 file byte-for-byte. The original module hashes were captured after generation, not before; the historical record does not exclude all intervening changes. Cross-platform floating-point and runtime differences may also change byte hashes.

For a fresh full rerun, build all three budget variants and B2/B3 as above, obtain an executable **official packaged** `wsprd` matching SHA-256 `9e3c2fc14f63c4b4c4e9fcc33b386cd22daf8fe76ce724c5e37f07875e9a3dd9`, then check without running a decoder:

```bash
for v in a0-budget b2-budget b3-budget; do
  bash decoder_extension/build.sh "$archive" "$v" /tmp/wspr-bin
done
python3 decoder_extension/run_screening.py \
  --manifest /tmp/wspr-gate2c-inputs/manifest.jsonl \
  --production /path/to/executable-official-wsprd \
  --decoder-dir /tmp/wspr-bin --output /tmp/wspr-gate2c-run --check-only
```

Remove `--check-only` only when you intend to run the full 12,960-invocation job. It uses four workers, a 120-second per-call timeout, separate output directories, and the frozen natural, unlimited-instrumented, 40-million and 100-million Fano-iteration configurations. Non-timeout errors and natural-versus-unlimited output differences stop the job. Failed and timed-out output remains in its working directory. Then verify and analyze:

```bash
python3 decoder_extension/verify_screening.py --manifest /tmp/wspr-gate2c-inputs/manifest.jsonl --output /tmp/wspr-gate2c-run
python3 decoder_extension/analyze_screening.py --manifest /tmp/wspr-gate2c-inputs/manifest.jsonl --output /tmp/wspr-gate2c-run
```

The verifier re-parses outputs with Parser V2 and checks per-call work limits. The analysis reports each message/SNR/drift cell separately, paired gains/losses, Wilson intervals, conservative paired intervals, and CPU/wall distributions. It treats the shared seeds across drift as paired, not independent. Intervals are exploratory and not corrected across cells. Recomputing this analysis from the saved historical records reproduced all four published Gate 2C CSVs byte-for-byte. The portable full job itself was not re-executed during this maintenance update.

## Historical corrections and limits

Table 5's RMS label is not the fitted SNR + peak + RMS design; see [the descriptor audit](ENGINEERING_EXTENSION.md#descriptor-model-reconciliation). The 0A screening did not prove formal equivalence. The 1B full oracle inserted truth-based candidate parameters; the 1C D-only intervention instead changed drift for the first candidate already accepted on the third pass. Neither is a deployable receiver. Gate 2C's earlier generous-budget stop at 1,000 demodulations was repaired by disabling all work caps for resumed equivalence checks; low/medium budgets were not changed. Historical stop records remain local, not uploaded.
