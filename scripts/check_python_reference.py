"""Require an exact production-decoder match for the Python reference."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys


MESSAGE = "K1ABC FN42 33"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    output = root / "results/python-reference"
    decoder_stdout = (output / "decoder.stdout.txt").read_text()
    decoder_stderr = (output / "decoder.stderr.txt").read_text()
    decoder_status = int((output / "decoder.exit_status.txt").read_text().strip())
    generator = json.loads((output / "generator_metadata.json").read_text())

    if decoder_status != 0:
        raise ValueError(f"wsprd exit status was {decoder_status}")
    if generator["matching_official_symbols"] != 162 or generator["symbol_count"] != 162:
        raise ValueError("Python symbols do not match all 162 official symbols")
    if "<DecodeFinished>" not in decoder_stdout:
        raise ValueError("wsprd did not report DecodeFinished")

    decoded_rows = []
    for line in decoder_stdout.splitlines():
        fields = line.split()
        if len(fields) == 8 and re.fullmatch(r"[0-9]{4}", fields[0]):
            decoded_rows.append(fields)
    expected = MESSAGE.split()
    matches = [fields for fields in decoded_rows if fields[5:8] == expected]
    if len(matches) != 1:
        raise ValueError(f"Expected one exact decode of {MESSAGE!r}; found {len(matches)}")
    fields = matches[0]

    c2 = output / "260924_0001.c2"
    metadata = {
        "phase": "1B",
        "status": "PASS",
        "transmitted_message": MESSAGE,
        "decoded_message": " ".join(fields[5:8]),
        "matching_official_symbols": generator["matching_official_symbols"],
        "test_command": "PYTHONPATH=src python3 -m unittest discover -s tests -v",
        "generator_command": "PYTHONPATH=src python3 scripts/generate_python_reference.py <repository-root>",
        "decoder_command": [
            "bash",
            str(root / "scripts/wsprd.sh"),
            "-H",
            "-a",
            str(output),
            "260924_0001.c2",
        ],
        "decoder_exit_status": decoder_status,
        "decoder_snr_db": float(fields[1]),
        "decoder_dt_s": float(fields[2]),
        "decoder_frequency_mhz": float(fields[3]),
        "decoder_drift_hz": int(fields[4]),
        "decoder_stdout": decoder_stdout,
        "decoder_stderr": decoder_stderr,
        "python_c2_sha256": sha256(c2),
        "python_c2_bytes": c2.stat().st_size,
    }
    (output / "validation_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"PHASE 1B = PASS: {metadata['decoded_message']}")
    print(f"Official channel-symbol match: {metadata['matching_official_symbols']}/162")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, IndexError) as error:
        print(f"PHASE 1B = FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
