# Phase 1B: independent Python generator validation

Phase 1B validates two independent conditions for the fixed Type-1 message `K1ABC FN42 33`:

1. the Python encoder's 162 channel symbols exactly equal the vector captured from official WSJT-X 3.0.2 `wsprsim`; and
2. the Python waveform is decoded to the exact message by the unmodified production WSJT-X 3.0.2 `wsprd`.

Both conditions pass. The Python implementation is not claimed as a research contribution. It is experimental infrastructure for later controlled impairment studies.

## Authoritative sources

The implementation was written against the matching official WSJT-X 3.0.2 release source:

- `lib/wsprd/wsprsim_utils.c`: Type-1 source packing, zero-tail packing, interleaver, 162-bit sync vector, and final tone mapping;
- `lib/wsprd/fano.c`: MSB-first rate-1/2, K=32 convolutional encoder and polynomials `0xf2d05351` and `0xe4613c47`;
- `lib/wsprd/wsprsim.c`: continuous-phase modulation, 375 Hz complex sampling, 256 samples per symbol, tone mapping, timing, and C2 writer;
- `lib/wsprd/wsprd.c`: C2 reader and production decoder input convention; and
- `tests/data/reference_symbols.json`: immutable 162-tone and packed-byte oracle captured from official `wsprsim -cd` in Phase 0B.

The source archive identity and official-tool hashes remain documented in [wspr-reference.md](wspr-reference.md).

## Encoder stages and bit ordering

`src/wspr/encoder.py` accepts an ordinary `CALL GRID POWER` Type-1 message and exposes every material stage through `EncodingStages`:

1. Callsign packing produces a 28-bit integer. Callsigns whose digit is in the second character are left-padded to the six-character packing field. Characters are accumulated using radices 36, 10, 27, 27, and 27 exactly as in the official source.
2. The four-character locator and power produce a 22-bit integer using the official locator transform, followed by the 7-bit power field offset by 64.
3. The 28 and 22-bit fields are concatenated MSB first to form 50 information bits, followed by 31 zero tail bits. Seven additional zero padding bits only complete the official 11-byte storage buffer; they are not convolutionally encoded for the 162-symbol frame.
4. Each of the 81 bits enters the K=32 rate-1/2 encoder MSB first. For each input bit, the parity for polynomial `0xf2d05351` is emitted before the parity for `0xe4613c47`, producing 162 coded bits.
5. The coded bits are placed using the official eight-bit reversal permutation.
6. Each transmitted tone is `2 × interleaved_bit + sync_bit`, yielding a value in `{0,1,2,3}`.

For `K1ABC FN42 33`, the verified intermediate values are:

- packed callsign: `259047992` (`0x0f70c238`);
- packed locator/power: `2896993` (`0x2c3461`);
- 50 information bits: `11110111000011000010001110001011000011010001100001`;
- official 11-byte representation: `F7 0C 23 8B 0D 18 40 00 00 00 00`;
- terminated input length: 81 bits;
- convolutional sequence length: 162 bits;
- interleaved sequence length: 162 bits; and
- official channel-symbol equality: **162/162**.

The packed bytes and final tones are assertions against the official captured output. Tests report exact mismatch indices if a tone differs.

## Waveform and decoder format

`src/wspr/waveform.py` represents the signal internally as Python complex samples with positive Q. It uses:

- sample rate: 375 complex samples/s;
- samples per symbol: 256;
- symbol duration: `256/375 = 0.682666…` s;
- symbol rate and tone spacing: `375/256 = 1.46484375` Hz;
- center-relative tone frequencies: `[-2.197265625, -0.732421875, 0.732421875, 2.197265625]` Hz;
- WSPR frame samples: 41,472;
- WSPR frame duration: 110.592 s;
- container samples: 45,000 (120 s);
- frame placement: sample 375, exactly 1 s after the container begins; and
- modulation: `phase += 2πf/Fs` for every sample, retaining phase across symbol boundaries.

The generator separates tone construction from the phase-accumulation loop. A future phase can add a frequency-error trajectory before accumulation without changing encoding or serialization. No CFO, drift, noise, or other impairment exists in this phase.

C2 was chosen because the matching official simulator and decoder use it directly, avoiding resampling and audio quantization. `write_c2` follows the inspected format: a 14-byte filename, little-endian int32 mode `2`, little-endian float64 dial frequency `10.1387` MHz, then 45,000 little-endian float32 `I, -Q` pairs. The Python file is `results/python-reference/260924_0001.c2`; the internal positive-Q convention is inverted only during serialization.

The official and Python signals have the same 45,000 sample count, active interval `[375, 41847)`, unit active amplitude, tone sequence, and phase convention. After both are represented as C2 float32 samples, their maximum complex-sample difference is approximately `3.49e-08`, attributable to floating-point evaluation. Byte identity is not required.

## Tests and production decode

The standard-library test suite checks the official packed bytes and all 162 tones, stage lengths, input validation, sample layout, frame duration, tone spacing measured from generated sample phase, phase continuity at every one of the 161 symbol boundaries, active amplitude, zero padding, determinism, and C2 header/size.

The authoritative validation command is:

```bash
bash scripts/validate_python_generator.sh
```

It runs all tests, regenerates the Python C2, invokes the Phase-0 production decoder, and requires one exact decoded message. A checkout-independent equivalent of the recorded decoder invocation, when run from the repository root, is:

```bash
repo=$(pwd)
(
  cd "$repo/results/python-reference"
  bash "$repo/scripts/wsprd.sh" -H \
    -a "$repo/results/python-reference" \
    260924_0001.c2
)
```

Actual stdout:

```text
0001  39 -0.0  10.140200  0  K1ABC FN42 33 
<DecodeFinished>
```

Decoder stderr was empty and exit status was 0. The reported 39 dB is from a clean unit-amplitude signal and is not an AWGN result. Raw outputs and metadata are under `results/python-reference/`.

**PHASE 1B = PASS.** No impairment experiment has been started.
