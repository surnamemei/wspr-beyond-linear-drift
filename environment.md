# Phase 0A environment and decoder provenance

## Host checked on 2026-09-24

- Development host: Windows workspace with Ubuntu 24.04 WSL2, x86_64. Reproduction does not depend on the original checkout path.
- Workspace was initially empty; a local Git repository was initialized during Phase 0A.
- Ubuntu's `wsjtx` candidate was `2.7.0~rc3+repack-1build2`, so the official WSJT-X release package was selected instead.

## Production decoder

- [Official WSJT-X release v3.0.2](https://github.com/WSJTX/wsjtx/releases/tag/v3.0.2); Debian package version `3.0.2`.
- Package: `wsjtx-3.0.2-linux-x86_64.deb`; SHA-256 `a0a00ebb74f2159b45930be1b2694b22f1a83a802622cd1d2edacb7c11e80e15`.
- Unmodified executable: `usr/bin/wsprd` from that package; SHA-256 `9e3c2fc14f63c4b4c4e9fcc33b386cd22daf8fe76ce724c5e37f07875e9a3dd9`.
- Missing base-image runtime: Ubuntu `libfftw3-single3` version `3.3.10-1ubuntu3`, extracted locally without root.
- Matching [official source archive](https://github.com/WSJTX/wsjtx/releases/download/v3.0.2/wsjtx-3.0.2-src.tar.gz); SHA-256 `574aee4a36c58c4dfeda4f2d659e74542212d4d9c25bfc040feba47c9f2b15d7`.

The binary and source are from the same release. No older standalone decoder was used for these findings. Decoder internals were not patched.

## Repeatable setup and invocation

Run in Ubuntu WSL or another compatible x86_64 Debian/Ubuntu environment:

```bash
bash scripts/setup_wsprd.sh
bash scripts/wsprd.sh -h
```

The setup script downloads the pinned package, checks its SHA-256, extracts it under `.cache/runtime/`, obtains FFTW with `apt download`, and verifies shared libraries. The launcher sets the local library path and passes arguments to the original executable. Record the full decoder command in later experiments.

Observed help check on 2026-09-24:

```text
$ bash scripts/wsprd.sh -h
wsprd: invalid option -- 'h'
Usage: wsprd [options...] infile
       infile must have suffix .wav or .c2
```

Exit status 1 is expected: upstream `wsprd` has no `--help`, `-h`, or version switch. Its version is established by the release package and hashes above.

## Relevant options and input

- Default operation decodes WSPR-2 WAV; `-m` selects WSPR-15.
- `-a <path>` selects a writable directory for data files. Later experiments should isolate trial or worker directories to avoid collisions.
- `-f <MHz>` sets dial frequency for reported absolute frequency; `-e <Hz>` adjusts dial-frequency error.
- `-w` expands the searched audio range from default ±110 Hz to ±150 Hz around 1500 Hz.
- `-s` requests single-pass mode; `-d`, `-q`, `-B`, `-J`, and `-o` alter decoding search or method.

The WSPR-2 WAV reader assumes **12,000 Hz, mono, signed 16-bit PCM**, a conventional 44-byte header, and up to 114 seconds of samples. `readwavfile` skips 44 bytes, reads 16-bit samples, assumes 12,000 samples/s, and selects a band centered on 1500 Hz. It does not validate header fields, so the later generator must. Use `YYMMDD_HHMM.wav`; the decoder extracts date/time from the suffix. Source: `lib/wsprd/wsprd.c`, `readwavfile` and WAV path in `main`.
