#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
out="$root/results/reference"
name='260924_0000.c2'
message='K1ABC FN42 33'
sim="$root/.cache/wsjtx-3.0.2/lib/wsprd/wsprsim"

mkdir -p "$out" "$root/tests/data"
bash "$root/scripts/setup_wsprd.sh" > "$out/setup-wsprd.log" 2>&1
bash "$root/scripts/setup_wsprsim.sh" > "$out/setup-wsprsim.log" 2>&1

printf '%s\n' "$message" > "$out/message.txt"
cd "$out"
rm -f -- "$name" ALL_WSPR.TXT hashtable.txt wspr_spots.txt wspr_timer.out wspr_wisdom.dat

# The unmodified upstream simulator returns 1 after successfully writing a C2 file.
set +e
"$sim" -cd -s 50 -o "$name" "$message" > simulator.stdout.txt 2> simulator.stderr.txt
sim_status=$?
set -e
printf '%s\n' "$sim_status" > simulator.exit_status.txt
if [[ $sim_status -ne 1 || ! -s "$name" ]]; then
    echo 'Official simulator did not produce the expected C2 file.' >&2
    exit 1
fi

set +e
bash "$root/scripts/wsprd.sh" -a "$out" "$name" > decoder.stdout.txt 2> decoder.stderr.txt
decoder_status=$?
set -e
printf '%s\n' "$decoder_status" > decoder.exit_status.txt

python3 "$root/scripts/check_official_reference.py" "$root" "$name"
