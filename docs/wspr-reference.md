# Official WSPR-2 clean reference (WSJT-X 3.0.2)

The generator and decoder come from the same [official WSJT-X 3.0.2 release](https://github.com/WSJTX/wsjtx/releases/tag/v3.0.2). The exact source archive SHA-256 is `574aee4a36c58c4dfeda4f2d659e74542212d4d9c25bfc040feba47c9f2b15d7`. The production `wsprd` binary is the unmodified executable from its Linux package (see [environment.md](../environment.md)).

## Official generator and build

- Source: `lib/wsprd/wsprsim.c`, `wsprsim_utils.c`, `wsprsim_utils.h`; the shared `lib/wsprd/Makefile` has a `wsprsim` target using `wsprsim.o wsprsim_utils.o wsprd_utils.o tab.o fano.o nhash.o`.
- The release Linux package does **not** include a `wsprsim` executable. We built it from the exact release source using `make -B -C .cache/wsjtx-3.0.2/lib/wsprd wsprsim LIBS=-lm`. The `LIBS` override removes FFTW and Fortran linker flags unused by `wsprsim`; source and signal-generation logic are unchanged. GCC was Ubuntu `13.3.0-6ubuntu2~24.04.1`.
- Built executable: `.cache/wsjtx-3.0.2/lib/wsprd/wsprsim`; SHA-256 on this host: `d850595e4da06792df483eb6f8b8645455e7294d5081ba4a015ee1010752e9f5`.
- `wsprsim -h` prints usage and `invalid option -- 'h'` but exits **0**. Its documented switches are `-c` (channel symbols), `-d` (packed data), `-f` (baseband frequency offset), `-o` (write C2), and `-s` (SNR parameter). With `-s >= 40`, the source bypasses noise addition and sets signal amplitude to 1. It returns **1** after successfully generating a file. The validation script accepts these upstream exit conventions only after checking the output file and full-message decode.

`wsprsim` emits a `.c2` complex-sample file, not audio WAV. Since the production `wsprd` directly reads C2, this reference uses that path without any resampling, normalization, or format conversion. In `wsprsim.c` (`writec2file`) the C2 file contains a 14-byte name, a 32-bit WSPR mode (`2`), a double dial frequency (`10.1387` MHz), and 45,000 pairs of 32-bit floating-point I/Q values. Its file convention stores `-Q`; `wsprd.c` (`readc2file`) reverses that sign. The resulting file is 360,026 bytes. For WAV work later, `wsprd.c` (`readwavfile`) expects 12,000 Hz mono 16-bit PCM with a conventional 44-byte header, 114 seconds of samples, and audio near 1500 Hz. These are distinct decoder input paths.

## Parameters verified in source

| Property | Value | Source location |
| --- | --- | --- |
| Channel symbols | 162 | `wsprsim.c` `add_signal_vector`; `wsprsim_utils.c` `get_wspr_channel_symbols` |
| Tone spacing and symbol rate | `375/256 = 1.46484375` Hz and symbols/s | `wsprsim.c` `add_signal_vector`: `df=375.0/256.0`, 256 samples per symbol at `dt=1/375.0` s |
| Symbol duration and frame duration | `256/375 = 0.682666…` s; `162×256/375 = 110.592` s | Same loops and constants in `add_signal_vector` |
| Modulation | Continuous-phase four-tone FSK; instantaneous baseband frequency `f0 + (symbol−1.5)×df` | `wsprsim.c` `add_signal_vector`, phase accumulator `phi += dphi` without reset between symbols |
| Simulator sample layout | 375 complex samples/s; 45,000 samples = 120 s | `wsprsim.c` `dt`, array sizes, and `writec2file` |
| Transmit placement | Symbol 0 begins at `t0=1.0` s in the C2 file; remaining file is zero outside the signal | `wsprsim.c` `main`, `add_signal_vector` (`idelay=t0/dt`) |
| Message payload | 50 packed bits plus 31 zero tail bits | `wsprsim_utils.c` `get_wspr_channel_symbols`, 11-byte `data` assembly; decoder `wsprd.c` `nbits=81` |
| Channel code | Rate 1/2, constraint length 32; polynomials `0xf2d05351`, `0xe4613c47` | `fano.c` `LL` selection and `encode`; 81 input bits produce 162 channel bits |
| Interleaving | Bit-reversal permutation over 162 coded bits | `wsprsim_utils.c` `interleave` |
| Sync sequence | Fixed 162-entry `pr3` sequence, combined as `symbol = 2×interleaved_bit + pr3[i]` | `wsprsim_utils.c` `get_wspr_channel_symbols`; matching `pr3` in `wsprd.c` |
| Decoder timing convention | Nominal start described as 2 s into WAV input; coarse time search around it, with partial decoding at edges | `wsprd.c`, coarse search comment at lines 1136–1150; C2 reference starts at 1 s and decoded `DT` prints `-0.0` s |

The 162-symbol vector and packed bytes for the fixed message are captured directly from official `wsprsim -cd` output in [reference_symbols.json](../tests/data/reference_symbols.json). This vector is the future oracle for a Python encoder; it was not independently constructed.

## Clean decode gate

Fixed ordinary Type-1 message: **`K1ABC FN42 33`**. The official encoder's packed bytes were `F7 0C 23 8B 0D 18 40 00 00 00 00`; `wsprd` decoded the canonical message identically.

From the repository root in Ubuntu WSL:

```bash
bash scripts/validate_official_reference.sh
```

The script builds/exposes both official tools, regenerates results/reference/260924_0000.c2 without noise or impairments, and runs the decoder launcher with its -a directory set to results/reference. It fails nonzero unless the decoder returns a full exact-message match. The exact commands are saved in results/reference/command_metadata.json alongside stdout, stderr, exit codes, hashes, C2 header details, and decoded fields.

Observed decoder stdout:

```text
0000  39 -0.0  10.140200  0  K1ABC FN42 33 
<DecodeFinished>
```

Decoder exit status: `0`; stderr: empty. Reported SNR: `39` dB; frequency: `10.140200` MHz; drift: `0` Hz. The simulator's `-s 50` is a clean-signal sentinel in this code, so the reported `39` is **not** an AWGN performance measurement. C2 SHA-256 on this host: `2f429d1f7e43e2eba047d2fd4fe100998ba155e8948cdf756a44721ad9e40af2`.

**CLEAN REFERENCE DECODE = PASS.** This establishes an official signal-generation to production-decoder reference chain. It does not validate a custom WAV generator or AWGN calibration.

## Observed wsprsim usage output

Running the built utility with -h printed an invalid-option diagnostic on stderr, then the usage text on stdout; the process exit status was 0:

    ./wsprsim: invalid option -- 'h'
    Usage: wsprsim [options] message
           message format:   "K1ABC FN42 33"
                             "PJ4/K1ABC 33"
                             "<PJ4/K1ABC> FK52UD 33"
    Options:
           -c   (print channel symbols)
           -d   (print packed data with zero tail - 11 bytes)
           -f x (-100 Hz < f < 100 Hz)
           -o filename (write a c2 file with this name)
           -s x (x is snr of signal that is written to .c2 file)
