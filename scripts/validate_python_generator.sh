#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
output="$root/results/python-reference"
filename='260924_0001.c2'
mkdir -p "$output"

bash "$root/scripts/setup_wsprd.sh" > "$output/setup-wsprd.log" 2>&1

set +e
PYTHONPATH="$root/src" python3 -m unittest discover -s "$root/tests" -v \
    > "$output/tests.stdout.txt" 2> "$output/tests.stderr.txt"
test_status=$?
set -e
printf '%s\n' "$test_status" > "$output/tests.exit_status.txt"
if [[ $test_status -ne 0 ]]; then
    cat "$output/tests.stdout.txt"
    cat "$output/tests.stderr.txt" >&2
    echo 'PHASE 1B = FAIL: Python tests failed.' >&2
    exit 1
fi

PYTHONPATH="$root/src" python3 "$root/scripts/generate_python_reference.py" "$root" \
    > "$output/generator.stdout.txt" 2> "$output/generator.stderr.txt"

cd "$output"
set +e
bash "$root/scripts/wsprd.sh" -H -a "$output" "$filename" \
    > decoder.stdout.txt 2> decoder.stderr.txt
decoder_status=$?
set -e
printf '%s\n' "$decoder_status" > decoder.exit_status.txt

python3 "$root/scripts/check_python_reference.py" "$root"
