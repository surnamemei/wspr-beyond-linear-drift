#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cache="$root/.cache"
archive="$cache/wsjtx-3.0.2-src.tar.gz"
source_dir="$cache/wsjtx-3.0.2/lib/wsprd"
url='https://github.com/WSJTX/wsjtx/releases/download/v3.0.2/wsjtx-3.0.2-src.tar.gz'
archive_sha='574aee4a36c58c4dfeda4f2d659e74542212d4d9c25bfc040feba47c9f2b15d7'

if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
    echo 'This setup requires x86_64 Linux (Ubuntu WSL is supported).' >&2
    exit 1
fi
for tool in curl tar sha256sum make gcc; do
    command -v "$tool" >/dev/null || { echo "Missing required command: $tool" >&2; exit 1; }
done

mkdir -p "$cache"
if [[ ! -f "$archive" ]] || ! printf '%s  %s\n' "$archive_sha" "$archive" | sha256sum -c --status; then
    curl -fL --retry 3 --output "$archive" "$url"
fi
printf '%s  %s\n' "$archive_sha" "$archive" | sha256sum -c
# Re-extract the verified archive so each build uses the original source.
tar -xzf "$archive" -C "$cache" wsjtx-3.0.2/lib/wsprd

# wsprsim uses libm, but not the FFTW or Fortran libraries in the shared Makefile LIBS.
# Override only the link libraries; compile the official, unmodified sources.
make -B -C "$source_dir" wsprsim LIBS=-lm
echo "Official WSJT-X 3.0.2 wsprsim: $source_dir/wsprsim"
sha256sum "$source_dir/wsprsim"
