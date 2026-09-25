# WSJT-X 3.0.2 `wsprd` frequency model

Source inspected: `lib/wsprd/wsprd.c` and `lib/wsprd/README` from the [official WSJT-X 3.0.2 source archive](https://github.com/WSJTX/wsjtx/releases/download/v3.0.2/wsjtx-3.0.2-src.tar.gz). Archive SHA-256 is recorded in [environment.md](../environment.md). The corresponding binary from the official release package is used unchanged.

## Search trajectory

The code explicitly describes its frequency drift model as linear, with a deviation of approximately ±`drift/2` over 162 symbols and zero deviation at the frame center (`wsprd.c`, lines 1136–1153). Its coarse search calculates a symbol-dependent frequency bin using

```text
f(k) = f_center + (drift / 2) × (k − 81) / 81,   k = 0, …, 161.
```

The same formula appears in `sync_and_demodulate` (`wsprd.c`, line 234), block demodulation, and signal subtraction. `drift` is approximately the total frequency change across the frame, in Hz. The endpoint is just short of `+drift/2` because the last index is 161.

In the first two decoding passes, `maxdrift = 4` and the coarse search tests integer `drift` values from −4 through +4 (`wsprd.c`, lines 1000–1005 and 1161–1169). It searches candidate frequency and timing as well. A later refinement compares the selected drift with `drift ± 0.5` Hz (`wsprd.c`, lines 1238–1256). The third pass sets `maxdrift = 0` for its block-demodulation path (`wsprd.c`, lines 1006–1010).

This supports the Phase-1 premise **for this specific production decoder**: it searches a center frequency and first-order linear drift. The sections inspected do not add a quadratic or stochastic frequency trajectory to that search. This does not characterize all WSPR decoders or establish a decode-probability boundary by itself.

The decoder reports estimated frequency and drift for successful decodes (`wsprd.c`, lines 1455–1471), enabling later control checks. Candidate search is constrained by the audio passband and default ±110 Hz center range documented in `lib/wsprd/README`.
