"""Check an official wsprsim → wsprd reference and preserve its provenance."""

import hashlib
import json
import re
import struct
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    root = Path(sys.argv[1])
    name = sys.argv[2]
    out = root / "results" / "reference"
    message = (out / "message.txt").read_text().strip()
    sim_stdout = (out / "simulator.stdout.txt").read_text()
    decoder_stdout = (out / "decoder.stdout.txt").read_text()
    sim_status = int((out / "simulator.exit_status.txt").read_text().strip())
    decoder_status = int((out / "decoder.exit_status.txt").read_text().strip())
    c2 = out / name

    if sim_status != 1 or decoder_status != 0:
        raise ValueError(f"Unexpected exit codes: wsprsim={sim_status}, wsprd={decoder_status}")
    if f"Writing {name}" not in sim_stdout:
        raise ValueError("Simulator did not report writing the expected file")
    if "<DecodeFinished>" not in decoder_stdout:
        raise ValueError("Decoder did not finish normally")

    sim_lines = sim_stdout.splitlines()
    packed_line = next((line for line in sim_lines if line.startswith("Data is :")), None)
    try:
        symbol_line = sim_lines[sim_lines.index("Channel symbols:") + 1]
    except (ValueError, IndexError):
        symbol_line = None
    if packed_line is None or symbol_line is None:
        raise ValueError("Official simulator did not print its packed data and channel symbols")
    packed = packed_line.removeprefix("Data is :").split()
    symbols = [int(value) for value in symbol_line.split()]
    if len(packed) != 11 or len(symbols) != 162:
        raise ValueError(f"Unexpected encoder lengths: {len(packed)} bytes, {len(symbols)} symbols")

    decoded = []
    for line in decoder_stdout.splitlines():
        fields = line.split()
        if len(fields) == 8 and re.fullmatch(r"\d{4}", fields[0]):
            decoded.append(fields)
    expected = message.split()
    matches = [fields for fields in decoded if fields[5:8] == expected]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one full-message decode of {message!r}; found {len(matches)}")
    fields = matches[0]

    raw = c2.read_bytes()
    if len(raw) != 26 + 2 * 45000 * 4:
        raise ValueError(f"Unexpected C2 size: {len(raw)} bytes")
    header_name = raw[:14].decode("ascii")
    mode = struct.unpack_from("<i", raw, 14)[0]
    dial_mhz = struct.unpack_from("<d", raw, 18)[0]
    if header_name != name or mode != 2 or abs(dial_mhz - 10.1387) > 1e-9:
        raise ValueError("Unexpected C2 header")

    source_archive = root / ".cache" / "wsjtx-3.0.2-src.tar.gz"
    sim_binary = root / ".cache" / "wsjtx-3.0.2" / "lib" / "wsprd" / "wsprsim"
    decoder_binary = root / ".cache" / "runtime" / "usr" / "bin" / "wsprd"
    vector = {
        "source": "official WSJT-X 3.0.2 lib/wsprd/wsprsim.c and wsprsim_utils.c",
        "source_archive_sha256": sha256(source_archive),
        "message": message,
        "packed_data_11_bytes_hex": packed,
        "channel_symbols": symbols,
    }
    (root / "tests" / "data" / "reference_symbols.json").write_text(
        json.dumps(vector, indent=2) + "\n"
    )
    metadata = {
        "release": "WSJT-X 3.0.2",
        "message": message,
        "simulator_command": [str(sim_binary), "-cd", "-s", "50", "-o", name, message],
        "simulator_exit_status": sim_status,
        "decoder_command": ["bash", str(root / "scripts" / "wsprd.sh"), "-a", str(out), name],
        "decoder_exit_status": decoder_status,
        "decoded_message": " ".join(fields[5:8]),
        "decoded_snr_db": float(fields[1]),
        "decoded_dt_s": float(fields[2]),
        "decoded_frequency_mhz": float(fields[3]),
        "decoded_drift_hz": int(fields[4]),
        "source_archive_sha256": sha256(source_archive),
        "simulator_binary_sha256": sha256(sim_binary),
        "decoder_binary_sha256": sha256(decoder_binary),
        "c2_sha256": sha256(c2),
        "c2_bytes": len(raw),
        "c2_mode": mode,
        "c2_dial_frequency_mhz": dial_mhz,
    }
    (out / "command_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"CLEAN REFERENCE DECODE = PASS: {metadata['decoded_message']}")
    print(f"SNR={fields[1]} dB; frequency={fields[3]} MHz; drift={fields[4]} Hz")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, IndexError) as error:
        print(f"CLEAN REFERENCE DECODE = FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
