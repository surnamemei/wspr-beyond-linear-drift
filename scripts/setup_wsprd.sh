#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cache="$root/.cache"
runtime="$cache/runtime"
package="$cache/wsjtx-3.0.2-linux-x86_64.deb"
url='https://github.com/WSJTX/wsjtx/releases/download/v3.0.2/wsjtx-3.0.2-linux-x86_64.deb'
package_sha='a0a00ebb74f2159b45930be1b2694b22f1a83a802622cd1d2edacb7c11e80e15'
binary_sha='9e3c2fc14f63c4b4c4e9fcc33b386cd22daf8fe76ce724c5e37f07875e9a3dd9'

if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
    echo 'This setup requires x86_64 Linux (Ubuntu WSL is supported).' >&2
    exit 1
fi
for tool in curl dpkg-deb sha256sum apt ldd; do
    command -v "$tool" >/dev/null || { echo "Missing required command: $tool" >&2; exit 1; }
done

mkdir -p "$cache" "$runtime"
if [[ ! -f "$package" ]] || ! printf '%s  %s\n' "$package_sha" "$package" | sha256sum -c --status; then
    curl -fL --retry 3 --output "$package" "$url"
fi
printf '%s  %s\n' "$package_sha" "$package" | sha256sum -c
dpkg-deb -x "$package" "$runtime"
printf '%s  %s\n' "$binary_sha" "$runtime/usr/bin/wsprd" | sha256sum -c

library_path="$runtime/usr/lib/x86_64-linux-gnu"
if ldd "$runtime/usr/bin/wsprd" | grep -q 'not found'; then
    if [[ ! -e "$library_path/libfftw3f.so.3" ]]; then
        (cd "$cache" && apt download libfftw3-single3)
        fftw_package=$(find "$cache" -maxdepth 1 -name 'libfftw3-single3_*_amd64.deb' -print -quit)
        [[ -n "$fftw_package" ]] || { echo 'FFTW package download failed.' >&2; exit 1; }
        dpkg-deb -x "$fftw_package" "$runtime"
    fi
fi

if LD_LIBRARY_PATH="$library_path${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ldd "$runtime/usr/bin/wsprd" | grep -q 'not found'; then
    echo 'Unresolved wsprd shared libraries.' >&2
    exit 1
fi

echo "Installed official WSJT-X $(dpkg-deb -f "$package" Version) wsprd: $runtime/usr/bin/wsprd"
echo 'Run: bash scripts/wsprd.sh -h (upstream help returns exit status 1)'
