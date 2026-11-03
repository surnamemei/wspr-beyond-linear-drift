#!/usr/bin/env python3
"""Write one deterministic clean Type-1 WSPR C2 input for a smoke test."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wspr.encoder import encode_type1
from wspr.waveform import generate_complex_baseband, write_c2

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path, help="new output path ending in 261103_0000.c2")
args = parser.parse_args()
if args.output.name != "261103_0000.c2":
    parser.error("output filename must be 261103_0000.c2")
if args.output.exists():
    parser.error("refusing to overwrite an existing input")
waveform = generate_complex_baseband(encode_type1("K1ABC FN42 33").channel_symbols)
write_c2(args.output, waveform)
print(args.output)
