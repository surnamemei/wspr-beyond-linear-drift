# Fixed-grid `wsprd` extension

These are GPL-covered source patches for the official WSJT-X 3.0.2 `wsprd` source. They implement the fixed-grid receiver comparisons described in [the engineering report](../docs/ENGINEERING_EXTENSION.md). They are not an official WSJT-X release or endorsement.

| Variant | Purpose |
|---|---|
| `original` | Unmodified source rebuild for local comparison |
| `b2` | Sync-score-ordered fixed-grid retries |
| `b3` | Zero-drift-first fixed-grid fallback |
| `a0-budget`, `b2-budget`, `b3-budget` | Exact diagnostic instrumentation for cumulative work-budget experiments |

B2/B3 are enabled with `WSPR_2B_ENABLE=1`; absent that variable, their retry change is disabled. The natural patches omit diagnostic logging. Budget variants retain the study's trace instrumentation and require `WSPR_DIAG_FILE` to name a writable new file. All variants retain the original per-call Fano limit and message validation. The `-H -a <isolated-directory>` settings used in the study are important; `-a` must identify a distinct writable directory per invocation.

## Build and clean smoke test

On x86-64 Linux/Ubuntu 24.04, install GCC, GNU Fortran, `make`, `patch`, `tar`, `sha256sum`, and FFTW single-precision development/runtime libraries (on Ubuntu: `build-essential gfortran libfftw3-dev`). Python 3.12 is used for the included example and screening tools; see [requirements.txt](../requirements.txt).

Obtain the official [WSJT-X 3.0.2 source archive](https://github.com/WSJTX/wsjtx/releases/download/v3.0.2/wsjtx-3.0.2-src.tar.gz). `build.sh` requires SHA-256 `574aee4a36c58c4dfeda4f2d659e74542212d4d9c25bfc040feba47c9f2b15d7`, extracts into a disposable directory, applies the selected patch, builds `wsprd`, and refuses to overwrite an existing output binary. Run from the repository root:

```bash
archive=/path/to/wsjtx-3.0.2-src.tar.gz
bash decoder_extension/build.sh "$archive" original /tmp/wspr-bin
bash decoder_extension/build.sh "$archive" b2 /tmp/wspr-bin
bash decoder_extension/build.sh "$archive" b3 /tmp/wspr-bin
python3 decoder_extension/make_clean_example.py /tmp/wspr-example/input/261103_0000.c2
mkdir -p /tmp/wspr-example/a0 /tmp/wspr-example/b2
(cd /tmp/wspr-example/a0 && /tmp/wspr-bin/wsprd-original -H -a . ../input/261103_0000.c2 > stdout.txt 2> stderr.txt)
(cd /tmp/wspr-example/b2 && WSPR_2B_ENABLE=1 /tmp/wspr-bin/wsprd-b2 -H -a . ../input/261103_0000.c2 > stdout.txt 2> stderr.txt)
python3 decoder_extension/parse_output.py /tmp/wspr-example/a0/stdout.txt --stderr /tmp/wspr-example/a0/stderr.txt --expected 'K1ABC FN42 33'
python3 decoder_extension/parse_output.py /tmp/wspr-example/b2/stdout.txt --stderr /tmp/wspr-example/b2/stderr.txt --expected 'K1ABC FN42 33'
```

The clean example tests basic execution and is generally decoded before the final-pass retry; it is not an efficacy test. The source rebuild is not byte-identical to the official packaged binary. The original archived package payload in the study had mode 0644, so do not assume it is executable or silently change it. Use an appropriately executable byte-identical copy of the official production binary when reproducing the A0 study.

`parse_output.py` uses Parser V2, checks the exact decoded message, completion marker, exit status and malformed output, and records unexpected messages. For a command that did not exit successfully, pass its actual `--exit-status`. Run `python3 decoder_extension/test_parser_v2.py` for its 13 unit checks.

## Budget diagnostics

Build `a0-budget`, `b2-budget` and `b3-budget` with the same script. For a 40-million-iteration test set `WSPR_2C_ITER_LIMIT=40000000`, `WSPR_2C_COARSE_LIMIT=100000`, `WSPR_2C_SYNC_LIMIT=10000` and `WSPR_2C_DEMOD_LIMIT=1000`; for the medium budget set the iteration limit to `100000000`. All caps are cumulative per input. A cap of `0` disables that counter's cap. Set all four to `0` for genuine unlimited instrumentation. A budget event records actual Fano main-loop iterations and separate search/demodulation counts. These binaries and the diagnostic patches are for the frozen Fano path (`-H`, default sequential decoder, OSD disabled), not an assertion that every alternative decoder path has equivalent budget accounting.

The separately obtained source is GPL v3 or later as stated in `wsprd.c`. Attribution and licensing are in [LICENSE_INFO.md](LICENSE_INFO.md).
