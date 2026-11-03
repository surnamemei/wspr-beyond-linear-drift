#!/usr/bin/env python3
"""Classify a wsprd stdout file with the validated Parser V2."""
import argparse
import json
from pathlib import Path
from parser_v2 import parse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("stdout", type=Path)
parser.add_argument("--expected", required=True, help="exact sent message, e.g. K1ABC FN42 33")
parser.add_argument("--stderr", type=Path)
parser.add_argument("--exit-status", type=int, default=0)
args = parser.parse_args()
result = parse(args.stdout.read_text(), args.exit_status, args.expected,
               args.stderr.read_text() if args.stderr else "")
print(json.dumps(result, indent=2))
raise SystemExit(0 if result["parse_status"] == "ok" else 1)
