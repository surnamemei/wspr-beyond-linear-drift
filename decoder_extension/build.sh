#!/usr/bin/env bash
# Build an isolated original/B2/B3 wsprd from the pinned official release archive.
set -euo pipefail
if [[ $# != 3 ]]; then
  printf 'Usage: %s WSJTX_3.0.2_SRC_TAR_GZ {original|b2|b3|a0-budget|b2-budget|b3-budget} OUTPUT_DIR\n' "$0" >&2
  exit 2
fi
archive=$(realpath "$1")
variant=$2
output=$3
case "$variant" in original|b2|b3|a0-budget|b2-budget|b3-budget) ;; *) echo 'Unknown variant' >&2; exit 2 ;; esac
expected=574aee4a36c58c4dfeda4f2d659e74542212d4d9c25bfc040feba47c9f2b15d7
actual=$(sha256sum "$archive" | awk '{print $1}')
[[ "$actual" == "$expected" ]] || { echo 'WSJT-X archive SHA-256 mismatch' >&2; exit 1; }
command -v gcc >/dev/null
command -v "${FC:-gfortran}" >/dev/null
command -v make >/dev/null
command -v patch >/dev/null
mkdir -p "$output"
output=$(realpath "$output")
target="$output/wsprd-$variant"
[[ ! -e "$target" ]] || { echo "Refusing to overwrite $target" >&2; exit 1; }
work=$(mktemp -d "${TMPDIR:-/tmp}/wsprd-build.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
tar -xzf "$archive" -C "$work"
source_dir="$work/wsjtx-3.0.2"
[[ -f "$source_dir/lib/wsprd/wsprd.c" ]]
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
case "$variant" in
  b2) patch -d "$source_dir" -p1 < "$script_dir/patches/wsprd_b2_fixed_grid.patch" ;;
  b3) patch -d "$source_dir" -p1 < "$script_dir/patches/wsprd_b3_fallback.patch" ;;
  a0-budget|b2-budget|b3-budget)
    arm=${variant%-budget}
    patch -d "$source_dir" -p1 < "$script_dir/patches/wsprd_${arm}_budget.patch"
    patch -d "$source_dir" -p1 < "$script_dir/patches/fano_budget.patch"
    ;;
esac
make -C "$source_dir/lib/wsprd" wsprd \
  "CC=${CC:-gcc}" "FC=${FC:-gfortran}" \
  'CFLAGS=-O3 -DNDEBUG -fdata-sections -ffunction-sections -I.' \
  'FFLAGS=-O2' "LDFLAGS=${WSPR_LDFLAGS:--Wl,--gc-sections}" \
  "LIBS=${WSPR_LIBS:--lfftw3f -lm -lgfortran}"
install -m 0755 "$source_dir/lib/wsprd/wsprd" "$target"
printf 'Built %s\n' "$target"
sha256sum "$target"
